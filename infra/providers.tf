provider "aws" {
  # LocalStack accepts static placeholder credentials. Real AWS credentials are
  # intentionally not required for this demonstration stack or CI workflow.
  region     = var.aws_region
  access_key = "test"
  secret_key = "test"

  # LocalStack does not need real AWS credential checks.
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Path-style addressing keeps all S3 traffic on the LocalStack edge endpoint
  # instead of trying bucket-name hostnames such as bucket.localhost.
  s3_use_path_style = true

  # Route every AWS service used by the platform to LocalStack.
  endpoints {
    apigateway = var.localstack_endpoint
    dynamodb   = var.localstack_endpoint
    iam        = var.localstack_endpoint
    lambda     = var.localstack_endpoint
    logs       = var.localstack_endpoint
    s3         = var.localstack_endpoint
    sqs        = var.localstack_endpoint
    sts        = var.localstack_endpoint
  }

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
