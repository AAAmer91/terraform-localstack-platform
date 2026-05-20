locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Both Lambdas use the same trust policy; their permissions stay separate in
  # role policies below so each function only receives the access it needs.
  lambda_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

// Raw webhook payloads are archived here after asynchronous processing.
resource "aws_s3_bucket" "events" {
  # CI creates objects during the test flow, so force_destroy prevents cleanup
  # failures when terraform destroy runs at the end of the workflow.
  bucket        = "${local.name_prefix}-events"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "events" {
  bucket = aws_s3_bucket.events.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

// Server-side encryption mirrors the default posture used for real event
// archives, even though LocalStack stores everything locally.
resource "aws_s3_bucket_server_side_encryption_configuration" "events" {
  bucket = aws_s3_bucket.events.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

// DynamoDB stores metadata that is cheap to query without reading S3 payloads.
resource "aws_dynamodb_table" "events" {
  name         = "${local.name_prefix}-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }
}

// Failed processor messages land here after SQS exhausts the redrive policy.
resource "aws_sqs_queue" "events_dlq" {
  name = "${local.name_prefix}-events-dlq"
}

// The queue decouples fast HTTP ingestion from slower storage/indexing work.
resource "aws_sqs_queue" "events" {
  name                       = "${local.name_prefix}-events"
  visibility_timeout_seconds = 60

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = 3
  })
}

// Explicit log groups make retention deterministic instead of relying on the
// provider/Lambda service to create groups with indefinite retention.
resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.name_prefix}-ingest"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/aws/lambda/${local.name_prefix}-processor"
  retention_in_days = 14
}

// Each Lambda is packaged independently so code changes only redeploy the
// function that owns that behavior.
data "archive_file" "ingest_zip" {
  type        = "zip"
  source_file = "${path.module}/../app/ingest_handler.py"
  output_path = "${path.module}/ingest.zip"
}

data "archive_file" "processor_zip" {
  type        = "zip"
  source_file = "${path.module}/../app/processor_handler.py"
  output_path = "${path.module}/processor.zip"
}

// Ingest only needs permission to enqueue accepted webhook events and write
// logs. It never touches S3 or DynamoDB directly.
resource "aws_iam_role" "ingest_exec" {
  name               = "${local.name_prefix}-ingest-exec"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "ingest_exec" {
  name = "${local.name_prefix}-ingest-policy"
  role = aws_iam_role.ingest_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ingest.arn}:*"
      }
    ]
  })
}

// Processor owns the durable side effects: read from SQS, archive to S3, index
// in DynamoDB, and emit operational logs.
resource "aws_iam_role" "processor_exec" {
  name               = "${local.name_prefix}-processor-exec"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "processor_exec" {
  name = "${local.name_prefix}-processor-policy"
  role = aws_iam_role.processor_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.events.arn}/events/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.events.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.processor.arn}:*"
      }
    ]
  })
}

// API Gateway invokes this function synchronously; it returns as soon as the
// event is durably queued.
resource "aws_lambda_function" "ingest" {
  function_name = "${local.name_prefix}-ingest"
  role          = aws_iam_role.ingest_exec.arn
  handler       = "ingest_handler.handler"
  runtime       = "python3.11"
  filename      = data.archive_file.ingest_zip.output_path
  timeout       = 10

  source_code_hash = data.archive_file.ingest_zip.output_base64sha256

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.events.url
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ingest,
    aws_iam_role_policy.ingest_exec
  ]
}

// SQS invokes this function asynchronously; partial batch responses keep
// successfully processed messages from being retried with failed ones.
resource "aws_lambda_function" "processor" {
  function_name = "${local.name_prefix}-processor"
  role          = aws_iam_role.processor_exec.arn
  handler       = "processor_handler.handler"
  runtime       = "python3.11"
  filename      = data.archive_file.processor_zip.output_path
  timeout       = 10

  source_code_hash = data.archive_file.processor_zip.output_base64sha256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.events.bucket
      TABLE_NAME  = aws_dynamodb_table.events.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.processor,
    aws_iam_role_policy.processor_exec
  ]
}

// Connect the SQS queue to the processor Lambda. ReportBatchItemFailures lets
// the handler return per-message failures for proper retry and DLQ behavior.
resource "aws_lambda_event_source_mapping" "processor_from_queue" {
  event_source_arn        = aws_sqs_queue.events.arn
  function_name           = aws_lambda_function.processor.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

// REST API Gateway is used here because LocalStack exposes a stable local
// execute-api URL for end-to-end HTTP testing.
resource "aws_api_gateway_rest_api" "webhook" {
  name        = "${local.name_prefix}-webhook-api"
  description = "GitHub webhook ingestion API backed by Lambda and SQS."

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

// The public route is POST /webhooks/github, matching a realistic webhook
// receiver shape instead of direct Lambda invocation.
resource "aws_api_gateway_resource" "webhooks" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  parent_id   = aws_api_gateway_rest_api.webhook.root_resource_id
  path_part   = "webhooks"
}

resource "aws_api_gateway_resource" "github" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  parent_id   = aws_api_gateway_resource.webhooks.id
  path_part   = "github"
}

resource "aws_api_gateway_method" "github_post" {
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  resource_id   = aws_api_gateway_resource.github.id
  http_method   = "POST"
  authorization = "NONE"
}

// AWS_PROXY preserves the full request body and headers for the Lambda handler.
resource "aws_api_gateway_integration" "github_post" {
  rest_api_id             = aws_api_gateway_rest_api.webhook.id
  resource_id             = aws_api_gateway_resource.github.id
  http_method             = aws_api_gateway_method.github_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ingest.invoke_arn
}

// API Gateway needs an explicit Lambda permission even in LocalStack because
// Terraform models the same invoke relationship as real AWS.
resource "aws_lambda_permission" "allow_api_gateway_ingest" {
  statement_id  = "AllowExecutionFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.webhook.execution_arn}/*/*"
}

// The deployment trigger includes route and handler inputs so Terraform creates
// a new deployment when the API wiring or ingest code changes.
resource "aws_api_gateway_deployment" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.github.id,
      aws_api_gateway_method.github_post.id,
      aws_api_gateway_integration.github_post.id,
      aws_lambda_function.ingest.source_code_hash
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.github_post,
    aws_lambda_permission.allow_api_gateway_ingest
  ]
}

// The stage name follows the environment variable, producing URLs like /dev.
resource "aws_api_gateway_stage" "webhook" {
  deployment_id = aws_api_gateway_deployment.webhook.id
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  stage_name    = var.environment
}
