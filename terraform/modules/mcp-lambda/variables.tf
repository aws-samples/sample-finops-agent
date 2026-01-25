# -----------------------------------------------------------------------------
# MCP Lambda Module Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for resources"
  type        = string
}

variable "server_name" {
  description = "Name of the MCP server (e.g., 'test', 'cost-explorer', 'athena')"
  type        = string
}

variable "description" {
  description = "Description of the Lambda function"
  type        = string
}

variable "source_file" {
  description = "Path to the Lambda function source file (for single-file Lambdas without dependencies)"
  type        = string
  default     = null
}

variable "source_dir" {
  description = "Path to the Lambda source directory (for Lambdas with requirements.txt dependencies)"
  type        = string
  default     = null
}

variable "aws_region" {
  description = "AWS region for resource ARNs"
  type        = string
}

variable "timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 256
}

variable "gateway_arn_pattern" {
  description = "ARN pattern for Gateway to invoke this Lambda"
  type        = string
}

variable "iam_policy_statements" {
  description = "List of IAM policy statements for the Lambda execution role"
  type = list(object({
    actions   = list(string)
    resources = list(string)
  }))
  default = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Cross-Account Configuration
# -----------------------------------------------------------------------------

variable "cross_account_enabled" {
  description = "Whether cross-account access is enabled (controls IAM policy creation)"
  type        = bool
  default     = false
}

variable "cross_account_role_arn" {
  description = "IAM role ARN to assume for cross-account access (empty = use execution role)"
  type        = string
  default     = ""
}

variable "cross_account_external_id" {
  description = "External ID for cross-account role assumption"
  type        = string
  default     = ""
  sensitive   = true
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}
