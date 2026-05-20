// These variables keep the stack portable across local and CI LocalStack runs.
// The defaults intentionally describe the demo environment used by the README.

variable "aws_region" {
  description = "AWS region used by the local AWS-compatible environment."
  type        = string
  default     = "eu-central-1"
}

variable "localstack_endpoint" {
  description = "LocalStack edge endpoint used by all AWS services in this demo."
  type        = string
  default     = "http://localhost:4566"
}

variable "project_name" {
  description = "Project name used in resource naming."
  type        = string
  default     = "localstack-platform"
}

variable "environment" {
  description = "Environment name used for tags and naming."
  type        = string
  default     = "dev"
}
