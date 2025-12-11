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
