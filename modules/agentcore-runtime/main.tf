# -----------------------------------------------------------------------------
# AgentCore Runtime - MCP Server Deployment
# Deploys aws-api-mcp-server from AWS Marketplace to AgentCore
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9.0"
    }
  }
}

locals {
  # Runtime name must match ^[a-zA-Z][a-zA-Z0-9_]{0,47}$
  runtime_name = replace("${var.project_name}_mcp_runtime", "-", "_")
}

# Wait for IAM policy propagation before creating runtime
resource "time_sleep" "wait_for_iam" {
  depends_on = [
    aws_iam_role_policy.agentcore_base,
    aws_iam_role_policy_attachment.aws_api_access
  ]

  create_duration = "10s"
}

resource "aws_bedrockagentcore_agent_runtime" "mcp_server" {
  agent_runtime_name = local.runtime_name
  description        = "AWS API MCP Server for ${var.project_name}"

  role_arn = aws_iam_role.runtime.arn

  # Ensure IAM policies are attached and propagated before creating runtime
  depends_on = [time_sleep.wait_for_iam]

  # Container configuration from AWS Marketplace
  agent_runtime_artifact {
    container_configuration {
      container_uri = var.container_uri
    }
  }

  # Network configuration - PUBLIC for MCP access
  network_configuration {
    network_mode = "PUBLIC"
  }

  # MCP Server environment variables
  environment_variables = {
    AUTH_TYPE                   = "no-auth" # AgentCore handles auth externally
    AWS_API_MCP_HOST            = "0.0.0.0"
    AWS_API_MCP_PORT            = "8000"
    AWS_API_MCP_STATELESS_HTTP  = "true"
    AWS_API_MCP_TRANSPORT       = "streamable-http"
    AWS_API_MCP_ALLOWED_HOSTS   = "*"
    AWS_API_MCP_ALLOWED_ORIGINS = "*"
  }

  # Protocol must be MCP for Model Context Protocol
  protocol_configuration {
    server_protocol = "MCP"
  }

  tags = var.tags
}
