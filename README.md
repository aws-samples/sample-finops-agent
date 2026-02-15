# AWS FinOps Agent

An MCP-enabled agent for Cloud Financial Management (CFM) that provides secure access to AWS Cost Explorer, Athena CUR 2.0, and AWS APIs. Deploys on Amazon Bedrock AgentCore and integrates with MCP clients like QuickSuite and Claude Code.

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

## Deployment Modes

The gateway supports two deployment modes, configured via `terraform/config/.env`:

- **Cross-account** (recommended): Gateway in a data collection account, CUR data in management/payer account. Set both `TF_VAR_aws_profile` and `TF_VAR_management_account_profile`. Best practice for AWS Organizations setups.
- **Single-account**: Gateway and CUR data in the same account. Set `AWS_PROFILE` only. Suitable for standalone accounts or testing.

Cross-account mode follows AWS best practices by keeping workloads out of the management account. It's the standard pattern for [AWS Cloud Intelligence Dashboards](https://docs.aws.amazon.com/guidance/latest/cloud-intelligence-dashboards/cudos-cid-kpi.html) (CUDOS, CID, KPI):

```
Data Collection Account              Management/Payer Account
┌─────────────────────────┐         ┌─────────────────────────┐
│  CUDOS Dashboard        │         │  IAM Role               │
│  CID Dashboard          │         │  (auto-created)         │
│  KPI Dashboard          │         │                         │
│                         │         │  Cost Explorer API      │
│  AWS FinOps Agent       │────────>│  CUR S3 Bucket          │
│  - cost-explorer-mcp    │ Assume  │  Athena/Glue            │
│  - cur-analyst-mcp      │  Role   │                         │
│  - athena-mcp           │         │                         │
└─────────────────────────┘         └─────────────────────────┘
```

A single `make deploy` creates resources in both accounts. For cross-account, Terraform auto-generates an [External ID](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-user_externalid.html) to secure the assumed role (stored in Terraform state).

## Prerequisites

