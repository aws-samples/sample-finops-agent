# -----------------------------------------------------------------------------
# n8n Cross-Account Lambda Invocation
# -----------------------------------------------------------------------------
# This configuration creates an IAM role that allows n8n (in a different AWS
# account) to invoke the cur-analyst Lambda function using role assumption.
#
# Architecture:
#   n8n Account (739907928487)          Lambda Account (this account)
#   ┌─────────────────────┐            ┌─────────────────────────────┐
#   │ n8n IAM User        │            │ n8n-lambda-invoker Role     │
#   │ (with access keys)  │──assumes──▶│ (trust: n8n account)        │
#   │                     │            │                             │
#   └─────────────────────┘            │ Policy: InvokeFunction      │
#                                      │         cur-analyst-mcp     │
#                                      └─────────────────────────────┘
# -----------------------------------------------------------------------------

locals {
  n8n_account_id  = var.n8n_cross_account_id
  n8n_external_id = var.n8n_external_id != "" ? var.n8n_external_id : "n8n-lambda-${random_id.external_id[0].hex}"
}

# Generate random external ID if not provided
resource "random_id" "external_id" {
  count       = var.n8n_external_id == "" ? 1 : 0
  byte_length = 16
}

# -----------------------------------------------------------------------------
# IAM Role for n8n Cross-Account Access
# -----------------------------------------------------------------------------
resource "aws_iam_role" "n8n_lambda_invoker" {
  count = var.n8n_cross_account_id != "" ? 1 : 0

  name        = "${var.project_name}-n8n-lambda-invoker"
  description = "Allows n8n from account ${local.n8n_account_id} to invoke cur-analyst Lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.n8n_account_id}:root"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = local.n8n_external_id
          }
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Purpose = "n8n-cross-account-lambda-invocation"
  })
}

# -----------------------------------------------------------------------------
# IAM Policy for Lambda Invocation
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "n8n_invoke_cur_analyst" {
  count = var.n8n_cross_account_id != "" ? 1 : 0

  name = "invoke-cur-analyst-lambda"
  role = aws_iam_role.n8n_lambda_invoker[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeCurAnalystLambda"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          module.mcp_cur_analyst.function_arn,
          "${module.mcp_cur_analyst.function_arn}:*"
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs for n8n Configuration
# -----------------------------------------------------------------------------
output "n8n_role_arn" {
  description = "IAM Role ARN for n8n to assume (use this in n8n AWS credentials)"
  value       = var.n8n_cross_account_id != "" ? aws_iam_role.n8n_lambda_invoker[0].arn : null
}

output "n8n_external_id" {
  description = "External ID for role assumption (keep this secret, use in n8n)"
  value       = var.n8n_cross_account_id != "" ? local.n8n_external_id : null
  sensitive   = true
}

output "n8n_cur_analyst_lambda_arn" {
  description = "Lambda ARN to invoke from n8n"
  value       = module.mcp_cur_analyst.function_arn
}

output "n8n_configuration_summary" {
  description = "Summary of values needed for n8n AWS Lambda node configuration"
  value = var.n8n_cross_account_id != "" ? {
    role_arn     = aws_iam_role.n8n_lambda_invoker[0].arn
    external_id  = local.n8n_external_id
    lambda_arn   = module.mcp_cur_analyst.function_arn
    region       = var.aws_region
    instructions = <<-EOT
      1. In n8n, create AWS credentials with:
         - Access Key ID: <your-n8n-account-iam-user-access-key>
         - Secret Access Key: <your-n8n-account-iam-user-secret-key>
         - Region: ${var.aws_region}
         - Role ARN: ${aws_iam_role.n8n_lambda_invoker[0].arn}
         - External ID: <run 'terraform output -raw n8n_external_id'>

      2. In n8n AWS Lambda node, set:
         - Function: ${module.mcp_cur_analyst.function_arn}
         - Invocation Type: RequestResponse
    EOT
  } : null
  sensitive = true
}
