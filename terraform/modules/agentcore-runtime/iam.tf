# -----------------------------------------------------------------------------
# IAM Role for AgentCore Runtime
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Trust policy for bedrock-agentcore.amazonaws.com
data "aws_iam_policy_document" "runtime_trust" {
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

resource "aws_iam_role" "runtime" {
  name               = "${var.project_name}-runtime-role"
  assume_role_policy = data.aws_iam_policy_document.runtime_trust.json

  tags = var.tags
}

# Base AgentCore permissions (ECR, CloudWatch, X-Ray, Workload Identity)
data "aws_iam_policy_document" "agentcore_base" {
  # ECR image access for AWS Marketplace container
  statement {
    sid    = "ECRImageAccess"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]
    resources = ["arn:aws:ecr:us-east-1:709825985650:repository/*"]
  }

  # ECR token access
  statement {
    sid       = "ECRTokenAccess"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # CloudWatch Logs - describe
  statement {
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  # CloudWatch Logs - create and write
  statement {
    effect = "Allow"
    actions = [
      "logs:DescribeLogStreams",
      "logs:CreateLogGroup"
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
  }

  # X-Ray tracing
  statement {
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets"
    ]
    resources = ["*"]
  }

  # CloudWatch metrics
  statement {
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }

  # Workload Identity tokens
  statement {
    sid    = "GetAgentAccessToken"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/*"
    ]
  }
}

resource "aws_iam_role_policy" "agentcore_base" {
  name   = "${var.project_name}-agentcore-base"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.agentcore_base.json
}

# Attach AWS managed policy for API access (e.g., ReadOnlyAccess)
resource "aws_iam_role_policy_attachment" "aws_api_access" {
  role       = aws_iam_role.runtime.name
  policy_arn = var.aws_policy_arn
}

# Athena query execution permissions (not included in ReadOnlyAccess)
data "aws_iam_policy_document" "athena_query" {
  # Athena query execution
  statement {
    sid    = "AthenaQueryExecution"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:StopQueryExecution"
    ]
    resources = [
      "arn:aws:athena:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workgroup/*"
    ]
  }

  # S3 write access for Athena query results
  statement {
    sid    = "AthenaResultsWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetBucketLocation"
    ]
    resources = [
      "arn:aws:s3:::*-athena-results",
      "arn:aws:s3:::*-athena-results/*",
      "arn:aws:s3:::*-cur-*",
      "arn:aws:s3:::*-cur-*/*"
    ]
  }
}

resource "aws_iam_role_policy" "athena_query" {
  name   = "${var.project_name}-athena-query"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.athena_query.json
}
