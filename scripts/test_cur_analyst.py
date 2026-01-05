#!/usr/bin/env python3
"""
Test script for CUR Analyst Strands Agent Lambda

Usage:
    uv run python scripts/test_cur_analyst.py

This script tests:
1. Module imports
2. Strands agent initialization
3. Tool definitions
4. (Optional) Full workflow execution with real Athena queries
"""

import sys
from pathlib import Path


# Add Lambda source to path
LAMBDA_DIR = Path(__file__).parent.parent / "src" / "lambda" / "mcp_servers" / "cur_analyst"
sys.path.insert(0, str(LAMBDA_DIR))

import lambda_function as module


def test_imports():
    """Test that all module imports work correctly."""
    print("=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)

    try:
        print("All imports successful")
        print(f"  - CUR_CONFIG: {module.CUR_CONFIG}")
        print(f"  - Historical queries: {list(module.HISTORICAL_QUERIES.keys())}")
        print(f"  - Detailed queries: {list(module.DETAILED_QUERIES.keys())}")
        return True
    except Exception as e:
        print(f"Import error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_agent_initialization():
    """Test Strands agent initialization."""
    print("\n" + "=" * 60)
    print("TEST 2: Strands Agent Initialization")
    print("=" * 60)

    try:
        print("Initializing Strands agent (connects to Bedrock)...")
        agent = module.get_agent()

        print("Agent initialized successfully")
        print(f"  - Tools available: {agent.tool_names}")
        return True
    except Exception as e:
        print(f"Agent initialization error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_tool_definitions():
    """Test tool definitions (dry run)."""
    print("\n" + "=" * 60)
    print("TEST 3: Tool Definitions")
    print("=" * 60)

    try:
        tools = [
            module.submit_historical_queries,
            module.submit_detailed_queries,
            module.retrieve_all_results,
        ]

        for tool in tools:
            print(f"Tool: {tool.__name__}")
            print(f"  - Doc: {(tool.__doc__ or 'No docstring').split(chr(10))[0].strip()}")

        return True
    except Exception as e:
        print(f"Tool check error: {e}")
        return False


def test_full_workflow(report_month: str, compare_month: str, dry_run: bool = True):
    """Test the full CUR analysis workflow."""
    print("\n" + "=" * 60)
    print("TEST 4: Full Workflow Execution")
    print("=" * 60)
    print(f"  Report month: {report_month}")
    print(f"  Compare month: {compare_month}")
    print(f"  Dry run: {dry_run}")

    if dry_run:
        print("\n[DRY RUN] Skipping actual Athena query execution")
        print("To run with real queries, use: --execute")
        return True

    try:
        agent = module.get_agent()

        print("\nInvoking Strands agent...")
        print("-" * 40)

        response = agent(
            f"Analyze CUR data for report_month={report_month} and compare_month={compare_month}. "
            f"Execute all three tools in sequence and return the aggregated results."
        )

        print("-" * 40)
        print(f"Agent completed with stop_reason: {response.stop_reason}")
        print("\nResponse summary:")
        print(str(response)[:500] + "..." if len(str(response)) > 500 else str(response))

        return True
    except Exception as e:
        print(f"Workflow error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test CUR Analyst Strands Agent")
    parser.add_argument("--report-month", default="2024-12", help="Report month (YYYY-MM)")
    parser.add_argument("--compare-month", default="2024-11", help="Compare month (YYYY-MM)")
    parser.add_argument("--execute", action="store_true", help="Execute real Athena queries")
    parser.add_argument("--skip-agent", action="store_true", help="Skip agent initialization test")
    args = parser.parse_args()

    print("CUR Analyst Strands Agent - Local Test")
    print("=" * 60)

    results = []

    # Test 1: Imports
    results.append(("Imports", test_imports()))

    # Test 2: Agent initialization (optional)
    if not args.skip_agent:
        results.append(("Agent Init", test_agent_initialization()))
    else:
        print("\n[SKIPPED] Agent initialization test")

    # Test 3: Tool definitions
    results.append(("Tool Definitions", test_tool_definitions()))

    # Test 4: Full workflow (optional)
    results.append(
        ("Full Workflow", test_full_workflow(args.report_month, args.compare_month, dry_run=not args.execute))
    )

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
