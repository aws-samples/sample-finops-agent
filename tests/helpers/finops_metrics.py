"""Custom RAGAS metrics for FinOps tool evaluation."""

from ragas.metrics import AspectCritic, RubricsScore


def create_finops_metrics(evaluator_llm):
    """Create all custom FinOps metrics with the given LLM.

    Returns a dict of metric_name -> metric instance.
    """
    date_correctness = AspectCritic(
        name="Date Range Correctness",
        llm=evaluator_llm,
        definition=(
            "Return 1 if the agent's tool call uses correct date ranges: "
            "start_date should be first of the target month (YYYY-MM-01), "
            "end_date should be first of the NEXT month (exclusive), "
            "and dates should match the user's request. "
            "Return 0 if dates are wrong, missing, or use inclusive end dates."
        ),
    )

    tool_efficiency = AspectCritic(
        name="Tool Selection Efficiency",
        llm=evaluator_llm,
        definition=(
            "Return 1 if the agent chose the most efficient tool for the task: "
            "use get_cost_and_usage for simple cost queries, "
            "get_cost_and_usage_comparisons for MoM comparisons, "
            "get_cost_forecast for projections, "
            "get_dimension_values for discovery, "
            "and Athena tools only for CUR-level detail. "
            "Return 0 if the agent used a complex tool when a simpler one sufficed."
        ),
    )

    param_completeness = AspectCritic(
        name="Parameter Completeness",
        llm=evaluator_llm,
        definition=(
            "Return 1 if the agent provided all parameters needed for an "
            "accurate FinOps answer: group_by when asked for breakdown, "
            "appropriate granularity (DAILY for trends, MONTHLY for totals), "
            "relevant metrics (UnblendedCost for actual spend, AmortizedCost "
            "for RI/SP analysis). Return 0 if critical parameters are missing."
        ),
    )

    cost_analysis_quality = RubricsScore(
        name="Cost Analysis Quality",
        llm=evaluator_llm,
        rubrics={
            "score-1_description": (
                "Agent returned wrong data, used wrong date range, called wrong tool, or failed to call any tool."
            ),
            "score0_description": (
                "Agent called the right tool but with suboptimal parameters "
                "(e.g., missing group_by when asked for breakdown, wrong granularity)."
            ),
            "score1_description": (
                "Agent called the right tool with correct parameters and the response "
                "contains actionable cost data matching the user's question."
            ),
        },
    )

    return {
        "date_correctness": date_correctness,
        "tool_efficiency": tool_efficiency,
        "param_completeness": param_completeness,
        "cost_analysis_quality": cost_analysis_quality,
    }
