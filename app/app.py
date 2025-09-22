import base64
import os
import json
import logging
import boto3
import mdformat
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

    # Get the HTTP method from the event
    http_method = event["httpMethod"]

    # Only allow POST requests
    if http_method != "POST":
        logger.warning(f"Method {http_method} not allowed. Only POST is supported.")
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json", "Allow": "POST"},
            "body": json.dumps(
                {
                    "error": "Method Not Allowed",
                    "message": f"HTTP method {http_method} is not supported. Only POST requests are allowed.",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
        }

    # Handle POST request
    logger.info("Processing POST request")

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

    # Create the Anthropic chat interface
    llm = ChatAnthropic(
        api_key=secret_value["anthropic_api_key"],
        model="claude-3-7-sonnet-20250219"
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

    # A sample diff from a Merge Request
    sample_diff = (
        "diff --git a/src/main.py b/src/main.py\n"
        "index 1234567..abcdefg 100644\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,10 +1,15 @@\n"
        " import os\n"
        " import sys\n"
        "+import logging\n"
        " \n"
        " def main():\n"
        '-    print("Hello World")\n'
        "+    logger = logging.getLogger(__name__)\n"
        "+    logger.setLevel(logging.INFO)\n"
        "+    \n"
        '+    print("Hello World - Updated")\n'
        "     return 0\n"
        " \n"
        "+def new_function():\n"
        '+    return "This is a new function"\n'
        "+\n"
        ' if __name__ == "__main__":\n'
        "     main()\n"
    )

    # Invoque the chain
    response = chain.invoke(
        {
            "input": sample_diff,
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

    # Return success response for POST
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "Event received successfully",
                "method": http_method,
                "data": formatted_content,
                "timestamp": datetime.now().isoformat(),
            }
        ),
    }
