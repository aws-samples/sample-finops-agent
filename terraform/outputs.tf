# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Outputs
# -----------------------------------------------------------------------------

# AgentCore Runtime Outputs
output "runtime_arn" {
  description = "AgentCore Runtime ARN (MCP Server)"
  value       = module.agentcore_runtime.runtime_arn
}

output "runtime_id" {
  description = "AgentCore Runtime ID"
  value       = module.agentcore_runtime.runtime_id
}

# Lambda Proxy Outputs
output "lambda_function_arn" {
  description = "Lambda proxy function ARN"
  value       = module.lambda_proxy.function_arn
}

output "lambda_log_group" {
  description = "CloudWatch Log Group for Lambda"
  value       = module.lambda_proxy.log_group_name
}

# AgentCore Gateway Outputs
output "gateway_id" {
  description = "AgentCore Gateway ID"
  value       = module.agentcore_gateway.gateway_id
}

output "gateway_endpoint" {
  description = "MCP Gateway URL for client configuration (use this in .mcp.json)"
  value       = module.agentcore_gateway.gateway_url
}

# Summary for MCP Client Configuration
output "mcp_client_config" {
  description = "Example MCP client configuration for .mcp.json"
  value = {
    gateway_endpoint = module.agentcore_gateway.gateway_url
    auth_type        = var.gateway_auth_type
    target_name      = "${var.project_name}-lambda-target"
  }
}
