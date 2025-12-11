# -----------------------------------------------------------------------------
# AgentCore Runtime Outputs
# -----------------------------------------------------------------------------

output "runtime_arn" {
  description = "ARN of the AgentCore Runtime (MCP Server)"
  value       = aws_bedrockagentcore_agent_runtime.mcp_server.agent_runtime_arn
}

output "runtime_id" {
  description = "ID of the AgentCore Runtime"
  value       = aws_bedrockagentcore_agent_runtime.mcp_server.agent_runtime_id
}

output "runtime_name" {
  description = "Name of the AgentCore Runtime"
  value       = aws_bedrockagentcore_agent_runtime.mcp_server.agent_runtime_name
}

output "role_arn" {
  description = "IAM Role ARN used by the runtime"
  value       = aws_iam_role.runtime.arn
}
