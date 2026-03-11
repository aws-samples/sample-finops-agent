# Security

## Overview

The AWS FinOps Agent is an MCP (Model Context Protocol) gateway for Cloud Financial Management (CFM) that accesses AWS Cost Explorer, Amazon Athena, and related services. It deploys on Amazon Bedrock AgentCore. This document describes the security controls, shared responsibilities, and design decisions.

## Shared Responsibility Model

| Responsibility | Project Provides | Deployer Must Configure |
|---------------|-----------------|------------------------|
| **Authentication** | CUSTOM_JWT gateway integration | OIDC identity provider, client credentials |
| **Network** | VPC module with private subnets, VPC endpoints, security groups | Enable VPC (`enable_vpc = true`), review CIDR ranges |
| **Encryption** | KMS variable support for Lambda env vars and CloudWatch Logs | Provide KMS key ARN if required by policy |
| **S3 Security** | IAM policies scoped to CUR bucket | Enable SSE, Block Public Access, versioning, access logging on CUR bucket |
| **IAM** | Least-privilege roles per Lambda function | Review IAM policies for your environment |
| **Monitoring** | CloudWatch Logs (365-day retention), X-Ray tracing | Set up alarms, dashboards, and log analysis |
| **Patching** | Terraform modules with pinned provider versions | Keep Terraform and providers updated |

## Authentication & Authorization

### Gateway Authentication

AgentCore Gateway supports three authentication modes:

- **CUSTOM_JWT** (recommended): Validates JWT tokens from an OIDC-compliant identity provider. Configure `jwt_discovery_url` and `jwt_allowed_audiences` in your tfvars.
- **AWS_IAM**: Uses SigV4 request signing. Suitable for programmatic access from AWS services.
- **NONE**: No authentication. Use only for local testing.

### IAM Role Design

Each component has a dedicated IAM role following least-privilege principles:

| Component | Role | Permissions |
|-----------|------|-------------|
| AgentCore Runtime | `{project}-runtime-role` | ReadOnlyAccess (configurable), X-Ray, CloudWatch Logs |
| Lambda Proxy | `{project}-lambda-role` | InvokeAgentRuntime (scoped to runtime ARN), X-Ray, CloudWatch Logs |
| Cost Explorer MCP | `{project}-cost-explorer-mcp-role` | ce:Get* (4 actions), CloudWatch Logs |
| Athena MCP | `{project}-athena-mcp-role` | athena:* (12 actions), s3:* (scoped to CUR + Athena results buckets), glue:Get* (6 actions), CloudWatch Logs |
| CUR Analyst MCP | `{project}-cur-analyst-mcp-role` | ce:Get* (8 actions), athena:* (4 actions), s3:* (scoped to CUR bucket), glue:Get* (6 actions), CloudWatch Logs |
| Management Account Role | `{project}-management-role` | ce:Get*, athena:*, s3:* (CUR bucket only), glue:Get* |

### Cross-Account Security

Cross-account access uses STS AssumeRole with:
- **External ID**: Auto-generated random value stored in Terraform state, preventing confused deputy attacks
- **Trust Policy**: Restricted to the data collection account ID only
- **Session Duration**: 1-hour maximum

## Encryption

### At Rest

- **Lambda Environment Variables**: Encrypted with AWS managed keys by default. Configure `lambda_kms_key_arn` for customer-managed KMS encryption.
- **CloudWatch Logs**: Optionally encrypted with KMS via `log_group_kms_key_arn` module variable.
- **S3 (CUR Bucket)**: Deployer responsibility. Enable SSE-S3 or SSE-KMS on your CUR bucket.
- **Terraform State**: Contains sensitive values (External ID). Store in an encrypted S3 backend with restricted access.

### Key Management

- Customer-managed KMS keys are optional. If provided via `lambda_kms_key_arn`, the deployer is responsible for key policy configuration, rotation, and access control.
- AWS managed keys (default) handle rotation automatically.
- KMS key ARNs are passed through Terraform variables — review key policies before deployment to ensure they grant appropriate access.

### In Transit

- All AWS API calls use TLS 1.2+.
- When VPC mode is enabled, traffic routes through VPC endpoints (PrivateLink), without traversing the public internet.

## Network Security

### VPC Deployment (Optional)

When `enable_vpc = true`:

- Lambda functions run in **private subnets** with no internet gateway or NAT gateway
- **VPC endpoints** provide private connectivity to AWS services: S3 (gateway), STS, CloudWatch Logs, Athena, AWS Glue, Cost Explorer, Bedrock AgentCore (interface)
- **Security groups** restrict traffic to HTTPS (port 443) only
- **VPC Flow Logs** capture network traffic to CloudWatch Logs
- **Default security group** denies all traffic (per [AWS VPC security guidance](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html))

### Without VPC

Lambda functions use AWS-managed networking. All API calls still use TLS but route through public AWS endpoints.

## IAM Wildcard Resource Justifications

Several IAM policies use `"*"` as the resource. These are AWS service limitations, not design choices:

| Service | Actions | Why `"*"` is Required |
|---------|---------|----------------------|
| AWS Cost Explorer | ce:GetCostAndUsage, ce:GetDimensionValues, ce:GetTags, ce:GetCostForecast, ce:GetSavingsPlansCoverage, ce:GetSavingsPlansUtilization, ce:GetReservationCoverage, ce:GetReservationUtilization | Cost Explorer APIs do not support resource-level permissions ([AWS docs](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awscostexplorerservice.html)) |
| Amazon Athena | athena:StartQueryExecution, athena:GetQueryExecution, athena:GetQueryResults, etc. | Athena APIs do not support resource-level permissions for most read operations |
| AWS Glue | glue:GetDatabase, glue:GetDatabases, glue:GetTable, glue:GetTables, glue:GetPartition, glue:GetPartitions | AWS Glue catalog read APIs do not support resource-level permissions |

