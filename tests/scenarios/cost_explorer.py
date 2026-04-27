"""Cost Explorer eval scenarios (CE-1 through CE-12).

Each scenario defines:
- id: unique scenario identifier
- user_input: natural language FinOps question
- target: MCP target name
- reference_tool_calls: expected tool name + args (for ToolCallAccuracy/F1)
- metric_type: which RAGAS metric tier to use
- ground_truth_fn: optional callable name on GroundTruthClient for differential testing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC


@dataclass
class EvalScenario:
    id: str
    user_input: str
    target: str
    reference_tool_calls: list[dict]
    metric_type: str = "deterministic"  # deterministic | llm_judge | ground_truth
    ground_truth_fn: str | None = None
    ground_truth_args: dict = field(default_factory=dict)
    notes: str = ""


def current_month_dates() -> tuple[str, str]:
    """Return (start, end) for the current billing month. Computed at import time."""
    from datetime import datetime

    now = datetime.now(tz=UTC)
    start = now.strftime("%Y-%m-01")
    end = f"{now.year + 1}-01-01" if now.month == 12 else f"{now.year}-{now.month + 1:02d}-01"
    return start, end


def previous_month_dates() -> tuple[str, str]:
    """Return (start, end) for the previous billing month."""
    from datetime import datetime

    now = datetime.now(tz=UTC)
    if now.month == 1:
        prev_start = f"{now.year - 1}-12-01"
        prev_end = f"{now.year}-01-01"
    else:
        prev_start = f"{now.year}-{now.month - 1:02d}-01"
        prev_end = now.strftime("%Y-%m-01")
    return prev_start, prev_end


START, END = current_month_dates()
PREV_START, PREV_END = previous_month_dates()

CE_TARGET = "cost-explorer-mcp"

COST_EXPLORER_SCENARIOS: list[EvalScenario] = [
    # CE-1: Top services by cost this month
    EvalScenario(
        id="CE-1",
        user_input="What are my top AWS services by cost this month?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "granularity": "MONTHLY",
                    "group_by": ["SERVICE"],
                },
            }
        ],
        metric_type="ground_truth",
        ground_truth_fn="get_cost_and_usage",
        ground_truth_args={
            "start_date": START,
            "end_date": END,
            "granularity": "MONTHLY",
            "group_by": ["SERVICE"],
        },
    ),
    # CE-2: Month-over-month comparison
    EvalScenario(
        id="CE-2",
        user_input="How did my costs change compared to last month?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage_comparisons",
                "args": {
                    "current_start": START,
                    "current_end": END,
                    "previous_start": PREV_START,
                    "previous_end": PREV_END,
                    "group_by": "SERVICE",
                },
            }
        ],
        metric_type="deterministic",
    ),
    # CE-3: Cost forecast
    EvalScenario(
        id="CE-3",
        user_input="What is my projected AWS spend for next month?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_forecast",
                "args": {
                    "granularity": "MONTHLY",
                    "metric": "UNBLENDED_COST",
                },
            }
        ],
        metric_type="deterministic",
    ),
    # CE-4: Regional cost breakdown
    EvalScenario(
        id="CE-4",
        user_input="Show me my costs broken down by AWS region",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "group_by": ["REGION"],
                    "granularity": "MONTHLY",
                },
            }
        ],
        metric_type="ground_truth",
        ground_truth_fn="get_cost_and_usage",
        ground_truth_args={
            "start_date": START,
            "end_date": END,
            "granularity": "MONTHLY",
            "group_by": ["REGION"],
        },
    ),
    # CE-5: Daily cost trend
    EvalScenario(
        id="CE-5",
        user_input="Show me daily cost trends for the past 2 weeks",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "granularity": "DAILY",
                },
            }
        ],
        metric_type="deterministic",
    ),
    # CE-6: Discover available services
    EvalScenario(
        id="CE-6",
        user_input="What AWS services am I using?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_dimension_values",
                "args": {"dimension": "SERVICE"},
            }
        ],
        metric_type="ground_truth",
        ground_truth_fn="get_dimension_values",
        ground_truth_args={"dimension": "SERVICE"},
    ),
    # CE-7: Tag-based cost analysis (flexible — agent may call get_tag_values first)
    EvalScenario(
        id="CE-7",
        user_input="Show me costs grouped by the Environment tag",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "group_by": ["TAG:Environment"],
                },
            }
        ],
        metric_type="deterministic",
        notes="Use ToolCallF1 (flexible order) — agent may call get_tag_values first",
    ),
    # CE-8: Account-level breakdown
    EvalScenario(
        id="CE-8",
        user_input="Break down my costs by AWS account",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "group_by": ["LINKED_ACCOUNT"],
                    "granularity": "MONTHLY",
                },
            }
        ],
        metric_type="ground_truth",
        ground_truth_fn="get_cost_and_usage",
        ground_truth_args={
            "start_date": START,
            "end_date": END,
            "granularity": "MONTHLY",
            "group_by": ["LINKED_ACCOUNT"],
        },
    ),
    # CE-9: Filter to specific service
    EvalScenario(
        id="CE-9",
        user_input="How much did I spend on Amazon S3 this month?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "filter": {
                        "Dimensions": {
                            "Key": "SERVICE",
                            "Values": ["Amazon Simple Storage Service"],
                        }
                    },
                },
            }
        ],
        metric_type="ground_truth",
        ground_truth_fn="get_cost_and_usage",
        ground_truth_args={
            "start_date": START,
            "end_date": END,
            "filter_expr": {
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Simple Storage Service"],
                }
            },
        },
    ),
    # CE-10: Amortized vs unblended
    EvalScenario(
        id="CE-10",
        user_input="Show me my amortized costs this month to understand RI/SP impact",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_cost_and_usage",
                "args": {
                    "metrics": ["AmortizedCost"],
                },
            }
        ],
        metric_type="deterministic",
    ),
    # CE-11: Current date context (simplest smoke test)
    EvalScenario(
        id="CE-11",
        user_input="What is today's date and the current billing period?",
        target=CE_TARGET,
        reference_tool_calls=[
            {
                "name": "get_today_date",
                "args": {},
            }
        ],
        metric_type="deterministic",
    ),
    # CE-12: Negative - invalid dimension (LLM judge)
    EvalScenario(
        id="CE-12",
        user_input="Show me costs grouped by INVALID_DIMENSION",
        target=CE_TARGET,
        reference_tool_calls=[],
        metric_type="llm_judge",
        notes="Agent should refuse or call get_dimension_values to discover valid options",
    ),
]
