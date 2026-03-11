#!/usr/bin/env python3
"""
Script to invoke the finops-mcp-proxy Lambda function.
Usage: python invoke_lambda.py
"""

import json
import os

import boto3


LAMBDA_FUNCTION_NAME = "finops-mcp-proxy"
AWS_REGION = "us-east-1"
AWS_PROFILE = os.environ.get("AWS_PROFILE", "root")


def invoke_lambda(payload: dict) -> dict:
    """Invoke the Lambda function with the given payload."""
    session = boto3.Session(profile_name=AWS_PROFILE)
    client = session.client("lambda", region_name=AWS_REGION)

    response = client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )

    response_payload = json.loads(response["Payload"].read().decode("utf-8"))
    return response_payload


def mcp_initialize() -> dict:
    """Send MCP initialize request."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    return invoke_lambda(payload)


def mcp_list_tools() -> dict:
    """Send MCP tools/list request."""
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    return invoke_lambda(payload)


def mcp_call_tool(tool_name: str, arguments: dict) -> dict:
    """Send MCP tools/call request."""
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    return invoke_lambda(payload)


def main():
    print("=" * 60)
    print("Testing finops-mcp-proxy Lambda")
    print("=" * 60)

    # Test 1: Initialize
    print("\n[1] MCP Initialize...")
    result = mcp_initialize()
    print(f"Status: {result.get('statusCode')}")
    if result.get("body"):
        body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
        print(f"Response: {json.dumps(body, indent=2)[:500]}")

    # Test 2: List Tools
    print("\n[2] MCP List Tools...")
    result = mcp_list_tools()
    print(f"Status: {result.get('statusCode')}")
    if result.get("body"):
        body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
        print(f"Response: {json.dumps(body, indent=2)[:1000]}")

    # Test 3: Call a tool (suggest_aws_commands)
    print("\n[3] MCP Call Tool: suggest_aws_commands...")
    result = mcp_call_tool(
        "suggest_aws_commands",
        {"query": "list all S3 buckets"},
    )
    print(f"Status: {result.get('statusCode')}")
    if result.get("body"):
        body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
        print(f"Response: {json.dumps(body, indent=2)[:1000]}")

    # Test 4: Call a tool (call_aws)
    print("\n[4] MCP Call Tool: call_aws...")
    result = mcp_call_tool(
        "call_aws",
        {"cli_command": "aws sts get-caller-identity"},
    )
    print(f"Status: {result.get('statusCode')}")
    if result.get("body"):
        body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
        print(f"Response: {json.dumps(body, indent=2)[:1000]}")


if __name__ == "__main__":
    main()
