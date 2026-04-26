variable "project_name" {
  description = "Project name prefix"
  type        = string
}

variable "aws_region" {
  description = "AWS region (used to build token/discovery URLs)"
  type        = string
}

variable "domain_prefix" {
  description = "Cognito Domain prefix (must be globally unique)"
  type        = string
}

variable "scope_name" {
  description = "Custom OAuth scope name (e.g. 'invoke')"
  type        = string
  default     = "invoke"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
