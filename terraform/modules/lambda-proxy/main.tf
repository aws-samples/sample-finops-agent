# -----------------------------------------------------------------------------
# Lambda Proxy Function
# Forwards MCP requests from Gateway to AgentCore Runtime
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
  }
}

# Package the Lambda function code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../../../src/lambda/proxy/lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-proxy"
  retention_in_days = var.log_retention_in_days
  kms_key_id        = var.log_group_kms_key_arn

  tags = var.tags
}

# Lambda Function
resource "aws_lambda_function" "proxy" {
  # checkov:skip=CKV_AWS_116:Synchronous invocation by AgentCore Gateway - DLQ only applies to async invocations
  # checkov:skip=CKV_AWS_272:Code packaged from local source via archive_file - code-signing requires CI/CD pipeline
  function_name = "${var.project_name}-proxy"
  description   = "MCP proxy for ${var.project_name} - forwards requests to AgentCore Runtime"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"

  role        = aws_iam_role.lambda.arn
  timeout     = var.timeout
  memory_size = var.memory_size
  kms_key_arn = var.lambda_kms_key_arn

  reserved_concurrent_executions = var.reserved_concurrent_executions

  dynamic "vpc_config" {
    for_each = length(var.subnet_ids) > 0 ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = var.security_group_ids
    }
  }

  tracing_config {
    mode = var.xray_tracing_mode
  }

  environment {
    variables = {
      RUNTIME_ARN = var.runtime_arn
      # AWS_REGION is set automatically by Lambda
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_permissions
  ]

  tags = var.tags
}

# Permission for AgentCore Gateway to invoke Lambda
resource "aws_lambda_permission" "gateway_invoke" {
  statement_id  = "AllowAgentCoreGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.proxy.function_name
  principal     = "bedrock-agentcore.amazonaws.com"
  source_arn    = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:gateway/*"
}
