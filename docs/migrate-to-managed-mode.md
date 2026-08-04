# Migrating an Existing Deployment to Managed Mode

This guide upgrades a deployment that proxies to the **AgentCore Runtime**
(`aws-api-mcp-server` container) so it uses the **managed AWS MCP Server**
instead, and optionally gains cross-account resource queries.

Why migrate: the `aws-api-mcp-server` container entered end-of-development on
2026-07-15 (removal 2027-07-15, [awslabs/mcp#4115](https://github.com/awslabs/mcp/issues/4115))
and its Marketplace listing is closed to new subscriptions. Managed mode needs
no container, no subscription, and no per-account runtime.

## What changes, and what doesn't

| Unchanged | Changed |
| --------- | ------- |
| Gateway ID and MCP endpoint URL | `aws-api-mcp` target's tools |
| Cognito user pool, `client_id` / `client_secret` / `token_url` | `call_aws` → `run_script` |
| `cost-explorer-mcp` and `athena-mcp` targets and their 14 tools | `suggest_aws_commands` → `list_member_accounts` |
| CUR export, Athena table, Glue catalog | Proxy execution role becomes a pure pipe |
| The `aws-api-mcp` target name | Read access moves to a per-account `finops-readonly` role |
| | Documentation and skill tools become available |

The Gateway endpoint and Cognito credentials are unchanged, so the connector's
settings carry over — but the connector's cached tool list **must be refreshed**
to pick up the new tools (step 4).

The AgentCore Runtime is **not** removed, which is what keeps
[rollback](#rollback) to a single variable. It sits idle: Runtime billing is
based on active CPU and memory consumption, so an unused Runtime is not a
recurring cost.

Note the two separate upstream timelines. The self-hosted
`aws-api-mcp-server` container is removed **2027-07-15**, which is what makes
legacy mode a dead end. Independently, the managed server's own `call_aws` tool
is removed **2026-08-31**; managed mode already uses `run_script` instead, so
that date only matters if a client is still pinned to the old tool name.

`lambda-proxy` is not placed in a VPC in this sample, so it reaches the managed
endpoint over the public internet with TLS and SigV4. Requirements here vary too
much between organizations to pick a default. If yours needs private egress, add
`subnet_ids` / `security_group_ids` to the proxy along with a NAT path; AWS has
stated that VPC endpoint support for managed MCP servers is planned but not yet
available, so a VPC alone does not keep this traffic off the internet today.

## How access is restricted

The member role's trust policy names the payer account as `Principal` and then
restricts assumption to the proxy's execution role:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<PAYER_ACCOUNT_ID>:root" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "ArnEquals": {
      "aws:PrincipalArn": "arn:aws:iam::<PAYER_ACCOUNT_ID>:role/<PROXY_ROLE_NAME>"
    }
  }
}
```

`Principal` names the account rather than the role, and the role is matched in a
condition instead. Both express the same restriction, but a role ARN in
`Principal` is resolved to a hidden unique ID when the policy is saved: the role
must already exist when the template is deployed, and the policy breaks silently
if that role is ever deleted and recreated. A condition ARN is compared as a
string, so member accounts can be provisioned before the Gateway account and
survive a proxy rebuild.

`aws:PrincipalArn` resolves to the *role* ARN, not the session ARN, so it matches
regardless of the session name the proxy uses.

There is no shared secret to distribute. If a third party operates the Gateway
account and an `sts:ExternalId` condition is also wanted, set
`member_role_external_id` and pass the template's `ExternalId` parameter; it
layers on top of the principal restriction.

## Prerequisites

- An existing deployment created by this repo, with `make output` working
- Terraform state you can apply against
- Permission to create IAM roles in the Gateway account
- Permission to administer the MCP client connector, since its tool list has to
  be refreshed (see step 4)
- For cross-account queries, additionally:
  - Permission to create IAM roles in each member account, and a way to deploy
    CloudFormation there (StackSet, or the organization's own CI/CD)
  - `list_member_accounts` calls `organizations:ListAccounts`, which AWS allows
    only from the organization's management account or a delegated
    administrator. Elsewhere that tool fails, but `run_script` still works when
    given a 12-digit account ID directly.

## Step 1 — Enable managed mode

Add to `terraform/config/terraform.tfvars`:

```hcl
aws_mcp_endpoint = "https://aws-mcp.us-east-1.api.aws/mcp"
member_role_name = "finops-readonly"  # optional, this is the default
lambda_timeout   = 120                # required: see note below
```

`lambda_timeout` matters. Multi-region inventory scripts routinely exceed the
30s default; a sweep across all enabled regions will time out mid-run and the
agent will report partial results.

There is no shared secret to configure — see
[How access is restricted](#how-access-is-restricted).

**Then check the tool schema.** `terraform/tool-schemas/aws_api_mcp.json` is what
the Gateway advertises, and it is a separate file from the variable above. It has
to describe the managed-mode tools:

```bash
python3 -c "import json; print([t['name'] for t in json.load(open('terraform/tool-schemas/aws_api_mcp.json'))])"
```

Expect `['run_script', 'list_member_accounts', 'get_aws_skill',
'search_documentation', 'read_documentation']`. If you instead see `call_aws` and
`suggest_aws_commands`, the file is still the legacy version — check out the
managed-mode one before deploying, or the next step will re-register the legacy
tools against a proxy that no longer serves them.

The variable and the schema file move together in both directions. This is the
same pairing that [Rollback](#rollback) reverses.

## Step 2 — Deploy the Gateway changes

```bash
make deploy
```

Use `make deploy`, not `make apply`. Only `deploy` runs
`scripts/update_tool_schemas.py` afterwards, which registers the full tool list
from the schema files. After a bare `apply` each Gateway target carries only a
single placeholder tool.

Then confirm the Gateway actually advertises the managed tools:

```bash
aws bedrock-agentcore-control get-gateway-target \
  --gateway-identifier $(terraform -chdir=terraform output -raw gateway_id) \
  --target-id <aws-api-mcp-target-id> \
  --query 'targetConfiguration.mcp.lambda.toolSchema.inlinePayload[].name' \
  --output text --region <region> --profile <gateway-account-profile>
