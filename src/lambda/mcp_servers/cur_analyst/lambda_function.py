"""
CUR Data Analyst - Lambda for AgentCore Gateway

This Lambda combines Cost Explorer API data with CUR 2.0 Athena queries
to provide comprehensive AWS cost analysis.

Data sources:
1. Cost Explorer API - Daily trends, service breakdown, regional costs
2. Savings/RI API - Coverage, utilization, and forecast data
3. CUR 2.0 Athena - 10 queries for detailed cost analysis

Tools implemented:
- analyze_cur: Execute full CUR analysis workflow and return raw data

Architecture:
    Gateway -> cur-analyst-mcp Lambda
                     |
         +-----------+-----------+
         |           |           |
    Cost Explorer   Savings    Athena
    (5 queries)    (5 queries) (10 queries)

Required IAM Permissions:
- ce:GetCostAndUsage, GetCostForecast, GetSavingsPlansCoverage, etc.
- athena:StartQueryExecution, GetQueryExecution, GetQueryResults
- s3:GetObject, s3:PutObject, s3:GetBucketLocation, s3:ListBucket
- glue:GetDatabase, GetTable, GetPartitions
"""

import json
import os
import time

import boto3

# Cross-account support - shared module is packaged alongside lambda_function.py
try:
    from shared.cross_account import get_aws_client
except ImportError:
    # Fallback for single-account mode (shared module not present)
    def get_aws_client(service_name, region_name=None, **kwargs):
        client_kwargs = {"region_name": region_name} if region_name else {}
        client_kwargs.update(kwargs)
        return boto3.client(service_name, **client_kwargs)


# Configuration from environment variables (with defaults for backward compatibility)
CUR_CONFIG = {
    "database": os.environ.get("CUR_DATABASE", "cur_database"),
    "table": os.environ.get("CUR_TABLE", "mycostexport"),
    "output_location": os.environ.get("CUR_OUTPUT_LOCATION", "s3://my-cur-cost-export/athena-results/"),
    "region": os.environ.get("CUR_REGION", "us-east-1"),
}

# Historical Queries (5)
HISTORICAL_QUERIES = {
    "monthly_totals": """
        SELECT billing_period, linked_account_id, linked_account_name,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as total_unblended,
               ROUND(SUM(CAST(amortized_cost AS DOUBLE)), 2) as total_amortized,
               COUNT(*) as line_items
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' OR billing_period LIKE '{compare_month}%'
        GROUP BY billing_period, linked_account_id, linked_account_name
        ORDER BY billing_period DESC, total_unblended DESC
    """,
    "service_by_account": """
        SELECT linked_account_name, service,
               ROUND(SUM(CASE WHEN billing_period LIKE '{report_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END), 2) as current_cost,
               ROUND(SUM(CASE WHEN billing_period LIKE '{compare_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END), 2) as previous_cost,
               ROUND(SUM(CASE WHEN billing_period LIKE '{report_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END) -
               SUM(CASE WHEN billing_period LIKE '{compare_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END), 2) as change
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' OR billing_period LIKE '{compare_month}%'
        GROUP BY linked_account_name, service
        HAVING SUM(CAST(unblended_cost AS DOUBLE)) > 0.01
        ORDER BY current_cost DESC
        LIMIT 50
    """,
    "top_services": """
        SELECT service, product_name,
               ROUND(SUM(CASE WHEN billing_period LIKE '{report_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END), 2) as current_cost,
               ROUND(SUM(CASE WHEN billing_period LIKE '{compare_month}%' THEN CAST(unblended_cost AS DOUBLE) ELSE 0 END), 2) as previous_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' OR billing_period LIKE '{compare_month}%'
        GROUP BY service, product_name
        ORDER BY current_cost DESC
        LIMIT 20
    """,
    "region_account": """
        SELECT linked_account_name, region,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as total_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%'
        GROUP BY linked_account_name, region
        ORDER BY total_cost DESC
    """,
    "charge_type": """
        SELECT linked_account_name, charge_type, charge_category,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as total_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%'
        GROUP BY linked_account_name, charge_type, charge_category
        ORDER BY total_cost DESC
    """,
}

