# AIOps MCP Gateway - Terraform Deployment

Deploy an Amazon Bedrock AgentCore Gateway that exposes MCP (Model Context Protocol) endpoints for AI assistants. This gateway integrates with QuickSuite and provides AI tools (like Claude Code) secure access to AWS APIs.

## Architecture

```
                                    ┌──────────────────────────────────────────────────────────────┐
                                    │                         AWS Cloud                            │
                                    │                                                              │
┌──────────────┐    Federate JWT    │  ┌─────────────┐      ┌──────────────────────────────────┐  │
│  MCP Client  │───────────────────▶│  │  AgentCore  │      │        Gateway Targets           │  │
│              │                    │  │   Gateway   │      │                                  │  │
│ Claude Code  │                    │  │             │─────▶│  ┌────────────────────────┐      │  │
│  QuickSuite  │◀───────────────────│  │   (Router)  │      │  │   Lambda Proxy         │──────┼──┼──▶ AgentCore Runtime
│              │                    │  │             │─────▶│  ├────────────────────────┤      │  │     (aws-api-mcp-server)
└──────────────┘                    │  │             │      │  │   test-mcp             │      │  │
                                    │  │             │─────▶│  ├────────────────────────┤      │  │
                                    │  │             │      │  │   cost-explorer-mcp    │──────┼──┼──▶ Cost Explorer API
                                    │  │             │─────▶│  ├────────────────────────┤      │  │
                                    │  │             │      │  │   athena-mcp           │──────┼──┼──▶ Athena + S3 + Glue
                                    │  │             │─────▶│  ├────────────────────────┤      │  │
                                    │  └─────────────┘      │  │   cur-analyst-mcp      │──────┼──┼──▶ Cost Explorer + Athena
                                    │                       │  └────────────────────────┘      │  │     (CUR 2.0 Analysis)
                                    │                       └──────────────────────────────────┘  │
                                    └──────────────────────────────────────────────────────────────┘
```

## Components

| Component | Description |
|-----------|-------------|
| **AgentCore Gateway** | MCP endpoint with Federate JWT authentication, integrates with QuickSuite |
| **Lambda Proxy** | Translates Gateway MCP calls to AgentCore Runtime invocations |
| **AgentCore Runtime** | Hosts aws-api-mcp-server container from AWS Marketplace |
| **test-mcp Lambda** | Simple test tools (hello, echo) for Gateway verification |
| **cost-explorer-mcp Lambda** | AWS Cost Explorer tools for cost analysis (6 tools) |
| **athena-mcp Lambda** | AWS Athena tools for data lake queries (8 tools) |
| **cur-analyst-mcp Lambda** | CUR 2.0 analysis combining Cost Explorer + Athena (1 tool) |

## Available MCP Tools

### AWS API MCP Server (via Lambda Proxy)
- `call_aws` - Execute AWS CLI commands
- `suggest_aws_commands` - Get AWS CLI command suggestions

### Test MCP (test-mcp)
- `hello` - Returns a greeting message
- `echo` - Echoes back the provided message

### Cost Explorer MCP (cost-explorer-mcp)
- `get_today_date` - Get current date for time period calculations
- `get_dimension_values` - Get available values for a dimension (SERVICE, REGION, etc.)
- `get_tag_values` - Get available values for a tag key
- `get_cost_and_usage` - Retrieve cost and usage data with filtering/grouping
- `get_cost_and_usage_comparisons` - Compare costs between two time periods
- `get_cost_forecast` - Generate cost forecasts

### Athena MCP (athena-mcp)
- `start_query_execution` - Start an Athena SQL query
- `get_query_execution` - Get status and details of a query
- `get_query_results` - Get results of a completed query
- `list_query_executions` - List recent query executions
- `list_databases` - List databases in a data catalog
- `list_tables` - List tables in a database
- `get_table_metadata` - Get detailed table metadata
- `stop_query_execution` - Cancel a running query

### CUR Analyst MCP (cur-analyst-mcp)
- `analyze_cur` - Execute comprehensive CUR 2.0 analysis (combines Cost Explorer API + Athena queries for monthly cost reports)