```

Get the target ID from `terraform output mcp_target_ids`, or from the Gateway's
Targets list in the console.

If this still prints `call_aws suggest_aws_commands`, the schema file was the
legacy version when you deployed. Fix the file as described in step 1 and re-run
`make deploy`. The proxy will already be serving `run_script` at this point, so
until the two agree every tool call fails — and it fails in the confusing way,
with the client believing a tool exists that the Lambda will reject.

Otherwise expect: the proxy's environment and IAM policy updated, and the
`aws-api-mcp` target's schema replaced. Nothing should be destroyed. The
`finops-readonly` role is not created here — that is step 3.

## Step 3 — Create the finops-readonly role in every account

The proxy assumes this role for **every** query, so the Gateway's own account
needs it too, not just member accounts. One template covers both; deploy it once
per account.

**Decide `PermissionsMode` before deploying.** It controls what the role may
read, and choosing now is easier than changing later:

| Mode | Grant |
| ---- | ----- |
| `ReadOnly` (default) | AWS managed `ReadOnlyAccess`. Every service works, including ones AWS adds later — but its read actions also return stored data: S3 object contents, DynamoDB items, decrypted SSM parameters, log events. |
| `InventoryOnly` | A scoped policy created in the same stack. Resource configuration, tags and cost data only; reads that return stored data are explicitly denied. Queries about services outside the policy fail until it is extended. |

`InventoryOnly` is the tighter grant and the better fit when the agent's job is
inventory and cost analysis. Omitting the parameter gives you `ReadOnly`. Use the
same value in every account, so the agent sees one consistent permission model
instead of succeeding in one account and failing in another. Either choice can be
changed afterwards — see [Changing the grant later](#changing-the-grant-later).

First read the proxy's role name — the only principal the role will trust:

```bash
terraform -chdir=terraform output -raw proxy_role_name
```

Then deploy [`examples/member-finops-readonly-role.yaml`](../examples/member-finops-readonly-role.yaml),
starting with the Gateway account itself:

```bash
aws cloudformation deploy \
  --template-file examples/member-finops-readonly-role.yaml \
  --stack-name finops-readonly \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      PayerAccountId=<gateway-account-id> \
      ProxyRoleName=<proxy-role-name> \
      PermissionsMode=InventoryOnly \
  --region <region> --profile <gateway-account-profile>
