# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for all resources (e.g., 'aiops-mcp-gateway')"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.project_name))
    error_message = "Project name must start with a letter and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

# -----------------------------------------------------------------------------
# MCP Server Configuration
# -----------------------------------------------------------------------------

variable "mcp_server_image_version" {
  description = "Version of aws-api-mcp-server from AWS Marketplace. Check: https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw"
  type        = string
  default     = "1.2.0"
}

variable "mcp_server_image_registry" {
  description = "ECR registry for aws-api-mcp-server (AWS Marketplace)"
  type        = string
  default     = "709825985650.dkr.ecr.us-east-1.amazonaws.com/amazon-web-services/aws-api-mcp-server"
}

# -----------------------------------------------------------------------------
# Lambda Configuration
# -----------------------------------------------------------------------------

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30

  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 256

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "Lambda memory must be between 128 and 10240 MB."
  }
}

# -----------------------------------------------------------------------------
# Gateway Configuration
# -----------------------------------------------------------------------------

variable "gateway_auth_type" {
  description = "Gateway authentication method: CUSTOM_JWT (Federate), AWS_IAM, or NONE"
  type        = string
  default     = "CUSTOM_JWT"

  validation {
    condition     = contains(["CUSTOM_JWT", "AWS_IAM", "NONE"], var.gateway_auth_type)
    error_message = "Gateway auth type must be 'CUSTOM_JWT', 'AWS_IAM', or 'NONE'."
  }
}

# Federate JWT Configuration (required when gateway_auth_type = CUSTOM_JWT)
variable "jwt_discovery_url" {
  description = "OIDC discovery URL for JWT validation (Amazon Federate)"
  type        = string
  default     = "https://idp-integ.federate.amazon.com/.well-known/openid-configuration"
}

variable "jwt_allowed_audiences" {
  description = "List of allowed JWT audiences for gateway authentication"
  type        = list(string)
  default     = ["mcp-federate-integ-es"]
}

variable "jwt_allowed_clients" {
  description = "List of allowed JWT client IDs (optional, leave empty for all clients)"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Optional Configuration
# -----------------------------------------------------------------------------

variable "environment" {
  description = "Environment name (e.g., 'dev', 'staging', 'prod')"
  type        = string
  default     = "dev"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project   = "AIOps MCP Gateway"
    ManagedBy = "Terraform"
  }
}

variable "runtime_aws_policy_arn" {
  description = "AWS managed policy ARN to attach to runtime role (e.g., ReadOnlyAccess)"
  type        = string
  default     = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# -----------------------------------------------------------------------------
# n8n Cross-Account Configuration
# -----------------------------------------------------------------------------

variable "n8n_cross_account_id" {
  description = "AWS Account ID where n8n is deployed (for cross-account Lambda invocation)"
  type        = string
  default     = ""

  validation {
    condition     = var.n8n_cross_account_id == "" || can(regex("^[0-9]{12}$", var.n8n_cross_account_id))
    error_message = "n8n_cross_account_id must be a 12-digit AWS account ID or empty string."
  }
}

variable "n8n_external_id" {
  description = "External ID for n8n role assumption (leave empty to auto-generate)"
  type        = string
  default     = ""
  sensitive   = true
}

# -----------------------------------------------------------------------------
# AWS Profile Configuration
# -----------------------------------------------------------------------------

variable "aws_profile" {
  description = "AWS CLI profile for data collection account"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Cross-Account Management Account Configuration
# -----------------------------------------------------------------------------
# For data collection account deployments (alongside CUDOS/CID/KPI dashboards),
# configure access to Cost Explorer and CUR data in the management account.

variable "management_account_profile" {
  description = "AWS CLI profile for management/payer account (empty = single-account mode)"
  type        = string
  default     = ""
}

variable "management_external_id" {
  description = "External ID for cross-account role assumption (auto-generated if empty)"
  type        = string
  default     = ""
  sensitive   = true
}

# -----------------------------------------------------------------------------
# CUR Configuration
# -----------------------------------------------------------------------------

variable "cur_bucket_name" {
  description = "S3 bucket containing CUR data (in management account)"
  type        = string
  default     = "my-cur-cost-export"
}

variable "cur_database_name" {
  description = "Athena/Glue database name for CUR data"
  type        = string
  default     = "cur_database"
}

variable "cur_table_name" {
  description = "Athena/Glue table name for CUR data"
  type        = string
  default     = "mycostexport"
}
