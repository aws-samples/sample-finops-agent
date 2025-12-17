# -----------------------------------------------------------------------------
# MCP Lambda Module Outputs
# -----------------------------------------------------------------------------

output "function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.mcp.arn
}

output "function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.mcp.function_name
}

output "role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.lambda.name
}
