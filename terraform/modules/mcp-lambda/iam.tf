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

# Cross-account role assumption permission (conditional)
data "aws_iam_policy_document" "lambda_cross_account" {
  count = var.cross_account_enabled ? 1 : 0

  statement {
    sid       = "AssumeManagementAccountRole"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [var.cross_account_role_arn]
  }
}

# X-Ray tracing permission (conditional)
data "aws_iam_policy_document" "lambda_xray" {
  count = var.xray_tracing_mode == "Active" ? 1 : 0

  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets"
    ]
    resources = ["*"]
  }
}

# VPC ENI management permission (conditional - only when VPC is configured)
data "aws_iam_policy_document" "lambda_vpc" {
  count = length(var.subnet_ids) > 0 ? 1 : 0

  statement {
    sid    = "VPCNetworkInterface"
    effect = "Allow"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface"
    ]
    resources = ["*"]
  }
}

# Combine base, custom, cross-account, X-Ray, and VPC policies
data "aws_iam_policy_document" "lambda_combined" {
  source_policy_documents = concat(
    [data.aws_iam_policy_document.lambda_base.json],
    length(var.iam_policy_statements) > 0 ? [data.aws_iam_policy_document.lambda_custom[0].json] : [],
    var.cross_account_enabled ? [data.aws_iam_policy_document.lambda_cross_account[0].json] : [],
    var.xray_tracing_mode == "Active" ? [data.aws_iam_policy_document.lambda_xray[0].json] : [],
    length(var.subnet_ids) > 0 ? [data.aws_iam_policy_document.lambda_vpc[0].json] : []
  )
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${var.project_name}-${var.server_name}-mcp-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_combined.json
}
