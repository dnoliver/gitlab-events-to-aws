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
      set -e
      # Log in to ECR
      aws ecr get-login-password --region ${data.aws_region.current.name} --profile dnoliver \
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
    # Monitor Python files and Dockerfile
    app_files_hash = md5(join("", [
      for f in fileset("${path.module}/app", "{*.py,Dockerfile,requirements.txt}") :
      filemd5("${path.module}/app/${f}")
    ]))

    # Monitor ECR URL for changes
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

resource "aws_secretsmanager_secret" "app_secrets" {
  name        = "my-application-secret"
  description = "Secret for my application"
}

resource "aws_secretsmanager_secret_version" "app_secret_version" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    "anthropic_api_key" = var.anthropic_api_key,
    "db_password"       = var.db_password
  })
}

# AIM role for secret access
resource "aws_iam_policy" "secret_access_policy" {
  name        = "lambda-secrets-manager-access"
  description = "Allows Lambda to read secrets from Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ],
        Resource = aws_secretsmanager_secret.app_secrets.arn
      }
    ]
  })
}

# IAM policy for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "secret_access_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.secret_access_policy.arn
}

# Introduce a delay (e.g., 60 seconds)
resource "time_sleep" "wait_for_deployment" {
  depends_on      = [null_resource.build_push_docker_images] # Wait after IAM role creation
  create_duration = "60s"                                    # Set delay duration
}

# Get the image digest from ECR
data "aws_ecr_image" "lambda_image" {
  repository_name = aws_ecr_repository.lambda_ecr_repo.name
  image_tag       = "latest"
  depends_on      = [null_resource.build_push_docker_images]
}

# Create the Lambda function using Docker image
resource "aws_lambda_function" "crud_lambda" {
  function_name = "crud_operations"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_ecr_repo.repository_url}@${data.aws_ecr_image.lambda_image.image_digest}"

  # Set Lambda timeout and memory size
  memory_size = 128
  timeout     = 30

  ephemeral_storage {
    size = 1024
  }

  # Environment variables (optional)
  environment {
    variables = {
      LOG_LEVEL   = "INFO"
      PORT        = 3000
      SECRETS_ARN = aws_secretsmanager_secret.app_secrets.arn
    }
  }

  depends_on = [time_sleep.wait_for_deployment]
}

# API Gateway
resource "aws_api_gateway_rest_api" "crud_api" {
  name        = "crud-api"
  description = "CRUD API Gateway"
}

# Create API Key
resource "aws_api_gateway_api_key" "api_key" {
  name        = "my-api-key"
  description = "API Key for CRUD operations"
  enabled     = true
}

# Create Usage Plan
resource "aws_api_gateway_usage_plan" "usage_plan" {
  name        = "my-usage-plan"
  description = "Usage plan for API key"

  api_stages {
    api_id = aws_api_gateway_rest_api.crud_api.id
    stage  = "prod"
  }

  quota_settings {
    limit  = 1000
    period = "DAY"
  }

  throttle_settings {
    rate_limit  = 100
    burst_limit = 200
  }
}

# Link API Key to Usage Plan
resource "aws_api_gateway_usage_plan_key" "usage_plan_key" {
  key_id        = aws_api_gateway_api_key.api_key.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.usage_plan.id
}

# API Gateway resource
resource "aws_api_gateway_resource" "events" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  parent_id   = aws_api_gateway_rest_api.crud_api.root_resource_id
  path_part   = "events"
}

# POST method
resource "aws_api_gateway_method" "post" {
  rest_api_id      = aws_api_gateway_rest_api.crud_api.id
  resource_id      = aws_api_gateway_resource.events.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

# Lambda integration for POST
resource "aws_api_gateway_integration" "lambda_post" {
  rest_api_id = aws_api_gateway_rest_api.crud_api.id
  resource_id = aws_api_gateway_resource.events.id
  http_method = aws_api_gateway_method.post.http_method

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
    aws_api_gateway_integration.lambda_post
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
  value = "${aws_api_gateway_stage.crud_stage.invoke_url}/events"
}

# Output the API Key
output "api_key_value" {
  value     = aws_api_gateway_api_key.api_key.value
  sensitive = true
}