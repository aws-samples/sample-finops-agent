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

# -----------------------------------------------------------------------------
# MCP Lambda Server Outputs
# -----------------------------------------------------------------------------

output "mcp_test_lambda_arn" {
  description = "Test MCP Lambda function ARN"
  value       = module.mcp_test.function_arn
}

output "mcp_cost_explorer_lambda_arn" {
  description = "Cost Explorer MCP Lambda function ARN"
  value       = module.mcp_cost_explorer.function_arn
}

output "mcp_athena_lambda_arn" {
  description = "Athena MCP Lambda function ARN"
  value       = module.mcp_athena.function_arn
}

output "mcp_target_ids" {
  description = "Map of MCP Lambda target names to their target IDs"
  value       = module.agentcore_gateway.mcp_target_ids
}

# Summary for MCP Client Configuration
output "mcp_client_config" {
  description = "Example MCP client configuration for .mcp.json"
  value = {
    gateway_endpoint = module.agentcore_gateway.gateway_url
    auth_type        = var.gateway_auth_type
    targets = {
      proxy          = "${var.project_name}-lambda-target"
      test           = "test-mcp"
      cost_explorer  = "cost-explorer-mcp"
      athena         = "athena-mcp"
    }
  }
}