```

Then repeat for each member account you want to query, changing only the
`--profile`. Keep `--region` the same: the role is global, but CloudFormation
needs a region for the stack itself, and using one region everywhere keeps the
stacks easy to find. `PayerAccountId` stays the Gateway account in every case —
it is the account being trusted, not the account being deployed to. Because the
parameters are identical everywhere, the same template and parameter set works
as a CloudFormation StackSet across the organization or an OU.

If a `finops-readonly` role already exists in an account — from an earlier pilot,
or from a version of this repo that created it in Terraform — **check the logical
ID of the stack that owns it** before deploying:

```bash
aws cloudformation describe-stack-resources --stack-name <existing-stack> \
  --query 'StackResources[].LogicalResourceId' --output text \
  --region <region> --profile <profile>
```

This template uses `FinOpsReadOnlyRole`. If the existing stack used a different
logical ID, deploying this template makes CloudFormation try to create a *second*
role with the same name, which fails with `finops-readonly already exists in
stack …` and rolls back. Delete the old stack first, or update the existing
role's trust policy in place with `aws iam update-assume-role-policy`.

If the role exists but no stack owns it — Terraform managed it in an earlier
version of this repo — drop it from Terraform state before deploying, so
Terraform stops trying to manage it and CloudFormation can take over:

```bash
terraform -chdir=terraform state rm 'aws_iam_role.finops_readonly[0]'
terraform -chdir=terraform state rm 'aws_iam_role_policy_attachment.finops_readonly[0]'
```

`state rm` only stops Terraform tracking the resource; it does not delete the
role. Then delete the role itself so the template can recreate it under
CloudFormation management:

```bash
aws iam detach-role-policy --role-name finops-readonly \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess --profile <profile>
aws iam delete-role --role-name finops-readonly --profile <profile>
```

Accounts without the role are not silently skipped: queries against them fail
with a message naming the missing role, so the agent reports the gap instead of
returning partial data.

### Confirm every account matches

Once the role exists everywhere, check that the grant is identical across
accounts. It is easy to deploy to one account, adjust the parameters, and forget
to re-run the others:

```bash
for p in <profile-1> <profile-2>; do
  printf "%-16s " "$p"
  aws iam list-attached-role-policies --role-name finops-readonly \
    --profile "$p" --region <region> \
    --query 'AttachedPolicies[].PolicyName' --output text
done
```

Every line must show the same policy — `ReadOnlyAccess` or
`finops-readonly-inventory`, not a mix. A mismatch means the same question
succeeds against one account and is denied against another, which reads like a
broken agent rather than a policy decision.

### What InventoryOnly actually denies

The scoped policy allows `Describe*` / `List*` for services whose read APIs only
return configuration, then explicitly denies the reads that return content:
`s3:GetObject*`, `dynamodb:Scan` / `Query` / `GetItem`,
`ec2:DescribeInstanceAttribute` (instance user data), `logs:GetLogEvents`,
`lambda:GetFunctionConfiguration` (environment variables), and the EC2
console-output APIs. An explicit `Deny` cannot be overridden by the wildcard
`Allow`, so adding a broad `Describe*` later does not reopen these.

Tags and resource metadata are unaffected — EC2 tags, for instance, arrive inside
`DescribeInstances`, not through the denied per-attribute call.

To cover a service the policy does not mention, add its `Describe*` / `List*` to
the `InventoryAndCostMetadata` statement in the template and redeploy.

### Changing the grant later

Redeploy the same stack with the other value:

```bash
aws cloudformation deploy \
  --template-file examples/member-finops-readonly-role.yaml \
  --stack-name finops-readonly \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      PayerAccountId=<gateway-account-id> \
      ProxyRoleName=<proxy-role-name> \
      PermissionsMode=ReadOnly \
  --region <region> --profile <profile>
