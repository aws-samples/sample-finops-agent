"""
AWS Cost Explorer MCP Server - Lambda Implementation for Amazon Bedrock AgentCore Gateway

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

This is a custom Lambda implementation inspired by the AWSlabs Cost Explorer MCP Server
(https://awslabs.github.io/mcp/servers/cost-explorer-mcp-server).

Why Custom Implementation vs AWSlabs MCP Server:

The AWSlabs MCP servers are not yet ready for multi-tenant MCP setups like AgentCore
Gateway. Current limitations include:
- Container-based MCP servers on AgentCore Runtime have long cold starts (30+ seconds)
- No native support for Gateway's Lambda target pattern
- Tool schema format differences (Gateway doesn't support 'enum' in JSON Schema)

This Lambda-based approach is a workaround that provides:
1. **Gateway Integration**: Lambda returns plain JSON; Gateway handles MCP protocol
2. **Simplified Deployment**: No container registry, no Dockerfile, just Python code
3. **Direct Tool Invocation**: Gateway invokes Lambda per tool call, no MCP session needed

Future Migration:
This project plans to migrate to AWSlabs-provided MCP servers when they support
multi-tenant Gateway deployments.

Tools (6 of 7 AWSlabs tools - omits get_cost_comparison_drivers):
- get_today_date: Get current date for time period calculations
- get_dimension_values: Get available values for a dimension (SERVICE, REGION, etc.)
- get_tag_values: Get available values for a tag key
- get_cost_and_usage: Retrieve cost and usage data with filtering/grouping
- get_cost_and_usage_comparisons: Compare costs between two time periods
- get_cost_forecast: Generate cost forecasts based on historical patterns

Architecture:
    Client (QuickSight) -> Gateway (OAuth+MCP) -> Lambda (JSON) -> Cost Explorer API

Required IAM Permissions:
- ce:GetCostAndUsage
- ce:GetDimensionValues
- ce:GetTags
- ce:GetCostForecast
"""

import json
import re
from datetime import datetime, timedelta

import boto3

# Valid Cost Explorer dimensions per AWS API
VALID_DIMENSIONS = {
    "AZ", "INSTANCE_TYPE", "LINKED_ACCOUNT", "LINKED_ACCOUNT_NAME",
    "OPERATION", "PURCHASE_TYPE", "REGION", "SERVICE", "SERVICE_CODE",
    "USAGE_TYPE", "USAGE_TYPE_GROUP", "RECORD_TYPE", "OPERATING_SYSTEM",
    "TENANCY", "SCOPE", "PLATFORM", "SUBSCRIPTION_ID", "LEGAL_ENTITY_NAME",
    "INVOICING_ENTITY", "DEPLOYMENT_OPTION", "DATABASE_ENGINE",
    "CACHE_ENGINE", "INSTANCE_TYPE_FAMILY", "BILLING_ENTITY",
    "RESERVATION_ID", "RESOURCE_ID", "SAVINGS_PLAN_ARN",
}

VALID_GRANULARITIES = {"DAILY", "MONTHLY", "HOURLY"}

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(value, param_name):
    """Validate date is in YYYY-MM-DD format."""
    if value and not DATE_PATTERN.match(value):
        return f"{param_name} must be in YYYY-MM-DD format, got: {value}"
    return None

# Cross-account support - shared module is packaged alongside lambda_function.py
try:
    from shared.cross_account import get_aws_client
except ImportError:
    # Fallback for single-account mode (shared module not present)
    def get_aws_client(service_name, region_name=None, **kwargs):
        client_kwargs = {"region_name": region_name} if region_name else {}
        client_kwargs.update(kwargs)
        return boto3.client(service_name, **client_kwargs)


def lambda_handler(event, context):
    """
    Main Lambda handler for Gateway MCP tools.

    Gateway passes tool name via context.client_context.custom["bedrockAgentCoreToolName"]
    in format: <target_name>___<tool_name>
    """
    print(f"Event: {json.dumps(event)}")

    # Get tool name from Gateway context
    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
    tool_name = extended_tool_name.split("___")[1]

    print(f"Tool name: {tool_name}")

    # Route to appropriate tool handler
    handlers = {
        "get_today_date": handle_get_today_date,
        "get_dimension_values": handle_get_dimension_values,
        "get_tag_values": handle_get_tag_values,
        "get_cost_and_usage": handle_get_cost_and_usage,
        "get_cost_and_usage_comparisons": handle_get_cost_and_usage_comparisons,
        "get_cost_forecast": handle_get_cost_forecast,
    }

    handler = handlers.get(tool_name)
    if handler:
        return handler(event)
    else:
        return {"error": f"Unknown tool: {tool_name}", "available_tools": list(handlers.keys())}


