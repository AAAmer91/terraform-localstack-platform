output "bucket_name" {
  description = "S3 bucket used to store raw events."
  value       = aws_s3_bucket.events.bucket
}

output "table_name" {
  description = "DynamoDB table used to store event metadata."
  value       = aws_dynamodb_table.events.name
}

output "lambda_name" {
  description = "Lambda function used to process incoming events."
  value       = aws_lambda_function.ingest.function_name
}