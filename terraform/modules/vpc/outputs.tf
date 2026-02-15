# -----------------------------------------------------------------------------
# VPC Module Outputs
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.this.id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = [for s in aws_subnet.private : s.id]
}

output "lambda_security_group_id" {
  description = "Security group ID for Lambda VPC configuration"
  value       = aws_security_group.lambda.id
}
