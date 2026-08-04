# MCP Tools Reference

All available MCP tools organized by Gateway target.

## AWS API MCP Server (via lambda-proxy)

**Target Name**: `aws-api-mcp`

The `lambda-proxy` Lambda forwards MCP requests to the **managed AWS MCP Server** for cross-account AWS API execution.

| Tool | Description |
|------|-------------|
| `run_script` | Execute Python code against AWS APIs in a sandboxed environment using await call_boto3(...); supports cross-account execution via optional account_id |
| `list_member_accounts` | Resolve member account names to 12-digit account IDs; returns all accounts in the organization |
| `get_aws_skill` | Retrieve an AWS-authored expert workflow with procedures, correct API usage, and known pitfalls. `aws-billing-and-cost-management` covers cost analysis, commitment evaluation, right-sizing, budgets, and CUR queries |
| `search_documentation` | Search official AWS documentation and discover available skill names |
| `read_documentation` | Fetch a full AWS documentation page as markdown |

`run_script` and `list_member_accounts` act on account resources. The three
knowledge tools read AWS documentation instead, so they ignore `account_id` and
run under the proxy's own credentials — no member-account role is involved.

## Naming read-only tools

Prefer a `get_` / `list_` / `read_` / `search_` / `describe_` prefix for any tool
that only reads.

MCP lets a server mark a tool read-only with the `annotations.readOnlyHint`
field, and the managed AWS MCP Server does set it. Gateway cannot forward it:
[`ToolDefinition`](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_ToolDefinition.html)
accepts only `name`, `description`, `inputSchema`, and `outputSchema`, so
supplying `annotations` fails parameter validation outright.

Without that hint a client has to infer intent, and at least one infers it from
the tool name. In Amazon Quick, tools classified as reads can be granted blanket
approval, while everything else prompts on every call. `get_aws_skill` is named
that way for this reason — it wraps the upstream `aws___retrieve_skill`, which is
annotated `readOnlyHint: true`, but under its original name Quick classified it
as a write and prompted on every call.

This is observed client behaviour, not a documented contract, so treat the
convention as a soft signal that may stop mattering once Gateway forwards
annotations. Do not rename a tool that genuinely has side effects in order to
dodge an approval prompt: `run_script` executes model-authored code and is
annotated `destructiveHint: true` upstream, so prompting on each call is correct.

## Cost Explorer MCP

**Target Name**: `cost-explorer-mcp`

Lambda implementing MCP protocol for AWS Cost Explorer API.

| Tool | Description |
|------|-------------|
| `get_today_date` | Get current date for time period calculations |
| `get_dimension_values` | Get available values for a dimension (SERVICE, REGION, etc.) |
| `get_tag_values` | Get available values for a tag key |
| `get_cost_and_usage` | Retrieve cost and usage data with filtering/grouping |
| `get_cost_and_usage_comparisons` | Compare costs between two time periods |
| `get_cost_forecast` | Generate cost forecasts |

## Athena MCP

**Target Name**: `athena-mcp`

Lambda implementing MCP protocol for AWS Athena queries.

| Tool | Description |
|------|-------------|
| `start_query_execution` | Start an Athena SQL query |
| `get_query_execution` | Get status and details of a query |
| `get_query_results` | Get results of a completed query |
| `list_query_executions` | List recent query executions |
| `list_databases` | List databases in a data catalog |
| `list_tables` | List tables in a database |
| `get_table_metadata` | Get detailed table metadata |
| `stop_query_execution` | Cancel a running query |

## Test MCP (Dummy)

**Target Name**: `test-mcp`

Dummy Lambda for Gateway verification. Not intended for production use.

| Tool | Description |
|------|-------------|
| `hello` | Returns a greeting message |
| `echo` | Echoes back the provided message |

---

## Tool Count Summary

| Target | Tools |
|--------|-------|
| lambda-proxy (managed AWS MCP Server) | 5 |
| cost-explorer-mcp | 6 |
| athena-mcp | 8 |
| **Total** | **19** |

(Excludes test-mcp dummy tools)
