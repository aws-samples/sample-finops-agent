# Architecture

## Overview

The FinOps MCP Gateway deploys an Amazon Bedrock AgentCore Gateway that exposes MCP (Model Context Protocol) endpoints for Cloud Financial Management (CFM). This gateway provides MCP clients secure access to AWS APIs through multiple AWS Lambda-based targets. It integrates with Amazon Athena, AWS Cost Explorer, AWS Glue, Amazon S3, and Amazon CloudWatch.

## Architecture Diagram

```
┌──────────────┐                 ┌─────────────────────────────────────────────────────────────────────────┐
│  MCP Client  │  Federate JWT   │                              AWS Cloud                                  │
│              │────────────────>│                                                                         │
│  QuickSuite  │                 │  ┌─────────────┐       ┌──────────────────────────────────────────────┐ │
│              │<────────────────│  │  AgentCore  │       │  Lambda Targets                              │ │
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
aws-finops-mcp-gateway/
├── .gitignore                 # Git ignore patterns
├── .gitmessage                # Commit message template
├── CLAUDE.md                  # Project knowledge base
├── Makefile                   # Build commands (run from root)
├── README.md                  # Quick start guide
│
├── docs/
│   ├── architecture.md           # This file
│   ├── configuration.md          # Detailed configuration guide
│   ├── mcp-tools-reference.md    # All available MCP tools
│   ├── n8n-integration.md        # Cross-account n8n setup
│   ├── quicksuite-agent-setup.md # Configure CFM agent in QuickSuite
│   └── troubleshooting.md        # Debugging and common issues
│
├── prompts/
│   └── cur_analysis_report.md # CFM report generation prompt
│
├── scripts/
│   ├── invoke_lambda.py       # Lambda testing script
│   ├── test_cur_analyst.py    # CUR analyst testing
│   ├── test_mcp_lambdas.py    # MCP Lambda testing
│   └── update_tool_schemas.py # Update gateway tool schemas
│
├── src/
│   └── lambda/
│       ├── proxy/
│       │   └── lambda_function.py     # Lambda proxy source code
│       │
│       └── mcp_servers/               # MCP Lambda servers
│           ├── shared/
│           │   ├── __init__.py
│           │   └── cross_account.py   # Cross-account utilities
│           ├── test/
│           │   └── lambda_function.py # Test tools (hello, echo)
│           ├── cost_explorer/
│           │   └── lambda_function.py # Cost Explorer tools
│           ├── athena/
│           │   └── lambda_function.py # Athena query tools
│           └── cur_analyst/
│               └── lambda_function.py # CUR analysis tool
│
└── terraform/
    ├── main.tf                    # Module orchestration
    ├── variables.tf               # Input variables
    ├── outputs.tf                 # Output values
    ├── versions.tf                # Provider requirements
    ├── management-account-role.tf # Cross-account IAM role
    ├── n8n-cross-account.tf       # n8n integration resources
    │
    ├── config/                    # Configuration files
    │   ├── .env.example
    │   ├── .env                   # Your AWS credentials (gitignored)
    │   ├── terraform.tfvars.example
    │   ├── terraform.tfvars       # Your project settings (gitignored)
    │   └── .tflint.hcl
    │
    ├── tool-schemas/              # MCP tool schema definitions
    │   ├── test.json
    │   ├── cost_explorer.json
    │   ├── athena.json
    │   └── cur_analyst.json
    │
    └── modules/
        ├── agentcore-gateway/     # Gateway configuration
        ├── agentcore-runtime/     # MCP Server (AWS Marketplace)
        ├── lambda-proxy/          # Lambda proxy function
        └── mcp-lambda/            # Reusable MCP Lambda module
```

## Security Model

For full security documentation, see [SECURITY.md](../SECURITY.md).

### Authentication & Authorization

- **Authentication**: CUSTOM_JWT with an OIDC-compliant identity provider validates user identity via JWT tokens at the AgentCore Gateway
- **Authorization**: Each Lambda function has a dedicated IAM role scoped to only the AWS services it needs
- **Least Privilege**: AgentCore Runtime uses ReadOnlyAccess by default; write permissions are granted only where required (Athena query results to S3)
- **Cross-Account**: STS AssumeRole with auto-generated External ID secures cross-account access to management account resources

### Network Security

- **VPC Deployment** (optional): Lambda functions run in private subnets with no internet access. All AWS API traffic routes through VPC endpoints (S3, STS, CloudWatch Logs, Athena, Glue, Cost Explorer, Bedrock AgentCore)
- **Security Groups**: Restrict traffic to HTTPS (port 443) only, limited to VPC endpoint communication

### Data Protection

- **Encryption in Transit**: All AWS API calls use TLS. VPC endpoints enforce private connectivity when VPC mode is enabled
- **Encryption at Rest**: Optional KMS encryption for Lambda environment variables and CloudWatch Log Groups. S3 buckets should use SSE-S3 or SSE-KMS (deployer responsibility)

### Monitoring & Audit

- **CloudWatch Logs**: All Lambda invocations logged with 365-day retention (configurable)
- **AWS X-Ray**: Active tracing enabled by default for end-to-end request tracing
- **Concurrency Limits**: Lambda functions have reserved concurrent execution limits (default: 10) to prevent runaway invocations

### Threat Considerations

| Threat | Mitigation |
|--------|------------|
| Unauthenticated access | JWT validation at AgentCore Gateway; AWS_IAM (SigV4) as alternative |
| Privilege escalation | Dedicated IAM roles per Lambda; no admin permissions; read-only by default |
| Data exfiltration | VPC with no internet egress (when enabled); S3 access scoped to CUR bucket |
| Cross-account abuse | External ID on AssumeRole; role trust policy restricted to specific account |
| Excessive invocations | Reserved concurrency limits on all Lambda functions |
