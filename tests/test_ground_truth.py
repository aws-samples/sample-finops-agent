"""Differential ground truth tests: MCP tool results vs direct AWS API calls.

For each scenario with ground_truth_fn, we call both the MCP tool (through Gateway)
and the direct boto3 API, then compare results.
"""

import json

import pytest

from tests.helpers.comparators import (
    assert_costs_match,
    assert_databases_match,
    assert_dimensions_match,
    assert_grouped_costs_match,
)
from tests.helpers.gateway_client import GatewayMCPClient
from tests.helpers.ground_truth import GroundTruthClient
from tests.scenarios.cost_explorer import COST_EXPLORER_SCENARIOS, END, START


GROUND_TRUTH_SCENARIOS = [s for s in COST_EXPLORER_SCENARIOS if s.ground_truth_fn]


def _pp(label: str, data) -> None:
    """Pretty-print a response with a label."""
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, default=str)[:2000])


@pytest.mark.integration
@pytest.mark.ground_truth
class TestCostExplorerGroundTruth:
    """Differential tests: MCP tool result == direct API result."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient, ground_truth: GroundTruthClient):
        self.gateway = gateway
        self.gt = ground_truth

    def test_ce1_services_by_cost(self):
        """CE-1: Top services by cost — grouped costs should match."""
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "granularity": "MONTHLY",
                "group_by": ["SERVICE"],
            },
        )
        gt_result = self.gt.get_cost_and_usage(
            start_date=START,
            end_date=END,
            granularity="MONTHLY",
            group_by=["SERVICE"],
        )
        _pp("CE-1 MCP (services by cost)", mcp_result)
        _pp("CE-1 Ground Truth (services by cost)", gt_result)
        assert_grouped_costs_match(mcp_result, gt_result)

    def test_ce4_regional_breakdown(self):
        """CE-4: Regional cost breakdown — grouped costs should match."""
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "granularity": "MONTHLY",
                "group_by": ["REGION"],
            },
        )
        gt_result = self.gt.get_cost_and_usage(
            start_date=START,
            end_date=END,
            granularity="MONTHLY",
            group_by=["REGION"],
        )
        _pp("CE-4 MCP (regional breakdown)", mcp_result)
        _pp("CE-4 Ground Truth (regional breakdown)", gt_result)
        assert_grouped_costs_match(mcp_result, gt_result)

    def test_ce6_service_dimensions(self):
        """CE-6: Service dimension values should match."""
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_dimension_values",
            arguments={"dimension": "SERVICE"},
        )
        gt_result = self.gt.get_dimension_values(dimension="SERVICE")
        _pp("CE-6 MCP (service dimensions)", mcp_result)
        _pp("CE-6 Ground Truth (service dimensions)", gt_result)
        assert_dimensions_match(mcp_result, gt_result)

    def test_ce8_account_breakdown(self):
        """CE-8: Account-level cost breakdown should match."""
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "granularity": "MONTHLY",
                "group_by": ["LINKED_ACCOUNT"],
            },
        )
        gt_result = self.gt.get_cost_and_usage(
            start_date=START,
            end_date=END,
            granularity="MONTHLY",
            group_by=["LINKED_ACCOUNT"],
        )
        _pp("CE-8 MCP (account breakdown)", mcp_result)
        _pp("CE-8 Ground Truth (account breakdown)", gt_result)
        assert_grouped_costs_match(mcp_result, gt_result)

    def test_ce9_s3_filtered_cost(self):
        """CE-9: S3 filtered cost should match."""
        filter_expr = {
            "Dimensions": {
                "Key": "SERVICE",
                "Values": ["Amazon Simple Storage Service"],
            }
        }
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "filter": filter_expr,
            },
        )
        gt_result = self.gt.get_cost_and_usage(
            start_date=START,
            end_date=END,
            filter_expr=filter_expr,
        )
        _pp("CE-9 MCP (S3 filtered)", mcp_result)
        _pp("CE-9 Ground Truth (S3 filtered)", gt_result)
        assert_costs_match(mcp_result, gt_result)

    def test_ce_total_cost_unfiltered(self):
        """Total unfiltered cost should match between MCP and direct API."""
        mcp_result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_cost_and_usage",
            arguments={
                "start_date": START,
                "end_date": END,
                "granularity": "MONTHLY",
            },
        )
        gt_result = self.gt.get_cost_and_usage(
            start_date=START,
            end_date=END,
            granularity="MONTHLY",
        )
        _pp("Total MCP (unfiltered)", mcp_result)
        _pp("Total Ground Truth (unfiltered)", gt_result)
        assert_costs_match(mcp_result, gt_result)


@pytest.mark.integration
@pytest.mark.ground_truth
class TestAthenaGroundTruth:
    """Differential tests for Athena tools."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient, ground_truth: GroundTruthClient):
        self.gateway = gateway
        self.gt = ground_truth

    def test_ath1_list_databases(self):
        """ATH-1: Database list should match between MCP and direct API."""
        mcp_result = self.gateway.call_tool(
            target="athena-mcp",
            tool_name="list_databases",
            arguments={},
        )
        gt_result = self.gt.list_databases()
        _pp("ATH-1 MCP (databases)", mcp_result)
        _pp("ATH-1 Ground Truth (databases)", gt_result)
        assert_databases_match(mcp_result, gt_result)
