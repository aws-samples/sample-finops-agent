# -----------------------------------------------------------------------------
# Lambda Proxy Module Outputs
# -----------------------------------------------------------------------------

output "function_arn" {
  description = "ARN of the Lambda proxy function"
  value       = aws_lambda_function.proxy.arn
}

output "function_name" {
  description = "Name of the Lambda proxy function"
  value       = aws_lambda_function.proxy.function_name
}

output "invoke_arn" {
  description = "Invoke ARN for the Lambda function"
  value       = aws_lambda_function.proxy.invoke_arn
}

output "role_arn" {
  description = "IAM Role ARN used by the Lambda function"
  value       = aws_iam_role.lambda.arn
}

output "log_group_name" {
  description = "CloudWatch Log Group name for Lambda logs"
  value       = aws_cloudwatch_log_group.lambda.name
}