S3 permissions for the CUR Analyst Lambda are scoped to the specific CUR bucket ARN (`arn:aws:s3:::{cur_bucket_name}` and `arn:aws:s3:::{cur_bucket_name}/*`).

## AI and Generative AI Security

### Scope of AI Interaction

- The agent provides **read-only financial data analysis**. No AI-generated actions modify AWS resources.
- MCP tools execute predefined AWS API calls (Cost Explorer, Athena queries). There is no arbitrary code execution.
- The CUR Analyst uses Amazon Bedrock with predefined SQL query templates. User-provided parameters (date ranges) are used in safe LIKE clause patterns.

### Input Handling

- Lambda functions validate required parameters before execution.
- Athena queries are executed via the Athena API (not string concatenation into SQL). The API handles query parsing and execution.
- The Athena MCP Lambda validates that SQL queries are read-only (SELECT, SHOW, DESCRIBE) and rejects DDL/DML operations (DROP, DELETE, INSERT, etc.) as defense in depth.
- Cost Explorer parameters (dimensions, dates, granularity) are validated against allowlists before API calls.
- CUR Analyst month parameters are validated against YYYY-MM format via regex.
- Environment variables for database/table names come from Terraform configuration, not user input. They are validated at Lambda cold start for safe identifier patterns.

### Output Handling

- Lambda functions return structured JSON responses with typed fields (amounts, dates, resource IDs).
- Error responses include only the exception message, not stack traces or internal state.
- Cost data responses contain only AWS billing data fields — no customer content or PII is included in outputs.

### Data Classification

- **Cost data**: Non-PII financial data (spend amounts, service names, resource IDs). No customer content or personal data flows through the agent.
- **Data retention**: Data processed by the agent is not used for model training. Amazon Bedrock AgentCore does not retain customer data for training purposes.

### Bias and Fairness

The CFM agent aggregates and presents factual AWS cost data (spend amounts, resource counts, usage metrics). It does not make subjective recommendations, score entities, or rank individuals. Cost allocation follows AWS billing data as-is, with no model-driven weighting or interpretation that could introduce bias.

### Third-Party Components

| Component | Source | Status |
|-----------|--------|--------|
| aws-api-mcp-server | [AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw) | AWS first-party; MIT No Attribution license |
| Amazon Bedrock AgentCore | AWS Service | AWS managed service |
| MCP Lambda functions | This repository | Custom code; see [LICENSE](LICENSE) |

## S3 Security Requirements

The CUR S3 bucket is managed by the deployer. Recommended security configuration:

- **Block Public Access**: Enable all four Block Public Access settings
- **Encryption**: SSE-S3 (default) or SSE-KMS
- **Versioning**: Enable for data protection
- **Access Logging**: Enable server access logging to a separate logging bucket
- **Lifecycle Rules**: Configure based on your data retention requirements
- **TLS Enforcement**: Add a bucket policy requiring `aws:SecureTransport`

## Logging & Monitoring

| Control | Configuration | Default |
|---------|--------------|---------|
| CloudWatch Log Retention | `log_retention_in_days` | 365 days |
| X-Ray Tracing | `xray_tracing_mode` | Active |
| Lambda Concurrency | `lambda_reserved_concurrent_executions` | 10 |
| VPC Flow Logs | Enabled when `enable_vpc = true` | N/A |

## Security Scanning Skip Justifications

### Checkov Skips

| Check | Resource | Justification |
|-------|----------|---------------|
| CKV_AWS_116 (DLQ) | All Lambda functions | Synchronous invocation by AgentCore Gateway. DLQ only applies to async invocations. |
| CKV_AWS_272 (Code Signing) | All Lambda functions | Code packaged from local source via `archive_file`. Code signing requires a CI/CD pipeline with a signing profile. |
| CKV_AWS_111 (IAM write without constraints) | Management account role | Cost Explorer, Athena, and AWS Glue APIs do not support resource-level permissions. Actions are read-only (Get*/List*). |
| CKV_AWS_356 (IAM `"*"` resource) | Management account role | Same as above. AWS service limitation documented in IAM policy comments. |

### Semgrep Skips

| Rule | File | Justification |
|------|------|---------------|
| python.lang.best-practice.arbitrary-sleep | cur_analyst/lambda_function.py | Controlled polling loop for Athena query completion. 5-second interval with 60-iteration max (5-minute timeout). Required because Athena queries are asynchronous. |

## Disclaimer

This project is sample code for demonstration and educational purposes, licensed under MIT No Attribution (see [LICENSE](LICENSE)). It is **not production-ready without review**. Before deploying to production:

1. **IAM**: Review all IAM policies for your security requirements
2. **Network**: Enable VPC mode (`enable_vpc = true`) for network isolation
3. **Encryption**: Configure KMS encryption if required by your organization's policies
4. **S3**: Ensure your CUR S3 bucket follows S3 security best practices (see [S3 Security Requirements](#s3-security-requirements))
5. **State**: Store Terraform state in an encrypted, access-controlled S3 backend
6. **Monitoring**: Implement CloudWatch alarms and log analysis for your deployment
7. **Authentication**: Configure CUSTOM_JWT with your OIDC identity provider (never deploy with `NONE` in production)

## Reporting Security Issues

If you discover a potential security issue, please report it via GitHub Issues or contact the repository maintainers directly. Do not create public issues for active security vulnerabilities.
