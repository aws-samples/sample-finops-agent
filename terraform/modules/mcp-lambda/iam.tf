# -----------------------------------------------------------------------------
# IAM Role for MCP Lambda Function
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Trust policy for Lambda
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    sid     = "AssumeRolePolicy"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-${var.server_name}-mcp-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json

  tags = var.tags
}

# Base permissions (CloudWatch Logs)
data "aws_iam_policy_document" "lambda_base" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.server_name}-mcp:*"
    ]
  }
}

# Custom permissions for specific MCP servers
data "aws_iam_policy_document" "lambda_custom" {
  count = length(var.iam_policy_statements) > 0 ? 1 : 0

  dynamic "statement" {
    for_each = var.iam_policy_statements
    content {
      effect    = "Allow"
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

# Combine base and custom policies
data "aws_iam_policy_document" "lambda_combined" {
  source_policy_documents = concat(
    [data.aws_iam_policy_document.lambda_base.json],
    length(var.iam_policy_statements) > 0 ? [data.aws_iam_policy_document.lambda_custom[0].json] : []
  )
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${var.project_name}-${var.server_name}-mcp-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_combined.json
}
