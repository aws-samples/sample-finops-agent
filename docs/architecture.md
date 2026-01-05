# Architecture

## Overview

The AIOps MCP Gateway deploys an Amazon Bedrock AgentCore Gateway that exposes MCP (Model Context Protocol) endpoints for AI assistants. This gateway provides MCP clients secure access to AWS APIs through multiple Lambda-based targets.

## Architecture Diagram

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

All Gateway targets are **Lambda functions**. The `lambda-proxy` Lambda forwards requests to the AgentCore Runtime which hosts the aws-api-mcp-server container from AWS Marketplace.

## Components

| Component | Description |
|-----------|-------------|
| **AgentCore Gateway** | MCP endpoint with Federate JWT authentication. Routes requests to Lambda targets. |
| **AgentCore Runtime** | Hosts the aws-api-mcp-server container from AWS Marketplace. Provides `call_aws` and `suggest_aws_commands` tools. |
| **lambda-proxy** | Lambda that forwards MCP requests to AgentCore Runtime. |
| **cost-explorer-mcp** | Lambda implementing MCP protocol for Cost Explorer API (6 tools). |
| **athena-mcp** | Lambda implementing MCP protocol for Athena queries (8 tools). |
| **cur-analyst-mcp** | Lambda implementing MCP protocol for Cost Explorer + Athena CUR 2.0 analysis (1 tool). |
| **test-mcp** | Dummy Lambda for Gateway verification (`hello`, `echo`). |

## Data Flow

1. **Authentication**: MCP client sends request with Federate JWT token to AgentCore Gateway
2. **Routing**: Gateway validates JWT and routes to the specified target based on `target_name`
3. **Execution**: Target Lambda executes the MCP tool and interacts with AWS services
4. **Response**: Results flow back through the Gateway to the MCP client

## Gateway Targets

| Target Name | Purpose |
|-------------|---------|
| `<project_name>-lambda-target` | Forwards to AgentCore Runtime for AWS CLI execution |
| `cost-explorer-mcp` | AWS Cost Explorer API access |
| `athena-mcp` | Athena query execution |
| `cur-analyst-mcp` | Cost Explorer + Athena CUR 2.0 analysis |
| `test-mcp` | Gateway verification (dummy) |

## Project Structure

```
aws-api-mcp-gateway/
├── .gitignore                 # Git ignore patterns
├── .gitmessage                # Commit message template
├── Makefile                   # Build commands (run from root)
├── README.md                  # Quick start guide
│
├── docs/
│   ├── architecture.md        # This file
│   ├── mcp-tools-reference.md # All available MCP tools
│   ├── configuration.md       # Detailed configuration guide
│   ├── troubleshooting.md     # Debugging and common issues
│   ├── n8n-integration.md     # Cross-account n8n setup
│   └── architecture.drawio    # Architecture diagrams
│
├── scripts/
│   └── invoke_lambda.py       # Lambda testing script
│
├── src/
│   └── lambda/
│       ├── proxy/
│       │   └── lambda_function.py  # Lambda proxy source code
│       │
│       └── mcp_servers/            # MCP Lambda servers
│           ├── test/
│           │   └── lambda_function.py  # Test tools (hello, echo)
│           ├── cost_explorer/
│           │   └── lambda_function.py  # Cost Explorer tools
│           ├── athena/
│           │   └── lambda_function.py  # Athena query tools
│           └── cur_analyst/
│               └── lambda_function.py  # CUR analysis tool
│
└── terraform/
    ├── main.tf                # Module orchestration
    ├── variables.tf           # Input variables
    ├── outputs.tf             # Output values
    ├── versions.tf            # Provider requirements
    │
    ├── config/                # Configuration examples
    │   ├── terraform.tfvars.example
    │   ├── .env.example
    │   └── .tflint.hcl
    │
    ├── tool-schemas/          # MCP tool schema definitions
    │   ├── test.json
    │   ├── cost_explorer.json
    │   └── athena.json
    │
    └── modules/
        ├── agentcore-runtime/ # MCP Server (AWS Marketplace)
        ├── lambda-proxy/      # Lambda proxy function
        ├── mcp-lambda/        # Reusable MCP Lambda module
        └── agentcore-gateway/ # Gateway configuration
```

## Security Model

- **Authentication**: CUSTOM_JWT with Amazon Federate validates user identity
- **Authorization**: IAM roles scope what each Lambda can access
- **Least Privilege**: Default ReadOnlyAccess with specific write permissions only where needed
- **Audit**: All Lambda invocations logged to CloudWatch
