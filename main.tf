# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Main Configuration
# -----------------------------------------------------------------------------
# This Terraform configuration deploys:
# 1. AgentCore Runtime - aws-api-mcp-server from AWS Marketplace
# 2. Lambda Proxy - Translates Gateway calls to InvokeAgentRuntime API
# 3. AgentCore Gateway - Exposes MCP endpoint for external clients
# -----------------------------------------------------------------------------

locals {
  container_uri = "${var.mcp_server_image_registry}:${var.mcp_server_image_version}"

  common_tags = merge(var.tags, {
    Environment = var.environment
    Project     = var.project_name
  })
}

# -----------------------------------------------------------------------------
# Module 1: AgentCore Runtime (MCP Server)
# -----------------------------------------------------------------------------
module "agentcore_runtime" {
  source = "./modules/agentcore-runtime"

  project_name   = var.project_name
  aws_region     = var.aws_region
  container_uri  = local.container_uri
  aws_policy_arn = var.runtime_aws_policy_arn

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Module 2: Lambda Proxy Function
# -----------------------------------------------------------------------------
module "lambda_proxy" {
  source = "./modules/lambda-proxy"

  project_name = var.project_name
  aws_region   = var.aws_region
  runtime_arn  = module.agentcore_runtime.runtime_arn
  timeout      = var.lambda_timeout
  memory_size  = var.lambda_memory_size

  tags = local.common_tags

  depends_on = [module.agentcore_runtime]
}

# -----------------------------------------------------------------------------
# Module 3: AgentCore Gateway
# -----------------------------------------------------------------------------
module "agentcore_gateway" {
  source = "./modules/agentcore-gateway"

  project_name        = var.project_name
  lambda_function_arn = module.lambda_proxy.function_arn
  auth_type           = var.gateway_auth_type

  # Federate JWT configuration (used when auth_type = CUSTOM_JWT)
  jwt_discovery_url     = var.jwt_discovery_url
  jwt_allowed_audiences = var.jwt_allowed_audiences
  jwt_allowed_clients   = var.jwt_allowed_clients

  tags = local.common_tags

  depends_on = [module.lambda_proxy]
}
