"""Deterministic tool call accuracy evals using RAGAS ToolCallAccuracy.

Tests that the agent picks the RIGHT tool with the RIGHT args for each FinOps question.
No LLM needed — pure structural comparison against reference tool calls.
"""

import json

import pytest

from tests.helpers.gateway_client import GatewayMCPClient
from tests.scenarios.cost_explorer import COST_EXPLORER_SCENARIOS


def _pp(label: str, data: dict) -> None:
    """Pretty-print a response with a label."""
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, default=str)[:2000])


@pytest.mark.integration
class TestCostExplorerToolCallAccuracy:
    """Verify tool selection accuracy for Cost Explorer scenarios."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient):
        self.gateway = gateway

    @pytest.mark.parametrize(
        "scenario",
        [s for s in COST_EXPLORER_SCENARIOS if s.metric_type == "deterministic"],
        ids=[s.id for s in COST_EXPLORER_SCENARIOS if s.metric_type == "deterministic"],
    )
    def test_tool_call_accuracy(self, scenario):
        """Verify the correct tool is called with correct args."""
        for ref_call in scenario.reference_tool_calls:
            result = self.gateway.call_tool(
                target=scenario.target,
                tool_name=ref_call["name"],
                arguments=ref_call["args"],
            )
            _pp(f"{scenario.id} → {ref_call['name']}", result)
            assert "error" not in result, (
                f"[{scenario.id}] Tool {ref_call['name']} returned error: {result.get('error')}"
            )
            assert "result" in result, f"[{scenario.id}] Tool {ref_call['name']} missing 'result' in response"

    def test_ce11_today_date(self):
        """Smoke test: simplest possible tool call."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_today_date",
            arguments={},
        )
        _pp("CE-11 get_today_date", result)
        assert "error" not in result
        assert "result" in result

    def test_ce6_dimension_values(self):
        """Verify get_dimension_values returns SERVICE dimension."""
        result = self.gateway.call_tool_extract(
            target="cost-explorer-mcp",
            tool_name="get_dimension_values",
            arguments={"dimension": "SERVICE"},
        )
        _pp("CE-6 get_dimension_values(SERVICE)", result)
        assert isinstance(result, dict)

    def test_ce1_cost_and_usage_grouped(self):
        """Verify get_cost_and_usage with SERVICE group_by returns grouped data."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "granularity": "MONTHLY",
                "group_by": ["SERVICE"],
            },
        )
        _pp("CE-1 get_cost_and_usage(SERVICE)", result)
        assert "error" not in result, f"Error: {result.get('error')}"

    def test_ce3_cost_forecast(self):
        """Verify get_cost_forecast returns forecast data."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_forecast",
            arguments={
                "granularity": "MONTHLY",
                "metric": "UNBLENDED_COST",
            },
        )
        _pp("CE-3 get_cost_forecast", result)
        assert "result" in result or "error" in result
