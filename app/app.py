import json
import logging
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
