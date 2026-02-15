# -----------------------------------------------------------------------------
# IAM Role for Lambda Proxy Function
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Trust policy for Lambda
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json

  tags = var.tags
}

# Lambda permissions - CloudWatch Logs and InvokeAgentRuntime
data "aws_iam_policy_document" "lambda_permissions" {
  # CloudWatch Logs
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-proxy:*"]
  }

  # InvokeAgentRuntime permission (includes runtime-endpoint sub-resources)
  statement {
    sid     = "InvokeAgentRuntime"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      var.runtime_arn,
      "${var.runtime_arn}/*"
    ]
  }

  # X-Ray tracing (conditional - only when Active tracing is enabled)
  dynamic "statement" {
    for_each = var.xray_tracing_mode == "Active" ? [1] : []
    content {
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

}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${var.project_name}-lambda-permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# VPC ENI management - AWS managed policy (conditional)
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  count      = length(var.subnet_ids) > 0 ? 1 : 0
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}
