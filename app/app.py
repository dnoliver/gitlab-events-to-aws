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
    http_method = event['httpMethod']
    
    # Prepare the response based on the HTTP method
    message_map = {
        'GET': 'This would GET (read) an item from the database',
        'POST': 'This would POST (create) a new item in the database',
        'PUT': 'This would PUT (update) an existing item in the database',
        'DELETE': 'This would DELETE an item from the database'
    }
    
    message = message_map.get(http_method, 'Unsupported HTTP method')

    # Return the response
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'message': message,
            'method': http_method,
            'timestamp': datetime.now().isoformat()
        })
    }
