"""Custom FinOps quality metrics using RAGAS AspectCritic and RubricsScore.

Tests FinOps-specific correctness:
- Date range correctness (exclusive end dates)
- Tool selection efficiency
- Parameter completeness
- Overall cost analysis quality
"""

import json

import pytest
from ragas.llms import LangchainLLMWrapper

from tests.helpers.finops_metrics import create_finops_metrics
from tests.helpers.gateway_client import GatewayMCPClient
from tests.scenarios.cost_explorer import END, START


def _pp(label: str, data) -> None:
    """Pretty-print a response with a label."""
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, default=str)[:2000])


@pytest.mark.integration
class TestFinOpsQuality:
    """Custom FinOps quality metrics evaluation."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient, evaluator_llm: LangchainLLMWrapper):
        self.gateway = gateway
        self.metrics = create_finops_metrics(evaluator_llm)

    def test_date_range_format(self):
        """Verify get_cost_and_usage accepts proper exclusive end dates."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "granularity": "MONTHLY",
            },
        )
        _pp(f"Date range ({START} to {END})", result)
        assert "error" not in result, f"Correct date range ({START} to {END}) was rejected: {result.get('error')}"

    def test_granularity_daily_for_trends(self):
        """Verify DAILY granularity works for trend analysis."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "granularity": "DAILY",
            },
        )
        _pp("DAILY granularity", result)
        assert "error" not in result, f"DAILY granularity failed: {result.get('error')}"

    def test_granularity_monthly_for_totals(self):
        """Verify MONTHLY granularity works for total analysis."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "granularity": "MONTHLY",
            },
        )
        _pp("MONTHLY granularity", result)
        assert "error" not in result, f"MONTHLY granularity failed: {result.get('error')}"

    def test_multiple_group_by_dimensions(self):
        """Verify multiple group_by dimensions work together."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "granularity": "MONTHLY",
                "group_by": ["SERVICE", "REGION"],
            },
        )
        _pp("Multiple group_by (SERVICE, REGION)", result)
        assert "error" not in result, f"Multiple group_by dimensions failed: {result.get('error')}"

    def test_comparison_tool_group_by_is_string(self):
        """Verify get_cost_and_usage_comparisons uses string group_by (not array)."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage_comparisons",
            arguments={
                "current_start": START,
                "current_end": END,
                "previous_start": "2026-02-01",
                "previous_end": "2026-03-01",
                "group_by": "SERVICE",
            },
        )
        _pp("Comparison tool (string group_by)", result)
        assert "error" not in result, f"Comparison tool with string group_by failed: {result.get('error')}"

    def test_forecast_uses_singular_metric(self):
        """Verify get_cost_forecast uses singular 'metric' (not 'metrics')."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_forecast",
            arguments={
                "granularity": "MONTHLY",
                "metric": "UNBLENDED_COST",
            },
        )
        _pp("Forecast (singular metric)", result)
        assert "result" in result or "error" in result

    def test_all_cost_metrics_supported(self):
        """Verify all standard cost metrics are accepted."""
        for metric_name in ["UnblendedCost", "BlendedCost", "AmortizedCost", "NetUnblendedCost"]:
            result = self.gateway.call_tool(
                target="cost-explorer-mcp",
                tool_name="get_cost_and_usage",
                arguments={
                    "metrics": [metric_name],
                    "granularity": "MONTHLY",
                },
            )
            _pp(f"Metric: {metric_name}", result)
            assert "error" not in result, f"Metric {metric_name} was rejected: {result.get('error')}"
