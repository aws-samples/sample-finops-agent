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

1. **AWS Marketplace Subscription** - [Subscribe to aws-api-mcp-server](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw) (free, accept terms). For cross-account deployments, subscribe from the **data collection account**.
2. **Identity Provider (IdP)** - OIDC-compliant IdP for JWT authentication (see below)
3. **Tools** - AWS CLI configured, Terraform >= 1.5.0, tflint (optional)

## Identity Provider Setup

AgentCore Gateway supports three authentication modes: `CUSTOM_JWT`, `AWS_IAM`, or `NONE`. For MCP clients like QuickSuite, you'll need `CUSTOM_JWT` with an OIDC-compliant identity provider.

### QuickSuite OAuth Requirements

QuickSuite connects to AgentCore Gateway using OAuth. You'll need these credentials from your IdP:

| Field | Description |
|-------|-------------|
| Client ID | OAuth application identifier |
| Client Secret | OAuth application secret |
| Token URL | Endpoint to exchange credentials for tokens |
| Authorization URL | Endpoint for user authorization |

### Amazon Federate (Internal Example)

1. Go to [Amazon Federate](https://idp.federate.amazon.com) and create a **Service Profile**
2. Configure OAuth grant type (e.g., Client Credentials)
3. Note down Client ID, Client Secret, and Discovery URL
4. Update `terraform.tfvars`:
   ```hcl
   gateway_auth_type     = "CUSTOM_JWT"
   jwt_discovery_url     = "https://idp.federate.amazon.com/.well-known/openid-configuration"
   jwt_allowed_audiences = ["your-service-profile-name"]
   ```

### Other Identity Providers

Any OIDC-compliant IdP works. Update `jwt_discovery_url` and `jwt_allowed_audiences` accordingly:

- **Okta**: `https://{domain}.okta.com/.well-known/openid-configuration`
- **Azure AD**: `https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration`
- **Auth0**: `https://{domain}.auth0.com/.well-known/openid-configuration`

## Quick Start

```bash
# 1. Initial setup (creates config files from examples)
make setup

# 2. Edit configuration files (see Configuration Files section below)
#    - terraform/config/.env: AWS credentials and optional features
#    - terraform/terraform.tfvars: Project settings

# 3. Initialize and deploy
make init
make deploy   # Runs: apply-auto + update-schemas

# 4. Get gateway endpoint
make output
```

## Configuration Files

### terraform/config/.env

Environment variables for the Makefile and Terraform. Created from `.env.example` by `make setup`.

**Single-account mode** (gateway and CUR data in same account):
```bash
AWS_PROFILE=default
AWS_REGION=us-east-1
```

**Cross-account mode** (see [Data Collection Account Deployment](#data-collection-account-deployment)):
```bash
AWS_REGION=us-east-1
AWS_PROFILE=data_collection                    # For Makefile scripts
TF_VAR_aws_profile=data_collection             # Terraform: data collection account
TF_VAR_management_account_profile=root         # Terraform: management/payer account
```

| Variable | Description |
|----------|-------------|
| `AWS_PROFILE` | AWS CLI profile for Makefile scripts (update-schemas, test-lambdas) |
| `AWS_REGION` | AWS region for deployment |
| `TF_VAR_aws_profile` | Terraform provider profile for data collection account |
| `TF_VAR_management_account_profile` | Terraform provider profile for management account (enables cross-account) |
| `TF_VAR_n8n_cross_account_id` | AWS account ID where n8n runs (optional) |

### terraform/terraform.tfvars

Terraform variables for project configuration. See [Configuration](docs/configuration.md) for all options.

## Data Collection Account Deployment

For organizations using the [AWS Cloud Intelligence Dashboards](https://docs.aws.amazon.com/guidance/latest/cloud-intelligence-dashboards/cudos-cid-kpi.html) architecture, deploy the MCP Gateway to your **data collection account** (alongside CUDOS, CID, and KPI dashboards) with cross-account access to Cost Explorer and CUR data in the **management/payer account**.

### Architecture

```
Data Collection Account              Management/Payer Account
┌─────────────────────────┐         ┌─────────────────────────┐
│  CUDOS Dashboard        │         │  IAM Role               │
│  CID Dashboard          │         │  (auto-created)         │
│  KPI Dashboard          │         │                         │
│                         │         │  Cost Explorer API      │
│  MCP Gateway            │────────>│  CUR S3 Bucket          │
│  - cost-explorer-mcp    │ Assume  │  Athena/Glue            │
│  - cur-analyst-mcp      │  Role   │                         │
│  - athena-mcp           │         │                         │
└─────────────────────────┘         └─────────────────────────┘
```

### Why This Architecture?

- **Centralized analytics**: All cost intelligence tools in one account
- **Least privilege**: Gateway only gets read access via assumed role
- **AWS best practice**: Follows Cloud Intelligence Dashboards pattern

### Setup

A single `make deploy` creates resources in both accounts. Just configure two AWS profiles.

**Step 1: Subscribe to AWS Marketplace**

Subscribe to [aws-api-mcp-server](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw) from the **data collection account** (where the gateway will be deployed).

**Step 2: Configure profiles**

Edit `terraform/config/.env`:
```bash
AWS_REGION=us-east-1

# For Makefile scripts (must match data collection account)
AWS_PROFILE=data_collection

# Terraform provider profiles
TF_VAR_aws_profile=data_collection             # Data collection account (gateway deploys here)
TF_VAR_management_account_profile=root         # Management/payer account (CUR data lives here)
```

**Step 3: Configure CUR settings**

Edit `terraform/terraform.tfvars`:
```hcl
cur_bucket_name   = "your-cur-bucket-name"
cur_database_name = "cur_database"
cur_table_name    = "mycostexport"
```

**Step 4: Deploy**

```bash
make init
make deploy
```

This creates:
- IAM role in management account (with auto-generated External ID)
- MCP Gateway + Lambdas in data collection account
- Cross-account access configured automatically

**Step 5: Verify deployment**

```bash
make output
```

### What is External ID?

The External ID is a shared secret that prevents the "confused deputy" attack—where a malicious actor tricks a service into assuming a role it shouldn't. It's auto-generated and stored in Terraform state, so you don't need to manage it manually.

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
| [QuickSuite Agent Setup](docs/quicksuite-agent-setup.md) | Configure CFM agent in QuickSuite |

## Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | Initial setup - creates config files from examples |
| `make init` | Initialize Terraform |
| `make plan` | Show execution plan (check for drift) |
| `make apply` | Apply changes (with confirmation) |
| `make deploy` | Full deploy: `apply-auto` + `update-schemas` |
| `make update-schemas` | Update gateway tool schemas (auto-detects gateway ID) |
| `make output` | Show outputs (gateway endpoint, etc.) |
| `make destroy` | Destroy all resources |

> **Note:** After `make apply`, run `make update-schemas` to update gateway targets with full tool definitions. Or use `make deploy` which does both.

## Cleanup

```bash
make destroy
```