```

CloudFormation swaps the policy attachment and, when moving back to `ReadOnly`,
deletes the scoped policy it created. The role keeps its name, ARN and trust
policy, so nothing on the client side needs reconfiguring.

Repeat for every account, or the agent will succeed in one and fail in another
for reasons that are hard to see from the outside.

CloudFormation reuses a stack's previous parameter values when you omit them, so
an update that does not mention `PermissionsMode` keeps whatever the stack was
last deployed with — it will not silently revert to `ReadOnly`.

The Gateway account's own role uses the same template and the same
`PermissionsMode` value — it is not special. Deploy it there first, then to each
member account.

## Step 4 — Refresh the MCP client's tool list

**This step is required and easy to miss.** MCP clients cache the `tools/list`
response from the moment the connector was configured. After migrating, a stale
client keeps calling `call_aws`, the Gateway rejects it, and the model quietly
falls back to other tools — so the agent looks like it is working while all AWS
API access is dead.

In QuickSuite, open the connector and choose **Sync**. That re-runs discovery and
picks up the new tool list in place; the connector's endpoint and credentials are
untouched.

**Sync only discovers the tools — it does not enable them.** Every managed-mode
tool is a new name that inherits no prior approval, so all five have to be
enabled by hand:

- `run_script`
- `list_member_accounts`
- `get_aws_skill`
- `search_documentation`
- `read_documentation`

Then check the count, because a tool left disabled fails silently — the model
simply never calls it:

```bash
# what the Gateway offers
aws bedrock-agentcore-control get-gateway-target \
  --gateway-identifier $(terraform -chdir=terraform output -raw gateway_id) \
  --target-id <aws-api-mcp-target-id> \
  --query 'length(targetConfiguration.mcp.lambda.toolSchema.inlinePayload)' \
  --output text --region <region> --profile <gateway-account-profile>

# what the connector has enabled
aws quicksight describe-action-connector \
  --aws-account-id <gateway-account-id> \
  --action-connector-id <connector-id> \
  --query 'length(ActionConnector.EnabledActions)' \
  --output text --region <region> --profile <gateway-account-profile>
```

The second number counts every target's tools, not just `aws-api-mcp`, so compare
it against the total across all four targets. With the stock deployment that is
5 + 6 + 8 + 2 = 21. Fewer means something is still disabled; find it in the
connector's tool list rather than guessing.

Get the connector ID from `aws quicksight list-action-connectors`.

Deleting and recreating the connector also works, and is the documented fallback
if Sync is unavailable in your version. Recreating means re-entering the same
endpoint and credentials, which are unchanged:

```bash
make show-cognito-creds
```

Note that the QuickSuite documentation currently states that tool lists are
static after registration and that the integration must be recreated. Sync was
observed to update the tool list without recreating, so try it first.

## Step 5 — Verify

Drive the agent first, then read the logs — the log filter below matches nothing
until a query has actually been made.

Ask these from the MCP client, in order. Each one exercises a different part of
what changed:

| Ask | Exercises | If it fails |
| --- | --------- | ----------- |
| "Which accounts are in my organization?" | `list_member_accounts` | The tool is disabled in the connector (step 4), or this is not the organization's management account (see Prerequisites) |
| "List EC2 instances in this account" | `run_script` with no `account_id` | The role is missing in the Gateway account (step 3) |
| "List EC2 instances and tags in account `<member-id>`" | The cross-account path | The role is missing in that member account, or its condition names the wrong proxy role (step 3) |
| Any cost question | `cost-explorer-mcp` still intact | Re-run `make deploy` (step 2) |

The strongest check on the cross-account query is that it returns *different*
resources than the same question asked without an account ID. Matching output
usually means the account ID was dropped and the query ran locally.

Now confirm the proxy took the managed path:

```bash
aws logs tail /aws/lambda/finops-mcp-proxy --since 15m \
  --region <region> --profile <gateway-account-profile> --filter-pattern "Managed"
