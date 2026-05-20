// LocalStack-backed S3 state gives the project the same remote-state workflow
// shape used by teams, while keeping every call inside the local AWS emulator.

bucket = "localstack-platform-terraform-state"
key    = "terraform-localstack-platform/dev/terraform.tfstate"
region = "eu-central-1"

// Static test credentials are accepted by LocalStack and avoid leaking or
// depending on real AWS credentials in CI.
access_key = "test"
secret_key = "test"

// These backend flags disable AWS account and region checks that do not apply
// to LocalStack's emulated S3 and STS services.
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
skip_region_validation      = true
skip_s3_checksum            = true
use_path_style              = true

// Terraform's backend has its own endpoint settings, separate from the AWS
// provider endpoints in providers.tf.
endpoints = {
  s3  = "http://localhost:4566"
  sts = "http://localhost:4566"
}