## Prerequisites

### 1. AWS Marketplace Subscription (Required First)

Before deploying, you must subscribe to the aws-api-mcp-server container on AWS Marketplace:

1. Visit [aws-api-mcp-server on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw)
2. Click **Continue to Subscribe**
3. Accept the terms and conditions
4. Wait for the subscription to be active (usually instant)

> **Note**: The container is free, but standard AWS usage fees apply for Lambda, CloudWatch, etc.

### 2. Amazon Federate Setup (Required for Authentication)

Set up Amazon Federate in nonprod environment for JWT authentication. This enables secure access to the MCP Gateway via QuickSuite and other Federate-integrated clients.

### 3. Tools and Access

- **AWS CLI** configured with appropriate credentials
- **Terraform >= 1.5.0** installed
- **tflint** (optional, for linting): `brew install tflint`
- IAM permissions to create Lambda, IAM roles, and Bedrock AgentCore resources

## Quick Start

```bash
# 1. Run initial setup (creates config files from examples)
make setup

# 2. Edit configuration files
#    - terraform/config/.env: Set your AWS_PROFILE and AWS_REGION
#    - terraform/terraform.tfvars: Set your project settings

# 3. Initialize Terraform
make init

# 4. Review the execution plan
make plan

# 5. Deploy all resources (Terraform + tool schema updates)
make deploy

# 6. Test the MCP Lambdas
make test-lambdas

# 7. Get the gateway endpoint for MCP client configuration
make output
```

## Configuration

### terraform/config/.env (AWS Credentials for Makefile)

```bash
AWS_PROFILE=default
AWS_REGION=us-east-1
```

### terraform.tfvars (Terraform Variables)

```hcl
# Required
project_name = "aiops-mcp-gateway"
aws_region   = "us-east-1"

# MCP Server version from AWS Marketplace
mcp_server_image_version = "1.2.0"

# Lambda settings
lambda_timeout     = 30
lambda_memory_size = 256

# Gateway authentication: CUSTOM_JWT (Federate), AWS_IAM, or NONE
gateway_auth_type = "CUSTOM_JWT"

# Federate JWT Configuration (required when gateway_auth_type = CUSTOM_JWT)
jwt_discovery_url     = "https://idp-integ.federate.amazon.com/.well-known/openid-configuration"
jwt_allowed_audiences = ["mcp-federate-integ-es"]
jwt_allowed_clients   = []  # Empty = allow all clients

# Runtime permissions (what AWS APIs the MCP server can access)
runtime_aws_policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"

# Resource tags
tags = {
  Owner       = "your-alias"
  CostCenter  = "your-cost-center"
  auto-delete = "no"
}
```

## Available Make Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make setup` | Copy example configs and initialize |
| `make init` | Initialize Terraform |
| `make plan` | Show execution plan |
| `make apply` | Apply changes (with confirmation) |
| `make apply-auto` | Apply changes (auto-approve) |
| `make deploy` | Full deploy (apply + update tool schemas) |
| `make update-schemas` | Update Gateway tool schemas (run after apply) |
| `make test-lambdas` | Test all MCP Lambda functions |
| `make destroy` | Destroy all resources |
| `make output` | Show outputs (gateway endpoint, etc.) |
| `make fmt` | Format Terraform files |
| `make validate` | Validate configuration |
| `make lint` | Run tflint checks |

> **Note**: The Terraform AWS provider only supports 1 tool schema per Lambda target. Use `make deploy` or `make update-schemas` after `make apply` to register all tools via the AWS API.

## Outputs

After deployment, run `make output` to get:

- **gateway_endpoint**: MCP endpoint URL for client configuration
- **gateway_id**: AgentCore Gateway identifier
- **runtime_arn**: AgentCore Runtime ARN
- **lambda_function_arn**: Lambda proxy function ARN
- **mcp_client_config**: Example configuration for MCP clients

Example output:
```
gateway_endpoint = "https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
gateway_id = "your-gateway-id"
mcp_client_config = {
  "auth_type" = "CUSTOM_JWT"
  "gateway_endpoint" = "https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
  "target_name" = "aiops-mcp-gateway-lambda-target"
}
```