1. **AWS Marketplace Subscription** - [Subscribe to aws-api-mcp-server](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw) (free, accept terms). For cross-account deployments, subscribe from the **data collection account**.
2. **CUR 2.0 Export** - [Create a Cost and Usage Report 2.0](https://docs.aws.amazon.com/cur/latest/userguide/cur-create.html) export to S3 with Athena integration enabled
3. **Identity Provider (IdP)** - OIDC-compliant IdP for JWT authentication (see [Identity Provider Setup](#identity-provider-setup))
4. **AWS CLI Profiles** - [Named profiles](https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-files.html) configured for target account(s)
5. **Tools** - Terraform >= 1.5.0, [uv](https://docs.astral.sh/uv/), tflint (optional)

## Quick Start

This deploys the AWS FinOps Agent infrastructure:
- AgentCore Gateway with JWT authentication
- Lambda functions (cost-explorer-mcp, athena-mcp, cur-analyst-mcp, lambda-proxy)
- IAM roles and policies (including cross-account role if configured)
- AgentCore Runtime (aws-api-mcp-server container)

**Not included:** QuickSuite requires manual setup after deployment. See [QuickSuite Agent Setup](docs/quicksuite-agent-setup.md).

```bash
# 1. Initial setup (creates config files from examples)
make setup

# 2. Edit configuration files (see Configuration Files section below)
#    - terraform/config/.env: AWS credentials and cross-account settings
#    - terraform/config/terraform.tfvars: CUR database/table names (REQUIRED)

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

**Cross-account mode** (recommended):

```bash
AWS_REGION=us-east-1
AWS_PROFILE=data_collection                    # For Makefile scripts
TF_VAR_aws_profile=data_collection             # Terraform: data collection account
TF_VAR_management_account_profile=root         # Terraform: management/payer account
```

| Variable                            | Description                                                               |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `AWS_PROFILE`                       | AWS CLI profile for Makefile scripts (update-schemas, test-lambdas)       |
| `AWS_REGION`                        | AWS region for deployment                                                 |
| `TF_VAR_aws_profile`                | Terraform provider profile for data collection account                    |
| `TF_VAR_management_account_profile` | Terraform provider profile for management account (enables cross-account) |
| `TF_VAR_n8n_cross_account_id`       | AWS account ID where n8n runs (optional)                                  |

### terraform/config/terraform.tfvars

Terraform variables for project configuration. Created from `terraform.tfvars.example` by `make setup`.

**Required: CUR Configuration**

You must configure these variables to match your CUR 2.0 export settings. Find these values in the AWS Cost and Usage Reports console or your Athena/Glue setup:

```hcl
# CUR (Cost and Usage Report) Configuration - REQUIRED
cur_bucket_name            = "your-cur-bucket"      # S3 bucket with CUR 2.0 data
cur_database_name          = "your_cur_database"    # Glue database name (check Athena)
cur_table_name             = "your_cur_table"       # Glue table name (check Athena)
cur_athena_output_location = ""                     # Optional: S3 path for Athena results
                                                    # Defaults to s3://{cur_bucket}/athena-results/
```

**Other settings:**

```hcl
project_name      = "finops-mcp"           # Prefix for all resources (optional)

# VPC: places Lambdas in a VPC with private subnets and 7 VPC endpoints
# (S3, STS, Logs, Athena, Glue, Cost Explorer, Bedrock AgentCore)
# No NAT Gateway needed — all AWS API traffic goes through VPC endpoints
enable_vpc        = true                   # Default: false
# vpc_cidr        = "10.0.0.0/24"         # Default: "10.0.0.0/24"

# Lambda concurrency and log retention
# lambda_reserved_concurrent_executions = 10   # Default: 10
# log_retention_in_days                 = 365  # Default: 365
```

See [Configuration](docs/configuration.md) for all options.

## Identity Provider Setup

AgentCore Gateway supports three authentication modes: `CUSTOM_JWT`, `AWS_IAM`, or `NONE`. For MCP clients like QuickSuite, you'll need `CUSTOM_JWT` with an OIDC-compliant identity provider.

### QuickSuite OAuth Requirements

QuickSuite connects to AgentCore Gateway using OAuth. You'll need these credentials from your IdP:

| Field             | Description                                 |
| ----------------- | ------------------------------------------- |
| Client ID         | OAuth application identifier                |
| Client Secret     | OAuth application secret                    |
| Token URL         | Endpoint to exchange credentials for tokens |
| Authorization URL | Endpoint for user authorization             |

### Amazon Federate (Internal Example)

1. Go to [Amazon Federate](https://idp.federate.amazon.com) and create a **Service Profile**
2. Configure OAuth grant type (e.g., Client Credentials)
3. Note down Client ID, Client Secret, and Discovery URL
4. Update `terraform/config/terraform.tfvars`:
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

## MCP Client Configuration

After deployment, configure your MCP client (QuickSuite) to connect to the gateway. See [QuickSuite Agent Setup](docs/quicksuite-agent-setup.md) for detailed instructions.

## Available Targets

| Target                         | Description                                       |
| ------------------------------ | ------------------------------------------------- |
| `<project_name>-lambda-target` | AWS CLI execution (forwards to AgentCore Runtime) |
| `cost-explorer-mcp`            | Cost Explorer API (6 tools)                       |
| `athena-mcp`                   | Athena queries (8 tools)                          |
| `cur-analyst-mcp`              | Cost Explorer + Athena CUR 2.0 (1 tool)           |

## Documentation

| Guide                                                    | Description                                          |
| -------------------------------------------------------- | ---------------------------------------------------- |
| [Architecture](docs/architecture.md)                     | Detailed architecture, components, project structure |
| [MCP Tools Reference](docs/mcp-tools-reference.md)       | All 17 MCP tools by target                           |
| [Configuration](docs/configuration.md)                   | tfvars, permissions, make commands                   |
| [Troubleshooting](docs/troubleshooting.md)               | Debugging, logs, common issues                       |
| [n8n Integration](docs/n8n-integration.md)               | Cross-account Lambda for CFM workflows               |
| [QuickSuite Agent Setup](docs/quicksuite-agent-setup.md) | Configure CFM agent in QuickSuite                    |

## Make Commands

| Command               | Description                                           |
| --------------------- | ----------------------------------------------------- |
| `make setup`          | Initial setup - creates config files from examples    |
| `make init`           | Initialize Terraform                                  |
| `make plan`           | Show execution plan (check for drift)                 |
| `make apply`          | Apply changes (with confirmation)                     |
| `make deploy`         | Full deploy: `apply-auto` + `update-schemas`          |
| `make update-schemas` | Update gateway tool schemas (auto-detects gateway ID) |
| `make output`         | Show outputs (gateway endpoint, etc.)                 |
| `make destroy`        | Destroy all resources                                 |

> **Note:** After `make apply`, run `make update-schemas` to update gateway targets with full tool definitions. Or use `make deploy` which does both.

## Cleanup

```bash
make destroy
```
