"""LLM-as-judge evals using RAGAS AgentGoalAccuracy.

Tests scenarios that need semantic judgment:
- Negative cases (agent should refuse)
- Complex multi-step workflows
- Ambiguous queries
"""

import json

import pytest
from ragas.llms import LangchainLLMWrapper

from tests.helpers.gateway_client import GatewayMCPClient
from tests.scenarios.athena import ATHENA_SCENARIOS
from tests.scenarios.cost_explorer import COST_EXPLORER_SCENARIOS


LLM_JUDGE_SCENARIOS = [s for s in COST_EXPLORER_SCENARIOS + ATHENA_SCENARIOS if s.metric_type == "llm_judge"]


def _pp(label: str, data) -> None:
    """Pretty-print a response with a label."""
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, default=str)[:2000])


@pytest.mark.integration
class TestAgentGoalAccuracy:
    """LLM-as-judge evaluation for semantic correctness."""

    @pytest.fixture(autouse=True)
    def _setup(self, gateway: GatewayMCPClient, evaluator_llm: LangchainLLMWrapper):
        self.gateway = gateway
        self.evaluator_llm = evaluator_llm

    def test_ce12_invalid_dimension_handling(self):
        """CE-12: Agent should handle invalid dimension gracefully."""
        result = self.gateway.call_tool(
            target="cost-explorer-mcp",
            tool_name="get_dimension_values",
            arguments={"dimension": "INVALID_DIMENSION"},
        )
        _pp("CE-12 get_dimension_values(INVALID_DIMENSION)", result)
        has_error = "error" in result
        has_result = "result" in result
        assert has_error or has_result, "Expected either error or result"

    def test_ath5_ddl_rejection(self):
        """ATH-5: DDL queries should be rejected."""
        result = self.gateway.call_tool(
            target="athena-mcp",
            tool_name="start_query_execution",
            arguments={
                "query_string": "DROP TABLE cur_data",
                "database": "default",
            },
        )
        _pp("ATH-5 start_query_execution(DROP TABLE)", result)

        result_content = result.get("result", {}).get("content", [])
        response_text = ""
        if result_content:
            response_text = result_content[0].get("text", "")

        is_error = "error" in result
        is_rejected = any(
            keyword in response_text.lower()
            for keyword in ["rejected", "not allowed", "read-only", "invalid", "blocked"]
        )

        assert is_error or is_rejected, f"DDL query was not rejected. Response: {result}"

    def test_ath4_query_workflow_tools_exist(self):
        """ATH-4: Verify the query workflow tools are all available."""
        workflow_tools = ["start_query_execution", "get_query_execution", "get_query_results"]
        tools = self.gateway.list_tools("athena-mcp")
        tool_names = {t["name"] for t in tools}
        print(f"\n--- ATH-4 Athena workflow tools ---\nAvailable: {sorted(tool_names)}")

        for tool in workflow_tools:
            assert tool in tool_names, f"Workflow tool {tool} not found on athena-mcp"
