# -----------------------------------------------------------------------------
# Lambda Proxy Module Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "runtime_arn" {
  description = "ARN of the AgentCore Runtime to invoke"
  type        = string
}

variable "timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 256
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Security Configuration
# -----------------------------------------------------------------------------

variable "log_group_kms_key_arn" {
  description = "ARN of the KMS key to encrypt CloudWatch Log Group. If null, AWS-managed encryption is used."
  type        = string
  default     = null
}

variable "lambda_kms_key_arn" {
  description = "ARN of the KMS key to encrypt Lambda environment variables at rest. If null, AWS-managed encryption is used."
  type        = string
  default     = null
}

variable "xray_tracing_mode" {
  description = "X-Ray tracing mode for the Lambda function. Valid values: PassThrough, Active."
  type        = string
  default     = "PassThrough"

  validation {
    condition     = contains(["PassThrough", "Active"], var.xray_tracing_mode)
    error_message = "xray_tracing_mode must be either 'PassThrough' or 'Active'."
  }
}
