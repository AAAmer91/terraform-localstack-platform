terraform {
  required_version = ">= 1.7.0"

  # Backend values live in backend.localstack.hcl so CI and local runs can point
  # Terraform state at the LocalStack S3 endpoint without hardcoding it here.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}
