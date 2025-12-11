variable "project_name" {
  description = "Name prefix for resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "container_uri" {
  description = "Full container URI for aws-api-mcp-server"
  type        = string
}

variable "aws_policy_arn" {
  description = "AWS managed policy ARN for runtime permissions (e.g., ReadOnlyAccess)"
  type        = string
  default     = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
