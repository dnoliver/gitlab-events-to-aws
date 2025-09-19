provider "aws" {
  region  = "us-west-2"
  profile = "dnoliver"
}

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

# Get current AWS region
data "aws_region" "current" {}

# Create an ECR repository for app
resource "aws_ecr_repository" "lambda_ecr_repo" {
  name                 = "lambda-docker-repo"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  force_delete = true
}

# Lifecyle policy for ECR repository
resource "aws_ecr_lifecycle_policy" "lifecycle_policy" {
  repository = aws_ecr_repository.lambda_ecr_repo.name

  policy     = <<EOF
{
    "rules": [
        {
          "rulePriority": 1,
          "description": "Expire tagged images and maintain last 2 latest images",
          "selection": {
              "tagStatus": "any",
              "countType": "imageCountMoreThan",
              "countNumber": 2
          },
          "action": {
              "type": "expire"
          }
      }
    ]
}
EOF
  depends_on = [aws_ecr_repository.lambda_ecr_repo]
}

# Policy for ECR repository allowing cross-account pulls
resource "aws_ecr_repository_policy" "policy" {

  repository = aws_ecr_repository.lambda_ecr_repo.name

  policy     = <<EOF
{
  "Version": "2008-10-17",
  "Statement": [
    {
      "Sid": "AllowCrossAccountPull",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "*"
        ]
      },
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ]
    }
    
  ]
}
EOF
  depends_on = [aws_ecr_repository.lambda_ecr_repo]

}

# Build and push Docker image using null_resource
resource "null_resource" "build_push_docker_images" {
  provisioner "local-exec" {
    command = <<EOT
      # Log in to ECR
      aws ecr get-login-password --region ${data.aws_region.current.name} \
      | docker login --username AWS --password-stdin ${aws_ecr_repository.lambda_ecr_repo.repository_url}
      # Build Docker image
      docker buildx build --platform linux/amd64 --provenance=false --tag lambda-docker-demo ./app/.
      # Tag Docker image
      docker tag lambda-docker-demo:latest ${aws_ecr_repository.lambda_ecr_repo.repository_url}:latest
      # Push Docker image to ECR
      docker push ${aws_ecr_repository.lambda_ecr_repo.repository_url}:latest
    EOT
  }

  triggers = {
    ecr_url = aws_ecr_repository.lambda_ecr_repo.repository_url
  }
}


# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "crud_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Introduce a delay (e.g., 60 seconds)
resource "time_sleep" "wait_for_deployment" {
  depends_on      = [null_resource.build_push_docker_images] # Wait after IAM role creation
  create_duration = "60s"                                    # Set delay duration
}

# Create the Lambda function using Docker image
resource "aws_lambda_function" "crud_lambda" {
  function_name = "crud_operations"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_ecr_repo.repository_url}:latest"

  # Set Lambda timeout and memory size
  memory_size = 128
  timeout     = 30

  ephemeral_storage {
    size = 1024
  }

  # Environment variables (optional)
  environment {
    variables = {
      LOG_LEVEL = "INFO"
      PORT      = 3000
    }
  }

  depends_on = [time_sleep.wait_for_deployment]
}

# API Gateway
resource "aws_api_gateway_rest_api" "crud_api" {
  name        = "crud-api"
  description = "CRUD API Gateway"
}

# API Gateway resource
resource "aws_api_gateway_resource" "items" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  parent_id   = aws_api_gateway_rest_api.crud_api.root_resource_id
  path_part   = "items"
}

# GET method
resource "aws_api_gateway_method" "get" {
  rest_api_id   = aws_api_gateway_rest_api.crud_api.id
  resource_id   = aws_api_gateway_resource.items.id
  http_method   = "GET"
  authorization = "NONE"
}

# POST method
resource "aws_api_gateway_method" "post" {
  rest_api_id   = aws_api_gateway_rest_api.crud_api.id
  resource_id   = aws_api_gateway_resource.items.id
  http_method   = "POST"
  authorization = "NONE"
}

# PUT method
resource "aws_api_gateway_method" "put" {
  rest_api_id   = aws_api_gateway_rest_api.crud_api.id
  resource_id   = aws_api_gateway_resource.items.id
  http_method   = "PUT"
  authorization = "NONE"
}

# DELETE method
resource "aws_api_gateway_method" "delete" {
  rest_api_id   = aws_api_gateway_rest_api.crud_api.id
  resource_id   = aws_api_gateway_resource.items.id
  http_method   = "DELETE"
  authorization = "NONE"
}

# Lambda integration for GET
resource "aws_api_gateway_integration" "lambda_get" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  resource_id = aws_api_gateway_resource.items.id
  http_method = aws_api_gateway_method.get.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_lambda.invoke_arn
}

# Lambda integration for POST
resource "aws_api_gateway_integration" "lambda_post" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  resource_id = aws_api_gateway_resource.items.id
  http_method = aws_api_gateway_method.post.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_lambda.invoke_arn
}

# Lambda integration for PUT
resource "aws_api_gateway_integration" "lambda_put" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  resource_id = aws_api_gateway_resource.items.id
  http_method = aws_api_gateway_method.put.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_lambda.invoke_arn
}

# Lambda integration for DELETE
resource "aws_api_gateway_integration" "lambda_delete" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  resource_id = aws_api_gateway_resource.items.id
  http_method = aws_api_gateway_method.delete.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_lambda.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.crud_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.crud_api.execution_arn}/*/*"
}

# API Gateway deployment
resource "aws_api_gateway_deployment" "crud_deployment" {
  depends_on = [
    aws_api_gateway_integration.lambda_get,
    aws_api_gateway_integration.lambda_post,
    aws_api_gateway_integration.lambda_put,
    aws_api_gateway_integration.lambda_delete
  ]

  rest_api_id = aws_api_gateway_rest_api.crud_api.id
}

# API Gateway stage
resource "aws_api_gateway_stage" "crud_stage" {
  deployment_id = aws_api_gateway_deployment.crud_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.crud_api.id
  stage_name    = "prod"
}

# Output the API Gateway URL
output "api_url" {
  value = "${aws_api_gateway_stage.crud_stage.invoke_url}/items"
}