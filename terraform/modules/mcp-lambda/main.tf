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
# Option 1: Single file packaging (no dependencies)
# -----------------------------------------------------------------------------
data "archive_file" "lambda_zip_single" {
  count       = local.use_source_dir ? 0 : 1
  type        = "zip"
  source_file = var.source_file
  output_path = "${path.module}/.build/${var.server_name}_lambda.zip"
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
resource "aws_lambda_function" "mcp" {
  function_name = "${var.project_name}-${var.server_name}-mcp"
  description   = var.description

  filename         = local.use_source_dir ? data.archive_file.lambda_zip_dir[0].output_path : data.archive_file.lambda_zip_single[0].output_path
  source_code_hash = local.use_source_dir ? data.archive_file.lambda_zip_dir[0].output_base64sha256 : data.archive_file.lambda_zip_single[0].output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"

  role        = aws_iam_role.lambda.arn
  timeout     = var.timeout
  memory_size = var.memory_size

  tags = var.tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-${var.server_name}-mcp"
  retention_in_days = 14

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
