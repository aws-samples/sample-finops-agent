# Configuration Guide

## Configuration Files

### terraform/config/.env

AWS credentials and region for Makefile commands.

```bash
AWS_PROFILE=default
AWS_REGION=us-east-1
```

### terraform/config/terraform.tfvars

Main Terraform configuration. Created from `terraform.tfvars.example` by `make setup`.

#### CUR Configuration (Required)

You **must** configure these variables to match your CUR 2.0 export. Find these values in the [AWS Glue Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html) or Athena console.

> **S3 Security**: Your CUR S3 bucket should have Block Public Access enabled, server-side encryption (SSE-S3 or SSE-KMS), versioning, and a bucket policy requiring TLS (`aws:SecureTransport`). See [SECURITY.md](../SECURITY.md#s3-security-requirements) for details.

```hcl
# CUR (Cost and Usage Report) Configuration
cur_bucket_name            = "your-cur-bucket"      # S3 bucket containing CUR data
cur_database_name          = "your_cur_database"    # AWS Glue/Athena database name
cur_table_name             = "your_cur_table"       # AWS Glue/Athena table name
cur_athena_output_location = ""                     # Optional: custom S3 path for Athena results
                                                    # Defaults to s3://{cur_bucket}/athena-results/
```

To find your CUR database and table names:
1. Go to AWS Console → Athena → Query Editor
2. In the left panel, look under "Data" → "AwsDataCatalog"
3. Find the database (often named like `athenacurcfn_your_report_name`)
4. The table is typically named after your CUR export

#### Other Settings

```hcl
# Project settings
project_name = "finops-mcp"
aws_region   = "us-east-1"

# MCP Server version from AWS Marketplace
mcp_server_image_version = "1.2.0"

# Lambda settings
lambda_timeout     = 30
lambda_memory_size = 256

# Gateway authentication: CUSTOM_JWT (Federate), AWS_IAM, or NONE
gateway_auth_type = "CUSTOM_JWT"

# JWT Configuration (required when gateway_auth_type = CUSTOM_JWT)
jwt_discovery_url     = "https://your-idp.example.com/.well-known/openid-configuration"
jwt_allowed_audiences = ["your-audience-id"]
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

### CUSTOM_JWT - Recommended

Uses an OIDC-compliant identity provider for JWT-based authentication.

```hcl
gateway_auth_type     = "CUSTOM_JWT"
jwt_discovery_url     = "https://your-idp.example.com/.well-known/openid-configuration"
jwt_allowed_audiences = ["your-audience-id"]
```

### AWS_IAM

Uses AWS IAM for authentication (SigV4 signing).

```hcl
gateway_auth_type = "AWS_IAM"
```

### NONE

No authentication. **Do not use in production** — this exposes the gateway to unauthenticated access.

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
  "target_name" = "finops-mcp-lambda-target"
}
```

## n8n Cross-Account Setup

To enable n8n workflows from another AWS account to invoke the cur-analyst Lambda:

Add to `terraform/config/.env`:

```bash
TF_VAR_n8n_cross_account_id=123456789012
```

See [n8n Integration Guide](n8n-integration.md) for complete setup instructions.
