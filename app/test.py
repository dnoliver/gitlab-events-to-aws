import urllib.request
import json
import unittest

class TestLambdaHandler(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.lambda_url = "http://localhost:9000/2015-03-31/functions/function/invocations"
        self.api_gateway_event = {
            "resource": "/",
            "path": "/",
            "httpMethod": "GET",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Host": "1234567890.execute-api.us-east-1.amazonaws.com",
                "User-Agent": "Test User Agent"
            },
            "multiValueHeaders": {},
            "queryStringParameters": {
                "test": "value"
            },
            "multiValueQueryStringParameters": {
                "test": ["value"]
            },
            "pathParameters": None,
            "stageVariables": None,
            "requestContext": {
                "resourceId": "123456",
                "resourcePath": "/",
                "httpMethod": "GET",
                "requestTime": "09/Apr/2015:12:34:56 +0000",
                "path": "/Prod/",
                "accountId": "123456789012",
                "protocol": "HTTP/1.1",
                "stage": "Prod",
                "requestId": "test-request-id",
                "identity": {
                    "sourceIp": "127.0.0.1",
                    "userAgent": "Test User Agent"
                },
                "domainName": "1234567890.execute-api.us-east-1.amazonaws.com",
                "apiId": "1234567890"
            },
            "body": None,
            "isBase64Encoded": False
        }
    
    def test_handler_get_request(self):
        """Test GET request to Lambda handler."""
        data = json.dumps(self.api_gateway_event).encode('utf-8')
        req = urllib.request.Request(
            self.lambda_url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req) as response:
            # Check status code
            self.assertEqual(response.getcode(), 200)

            # Parse the Lambda response
            response_data = response.read().decode('utf-8')
            lambda_response = json.loads(response_data)

            # Assert Lambda response structure
            self.assertIn('statusCode', lambda_response)
            self.assertIn('body', lambda_response)

            # Assert successful response
            self.assertEqual(lambda_response['statusCode'], 200)

if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)