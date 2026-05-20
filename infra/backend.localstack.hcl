bucket = "localstack-platform-terraform-state"
key    = "terraform-localstack-platform/dev/terraform.tfstate"
region = "eu-central-1"

access_key = "test"
secret_key = "test"

skip_credentials_validation = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
skip_region_validation      = true
skip_s3_checksum            = true
use_path_style              = true

endpoints = {
  s3  = "http://localhost:4566"
  sts = "http://localhost:4566"
}
