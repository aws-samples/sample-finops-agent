#!/usr/bin/env python3
"""
Test script for MCP Lambda functions.
Tests the test-mcp, cost-explorer-mcp, and athena-mcp Lambda functions.
"""

import base64
import json
import os

import boto3


AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")


def invoke_mcp_lambda(function_name: str, target_name: str, tool_name: str, payload: dict) -> dict:
    """Invoke an MCP Lambda function with the proper client context."""
    try:
        session = boto3.Session(profile_name=AWS_PROFILE)
        client = session.client("lambda", region_name=AWS_REGION)

        # Create client context with tool name (format: target___tool)
        client_context = {"custom": {"bedrockAgentCoreToolName": f"{target_name}___{tool_name}"}}
        client_context_b64 = base64.b64encode(json.dumps(client_context).encode()).decode()

        response = client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
            ClientContext=client_context_b64,
        )

        response_payload = json.loads(response["Payload"].read().decode("utf-8"))
        return response_payload
    except boto3.exceptions.Boto3Error as e:
        print(f"AWS error invoking {function_name}: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"Failed to parse response from {function_name}: {e}")
        raise


def test_test_mcp():
    """Test the test-mcp Lambda."""
    print("\n" + "=" * 60)
    print("Testing: test-mcp Lambda")
    print("=" * 60)

    # Test hello tool
    print("\n[1] hello tool...")
    result = invoke_mcp_lambda("aiops-mcp-gateway-test-mcp", "test-mcp", "hello", {"name": "Claude"})
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test echo tool
    print("\n[2] echo tool...")
    result = invoke_mcp_lambda(
        "aiops-mcp-gateway-test-mcp", "test-mcp", "echo", {"message": "Hello from MCP Gateway!"}
    )
    print(f"Result: {json.dumps(result, indent=2)}")


def test_cost_explorer_mcp():
    """Test the cost-explorer-mcp Lambda."""
    print("\n" + "=" * 60)
    print("Testing: cost-explorer-mcp Lambda")
    print("=" * 60)

    # Test get_today_date tool
    print("\n[1] get_today_date tool...")
    result = invoke_mcp_lambda("aiops-mcp-gateway-cost-explorer-mcp", "cost-explorer-mcp", "get_today_date", {})
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test get_dimension_values tool
    print("\n[2] get_dimension_values tool (SERVICE)...")
    result = invoke_mcp_lambda(
        "aiops-mcp-gateway-cost-explorer-mcp", "cost-explorer-mcp", "get_dimension_values", {"dimension": "SERVICE"}
    )
    print(f"Result: {json.dumps(result, indent=2)[:500]}...")


def test_athena_mcp():
    """Test the athena-mcp Lambda."""
    print("\n" + "=" * 60)
    print("Testing: athena-mcp Lambda")
    print("=" * 60)

    # Test list_databases tool
    print("\n[1] list_databases tool...")
    result = invoke_mcp_lambda("aiops-mcp-gateway-athena-mcp", "athena-mcp", "list_databases", {})
    print(f"Result: {json.dumps(result, indent=2)[:500]}...")


def main():
    print("=" * 60)
    print("MCP Lambda Health Check")
    print("=" * 60)

    failures = []
    for test_fn in [test_test_mcp, test_cost_explorer_mcp, test_athena_mcp]:
        try:
            test_fn()
        except Exception as e:
            failures.append(f"{test_fn.__name__}: {e}")
            print(f"\nFAILED: {test_fn.__name__}: {e}")

    print("\n" + "=" * 60)
    if failures:
        print(f"Completed with {len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
    else:
        print("All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