## MCP Client Configuration

### Claude Code (.mcp.json)

After deployment, configure Claude Code with the gateway endpoint. You can access multiple targets:

```json
{
  "mcpServers": {
    "aws-api": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint from terraform output>",
      "target_name": "aiops-mcp-gateway-lambda-target"
    },
    "aws-cost-explorer": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint from terraform output>",
      "target_name": "cost-explorer-mcp"
    },
    "aws-athena": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint from terraform output>",
      "target_name": "athena-mcp"
    }
  }
}
```

### Available Gateway Targets

| Target Name | Description |
|-------------|-------------|
| `<project_name>-lambda-target` | AWS API MCP server (call_aws, suggest_aws_commands) |
| `test-mcp` | Test tools for Gateway verification |
| `cost-explorer-mcp` | AWS Cost Explorer tools |
| `athena-mcp` | AWS Athena query tools |

### QuickSuite Integration

The AgentCore Gateway is designed to integrate with QuickSuite for enterprise MCP access. Configure QuickSuite with:

- **Gateway URL**: The `gateway_endpoint` output value
- **Target Names**: See table above for available targets
- **Auth Type**: CUSTOM_JWT (Federate)

## Runtime Permissions

By default, the MCP server has `ReadOnlyAccess` to AWS APIs, plus additional write permissions for specific services:

### Included Permissions

| Service | Permissions | Purpose |
|---------|-------------|---------|
| AWS APIs | ReadOnlyAccess | Read access to most AWS services |
| Athena | StartQueryExecution, StopQueryExecution | Execute Athena queries |
| S3 | PutObject, GetBucketLocation | Write Athena query results |

The S3 write permissions are scoped to buckets matching `*-athena-results` and `*-cur-*` patterns.

### Customizing Permissions

```hcl
# For more permissions (use with caution)
runtime_aws_policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"

# For custom permissions, create a policy and use its ARN
runtime_aws_policy_arn = "arn:aws:iam::123456789012:policy/MyCustomPolicy"
```

## Troubleshooting

### AWS Marketplace Subscription Error

If you see an error like:
```
Error creating AgentCore Runtime: ECR repository access denied
```

You need to subscribe to the aws-api-mcp-server on AWS Marketplace first. See Prerequisites section.

### Check Lambda Logs

```bash
# Get log group name
make output | grep lambda_log_group

# View recent logs
aws logs tail /aws/lambda/aiops-mcp-gateway-proxy --follow
```

### Verify Runtime Status

```bash
aws bedrock-agentcore list-agent-runtimes --region us-east-1
```

### Verify Gateway Status

```bash
aws bedrock-agentcore list-gateways --region us-east-1
```

### Test Gateway Connectivity

```bash
# Using the gateway endpoint from outputs (requires SIGV4 signing)
aws bedrock-agentcore invoke-gateway \
  --gateway-identifier <gateway_id> \
  --target-name aiops-mcp-gateway-lambda-target \
  --payload '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Cleanup

```bash
# Destroy all resources (with confirmation)
make destroy

# Or auto-approve
make destroy-auto
```

## Security Considerations

- **Authentication**: CUSTOM_JWT with Amazon Federate for secure user authentication
- **Permissions**: Start with ReadOnlyAccess and only expand as needed
- **Logging**: All Lambda invocations are logged to CloudWatch
- **State file**: Keep `terraform.tfstate` secure - it contains resource IDs and configuration
- **Tags**: Use tags for cost tracking and resource management

## Project Structure

```
aws-api-mcp-gateway/
├── .gitignore                 # Git ignore patterns
├── .gitmessage                # Commit message template
├── Makefile                   # Build commands (run from root)
├── README.md                  # This file
│
├── docs/
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
│           └── athena/
│               └── lambda_function.py  # Athena query tools
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

## Related Resources

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [MCP (Model Context Protocol) Specification](https://modelcontextprotocol.io/)
- [aws-api-mcp-server on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw)
- [QuickSuite Documentation](https://quicksuite.amazon.com)

## License

This project is provided as-is for educational and development purposes.