# Detailed Queries (5)
DETAILED_QUERIES = {
    "daily_trend": """
        SELECT usage_date, linked_account_name,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as daily_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%'
        GROUP BY usage_date, linked_account_name
        ORDER BY usage_date, linked_account_name
    """,
    "usage_types": """
        SELECT linked_account_name, service, usage_type, operation, pricing_unit,
               ROUND(SUM(CAST(usage_quantity AS DOUBLE)), 4) as total_quantity,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as total_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' AND CAST(unblended_cost AS DOUBLE) > 0.01
        GROUP BY linked_account_name, service, usage_type, operation, pricing_unit
        ORDER BY total_cost DESC
        LIMIT 50
    """,
    "purchase_option": """
        SELECT linked_account_name, purchase_option,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as unblended_cost,
               ROUND(SUM(CAST(amortized_cost AS DOUBLE)), 2) as amortized_cost,
               ROUND(SUM(CAST(public_cost AS DOUBLE)), 2) as public_cost
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%'
        GROUP BY linked_account_name, purchase_option
        ORDER BY unblended_cost DESC
    """,
    "ri_sp_savings": """
        SELECT linked_account_name, service,
               ROUND(SUM(CAST(ri_sp_trueup AS DOUBLE)), 2) as ri_sp_trueup,
               ROUND(SUM(CAST(ri_sp_upfront_fees AS DOUBLE)), 2) as upfront_fees,
               ROUND(SUM(CAST(public_cost AS DOUBLE)) - SUM(CAST(unblended_cost AS DOUBLE)), 2) as estimated_savings
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' AND purchase_option != 'OnDemand'
        GROUP BY linked_account_name, service
        HAVING SUM(CAST(unblended_cost AS DOUBLE)) > 0
        ORDER BY estimated_savings DESC
    """,
    "instance_type": """
        SELECT linked_account_name, service, instance_type_family, instance_type, platform, tenancy,
               ROUND(SUM(CAST(unblended_cost AS DOUBLE)), 2) as total_cost,
               ROUND(SUM(CAST(usage_quantity AS DOUBLE)), 2) as total_hours
        FROM cur_database.mycostexport
        WHERE billing_period LIKE '{report_month}%' AND instance_type IS NOT NULL AND instance_type != ''
        GROUP BY linked_account_name, service, instance_type_family, instance_type, platform, tenancy
        ORDER BY total_cost DESC
        LIMIT 30
    """,
}


def submit_historical_queries(report_month: str, compare_month: str) -> dict:
    """Submit 5 historical CUR queries to Athena and return execution IDs.

    Args:
        report_month: Report month partition (e.g., '2024-12')
        compare_month: Comparison month partition (e.g., '2024-11')

    Returns:
        Dictionary with query execution IDs
    """
    athena = get_aws_client("athena", region_name=CUR_CONFIG["region"])
    query_ids = {}

    for name, query_template in HISTORICAL_QUERIES.items():
        query = query_template.format(report_month=report_month, compare_month=compare_month)
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": CUR_CONFIG["database"]},
            ResultConfiguration={"OutputLocation": CUR_CONFIG["output_location"]},
        )
        query_ids[name] = response["QueryExecutionId"]

    return {
        "status": "success",
        "content": [{"text": f"Submitted 5 historical queries. IDs: {json.dumps(query_ids)}"}],
        "query_ids": query_ids,
    }


def submit_detailed_queries(report_month: str, compare_month: str) -> dict:
    """Submit 5 detailed analysis queries to Athena and return execution IDs.

    Args:
        report_month: Report month partition (e.g., '2024-12')
        compare_month: Comparison month partition (e.g., '2024-11')

    Returns:
        Dictionary with query execution IDs
    """
    athena = get_aws_client("athena", region_name=CUR_CONFIG["region"])
    query_ids = {}

    for name, query_template in DETAILED_QUERIES.items():
        query = query_template.format(report_month=report_month, compare_month=compare_month)
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": CUR_CONFIG["database"]},
            ResultConfiguration={"OutputLocation": CUR_CONFIG["output_location"]},
        )
        query_ids[name] = response["QueryExecutionId"]

    return {
        "status": "success",
        "content": [{"text": f"Submitted 5 detailed queries. IDs: {json.dumps(query_ids)}"}],
        "query_ids": query_ids,
    }


