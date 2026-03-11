# -----------------------------------------------------------------------------
# Cross-Account IAM Role in Management Account
# -----------------------------------------------------------------------------
# This role is created in the management/payer account and allows the
# MCP Gateway (in data collection account) to access Cost Explorer and CUR data.
#
# Only created when management_account_profile is set.
# -----------------------------------------------------------------------------

# Get data collection account ID (always available)
data "aws_caller_identity" "data_collection" {}

# Get management account ID (only when cross-account is enabled)
data "aws_caller_identity" "management" {
  count    = var.management_account_profile != "" ? 1 : 0
  provider = aws.management
}

# Generate external ID if not provided
resource "random_id" "cross_account_external_id" {
  count       = var.management_account_profile != "" && var.management_external_id == "" ? 1 : 0
  byte_length = 16
}

locals {
  # Whether cross-account mode is enabled (known at plan time)
  cross_account_enabled = var.management_account_profile != ""

  # Use provided external ID or generate one
  cross_account_external_id = local.cross_account_enabled ? (
    var.management_external_id != "" ? var.management_external_id : random_id.cross_account_external_id[0].hex
  ) : ""

  # Role ARN for Lambda environment variables
  management_role_arn = local.cross_account_enabled ? aws_iam_role.mcp_gateway_cross_account[0].arn : ""
}

# Trust policy - allows data collection account to assume this role
data "aws_iam_policy_document" "cross_account_trust" {
  count = var.management_account_profile != "" ? 1 : 0

  statement {
    sid     = "AllowDataCollectionAccountAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.data_collection.account_id}:root"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [local.cross_account_external_id]
    }
  }
}

# Combined permissions policy
data "aws_iam_policy_document" "cross_account_permissions" {
  # checkov:skip=CKV_AWS_111:Athena requires write access (StartQueryExecution, S3 PutObject) for query results - scoped to CUR bucket
  # checkov:skip=CKV_AWS_356:Cost Explorer, Athena, and AWS Glue read APIs do not support resource-level permissions (AWS limitation)
  count = var.management_account_profile != "" ? 1 : 0

  # Cost Explorer - Read-only access for cost analysis
  statement {
    sid    = "CostExplorerReadOnly"
    effect = "Allow"
    actions = [
      "ce:GetCostAndUsage",
      "ce:GetCostForecast",
      "ce:GetDimensionValues",
      "ce:GetTags",
      "ce:GetSavingsPlansCoverage",
      "ce:GetSavingsPlansUtilization",
      "ce:GetReservationCoverage",
      "ce:GetReservationUtilization"
    ]
    resources = ["*"]
  }

  # Athena - Query access for CUR analysis
  statement {
    sid    = "AthenaQueryAccess"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:BatchGetQueryExecution",
      "athena:ListQueryExecutions",
      "athena:StopQueryExecution",
      "athena:ListDatabases",
      "athena:ListTableMetadata",
      "athena:GetTableMetadata",
      "athena:GetDatabase",
      "athena:ListDataCatalogs",
      "athena:GetDataCatalog"
    ]
    resources = ["*"]
  }

  # S3 - Access to CUR bucket for data and Athena results
  statement {
    sid    = "CURBucketAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts"
    ]
    resources = [
      "arn:aws:s3:::${var.cur_bucket_name}",
      "arn:aws:s3:::${var.cur_bucket_name}/*"
    ]
  }

  # AWS Glue - Access to CUR metadata catalog
  statement {
    sid    = "GlueCatalogAccess"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions"
    ]
    resources = ["*"]
  }
}

# IAM Role in management account
resource "aws_iam_role" "mcp_gateway_cross_account" {
  count    = var.management_account_profile != "" ? 1 : 0
  provider = aws.management

  name               = "${var.project_name}-cross-account"
  description        = "Allows MCP Gateway in data collection account to access Cost Explorer and CUR data"
  assume_role_policy = data.aws_iam_policy_document.cross_account_trust[0].json

  tags = merge(local.common_tags, {
    Purpose = "mcp-gateway-cross-account"
  })
}

resource "aws_iam_role_policy" "mcp_gateway_cross_account" {
  count    = var.management_account_profile != "" ? 1 : 0
  provider = aws.management

  name   = "CrossAccountAccess"
  role   = aws_iam_role.mcp_gateway_cross_account[0].id
  policy = data.aws_iam_policy_document.cross_account_permissions[0].json
}
