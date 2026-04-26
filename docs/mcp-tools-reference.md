# MCP Tools Reference

All available MCP tools organized by Gateway target.

## AWS API MCP Server (via lambda-proxy)

**Target Name**: `aws-api-mcp`

The `lambda-proxy` Lambda forwards MCP requests to the **AgentCore Runtime** which hosts the `aws-api-mcp-server` container from AWS Marketplace.

| Tool | Description |
|------|-------------|
| `call_aws` | Execute AWS CLI commands |
| `suggest_aws_commands` | Get AWS CLI command suggestions |

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

## CUR Analyst MCP

**Target Name**: `cur-analyst-mcp`

Lambda implementing MCP protocol for comprehensive cost analysis combining Cost Explorer API and Athena CUR 2.0 queries.

| Tool | Description |
|------|-------------|
| `analyze_cur` | Execute comprehensive cost analysis for monthly reports |

### analyze_cur Parameters

```json
{}
```
Uses current month vs previous month (default).

```json
{"report_month": "2024-12", "compare_month": "2024-11"}
```
Specify months explicitly.

### What analyze_cur Returns

**Cost Explorer API (5 queries):**
- Monthly trends by account (6 months)
- Monthly trends by service (6 months)
- Current month by account/service/region

**Savings & RI API (5 queries):**
- Savings Plans coverage and utilization (6 months)
- Reserved Instance coverage and utilization (6 months)
- Cost forecast

**Athena CUR 2.0 (10 queries):**
- Monthly totals, service by account, top services
- Region/account breakdown, charge types
- Daily trends, usage types, purchase options
- RI/SP savings, instance types

Results are aggregated and optimized for Gateway response size limits.

---

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
| lambda-proxy (aws-api-mcp-server) | 2 |
| cost-explorer-mcp | 6 |
| athena-mcp | 8 |
| cur-analyst-mcp | 1 |
| **Total** | **17** |

(Excludes test-mcp dummy tools)