def retrieve_all_results(historical_ids: dict, detailed_ids: dict) -> dict:
    """Poll for completion and retrieve results for all query execution IDs.

    Args:
        historical_ids: Query IDs from submit_historical_queries
        detailed_ids: Query IDs from submit_detailed_queries

    Returns:
        Dictionary with all query results
    """
    athena = get_aws_client("athena", region_name=CUR_CONFIG["region"])
    results = {}

    all_ids = {**historical_ids, **detailed_ids}

    for name, query_id in all_ids.items():
        state = None
        # Poll for completion
        for _ in range(60):  # Max 5 min wait
            status = athena.get_query_execution(QueryExecutionId=query_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                break
            elif state in ["FAILED", "CANCELLED"]:
                error_reason = status["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
                results[name] = {"error": state, "reason": error_reason}
                break
            time.sleep(5)

        if state == "SUCCEEDED":
            result = athena.get_query_results(QueryExecutionId=query_id, MaxResults=500)
            results[name] = parse_athena_results(result)

    return {
        "status": "success",
        "content": [{"text": f"Retrieved results for {len(results)} queries"}],
        "results": results,
    }


def parse_athena_results(response: dict) -> list:
    """Parse Athena query results into list of dicts."""
    result_set = response.get("ResultSet", {})
    rows = result_set.get("Rows", [])

    if not rows:
        return []

    # First row is headers
    headers = [col.get("VarCharValue", "") for col in rows[0].get("Data", [])]

    # Parse data rows
    data = []
    for row in rows[1:]:
        row_data = [col.get("VarCharValue", "") for col in row.get("Data", [])]
        data.append(dict(zip(headers, row_data, strict=False)))

    return data


def collect_cost_explorer_data() -> dict:
    """Collect Cost Explorer API data with monthly trends and current month breakdown.

    Fetches:
    1. Monthly trend by account (last 6 months) - for historical analysis
    2. Monthly trend by service (last 6 months) - for service cost trends
    3. Current month by account (totals)
    4. Current month by service (totals)
    5. Current month by region (totals)

    Uses MONTHLY granularity for efficiency and to keep response size manageable.

    Returns:
        Dictionary with all Cost Explorer results
    """
    from datetime import datetime, timedelta

    ce = get_aws_client("ce", region_name=CUR_CONFIG["region"])

    # Calculate date ranges
    today = datetime.now()
    # Cost Explorer end date is exclusive, so use tomorrow
    report_end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    report_start = today.replace(day=1).strftime("%Y-%m-%d")
    # 6 months ago for trend analysis
    six_months_ago = (today.replace(day=1) - timedelta(days=180)).replace(day=1).strftime("%Y-%m-%d")

    results = {}

    # === MONTHLY TRENDS (6 months) ===
    try:
        # 1. Monthly trend by account - shows cost trajectory over time
        results["monthly_trend_by_account"] = ce.get_cost_and_usage(
            TimePeriod={"Start": six_months_ago, "End": report_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost", "AmortizedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"}],
        ).get("ResultsByTime", [])
    except Exception as e:
        results["monthly_trend_by_account"] = {"error": str(e)}

    try:
        # 2. Monthly trend by service - shows which services are growing
        results["monthly_trend_by_service"] = ce.get_cost_and_usage(
            TimePeriod={"Start": six_months_ago, "End": report_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        ).get("ResultsByTime", [])
    except Exception as e:
        results["monthly_trend_by_service"] = {"error": str(e)}

    # === CURRENT MONTH BREAKDOWN ===
    try:
        # 3. Current month by account
        results["current_month_by_account"] = ce.get_cost_and_usage(
            TimePeriod={"Start": report_start, "End": report_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost", "AmortizedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"}],
        ).get("ResultsByTime", [])
    except Exception as e:
        results["current_month_by_account"] = {"error": str(e)}

    try:
        # 4. Current month by service and account
        results["current_month_by_service"] = ce.get_cost_and_usage(
            TimePeriod={"Start": report_start, "End": report_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"}],
        ).get("ResultsByTime", [])
    except Exception as e:
        results["current_month_by_service"] = {"error": str(e)}

    try:
        # 5. Current month by region
        results["current_month_by_region"] = ce.get_cost_and_usage(
            TimePeriod={"Start": report_start, "End": report_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "REGION"}],
        ).get("ResultsByTime", [])
    except Exception as e:
        results["current_month_by_region"] = {"error": str(e)}

    return {
        "status": "success",
        "content": [{"text": "Collected Cost Explorer data: 6-month trends + current month breakdown"}],
        "cost_explorer_data": results,
        "date_range": {"report_start": report_start, "report_end": report_end, "trend_start": six_months_ago},
    }


def collect_savings_and_forecast() -> dict:
    """Collect savings plans, reserved instance data, and cost forecast.

    Fetches using MONTHLY granularity (6 months) for trend analysis:
    1. Savings Plans Coverage (6 months)
    2. Savings Plans Utilization (6 months)
    3. Reserved Instance Coverage (6 months)
    4. Reserved Instance Utilization (6 months)
    5. Cost Forecast (requires 14+ days history - may not be available)

    Returns:
        Dictionary with savings and forecast data
    """
    from datetime import datetime, timedelta

    ce = get_aws_client("ce", region_name=CUR_CONFIG["region"])

    today = datetime.now()
    # End date is exclusive for Cost Explorer
    end_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    # 6 months ago for historical trends
    six_months_ago = (today.replace(day=1) - timedelta(days=180)).replace(day=1).strftime("%Y-%m-%d")
    next_month_start = (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")

    results = {}

    # 1. Savings Plans Coverage (6 months, monthly)
    try:
        results["sp_coverage"] = ce.get_savings_plans_coverage(
            TimePeriod={"Start": six_months_ago, "End": end_date}, Granularity="MONTHLY"
        ).get("SavingsPlansCoverages", [])
    except Exception as e:
        results["sp_coverage"] = {"error": str(e)}

    # 2. Savings Plans Utilization (6 months, monthly)
    try:
        results["sp_utilization"] = ce.get_savings_plans_utilization(
            TimePeriod={"Start": six_months_ago, "End": end_date}, Granularity="MONTHLY"
        ).get("SavingsPlansUtilizationsByTime", [])
    except Exception as e:
        results["sp_utilization"] = {"error": str(e)}

    # 3. Reserved Instance Coverage (6 months, monthly)
    try:
        results["ri_coverage"] = ce.get_reservation_coverage(
            TimePeriod={"Start": six_months_ago, "End": end_date}, Granularity="MONTHLY"
        ).get("CoveragesByTime", [])
    except Exception as e:
        results["ri_coverage"] = {"error": str(e)}

    # 4. Reserved Instance Utilization (6 months, monthly)
    try:
        results["ri_utilization"] = ce.get_reservation_utilization(
            TimePeriod={"Start": six_months_ago, "End": end_date}, Granularity="MONTHLY"
        ).get("UtilizationsByTime", [])
    except Exception as e:
        results["ri_utilization"] = {"error": str(e)}

    # 5. Cost Forecast (requires 14+ days history)
    try:
        results["forecast"] = ce.get_cost_forecast(
            TimePeriod={"Start": end_date, "End": next_month_start}, Metric="UNBLENDED_COST", Granularity="MONTHLY"
        )
    except Exception as e:
        error_msg = str(e)
        if "DataUnavailable" in error_msg or "BillEstimate" in error_msg:
            results["forecast"] = {"note": "insufficient history for forecast (requires 14+ days)"}
        else:
            results["forecast"] = {"error": error_msg}

    return {
        "status": "success",
        "content": [{"text": "Collected 6-month savings plans, RI data, and forecast"}],
        "savings_data": results,
        "date_range": {"trend_start": six_months_ago, "end_date": end_date},
    }


def lambda_handler(event, context):
    """
    Main Lambda handler for Gateway MCP tools.

    Gateway passes tool name via context.client_context.custom["bedrockAgentCoreToolName"]
    in format: <target_name>___<tool_name>

    For direct invocation (testing), pass tool_name in the event body.
    """
    print(f"Event: {json.dumps(event)}")

    # Get tool name from Gateway context or event (for testing)
    tool_name = None
    if context and hasattr(context, "client_context") and context.client_context:
        custom = getattr(context.client_context, "custom", None)
        if custom and "bedrockAgentCoreToolName" in custom:
            extended_tool_name = custom["bedrockAgentCoreToolName"]
            tool_name = extended_tool_name.split("___")[1]

    # Fallback: get tool_name from event body (for direct testing)
    if not tool_name:
        tool_name = event.get("tool_name", "analyze_cur")

    print(f"Tool name: {tool_name}")

    handlers = {
        "analyze_cur": handle_analyze_cur,
    }

    handler = handlers.get(tool_name)
    if handler:
        return handler(event)
    else:
        return {"error": f"Unknown tool: {tool_name}", "available_tools": list(handlers.keys())}


def handle_analyze_cur(event):
    """Execute CUR analysis workflow directly (no agent - faster and returns raw data)."""
    from datetime import datetime, timedelta

    # Default to current month and previous month if not provided
    now = datetime.now()
    default_report_month = now.strftime("%Y-%m")
    first_of_month = now.replace(day=1)
    last_month = first_of_month - timedelta(days=1)
    default_compare_month = last_month.strftime("%Y-%m")

    report_month = event.get("report_month") or default_report_month
    compare_month = event.get("compare_month") or default_compare_month

    print(f"Using report_month={report_month}, compare_month={compare_month}")

    results = {
        "status": "completed",
        "report_month": report_month,
        "compare_month": compare_month,
        "cost_explorer": None,
        "savings_forecast": None,
        "cur_data": None,
        "errors": [],
    }

    # Phase 1: Cost Explorer API Data
    try:
        print("Phase 1a: Collecting Cost Explorer data...")
        ce_result = collect_cost_explorer_data()
        results["cost_explorer"] = ce_result.get("cost_explorer_data", {})
        results["cost_explorer_date_range"] = ce_result.get("date_range", {})
    except Exception as e:
        results["errors"].append(f"cost_explorer: {e!s}")
        print(f"Cost Explorer error: {e}")

    try:
        print("Phase 1b: Collecting Savings and Forecast data...")
        savings_result = collect_savings_and_forecast()
        results["savings_forecast"] = savings_result.get("savings_data", {})
    except Exception as e:
        results["errors"].append(f"savings_forecast: {e!s}")
        print(f"Savings/Forecast error: {e}")

    # Phase 2: CUR Athena Queries
    try:
        print("Phase 2a: Submitting historical queries...")
        historical = submit_historical_queries(report_month, compare_month)
        historical_ids = historical.get("query_ids", {})

        print("Phase 2b: Submitting detailed queries...")
        detailed = submit_detailed_queries(report_month, compare_month)
        detailed_ids = detailed.get("query_ids", {})

        print("Phase 2c: Retrieving all results...")
        cur_results = retrieve_all_results(historical_ids, detailed_ids)
        results["cur_data"] = cur_results.get("results", {})
    except Exception as e:
        results["errors"].append(f"cur_athena: {e!s}")
        print(f"CUR Athena error: {e}")

    # Remove errors key if empty
    if not results["errors"]:
        del results["errors"]

    # Postprocess to reduce response size for Gateway limits (~200KB max)
    results = postprocess_results(results)

    # Log response size for debugging
    response_json = json.dumps(results)
    print(f"Response size: {len(response_json)} bytes ({len(response_json) / 1024:.1f} KB)")

    return results


def postprocess_results(results):
    """Aggregate and summarize data to reduce response size."""

    # Aggregate Cost Explorer daily data to totals
    if results.get("cost_explorer"):
        results["cost_explorer"] = aggregate_cost_explorer(results["cost_explorer"])

    # Aggregate Savings data to totals
    if results.get("savings_forecast"):
        results["savings_forecast"] = aggregate_savings(results["savings_forecast"])

    # Limit CUR data rows
    if results.get("cur_data"):
        results["cur_data"] = limit_cur_rows(results["cur_data"], max_rows=30)

    return results


def aggregate_cost_explorer(ce_data):
    """Simplify Cost Explorer response structure and limit to top items."""
    simplified = {}

    for query_name, data in ce_data.items():
        if isinstance(data, dict) and "error" in data:
            simplified[query_name] = data
            continue

        if not isinstance(data, list) or not data:
            simplified[query_name] = data
            continue

        # For trend queries (multiple months), keep the time series structure but simplify
        if "trend" in query_name:
            # Keep monthly data points but simplify the structure
            trend_data = []
            for time_period in data:
                period = time_period.get("TimePeriod", {})
                month = period.get("Start", "")[:7]  # YYYY-MM
                groups = time_period.get("Groups", [])

                month_data = {"month": month, "costs": []}
                for group in groups[:20]:  # Top 20 per month
                    entry = {"keys": group.get("Keys", [])}
                    for metric_name, metric_value in group.get("Metrics", {}).items():
                        entry[metric_name] = round(float(metric_value.get("Amount", 0)), 2)
                    month_data["costs"].append(entry)
                trend_data.append(month_data)
            simplified[query_name] = trend_data
        else:
            # For current month queries, flatten to simple list
            all_groups = []
            for time_period in data:
                for group in time_period.get("Groups", []):
                    entry = {"keys": group.get("Keys", [])}
                    for metric_name, metric_value in group.get("Metrics", {}).items():
                        entry[metric_name] = round(float(metric_value.get("Amount", 0)), 2)
                    all_groups.append(entry)

            # Sort by first metric descending and limit
            if all_groups:
                first_metric = next(k for k in all_groups[0] if k != "keys")
                all_groups.sort(key=lambda x: x.get(first_metric, 0), reverse=True)
            simplified[query_name] = all_groups[:30]

    return simplified


def aggregate_savings(savings_data):
    """Simplify savings data structure while keeping monthly trends."""
    simplified = {}

    for query_name, data in savings_data.items():
        if isinstance(data, dict):
            # Handle errors or single objects (like forecast)
            simplified[query_name] = data
            continue

        if not isinstance(data, list) or not data:
            simplified[query_name] = data
            continue

        # Simplify coverage/utilization lists to monthly data points
        if query_name in ["sp_coverage", "ri_coverage"]:
            monthly = []
            for item in data:
                period = item.get("TimePeriod", {})
                month = period.get("Start", "")[:7]
                coverage = item.get("Coverage", {}).get("CoverageHours", {})
                monthly.append(
                    {
                        "month": month,
                        "coverage_percent": round(float(coverage.get("CoverageHoursPercentage", 0)), 2),
                        "on_demand_hours": round(float(coverage.get("OnDemandHours", 0)), 2),
                        "covered_hours": round(float(coverage.get("CoverageHours", 0)), 2),
                    }
                )
            simplified[query_name] = monthly
        elif query_name in ["sp_utilization", "ri_utilization"]:
            monthly = []
            for item in data:
                period = item.get("TimePeriod", {})
                month = period.get("Start", "")[:7]
                util = item.get("Utilization", {})
                monthly.append(
                    {
                        "month": month,
                        "utilization_percent": round(float(util.get("UtilizationPercentage", 0)), 2),
                        "used_commitment": round(float(util.get("UsedCommitment", 0)), 2),
                        "unused_commitment": round(float(util.get("UnusedCommitment", 0)), 2),
                    }
                )
            simplified[query_name] = monthly
        else:
            simplified[query_name] = data

    return simplified


def limit_cur_rows(cur_data, max_rows=30):
    """Limit CUR query results to top N rows."""
    limited = {}
    for query_name, rows in cur_data.items():
        if isinstance(rows, list):
            if len(rows) > max_rows:
                limited[query_name] = rows[:max_rows]
                limited[query_name].append({"_note": f"truncated, {len(rows) - max_rows} more rows"})
            else:
                limited[query_name] = rows
        else:
            limited[query_name] = rows
    return limited