def handle_get_today_date(event):
    """Get the current date for determining relevant time periods."""
    today = datetime.utcnow()
    return {
        "today": today.strftime("%Y-%m-%d"),
        "year": today.year,
        "month": today.month,
        "day": today.day,
        "first_of_month": today.replace(day=1).strftime("%Y-%m-%d"),
        "last_month_start": (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d"),
        "last_month_end": (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d"),
    }


def handle_get_dimension_values(event):
    """Get available values for a specific dimension (e.g., SERVICE, REGION)."""
    dimension = event.get("dimension", "SERVICE")
    start_date = event.get("start_date")
    end_date = event.get("end_date")

    if dimension not in VALID_DIMENSIONS:
        return {"error": f"Invalid dimension: {dimension}. Valid values: {sorted(VALID_DIMENSIONS)}"}
    for name, val in [("start_date", start_date), ("end_date", end_date)]:
        err = validate_date(val, name)
        if err:
            return {"error": err}

    # Default to last 30 days if not specified
    if not start_date or not end_date:
        today = datetime.utcnow()
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    ce = get_aws_client("ce")

    try:
        response = ce.get_dimension_values(TimePeriod={"Start": start_date, "End": end_date}, Dimension=dimension)

        values = [item["Value"] for item in response.get("DimensionValues", [])]
        return {
            "dimension": dimension,
            "time_period": {"start": start_date, "end": end_date},
            "values": values,
            "count": len(values),
        }
    except Exception as e:
        return {"error": str(e), "dimension": dimension}


def handle_get_tag_values(event):
    """Get available values for a specific tag key."""
    tag_key = event.get("tag_key", "")
    start_date = event.get("start_date")
    end_date = event.get("end_date")

    if not tag_key:
        return {"error": "tag_key parameter is required"}

    # Default to last 30 days if not specified
    if not start_date or not end_date:
        today = datetime.utcnow()
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    ce = get_aws_client("ce")

    try:
        response = ce.get_tags(TimePeriod={"Start": start_date, "End": end_date}, TagKey=tag_key)

        values = response.get("Tags", [])
        return {
            "tag_key": tag_key,
            "time_period": {"start": start_date, "end": end_date},
            "values": values,
            "count": len(values),
        }
    except Exception as e:
        return {"error": str(e), "tag_key": tag_key}


def handle_get_cost_and_usage(event):
    """Retrieve AWS cost and usage data with filtering and grouping options."""
    start_date = event.get("start_date")
    end_date = event.get("end_date")
    granularity = event.get("granularity", "MONTHLY")
    metrics = event.get("metrics", ["UnblendedCost"])
    group_by = event.get("group_by", [])
    filter_expr = event.get("filter")

    if granularity not in VALID_GRANULARITIES:
        return {"error": f"Invalid granularity: {granularity}. Valid values: {sorted(VALID_GRANULARITIES)}"}
    for name, val in [("start_date", start_date), ("end_date", end_date)]:
        err = validate_date(val, name)
        if err:
            return {"error": err}

    # Default to current month if not specified
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    ce = get_aws_client("ce")

    try:
        params = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": granularity,
            "Metrics": metrics if isinstance(metrics, list) else [metrics],
        }

        # Add group by if specified
        if group_by:
            if isinstance(group_by, str):
                group_by = [group_by]
            params["GroupBy"] = [{"Type": "DIMENSION", "Key": dim} for dim in group_by]

        # Add filter if specified
        if filter_expr:
            params["Filter"] = filter_expr

        response = ce.get_cost_and_usage(**params)

        # Format results
        results = []
        for result in response.get("ResultsByTime", []):
            period_result = {"time_period": result.get("TimePeriod"), "total": result.get("Total", {}), "groups": []}
            for group in result.get("Groups", []):
                period_result["groups"].append({"keys": group.get("Keys", []), "metrics": group.get("Metrics", {})})
            results.append(period_result)

        return {
            "time_period": {"start": start_date, "end": end_date},
            "granularity": granularity,
            "metrics": metrics,
            "results": results,
        }
    except Exception as e:
        return {"error": str(e)}


def handle_get_cost_and_usage_comparisons(event):
    """Compare costs between two time periods to identify changes and trends."""
    current_start = event.get("current_start")
    current_end = event.get("current_end")
    previous_start = event.get("previous_start")
    previous_end = event.get("previous_end")
    granularity = event.get("granularity", "MONTHLY")
    metrics = event.get("metrics", ["UnblendedCost"])
    group_by = event.get("group_by", "SERVICE")

    # Default to current month vs previous month
    if not all([current_start, current_end, previous_start, previous_end]):
        today = datetime.utcnow()
        current_start = today.replace(day=1).strftime("%Y-%m-%d")
        current_end = today.strftime("%Y-%m-%d")
        prev_month_end = today.replace(day=1) - timedelta(days=1)
        previous_start = prev_month_end.replace(day=1).strftime("%Y-%m-%d")
        previous_end = prev_month_end.strftime("%Y-%m-%d")

    ce = get_aws_client("ce")

    try:
        # Get current period costs
        current_response = ce.get_cost_and_usage(
            TimePeriod={"Start": current_start, "End": current_end},
            Granularity=granularity,
            Metrics=metrics if isinstance(metrics, list) else [metrics],
            GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
        )

        # Get previous period costs
        previous_response = ce.get_cost_and_usage(
            TimePeriod={"Start": previous_start, "End": previous_end},
            Granularity=granularity,
            Metrics=metrics if isinstance(metrics, list) else [metrics],
            GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
        )

        # Calculate comparison
        current_costs = {}
        for result in current_response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                key = group["Keys"][0]
                amount = float(group["Metrics"].get("UnblendedCost", {}).get("Amount", 0))
                current_costs[key] = current_costs.get(key, 0) + amount

        previous_costs = {}
        for result in previous_response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                key = group["Keys"][0]
                amount = float(group["Metrics"].get("UnblendedCost", {}).get("Amount", 0))
                previous_costs[key] = previous_costs.get(key, 0) + amount

        # Build comparison
        comparisons = []
        all_keys = set(current_costs.keys()) | set(previous_costs.keys())
        for key in all_keys:
            current = current_costs.get(key, 0)
            previous = previous_costs.get(key, 0)
            change = current - previous
            change_pct = (change / previous * 100) if previous > 0 else (100 if current > 0 else 0)
            comparisons.append(
                {
                    "name": key,
                    "current_cost": round(current, 2),
                    "previous_cost": round(previous, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 1),
                }
            )

        # Sort by absolute change
        comparisons.sort(key=lambda x: abs(x["change"]), reverse=True)

        return {
            "current_period": {"start": current_start, "end": current_end},
            "previous_period": {"start": previous_start, "end": previous_end},
            "group_by": group_by,
            "comparisons": comparisons[:20],  # Top 20
            "total_current": round(sum(current_costs.values()), 2),
            "total_previous": round(sum(previous_costs.values()), 2),
        }
    except Exception as e:
        return {"error": str(e)}


def handle_get_cost_forecast(event):
    """Generate cost forecasts based on historical usage patterns."""
    start_date = event.get("start_date")
    end_date = event.get("end_date")
    granularity = event.get("granularity", "MONTHLY")
    metric = event.get("metric", "UNBLENDED_COST")

    # Default to forecast for rest of month
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        # End of next month
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = (next_month.replace(day=1) + timedelta(days=31)).replace(day=1).strftime("%Y-%m-%d")

    ce = get_aws_client("ce")

    try:
        response = ce.get_cost_forecast(
            TimePeriod={"Start": start_date, "End": end_date}, Granularity=granularity, Metric=metric
        )

        return {
            "forecast_period": {"start": start_date, "end": end_date},
            "granularity": granularity,
            "metric": metric,
            "total_forecast": {
                "amount": response.get("Total", {}).get("Amount"),
                "unit": response.get("Total", {}).get("Unit"),
            },
            "forecast_by_time": [
                {
                    "time_period": item.get("TimePeriod"),
                    "mean_value": item.get("MeanValue"),
                    "prediction_interval_lower": item.get("PredictionIntervalLowerBound"),
                    "prediction_interval_upper": item.get("PredictionIntervalUpperBound"),
                }
                for item in response.get("ForecastResultsByTime", [])
            ],
        }
    except Exception as e:
        return {"error": str(e)}
