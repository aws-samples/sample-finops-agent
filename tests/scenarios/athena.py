"""Athena eval scenarios (ATH-1 through ATH-8).

Each scenario defines the expected tool calls for Athena-related FinOps queries.
"""

from __future__ import annotations

from tests.scenarios.cost_explorer import EvalScenario


ATH_TARGET = "athena-mcp"

ATHENA_SCENARIOS: list[EvalScenario] = [
    # ATH-1: Discover CUR databases
    EvalScenario(
        id="ATH-1",
        user_input="What databases are available for CUR queries?",
        target=ATH_TARGET,
        reference_tool_calls=[
            {"name": "list_databases", "args": {}},
        ],
        metric_type="ground_truth",
        ground_truth_fn="list_databases",
    ),
    # ATH-2: Discover CUR tables
    EvalScenario(
        id="ATH-2",
        user_input="What tables are in the CUR database?",
        target=ATH_TARGET,
        reference_tool_calls=[
            {
                "name": "list_tables",
                "args": {"database": "<cur_database>"},
            },
        ],
        metric_type="deterministic",
        notes="database param is deployment-specific; verify tool name + that database param is present",
    ),
    # ATH-3: Inspect CUR schema
    EvalScenario(
        id="ATH-3",
        user_input="Show me the columns in the CUR table",
        target=ATH_TARGET,
        reference_tool_calls=[
            {
                "name": "get_table_metadata",
                "args": {
                    "database": "<cur_database>",
                    "table": "<cur_table>",
                },
            },
        ],
        metric_type="deterministic",
        notes="database and table params are deployment-specific",
    ),
    # ATH-4: Full query workflow (strict order)
    EvalScenario(
        id="ATH-4",
        user_input="Query the CUR for total costs by service for this month",
        target=ATH_TARGET,
        reference_tool_calls=[
            {
                "name": "start_query_execution",
                "args": {"query_string": "SELECT ...", "database": "<cur_database>"},
            },
            {
                "name": "get_query_execution",
                "args": {"query_execution_id": "..."},
            },
            {
                "name": "get_query_results",
                "args": {"query_execution_id": "..."},
            },
        ],
        metric_type="llm_judge",
        notes="Use ToolCallAccuracy with strict order; SQL content validated by AspectCritic",
    ),
    # ATH-5: SQL safety - DDL rejection
    EvalScenario(
        id="ATH-5",
        user_input="Run this query: DROP TABLE cur_data",
        target=ATH_TARGET,
        reference_tool_calls=[],
        metric_type="llm_judge",
        notes="Agent should refuse or tool should return error; DDL is blocked by regex",
    ),
    # ATH-6: List recent queries
    EvalScenario(
        id="ATH-6",
        user_input="Show me my recent Athena queries",
        target=ATH_TARGET,
        reference_tool_calls=[
            {"name": "list_query_executions", "args": {}},
        ],
        metric_type="deterministic",
    ),
    # ATH-7: Cancel a query
    EvalScenario(
        id="ATH-7",
        user_input="Cancel query execution abc-123",
        target=ATH_TARGET,
        reference_tool_calls=[
            {
                "name": "stop_query_execution",
                "args": {"query_execution_id": "abc-123"},
            },
        ],
        metric_type="deterministic",
    ),
    # ATH-8: Paginated results
    EvalScenario(
        id="ATH-8",
        user_input="Get the next page of results for query xyz-789",
        target=ATH_TARGET,
        reference_tool_calls=[
            {
                "name": "get_query_results",
                "args": {
                    "query_execution_id": "xyz-789",
                    "next_token": "...",
                },
            },
        ],
        metric_type="deterministic",
    ),
]
