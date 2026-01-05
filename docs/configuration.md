# Configuration Guide

## Configuration Files

### terraform/config/.env

AWS credentials and region for Makefile commands.

```bash
AWS_PROFILE=default
AWS_REGION=us-east-1
```

### terraform/terraform.tfvars

Main Terraform configuration.

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

## Authentication Options

### CUSTOM_JWT (Federate) - Recommended

Uses Amazon Federate for JWT-based authentication.

```hcl
gateway_auth_type     = "CUSTOM_JWT"
jwt_discovery_url     = "https://idp-integ.federate.amazon.com/.well-known/openid-configuration"
jwt_allowed_audiences = ["mcp-federate-integ-es"]
```

### AWS_IAM

Uses AWS IAM for authentication (SigV4 signing).

```hcl
gateway_auth_type = "AWS_IAM"
```

### NONE

No authentication (use only for testing).

```hcl
gateway_auth_type = "NONE"
```

## Runtime Permissions

By default, the MCP server has `ReadOnlyAccess` plus write permissions for specific services.

### Default Permissions

| Service | Permissions | Purpose |
|---------|-------------|---------|
| AWS APIs | ReadOnlyAccess | Read access to most AWS services |
| Athena | StartQueryExecution, StopQueryExecution | Execute Athena queries |
| S3 | PutObject, GetBucketLocation | Write Athena query results |

S3 write permissions are scoped to buckets matching `*-athena-results` and `*-cur-*` patterns.

### Customizing Permissions

```hcl
# More permissions (use with caution)
runtime_aws_policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"

# Custom policy
runtime_aws_policy_arn = "arn:aws:iam::123456789012:policy/MyCustomPolicy"
```

## Make Commands

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
| `make check` | Run formatting, validation, and linting |

## Outputs

After deployment, run `make output` to get:

| Output | Description |
|--------|-------------|
| `gateway_endpoint` | MCP endpoint URL for client configuration |
| `gateway_id` | AgentCore Gateway identifier |
| `runtime_arn` | AgentCore Runtime ARN |
| `lambda_function_arn` | Lambda proxy function ARN |
| `mcp_client_config` | Example configuration for MCP clients |

Example:

```
gateway_endpoint = "https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
gateway_id = "your-gateway-id"
mcp_client_config = {
  "auth_type" = "CUSTOM_JWT"
  "gateway_endpoint" = "https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
  "target_name" = "aiops-mcp-gateway-lambda-target"
}
```

## n8n Cross-Account Setup

To enable n8n workflows from another AWS account to invoke the cur-analyst Lambda:

Add to `terraform/config/.env`:

```bash
TF_VAR_n8n_cross_account_id=123456789012
```

See [n8n Integration Guide](n8n-integration.md) for complete setup instructions.
