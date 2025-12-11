# -----------------------------------------------------------------------------
# AgentCore Gateway Module Outputs
# -----------------------------------------------------------------------------

output "gateway_id" {
  description = "ID of the AgentCore Gateway"
  value       = aws_bedrockagentcore_gateway.mcp.gateway_id
}

output "gateway_arn" {
  description = "ARN of the AgentCore Gateway"
  value       = aws_bedrockagentcore_gateway.mcp.gateway_arn
}

output "gateway_name" {
  description = "Name of the AgentCore Gateway"
  value       = aws_bedrockagentcore_gateway.mcp.name
}

output "gateway_url" {
  description = "MCP Gateway URL for client configuration"
  value       = aws_bedrockagentcore_gateway.mcp.gateway_url
}

output "target_id" {
  description = "ID of the Gateway Target"
  value       = aws_bedrockagentcore_gateway_target.lambda.target_id
}

output "role_arn" {
  description = "IAM Role ARN used by the Gateway"
  value       = aws_iam_role.gateway.arn
}
