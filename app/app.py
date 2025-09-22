import base64
import os
import json
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime

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

    secrets_manager = boto3.client('secretsmanager')
    secret_arn = os.environ.get('SECRETS_ARN')

    try:
        response = secrets_manager.get_secret_value(SecretId=secret_arn)
        if 'SecretString' in response:
            secret_value = json.loads(response['SecretString'])
        else:
            # Decode binary secret
            secret_value = base64.b64decode(response['SecretBinary']).decode('ascii')
        
        logger.info(f"Retrieved secret: {secret_value}")
    except ClientError as e:
        logger.error(f"Error retrieving secret: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing secret JSON: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    # Return success response for POST
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "Event received successfully",
                "method": http_method,
                "timestamp": datetime.now().isoformat(),
            }
        ),
    }
