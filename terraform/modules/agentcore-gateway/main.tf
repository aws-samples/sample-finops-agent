# -----------------------------------------------------------------------------
# AgentCore Gateway
# Exposes MCP (Model Context Protocol) endpoint for external clients (Claude Code, etc.)
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70.0"
    }
  }
}

resource "aws_bedrockagentcore_gateway" "mcp" {
  name        = "${var.project_name}-gateway"
  description = "MCP Gateway for ${var.project_name}"

  protocol_type   = "MCP"
  authorizer_type = var.auth_type

  role_arn = aws_iam_role.gateway.arn

  # JWT authorizer configuration for Federate authentication
  dynamic "authorizer_configuration" {
    for_each = var.auth_type == "CUSTOM_JWT" ? [1] : []
    content {
      custom_jwt_authorizer {
        discovery_url = var.jwt_discovery_url
        # Nullable — Cognito M2M tokens (client_credentials) have no `aud` claim.
        # When empty, we skip audience validation entirely; auth is enforced via
        # allowed_clients (client_id) + allowed_scopes.
        allowed_audience = length(var.jwt_allowed_audiences) > 0 ? toset(var.jwt_allowed_audiences) : null
        allowed_clients  = length(var.jwt_allowed_clients) > 0 ? toset(var.jwt_allowed_clients) : null
        allowed_scopes   = length(var.jwt_allowed_scopes) > 0 ? toset(var.jwt_allowed_scopes) : null
      }
    }
  }

  tags = var.tags
}

# Gateway Target - AWS API MCP server (from AWS Marketplace), fronted by the
# Lambda proxy which forwards MCP calls to the aws-api-mcp-server container
# running in AgentCore Runtime.
resource "aws_bedrockagentcore_gateway_target" "lambda" {
  name        = "aws-api-mcp"
  description = "AWS API MCP server (Marketplace) — exposes call_aws / suggest_aws_commands"

  gateway_identifier = aws_bedrockagentcore_gateway.mcp.gateway_id

  # Use Gateway's IAM role to invoke Lambda
  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = var.lambda_function_arn

        tool_schema {
          inline_payload {
            name        = "mcp_proxy"
            description = "MCP proxy to AWS API server - supports call_aws and suggest_aws_commands tools"

            input_schema {
              type        = "object"
              description = "MCP JSON-RPC request"
            }
          }
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Dynamic MCP Lambda Targets
# -----------------------------------------------------------------------------

resource "aws_bedrockagentcore_gateway_target" "mcp_lambda" {
  for_each = { for t in var.mcp_lambda_targets : t.name => t }

  name        = each.value.name
  description = each.value.description

  gateway_identifier = aws_bedrockagentcore_gateway.mcp.gateway_id

  # Use Gateway's IAM role to invoke Lambda
  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = each.value.lambda_arn

        tool_schema {
          inline_payload {
            name        = each.value.name
            description = each.value.description

            input_schema {
              type        = "object"
              description = "Tool input parameters"
            }
          }
        }
      }
    }
  }
}
