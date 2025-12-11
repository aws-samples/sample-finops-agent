# AIOps MCP Gateway Proxy - Terraform Deployment

Deploy an Amazon Bedrock AgentCore Gateway that exposes MCP (Model Context Protocol) endpoints for AI assistants. This gateway integrates with QuickSuite and provides AI tools (like Claude Code) secure access to AWS APIs.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Claude Code   │────▶│    AgentCore    │────▶│  Lambda Proxy   │────▶│   AgentCore     │
│   (MCP Client)  │     │    Gateway      │     │                 │     │   Runtime       │
│                 │◀────│  (Federate JWT) │◀────│                 │◀────│ (MCP Server)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
                              │                                               │
                              │                                               │
                              ▼                                               ▼
                        Authentication                                 AWS APIs
                        (Amazon Federate)                         (ReadOnlyAccess)
```

## Components

| Component | Description |
|-----------|-------------|
| **AgentCore Gateway** | MCP endpoint with Federate JWT authentication, integrates with QuickSuite |
| **Lambda Proxy** | Translates Gateway MCP calls to AgentCore Runtime invocations |
| **AgentCore Runtime** | Hosts aws-api-mcp-server container from AWS Marketplace |

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
# 1. Navigate to terraform directory
cd terraform/

# 2. Run initial setup (creates config files from examples)
make setup

# 3. Edit configuration files
#    - config/.env: Set your AWS_PROFILE and AWS_REGION
#    - terraform.tfvars: Set your project settings and tags

# 4. Initialize Terraform
make init

# 5. Review the execution plan
make plan

# 6. Deploy all resources
make apply

# 7. Get the gateway endpoint for MCP client configuration
make output
```

## Configuration

### config/.env (AWS Credentials for Makefile)

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
| `make destroy` | Destroy all resources |
| `make output` | Show outputs (gateway endpoint, etc.) |
| `make fmt` | Format Terraform files |
| `make validate` | Validate configuration |
| `make lint` | Run tflint checks |

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

After deployment, configure Claude Code with the gateway endpoint:

```json
{
  "mcpServers": {
    "aws-api": {
      "type": "agentcore",
      "gateway_url": "<gateway_endpoint from terraform output>",
      "target_name": "aiops-mcp-gateway-lambda-target"
    }
  }
}
```

### QuickSuite Integration

The AgentCore Gateway is designed to integrate with QuickSuite for enterprise MCP access. Configure QuickSuite with:

- **Gateway URL**: The `gateway_endpoint` output value
- **Target Name**: `<project_name>-lambda-target`
- **Auth Type**: CUSTOM_JWT (Federate)

## Runtime Permissions

By default, the MCP server has `ReadOnlyAccess` to AWS APIs. To change permissions:

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
aiops_mcp_gateway_proxy/
├── .gitignore                 # Git ignore patterns
├── .gitmessage                # Commit message template
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
│       └── proxy/
│           └── lambda_function.py  # Lambda source code
│
└── terraform/
    ├── main.tf                # Module orchestration
    ├── variables.tf           # Input variables
    ├── outputs.tf             # Output values
    ├── versions.tf            # Provider requirements
    ├── Makefile               # Command wrapper
    │
    ├── config/                # Configuration examples
    │   ├── terraform.tfvars.example
    │   ├── .env.example
    │   └── .tflint.hcl
    │
    └── modules/
        ├── agentcore-runtime/ # MCP Server (AWS Marketplace)
        ├── lambda-proxy/      # Lambda function
        └── agentcore-gateway/ # Gateway configuration
```

## Related Resources

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [MCP (Model Context Protocol) Specification](https://modelcontextprotocol.io/)
- [aws-api-mcp-server on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw)
- [QuickSuite Documentation](https://quicksuite.amazon.com)

## License

This project is provided as-is for educational and development purposes.
