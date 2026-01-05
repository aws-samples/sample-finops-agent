# n8n Integration - Cross-Account Lambda Invocation

Invoke the `cur-analyst-mcp` Lambda from an n8n workflow running in a different AWS account.

## Architecture

```
n8n Account                             Lambda Account (this deployment)
┌──────────────────────────┐           ┌─────────────────────────────────────┐
│ n8n-lambda-invoker       │           │ <project>-n8n-lambda-invoker Role   │
│ (IAM User)               │──────────▶│                                     │
│                          │           │ Policy: lambda:InvokeFunction       │
└──────────────────────────┘           └────────────────┬────────────────────┘
                                                        ▼
                                       ┌─────────────────────────────────────┐
                                       │ <project>-cur-analyst-mcp Lambda    │
                                       └─────────────────────────────────────┘
```

## Setup

### 1. Configure .env

Add your n8n AWS account ID to `terraform/config/.env`:

```bash
TF_VAR_n8n_cross_account_id=739907928487
```

### 2. Deploy

```bash
make init && make deploy
```

### 3. Get n8n Credentials

```bash
cd terraform
terraform output n8n_role_arn
terraform output -raw n8n_external_id
terraform output n8n_cur_analyst_lambda_arn
```

### 4. Create IAM User in n8n Account

```bash
AWS_PROFILE=dev aws iam create-user --user-name n8n-lambda-invoker

AWS_PROFILE=dev aws iam put-user-policy \
  --user-name n8n-lambda-invoker \
  --policy-name AssumeN8nLambdaInvokerRole \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "<n8n_role_arn>"
    }]
  }'

AWS_PROFILE=dev aws iam create-access-key --user-name n8n-lambda-invoker
```

### 5. Configure n8n

**AWS Credentials** (Settings → Credentials → AWS):

| Field | Value |
|-------|-------|
| Access Key ID | From step 4 |
| Secret Access Key | From step 4 |
| Region | `us-east-1` |
| Role ARN | `terraform output n8n_role_arn` |
| External ID | `terraform output -raw n8n_external_id` |

**AWS Lambda Node**:

| Field | Value |
|-------|-------|
| Function | `terraform output n8n_cur_analyst_lambda_arn` |
| Invocation Type | `Wait for Results` |
| JSON Input | `{}` |

## JSON Input

```json
{}
```
Uses current month vs previous month.

```json
{"report_month": "2024-12", "compare_month": "2024-11"}
```
Specify months explicitly.

## Notes

- Lambda timeout: up to **5 minutes**
- `DataUnavailableException` errors are normal (no Savings Plans/RIs)
- Config file: `terraform/n8n-cross-account.tf`
