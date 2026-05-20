// Outputs are part of the developer and CI contract. The workflow consumes
// these values instead of reconstructing names or endpoint URLs by hand.

output "api_gateway_invoke_url" {
  description = "LocalStack URL for posting GitHub webhook events."
  value       = "${var.localstack_endpoint}/_aws/execute-api/${aws_api_gateway_rest_api.webhook.id}/${aws_api_gateway_stage.webhook.stage_name}/webhooks/github"
}

output "bucket_name" {
  description = "S3 bucket used to archive raw event payloads."
  value       = aws_s3_bucket.events.bucket
}

output "table_name" {
  description = "DynamoDB table used to index processed event metadata."
  value       = aws_dynamodb_table.events.name
}

output "queue_name" {
  description = "SQS queue that buffers accepted webhook events."
  value       = aws_sqs_queue.events.name
}

output "dead_letter_queue_name" {
  description = "SQS dead-letter queue for messages that fail processing repeatedly."
  value       = aws_sqs_queue.events_dlq.name
}

output "ingest_lambda_name" {
  description = "Lambda function that accepts API Gateway webhook requests."
  value       = aws_lambda_function.ingest.function_name
}

output "processor_lambda_name" {
  description = "Lambda function that processes SQS messages."
  value       = aws_lambda_function.processor.function_name
}

output "ingest_log_group_name" {
  description = "CloudWatch log group for the ingest Lambda."
  value       = aws_cloudwatch_log_group.ingest.name
}

output "processor_log_group_name" {
  description = "CloudWatch log group for the processor Lambda."
  value       = aws_cloudwatch_log_group.processor.name
}