```

Expect a line per call, such as `Managed mode tool: run_script`. If you see
`Invoking runtime:` instead, the client is still on its cached tool list — return
to step 4. If there is no output at all, no request reached the Lambda: the
connector is likely waiting on an approval prompt in the client, so check there
before assuming the deployment is broken.

The function name above assumes the default `project_name` of `finops-mcp`;
substitute your own if it differs.

Finally, confirm a cross-account call really executed in the member account by
checking that account's CloudTrail for the proxy's role session name, which is
always `finops-mcp-proxy` regardless of `project_name`:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=finops-mcp-proxy \
  --max-results 5 --region <region> --profile <member-account-profile>
```

CloudTrail lags by several minutes, so an empty result here right after a query
is not a failure — the successful response in the client is the stronger signal.

## Rollback

The Runtime is still deployed, so rolling back is a configuration change rather
than a redeployment. Two things have to move together.

Unset the endpoint in `terraform.tfvars`:

```hcl
aws_mcp_endpoint = ""
```

Then restore the legacy tool schema. `terraform/tool-schemas/aws_api_mcp.json`
describes the tools the Gateway advertises, and managed mode replaced its
contents. Unsetting the endpoint alone leaves the Gateway advertising
`run_script` while the proxy only serves `call_aws` — every call then fails.
Recover the legacy version from git:

```bash
git show <pre-migration-ref>:terraform/tool-schemas/aws_api_mcp.json \
  > terraform/tool-schemas/aws_api_mcp.json
```

The legacy file declares `call_aws` and `suggest_aws_commands`. Confirm that
before deploying:

```bash
make deploy
```

Then refresh the connector's tool list again (step 4) so the client picks up
`call_aws`.

The `finops-readonly` roles can stay — they are inert in legacy mode, since the
proxy signs with its own execution role there. Leaving them in place makes a
second migration a configuration change only.

## Troubleshooting

Every failure below is silent — the error text does not identify which step was
missed.

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| Agent reports a missing read permission (e.g. `ec2:DescribeInstances`) for the Gateway's own account | The local `finops-readonly` role is missing. Read access no longer comes from the proxy's execution role. | Confirm the role exists in that account with `aws iam get-role --role-name finops-readonly`, then re-run step 3. |
| `AccessDenied` on `sts:AssumeRole` for a member account | The role is absent there, or its `aws:PrincipalArn` condition names a different role than the proxy actually uses. | Compare the member role's trust policy against `terraform output -raw proxy_role_name`; redeploy the template with the correct `ProxyRoleName`. |
| `finops-readonly already exists in stack …` when deploying the member template | A role from an earlier pilot exists under a different CloudFormation logical ID, so CloudFormation tries to create a second one. | Either `aws iam update-assume-role-policy` on the existing role, or delete the old stack first. See step 3. |
| Gateway rejects the tool, or the agent stops calling AWS APIs while still answering | Stale client tool list, or `make apply` ran without `update-schemas`. | Re-run `make deploy`, then Sync the connector (step 4). |
| Multi-region queries return partial results or time out | `lambda_timeout` is still at the 30s default. | Set `lambda_timeout = 120` and `make deploy` (step 1). |
| Cross-account query returns the Gateway account's resources instead of the member's | The model omitted `account_id`, usually because it could not resolve the account name. | Ask for the account by ID, or check that `list_member_accounts` is in the connector's approved tools. |
