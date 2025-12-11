# -----------------------------------------------------------------------------
# IAM Role for AgentCore Gateway
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Trust policy for bedrock-agentcore.amazonaws.com
data "aws_iam_policy_document" "gateway_trust" {
  statement {
    sid     = "AssumeRolePolicy"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:*:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.project_name}-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json

  tags = var.tags
}

# Permission to invoke Lambda
data "aws_iam_policy_document" "gateway_permissions" {
  statement {
    sid       = "InvokeLambdaTarget"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.lambda_function_arn]
  }
}

resource "aws_iam_role_policy" "gateway_permissions" {
  name   = "${var.project_name}-gateway-permissions"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_permissions.json
}
