# AIOps MCP Gateway

Deploy an Amazon Bedrock AgentCore Gateway that exposes MCP endpoints for AI assistants. Provides MCP clients (Claude Code, QuickSuite) secure access to AWS APIs.

## Architecture

```
┌──────────────┐                 ┌─────────────────────────────────────────────────────────────────────────┐
│  MCP Client  │  Federate JWT   │                              AWS Cloud                                  │
│              │────────────────>│                                                                         │
│ Claude Code  │                 │  ┌─────────────┐       ┌──────────────────────────────────────────────┐ │
│  QuickSuite  │<────────────────│  │  AgentCore  │       │  Lambda Targets                              │ │
│              │                 │  │   Gateway   │       │                                              │ │
└──────────────┘                 │  │             │──────>│  cost-explorer-mcp ───> Cost Explorer API    │ │
                                 │  │             │       │  athena-mcp ──────────> Athena + S3 + Glue   │ │
                                 │  │             │       │  cur-analyst-mcp ─────> Cost Explorer +      │ │
                                 │  │             │       │                         Athena CUR 2.0       │ │
                                 │  │             │       │                                              │ │
                                 │  │             │       │  lambda-proxy ────────────────┐              │ │
                                 │  └─────────────┘       └───────────────────────────────┼──────────────┘ │
                                 │                                                        │                │
                                 │                                                        v                │
                                 │                        ┌──────────────────────────────────────────────┐ │
                                 │                        │  AgentCore Runtime                           │ │
                                 │                        │  (aws-api-mcp-server from AWS Marketplace)   │ │
                                 │                        │                                              │ │
                                 │                        │  Tools: call_aws, suggest_aws_commands       │ │
                                 │                        └──────────────────────────────────────────────┘ │
                                 └─────────────────────────────────────────────────────────────────────────┘
```

All Gateway targets are **Lambda functions**. The `lambda-proxy` Lambda forwards requests to the AgentCore Runtime which hosts the aws-api-mcp-server container.

## Prerequisites

1. **AWS Marketplace Subscription** - [Subscribe to aws-api-mcp-server](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw) (free, accept terms)
2. **Amazon Federate** - Set up in nonprod environment for JWT authentication
3. **Tools** - AWS CLI configured, Terraform >= 1.5.0, tflint (optional)

## Quick Start

```bash
# 1. Initial setup (creates config files from examples)
make setup

# 2. Edit configuration files (see Configuration Files section below)
#    - terraform/config/.env: AWS credentials and optional features
#    - terraform/terraform.tfvars: Project settings

# 3. Initialize and deploy
make init
make deploy

# 4. Get gateway endpoint
make output
```

## Configuration Files

### terraform/config/.env

Environment variables for the Makefile and Terraform. Created from `.env.example` by `make setup`.

```bash
# AWS credentials (required)
AWS_PROFILE=root
AWS_REGION=us-east-1

# n8n Cross-Account Configuration (optional)
# Set this to enable cross-account Lambda invocation from n8n
# See docs/n8n-integration.md for full setup instructions
TF_VAR_n8n_cross_account_id=739907928487
```

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_PROFILE` | Yes | AWS CLI profile to use |
| `AWS_REGION` | Yes | AWS region for deployment |
| `TF_VAR_n8n_cross_account_id` | No | AWS account ID where n8n runs (enables cross-account Lambda invocation) |

### terraform/terraform.tfvars

Terraform variables for project configuration. See [Configuration](docs/configuration.md) for all options.

## MCP Client Configuration

After deployment, configure your MCP client with the gateway endpoint from `make output`:

```json
{
  "mcpServers": {
    "aws-api": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint>",
      "target_name": "<project_name>-lambda-target"
    },
    "aws-cost-explorer": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint>",
      "target_name": "cost-explorer-mcp"
    },
    "aws-athena": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint>",
      "target_name": "athena-mcp"
    },
    "cur-analyst": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint>",
      "target_name": "cur-analyst-mcp"
    }
  }
}
```

## Available Targets

| Target | Description |
|--------|-------------|
| `<project_name>-lambda-target` | AWS CLI execution (forwards to AgentCore Runtime) |
| `cost-explorer-mcp` | Cost Explorer API (6 tools) |
| `athena-mcp` | Athena queries (8 tools) |
| `cur-analyst-mcp` | Cost Explorer + Athena CUR 2.0 (1 tool) |

## Documentation

| Guide | Description |
|-------|-------------|
| [Architecture](docs/architecture.md) | Detailed architecture, components, project structure |
| [MCP Tools Reference](docs/mcp-tools-reference.md) | All 17 MCP tools by target |
| [Configuration](docs/configuration.md) | tfvars, permissions, make commands |
| [Troubleshooting](docs/troubleshooting.md) | Debugging, logs, common issues |
| [n8n Integration](docs/n8n-integration.md) | Cross-account Lambda for CFM workflows |

## Cleanup

```bash
make destroy
```
