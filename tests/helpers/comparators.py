"""Comparators for differential testing: MCP tool results vs direct AWS API results.

MCP Gateway response format:
  {jsonrpc, id, result: {isError, content: [{type: "text", text: "<stringified JSON>"}]}}

The inner JSON from MCP uses lowercase keys:
  {results: [{time_period: {Start, End}, groups: [{keys: [...], metrics: {...}}]}]}

Direct Cost Explorer API uses uppercase:
  {ResultsByTime: [{TimePeriod: {Start, End}, Groups: [{Keys: [...], Metrics: {...}}]}]}
"""

from __future__ import annotations

import json
import math


COST_TOLERANCE = 0.01  # 1 cent tolerance for float comparison


def _parse_mcp_content(mcp_response: dict) -> dict:
    """Extract parsed content from an MCP JSON-RPC response.

    Handles the Gateway format: result.content[0].text = stringified JSON.
    """
    result = mcp_response.get("result", mcp_response)
    content_blocks = result.get("content", [])
    if not content_blocks:
        return result

    text = content_blocks[0].get("text", "")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}


def _floats_match(a: float, b: float, tolerance: float = COST_TOLERANCE) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tolerance


def _normalize_results_by_time(data: dict) -> list[dict]:
    """Extract the results-by-time array from either MCP or direct API format.

    MCP format:  data["results"] with lowercase keys (groups, keys, metrics)
    Direct API:  data["ResultsByTime"] with uppercase keys (Groups, Keys, Metrics)

    Returns normalized list with uppercase keys to match direct API format.
    """
    # Direct API format
    if "ResultsByTime" in data:
        return data["ResultsByTime"]

    # MCP format (lowercase "results")
    if "results" in data:
        normalized = []
        for period in data["results"]:
            entry = {
                "TimePeriod": period.get("time_period", {}),
                "Total": period.get("total", {}),
                "Groups": [],
            }
            for group in period.get("groups", []):
                entry["Groups"].append(
                    {
                        "Keys": group.get("keys", []),
                        "Metrics": group.get("metrics", {}),
                    }
                )
            normalized.append(entry)
        return normalized

    return []


def _extract_total_cost(results_by_time: list[dict], metric: str = "UnblendedCost") -> float:
    """Sum up total cost from ResultsByTime."""
    total = 0.0
    for period in results_by_time:
        if period.get("Total"):
            amount = period["Total"].get(metric, {}).get("Amount", "0")
            total += float(amount)
        elif period.get("Groups"):
            for group in period["Groups"]:
                amount = group.get("Metrics", {}).get(metric, {}).get("Amount", "0")
                total += float(amount)
    return total


def _extract_group_costs(
    results_by_time: list[dict],
    metric: str = "UnblendedCost",
) -> dict[str, float]:
    """Extract cost per group key from ResultsByTime."""
    costs: dict[str, float] = {}
    for period in results_by_time:
        for group in period.get("Groups", []):
            key = " / ".join(group.get("Keys", ["unknown"]))
            amount = float(group.get("Metrics", {}).get(metric, {}).get("Amount", "0"))
            costs[key] = costs.get(key, 0.0) + amount
    return costs


def assert_costs_match(
    mcp_response: dict,
    gt_response: dict,
    metric: str = "UnblendedCost",
    tolerance: float = COST_TOLERANCE,
) -> None:
    """Compare total costs between MCP tool result and direct API result."""
    mcp_data = _parse_mcp_content(mcp_response)
    mcp_results = _normalize_results_by_time(mcp_data)
    gt_results = _normalize_results_by_time(gt_response)

    assert len(mcp_results) == len(gt_results), f"Period count mismatch: MCP={len(mcp_results)}, GT={len(gt_results)}"

    mcp_total = _extract_total_cost(mcp_results, metric)
    gt_total = _extract_total_cost(gt_results, metric)

    assert _floats_match(mcp_total, gt_total, tolerance), (
        f"Total cost mismatch: MCP=${mcp_total:.2f}, GT=${gt_total:.2f} (tolerance=${tolerance:.2f})"
    )


def assert_grouped_costs_match(
    mcp_response: dict,
    gt_response: dict,
    metric: str = "UnblendedCost",
    tolerance: float = COST_TOLERANCE,
) -> None:
    """Compare grouped costs between MCP tool result and direct API result."""
    mcp_data = _parse_mcp_content(mcp_response)
    mcp_results = _normalize_results_by_time(mcp_data)
    gt_results = _normalize_results_by_time(gt_response)

    mcp_costs = _extract_group_costs(mcp_results, metric)
    gt_costs = _extract_group_costs(gt_results, metric)

    mcp_keys = set(mcp_costs.keys())
    gt_keys = set(gt_costs.keys())

    assert mcp_keys == gt_keys, (
        f"Group key mismatch:\n  Only in MCP: {mcp_keys - gt_keys}\n  Only in GT:  {gt_keys - mcp_keys}"
    )

    mismatches = [
        f"  {key}: MCP=${mcp_costs[key]:.4f}, GT=${gt_costs[key]:.4f}"
        for key in sorted(gt_keys)
        if not _floats_match(mcp_costs[key], gt_costs[key], tolerance)
    ]

    assert not mismatches, f"Cost mismatches (tolerance=${tolerance:.2f}):\n" + "\n".join(mismatches)


def assert_dimensions_match(
    mcp_response: dict,
    gt_response: dict,
) -> None:
    """Compare dimension values between MCP tool result and direct API result.

    MCP format: {dimension, values: [...], count}
    Direct API: {DimensionValues: [{Value, Attributes}]}
    """
    mcp_data = _parse_mcp_content(mcp_response)

    # MCP returns values as a flat list
    if "values" in mcp_data:
        mcp_values = set(mcp_data["values"])
    elif "DimensionValues" in mcp_data:
        mcp_values = {d.get("Value", d) for d in mcp_data["DimensionValues"]}
    else:
        mcp_values = set()

    gt_values = {d["Value"] for d in gt_response.get("DimensionValues", [])}

    assert mcp_values == gt_values, (
        f"Dimension value mismatch:\n  Only in MCP: {mcp_values - gt_values}\n  Only in GT:  {gt_values - mcp_values}"
    )


def assert_databases_match(
    mcp_response: dict,
    gt_response: dict,
) -> None:
    """Compare Athena database lists between MCP and direct API.

    MCP format: {databases: [...]}
    Direct API: {DatabaseList: [{Name, ...}]}
    """
    mcp_data = _parse_mcp_content(mcp_response)

    if "databases" in mcp_data:
        # MCP returns [{name: "...", description: "...", parameters: {}}, ...]
        raw = mcp_data["databases"]
        mcp_dbs = {d["name"] if isinstance(d, dict) else d for d in raw}
    elif "DatabaseList" in mcp_data:
        mcp_dbs = {d.get("Name", d) for d in mcp_data["DatabaseList"]}
    else:
        mcp_dbs = set()

    gt_dbs = {d["Name"] for d in gt_response.get("DatabaseList", [])}

    assert mcp_dbs == gt_dbs, (
        f"Database list mismatch:\n  Only in MCP: {mcp_dbs - gt_dbs}\n  Only in GT:  {gt_dbs - mcp_dbs}"
    )
