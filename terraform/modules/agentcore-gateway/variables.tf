# -----------------------------------------------------------------------------
# AgentCore Gateway Module Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name prefix for resources"
  type        = string
}

variable "lambda_function_arn" {
  description = "ARN of the Lambda proxy function"
  type        = string
}

variable "auth_type" {
  description = "Authentication type: CUSTOM_JWT, AWS_IAM, or NONE"
  type        = string
  default     = "CUSTOM_JWT"

  validation {
    condition     = contains(["CUSTOM_JWT", "AWS_IAM", "NONE"], var.auth_type)
    error_message = "Auth type must be 'CUSTOM_JWT', 'AWS_IAM', or 'NONE'."
  }
}

# Federate JWT Configuration (required when auth_type = CUSTOM_JWT)
variable "jwt_discovery_url" {
  description = "OIDC discovery URL for JWT validation (e.g., Federate)"
  type        = string
  default     = "https://idp-integ.federate.amazon.com/.well-known/openid-configuration"
}

variable "jwt_allowed_audiences" {
  description = "List of allowed JWT audiences"
  type        = list(string)
  default     = ["mcp-federate-integ-es"]
}

variable "jwt_allowed_clients" {
  description = "List of allowed JWT client IDs (optional)"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# MCP Lambda Targets Configuration
# -----------------------------------------------------------------------------

variable "mcp_lambda_targets" {
  description = "List of MCP Lambda targets to add to the gateway"
  type        = any # List of objects with name, description, lambda_arn, tool_schemas
  default     = []
}
