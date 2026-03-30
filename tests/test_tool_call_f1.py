"""Tool call F1 (precision/recall) evals for scenarios with flexible tool ordering.

Used for scenarios where the agent might call tools in different orders
(e.g., get_tag_values before get_cost_and_usage for tag-based queries).
"""

import json

import pytest

from tests.helpers.gateway_client import GatewayMCPClient


def _pp(label: str, data) -> None:
    """Pretty-print a response with a label."""
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, default=str)[:2000])


@pytest.mark.integration
class TestToolCallF1:
    """Verify tool selection with flexible ordering for Cost Explorer scenarios."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient):
        self.gateway = gateway

    def test_ce7_tag_based_cost_analysis(self):
        """CE-7: Tag-based cost analysis — agent may call get_tag_values first."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "granularity": "MONTHLY",
                "group_by": ["TAG:Environment"],
            },
        )
        _pp("CE-7 get_cost_and_usage(TAG:Environment)", result)
        assert "error" not in result, f"Tag grouping failed: {result.get('error')}"

    def test_ce9_filtered_cost_query(self):
        """CE-9: Filtered cost query — verify filter syntax works."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "filter": {
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": ["Amazon Simple Storage Service"],
                    }
                },
            },
        )
        _pp("CE-9 get_cost_and_usage(S3 filter)", result)
        assert "error" not in result, f"Filter query failed: {result.get('error')}"

    def test_ce10_amortized_cost_metric(self):
        """CE-10: Verify AmortizedCost metric works."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "metrics": ["AmortizedCost"],
            },
        )
        _pp("CE-10 get_cost_and_usage(AmortizedCost)", result)
        assert "error" not in result, f"AmortizedCost metric failed: {result.get('error')}"

    def test_tool_list_completeness(self):
        """Verify all expected CE tools are registered on the target."""
        tools = self.gateway.list_tools("cost-explorer-mcp")
        tool_names = {t["name"] for t in tools}
        print(f"\n--- CE tools registered ---\n{sorted(tool_names)}")

        expected_tools = {
            "get_today_date",
            "get_dimension_values",
            "get_tag_values",
            "get_cost_and_usage",
            "get_cost_and_usage_comparisons",
            "get_cost_forecast",
        }
        missing = expected_tools - tool_names
        assert not missing, f"Missing tools on cost-explorer-mcp target: {missing}"

    def test_athena_tool_list_completeness(self):
        """Verify all expected Athena tools are registered."""
        tools = self.gateway.list_tools("athena-mcp")
        tool_names = {t["name"] for t in tools}
        print(f"\n--- Athena tools registered ---\n{sorted(tool_names)}")

        expected_tools = {
            "start_query_execution",
            "get_query_execution",
            "get_query_results",
            "list_query_executions",
            "list_databases",
            "list_tables",
            "get_table_metadata",
            "stop_query_execution",
        }
        missing = expected_tools - tool_names
        assert not missing, f"Missing tools on athena-mcp target: {missing}"
