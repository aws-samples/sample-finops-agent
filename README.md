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

# 2. Edit configuration files
#    - terraform/config/.env: Set AWS_PROFILE and AWS_REGION
#    - terraform/terraform.tfvars: Set project settings

# 3. Initialize and deploy
make init
make deploy

# 4. Get gateway endpoint
make output
```

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
