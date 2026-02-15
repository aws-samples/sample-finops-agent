# -----------------------------------------------------------------------------
# MCP Lambda Module
# Reusable module for deploying Lambda-based MCP servers
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

locals {
  # Use source_dir if provided, otherwise use source_file
  use_source_dir = var.source_dir != null
  build_dir      = "${path.module}/.build/${var.server_name}"
}

# -----------------------------------------------------------------------------
# Option 1: Single file packaging (with shared modules if cross-account enabled)
# -----------------------------------------------------------------------------

# Build step for single file: copy source + shared modules
resource "null_resource" "single_file_build" {
  count = local.use_source_dir ? 0 : 1

  triggers = {
    source_hash = filemd5(var.source_file)
    shared_hash = fileexists("${dirname(var.source_file)}/../shared/cross_account.py") ? filemd5("${dirname(var.source_file)}/../shared/cross_account.py") : ""
    build_dir   = local.build_dir
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${local.build_dir}"
      mkdir -p "${local.build_dir}"

      # Copy Lambda function code
      cp "${var.source_file}" "${local.build_dir}/"

      # Copy shared modules if they exist
      if [ -d "${dirname(var.source_file)}/../shared" ]; then
        mkdir -p "${local.build_dir}/shared"
        cp "${dirname(var.source_file)}/../shared/"*.py "${local.build_dir}/shared/" 2>/dev/null || true
      fi

      echo "Build complete: ${local.build_dir}"
    EOT
  }
}

data "archive_file" "lambda_zip_single" {
  count       = local.use_source_dir ? 0 : 1
  type        = "zip"
  source_dir  = local.build_dir
  output_path = "${path.module}/.build/${var.server_name}_lambda.zip"

  depends_on = [null_resource.single_file_build]
}

# -----------------------------------------------------------------------------
# Option 2: Directory packaging with dependencies
# -----------------------------------------------------------------------------

# Build step: Install dependencies using uv pip
resource "null_resource" "pip_install" {
  count = local.use_source_dir ? 1 : 0

  triggers = {
    # Rebuild when requirements.txt or lambda_function.py changes
    requirements_hash = fileexists("${var.source_dir}/requirements.txt") ? filemd5("${var.source_dir}/requirements.txt") : ""
    source_hash       = filemd5("${var.source_dir}/lambda_function.py")
    build_dir         = local.build_dir
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${local.build_dir}"
      mkdir -p "${local.build_dir}"

      # Install dependencies if requirements.txt exists
      # Use Linux platform to ensure Lambda compatibility
      if [ -f "${var.source_dir}/requirements.txt" ]; then
        echo "Installing dependencies from requirements.txt for Lambda (linux x86_64)..."
        uv run --with pip pip install \
          -r "${var.source_dir}/requirements.txt" \
          --target "${local.build_dir}" \
          --platform manylinux2014_x86_64 \
          --implementation cp \
          --python-version 3.12 \
          --only-binary=:all: \
          --quiet
      fi

      # Copy Lambda function code
      cp "${var.source_dir}/lambda_function.py" "${local.build_dir}/"

      # Copy shared modules if they exist
      if [ -d "${var.source_dir}/../shared" ]; then
        mkdir -p "${local.build_dir}/shared"
        cp "${var.source_dir}/../shared/"*.py "${local.build_dir}/shared/" 2>/dev/null || true
      fi

      echo "Build complete: ${local.build_dir}"
    EOT
  }
}

# Archive the built directory
data "archive_file" "lambda_zip_dir" {
  count       = local.use_source_dir ? 1 : 0
  type        = "zip"
  source_dir  = local.build_dir
  output_path = "${path.module}/.build/${var.server_name}_lambda.zip"

  depends_on = [null_resource.pip_install]
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
locals {
  # Merge custom environment variables with cross-account variables
  lambda_env_vars = merge(
    var.environment_variables,
    var.cross_account_role_arn != "" ? {
      CROSS_ACCOUNT_ROLE_ARN    = var.cross_account_role_arn
      CROSS_ACCOUNT_EXTERNAL_ID = var.cross_account_external_id
    } : {}
  )
}

# nosemgrep: terraform.aws.security.aws-lambda-x-ray-tracing-not-active.aws-lambda-x-ray-tracing-not-active
resource "aws_lambda_function" "mcp" {
  # checkov:skip=CKV_AWS_117:Lambdas call AWS APIs only - VPC would require NAT Gateway with no security benefit
  # checkov:skip=CKV_AWS_116:Synchronous invocation by AgentCore Gateway - DLQ only applies to async invocations
  # checkov:skip=CKV_AWS_272:Code packaged from local source via archive_file - code-signing requires CI/CD pipeline
  # checkov:skip=CKV_AWS_115:Concurrency limits are deployment-specific - set via reserved_concurrent_executions variable
  function_name = "${var.project_name}-${var.server_name}-mcp"
  description   = var.description

  filename         = local.use_source_dir ? data.archive_file.lambda_zip_dir[0].output_path : data.archive_file.lambda_zip_single[0].output_path
  source_code_hash = local.use_source_dir ? data.archive_file.lambda_zip_dir[0].output_base64sha256 : data.archive_file.lambda_zip_single[0].output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"

  role        = aws_iam_role.lambda.arn
  timeout     = var.timeout
  memory_size = var.memory_size
  kms_key_arn = var.lambda_kms_key_arn # nosemgrep: terraform.aws.security.aws-lambda-environment-unencrypted.aws-lambda-environment-unencrypted

  tracing_config {
    mode = var.xray_tracing_mode
  }

  dynamic "environment" {
    for_each = length(local.lambda_env_vars) > 0 ? [1] : []
    content {
      variables = local.lambda_env_vars
    }
  }

  tags = var.tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  # checkov:skip=CKV_AWS_338:Short retention (14 days) is intentional for cost management - operational logs, not audit logs
  name              = "/aws/lambda/${var.project_name}-${var.server_name}-mcp"
  retention_in_days = 14
  kms_key_id        = var.log_group_kms_key_arn

  tags = var.tags
}

# Permission for Gateway to invoke Lambda
resource "aws_lambda_permission" "gateway_invoke" {
  statement_id  = "AllowAgentCoreGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp.function_name
  principal     = "bedrock-agentcore.amazonaws.com"
  source_arn    = var.gateway_arn_pattern
}
