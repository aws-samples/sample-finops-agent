# -----------------------------------------------------------------------------
# AIOps MCP Gateway Proxy - Main Configuration
# -----------------------------------------------------------------------------
# This Terraform configuration deploys:
# 1. AgentCore Runtime - aws-api-mcp-server from AWS Marketplace
# 2. Lambda Proxy - Translates Gateway calls to InvokeAgentRuntime API
# 3. MCP Lambda Servers - test, cost_explorer, athena
# 4. AgentCore Gateway - Exposes MCP endpoint for external clients
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  container_uri = "${var.mcp_server_image_registry}:${var.mcp_server_image_version}"

  common_tags = merge(var.tags, {
    Environment = var.environment
    Project     = var.project_name
  })

  # Gateway ARN pattern for Lambda permissions
  gateway_arn_pattern = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:gateway/*"

  # Tool schemas loaded from JSON files
  test_tools          = jsondecode(file("${path.module}/tool-schemas/test.json"))
  cost_explorer_tools = jsondecode(file("${path.module}/tool-schemas/cost_explorer.json"))
  athena_tools        = jsondecode(file("${path.module}/tool-schemas/athena.json"))
  cur_analyst_tools   = jsondecode(file("${path.module}/tool-schemas/cur_analyst.json"))
}

# -----------------------------------------------------------------------------
# VPC for Lambda Functions (conditional)
# -----------------------------------------------------------------------------
module "vpc" {
  count  = var.enable_vpc ? 1 : 0
  source = "./modules/vpc"

  project_name = var.project_name
  aws_region   = var.aws_region
  vpc_cidr     = var.vpc_cidr

  tags = local.common_tags
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

  # Security
  subnet_ids                     = var.enable_vpc ? module.vpc[0].private_subnet_ids : []
  security_group_ids             = var.enable_vpc ? [module.vpc[0].lambda_security_group_id] : []
  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions
  log_retention_in_days          = var.log_retention_in_days

  tags = local.common_tags

  depends_on = [module.agentcore_runtime]
}

# -----------------------------------------------------------------------------
# Module 3: MCP Lambda Servers
# -----------------------------------------------------------------------------

# Test MCP Lambda - Simple tools for Gateway verification
module "mcp_test" {
  source = "./modules/mcp-lambda"

  project_name        = var.project_name
  server_name         = "test"
  description         = "Simple test MCP tools (hello, echo) for Gateway verification"
  source_file         = "${path.module}/../src/lambda/mcp_servers/test/lambda_function.py"
  aws_region          = var.aws_region
  timeout             = 30
  memory_size         = 128
  gateway_arn_pattern = local.gateway_arn_pattern

  # No special permissions needed for test tools
  iam_policy_statements = []

  # Security
  subnet_ids                     = var.enable_vpc ? module.vpc[0].private_subnet_ids : []
  security_group_ids             = var.enable_vpc ? [module.vpc[0].lambda_security_group_id] : []
  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions
  log_retention_in_days          = var.log_retention_in_days

  tags = local.common_tags
}

# Cost Explorer MCP Lambda - AWS cost analysis tools
module "mcp_cost_explorer" {
  source = "./modules/mcp-lambda"

  project_name        = var.project_name
  server_name         = "cost-explorer"
  description         = "AWS Cost Explorer MCP tools for analyzing cloud costs"
  source_file         = "${path.module}/../src/lambda/mcp_servers/cost_explorer/lambda_function.py"
  aws_region          = var.aws_region
  timeout             = 30
  memory_size         = 128
  gateway_arn_pattern = local.gateway_arn_pattern

  # Cross-account configuration (uses locals from management-account-role.tf)
  cross_account_enabled     = local.cross_account_enabled
  cross_account_role_arn    = local.management_role_arn
  cross_account_external_id = local.cross_account_external_id

  iam_policy_statements = [
    {
      actions = [
        "ce:GetCostAndUsage",
        "ce:GetDimensionValues",
        "ce:GetTags",
        "ce:GetCostForecast"
      ]
      resources = ["*"]
    }
  ]

  # Security
  subnet_ids                     = var.enable_vpc ? module.vpc[0].private_subnet_ids : []
  security_group_ids             = var.enable_vpc ? [module.vpc[0].lambda_security_group_id] : []
  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions
  log_retention_in_days          = var.log_retention_in_days

  tags = local.common_tags
}

# Athena MCP Lambda - Data lake query tools
module "mcp_athena" {
  source = "./modules/mcp-lambda"

  project_name        = var.project_name
  server_name         = "athena"
  description         = "AWS Athena MCP tools for querying data lakes"
  source_file         = "${path.module}/../src/lambda/mcp_servers/athena/lambda_function.py"
  aws_region          = var.aws_region
  timeout             = 60
  memory_size         = 256
  gateway_arn_pattern = local.gateway_arn_pattern

  # Cross-account configuration (uses locals from management-account-role.tf)
  cross_account_enabled     = local.cross_account_enabled
  cross_account_role_arn    = local.management_role_arn
  cross_account_external_id = local.cross_account_external_id

  iam_policy_statements = [
    {
      actions = [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:ListQueryExecutions",
        "athena:StopQueryExecution",
        "athena:BatchGetQueryExecution",
        "athena:ListDatabases",
        "athena:ListTableMetadata",
        "athena:GetTableMetadata",
        "athena:GetDatabase",
        "athena:ListDataCatalogs",
        "athena:GetDataCatalog"
      ]
      resources = ["*"]
    },
    {
      actions = [
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ]
      resources = ["arn:aws:s3:::*"]
    },
    {
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
  ]

  # Security
  subnet_ids                     = var.enable_vpc ? module.vpc[0].private_subnet_ids : []
  security_group_ids             = var.enable_vpc ? [module.vpc[0].lambda_security_group_id] : []
  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions
  log_retention_in_days          = var.log_retention_in_days

  tags = local.common_tags
}

# CUR Analyst MCP Lambda - Strands Agent for CUR data analysis
module "mcp_cur_analyst" {
  source = "./modules/mcp-lambda"

  project_name        = var.project_name
  server_name         = "cur-analyst"
  description         = "CUR Data Analyst Strands Agent for multi-agentic cost analysis"
  source_dir          = "${path.module}/../src/lambda/mcp_servers/cur_analyst"
  aws_region          = var.aws_region
  timeout             = 300 # 5 min for full workflow
  memory_size         = 512
  gateway_arn_pattern = local.gateway_arn_pattern

  # Cross-account configuration (uses locals from management-account-role.tf)
  cross_account_enabled     = local.cross_account_enabled
  cross_account_role_arn    = local.management_role_arn
  cross_account_external_id = local.cross_account_external_id

  # CUR configuration passed via environment variables
  environment_variables = {
    CUR_DATABASE        = var.cur_database_name
    CUR_TABLE           = var.cur_table_name
    CUR_OUTPUT_LOCATION = var.cur_athena_output_location != "" ? var.cur_athena_output_location : "s3://${var.cur_bucket_name}/athena-results/"
    CUR_REGION          = var.aws_region
  }

  iam_policy_statements = [
    # Cost Explorer for API data collection
    {
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
    },
    # Athena permissions for CUR queries
    {
      actions = [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:BatchGetQueryExecution"
      ]
      resources = ["*"]
    },
    # S3 for CUR data and Athena results (uses variable for bucket name)
    {
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetBucketLocation",
        "s3:ListBucket"
      ]
      resources = [
        "arn:aws:s3:::${var.cur_bucket_name}",
        "arn:aws:s3:::${var.cur_bucket_name}/*"
      ]
    },
    # Glue for Athena table metadata
    {
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
  ]

  # Security
  subnet_ids                     = var.enable_vpc ? module.vpc[0].private_subnet_ids : []
  security_group_ids             = var.enable_vpc ? [module.vpc[0].lambda_security_group_id] : []
  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions
  log_retention_in_days          = var.log_retention_in_days

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Module 4: AgentCore Gateway
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

  # MCP Lambda targets
  mcp_lambda_targets = [
    {
      name         = "test-mcp"
      description  = "Simple test MCP tools (hello, echo)"
      lambda_arn   = module.mcp_test.function_arn
      tool_schemas = local.test_tools
    },
    {
      name         = "cost-explorer-mcp"
      description  = "AWS Cost Explorer MCP tools"
      lambda_arn   = module.mcp_cost_explorer.function_arn
      tool_schemas = local.cost_explorer_tools
    },
    {
      name         = "athena-mcp"
      description  = "AWS Athena MCP tools"
      lambda_arn   = module.mcp_athena.function_arn
      tool_schemas = local.athena_tools
    },
    {
      name         = "cur-analyst-mcp"
      description  = "CUR Data Analyst MCP tools (analyze_cur)"
      lambda_arn   = module.mcp_cur_analyst.function_arn
      tool_schemas = local.cur_analyst_tools
    }
  ]

  tags = local.common_tags

  depends_on = [
    module.lambda_proxy,
    module.mcp_test,
    module.mcp_cost_explorer,
    module.mcp_athena,
    module.mcp_cur_analyst
  ]
}
