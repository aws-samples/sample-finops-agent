# -----------------------------------------------------------------------------
# VPC Module Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for all VPC resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region for VPC endpoint service names"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC (a /24 provides 256 IPs, sufficient for endpoints + Lambda ENIs)"
  type        = string
  default     = "10.0.0.0/24"
}

variable "interface_endpoint_services" {
  description = "List of AWS service suffixes for interface VPC endpoints (e.g., 'sts', 'logs')"
  type        = list(string)
  default     = ["sts", "logs", "athena", "glue", "ce", "bedrock-agentcore"]
}

variable "flow_log_retention_in_days" {
  description = "Retention in days for VPC flow log CloudWatch log group"
  type        = number
  default     = 365
}

variable "log_group_kms_key_arn" {
  description = "ARN of the KMS key to encrypt CloudWatch Log Groups. If null, AWS-managed encryption is used."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
