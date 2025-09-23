import base64
import os
import json
import logging
import boto3
import mdformat
import gitlab
from botocore.exceptions import ClientError
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel
from langchain_anthropic import ChatAnthropic

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    # Log the start of the Lambda function
    logger.info("Lambda function started")

    # Log the event
    logger.info(f"Received event: \n{json.dumps(event, indent=2)}")

    # Handle POST request
    logger.info("Processing POST request")

    # Circuit breaker for unsupported events
    # The event should have the following fields and values:
    #
    #   "event_type": "merge_request",
    #   "state": "opened",
    #
    event_type = event.get("event_type")
    object_kind = event.get("object_kind")

    # Check if this is a merge request event
    if event_type != "merge_request" or object_kind != "merge_request":
        logger.info(f"Unsupported event_type: {event_type}, object_kind: {object_kind}")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "message": "Event ignored - not a merge request event",
                    "event_type": event_type,
                    "object_kind": object_kind,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }

    # Check if the merge request is opened
    object_attributes = event.get("object_attributes", {})
    state = object_attributes.get("state")

    if state != "opened":
        logger.info(f"Merge request state is '{state}', not 'opened'")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "message": "Event ignored - merge request not in opened state",
                    "state": state,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }

    # Get the project id and the merge request internal id
    #
    #       "target_project_id": <int>,
    #       "object_attributes: {
    #           "iid": <int>
    #       }
    object_attributes = event.get("object_attributes", {})
    project_id = object_attributes.get("target_project_id")
    merge_request_iid = object_attributes.get("iid")

    # Retrieve the secrets from AWS Secrets Manager
    secrets_manager = boto3.client("secretsmanager")
    secret_arn = os.environ.get("SECRETS_ARN")

    try:
        response = secrets_manager.get_secret_value(SecretId=secret_arn)
        if "SecretString" in response:
            secret_value = json.loads(response["SecretString"])
        else:
            # Decode binary secret
            secret_value = base64.b64decode(response["SecretBinary"]).decode("ascii")

        logger.info(f"Retrieved secret")
    except ClientError as e:
        logger.error(f"Error retrieving secret: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "error": "Internal Server Error",
                    "message": "Failed to retrieve secret",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing secret JSON: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "error": "Internal Server Error",
                    "message": "Failed to parse secret",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }

    # Create a Gitlab API interface
    gl = gitlab.Gitlab(
        url="https://gitlab.com",
        private_token=secret_value["gitlab_private_token"],
    )

    # Log the merge request state
    logger.info(
        f"Processing merge request '{merge_request_iid}' for project '{project_id}' in state '{state}'"
    )

    # Retrieve the diff from the Merge Request
    try:
        merge_request_diff = gl.http_get(
            f"/projects/{project_id}/merge_requests/{merge_request_iid}/raw_diffs",
            params={"unidiff": True},
        )

        merge_request_diff = merge_request_diff.text
    except Exception as e:
        logger.error(f"Failed to retrieve merge request diff: {e}")
        return {
            "statusCode": 502,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "error": "Failed to contact GitLab API",
                    "message": "Failed to retrieve merge request diff",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }

    # Log Merge Request Diff
    logger.info(
        f"Merge request diff retrieved for Project {project_id} Merge Request {merge_request_iid}"
    )
    logger.info(merge_request_diff)

    # Create the Anthropic chat interface
    llm = ChatAnthropic(
        api_key=secret_value["anthropic_api_key"], model="claude-3-7-sonnet-20250219"
    )

    # Create the summary prompt template
    summary_prompt = ChatPromptTemplate(
        [
            (
                "system",
                (
                    "You are a code reviewer. Your task is to review diffs from a GitLab Merge Request.\n"
                    "Provide a high-level summary of the changes made in this merge request.\n"
                    "Focus on what was changed, added, or removed without detailed analysis.\n"
                    "If the code is fine, say so. Use a structured format in your response.\n"
                    "\n"
                    "Format your review like this:\n"
                    "\n"
                    "## Merge Request Overview\n"
                    "\n"
                    "A high-level summary of the changes and overall impression.\n"
                    "\n"
                    "### Reviewed Changes\n"
                    "\n"
                    "| File | Description |\n"
                    "| ---- | ----------- |"
                    "| path/to/file1 | Your comments on this specific file |\n"
                    "| path/to/file2 | Your comments on this specific file |\n"
                ),
            ),
            ("human", "{input}"),
        ]
    )

    # Create the chain instances
    summary_chain = summary_prompt | llm

    # Combine chains in a RunnableParallel
    chain = RunnableParallel(
        summary=summary_chain,
    )

    # Invoque the chain
    response = chain.invoke(
        {
            "input": merge_request_diff,
        }
    )

    # Construct the sections
    sections = [
        response["summary"].content,
    ]

    # Join the content
    output_content = "".join(sections)

    # Format the response using mdformat
    formatted_content = mdformat.text(
        output_content,
        options={
            "number": True,
            "wrap": 120,
        },
        extensions={"tables"},
    )

    # Log the formatted content
    logger.info("Formatted content:")
    logger.info(formatted_content)

    # Return success response for POST
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "Event received successfully",
                "method": "POST",
                "data": formatted_content,
                "timestamp": datetime.now().isoformat(),
            }
        ),
    }
