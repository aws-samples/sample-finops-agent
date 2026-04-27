# Troubleshooting

## Common Issues

### AWS Marketplace Subscription Error

**Error:**
```
Error creating AgentCore Runtime: ECR repository access denied
```

**Solution:** Subscribe to aws-api-mcp-server on AWS Marketplace first:

1. Visit [aws-api-mcp-server on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-lqqkwbcraxsgw)
2. Click **Continue to Subscribe**
3. Accept terms and conditions
4. Wait for subscription to be active (usually instant)

### DataUnavailableException

**Error:**
```
DataUnavailableException: The data you are requesting is not available
```

**Cause:** No Savings Plans or Reserved Instances in account.

**Solution:** This is normal for accounts without SP/RI coverage. The tool will still return other cost data.

## Checking Status

### Lambda Logs

```bash
# Get log group name
make output | grep lambda_log_group

# View recent logs (replace with your function name)
aws logs tail /aws/lambda/finops-mcp-proxy --follow

# View specific Lambda logs
aws logs tail /aws/lambda/finops-mcp-cost-explorer-mcp --follow
aws logs tail /aws/lambda/finops-mcp-athena-mcp --follow
aws logs tail /aws/lambda/finops-mcp-cur-analyst-mcp --follow
```

### Runtime Status

```bash
aws bedrock-agentcore list-agent-runtimes --region us-east-1
```

### Gateway Status

```bash
aws bedrock-agentcore list-gateways --region us-east-1
```

## Testing

### Test Gateway Connectivity

Using AWS CLI (requires SigV4 signing):

```bash
aws bedrock-agentcore invoke-gateway \
  --gateway-identifier <gateway_id> \
  --target-name aws-api-mcp \
  --payload '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Test Lambda Functions Directly

```bash
make test-lambdas
```

Or test individual functions:

```bash
# Test test-mcp
aws lambda invoke \
  --function-name finops-mcp-test-mcp \
  --payload '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  /dev/stdout

# Test cost-explorer-mcp
aws lambda invoke \
  --function-name finops-mcp-cost-explorer-mcp \
  --payload '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_today_date","arguments":{}}}' \
  /dev/stdout
```

## Cleanup

### Destroy All Resources

```bash
# With confirmation
make destroy

# Auto-approve
make destroy-auto
```

### Clean Local Files

```bash
# Remove local Terraform files (keeps config)
make clean

# Remove all including state (with confirmation)
make clean-all
```

## Security Considerations

- **State file**: Keep `terraform.tfstate` secure - it contains resource IDs and configuration
- **External ID**: The n8n external ID (`terraform output -raw n8n_external_id`) is sensitive - treat as a secret
- **Credentials**: Never commit `.env` or `terraform.tfvars` with real credentials to version control
