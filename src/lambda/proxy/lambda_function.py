"""
Lambda proxy for Amazon Bedrock AgentCore MCP (Model Context Protocol) runtime.
Forwards MCP requests to the hosted runtime using InvokeAgentRuntime API.

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""

import contextlib
import json
import os
import uuid

import boto3


RUNTIME_ARN = os.environ.get("RUNTIME_ARN")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Store session ID per Lambda execution context for session continuity
session_id = None


def get_or_create_session_id():
    """Get existing session ID or create a new one."""
    global session_id
    if session_id is None:
        session_id = str(uuid.uuid4())
    return session_id


def invoke_mcp_runtime(mcp_request: dict) -> dict:
    """Invoke MCP method using InvokeAgentRuntime API."""
    client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)

    # Serialize MCP request
    payload = json.dumps(mcp_request).encode("utf-8")

    print(f"Invoking runtime: {RUNTIME_ARN}")
    print(f"Payload: {mcp_request}")

    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=RUNTIME_ARN,
            payload=payload,
            contentType="application/json",
            accept="application/json, text/event-stream",
            mcpSessionId=get_or_create_session_id(),
        )

        print(f"Response metadata: {response.get('ResponseMetadata')}")
        print(f"Content-Type: {response.get('contentType')}")

        # Read the streaming response
        content_type = response.get("contentType", "")

        if "text/event-stream" in content_type:
            # Handle SSE streaming response
            body_stream = response.get("body") or response.get("response")
            chunks = []
            for chunk in body_stream:
                if isinstance(chunk, bytes):
                    chunks.append(chunk.decode("utf-8"))
                elif isinstance(chunk, dict) and "chunk" in chunk:
                    chunks.append(chunk["chunk"].get("bytes", b"").decode("utf-8"))

            full_response = "".join(chunks)
            print(f"SSE Response: {full_response[:1000]}")

            # Parse SSE data events
            result_data = None
            for line in full_response.split("\n"):
                if line.startswith("data: "):
                    with contextlib.suppress(json.JSONDecodeError):
                        result_data = json.loads(line[6:])

            return result_data if result_data else {"raw": full_response}
        else:
            # Handle JSON response
            body_stream = response.get("body") or response.get("response")
            chunks = []
            for chunk in body_stream:
                if isinstance(chunk, bytes):
                    chunks.append(chunk.decode("utf-8"))
                elif isinstance(chunk, dict) and "chunk" in chunk:
                    chunks.append(chunk["chunk"].get("bytes", b"").decode("utf-8"))

            full_response = "".join(chunks)
            print(f"JSON Response: {full_response[:1000]}")

            try:
                return json.loads(full_response)
            except json.JSONDecodeError:
                return {"raw": full_response}

    except Exception as e:
        print(f"InvokeAgentRuntime error: {e}")
        raise


def detect_tool_from_args(args: dict) -> str:
    """Detect which tool is being called based on arguments."""
    if "cli_command" in args:
        return "call_aws"
    elif "query" in args:
        return "suggest_aws_commands"
    return None


def lambda_handler(event, context):
    """Lambda handler for MCP proxy requests."""
    print(f"Received event: {json.dumps(event)}")

    # Extract request body
    if "body" in event:
        body = event["body"]
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode("utf-8")
        request = json.loads(body) if isinstance(body, str) else body
    else:
        request = event

    # Check if this is a gateway tool call (no 'method' field, just tool arguments)
    # Gateway sends: {"cli_command": "aws s3 ls"} or {"query": "list buckets"}
    if "method" not in request and ("cli_command" in request or "query" in request):
        # This is a gateway tool invocation - detect tool and build MCP request
        tool_name = detect_tool_from_args(request)
        print(f"Gateway tool call detected: {tool_name}")
        method = "tools/call"
        params = {"name": tool_name, "arguments": request}
        request_id = 1
    else:
        # Standard JSON-RPC request
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id", 1)

    # Build MCP JSON-RPC request
    mcp_request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    try:
        # Invoke the MCP runtime
        result = invoke_mcp_runtime(mcp_request)

        # If result is already a JSON-RPC response, return it
        if isinstance(result, dict) and "jsonrpc" in result:
            return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(result)}

        # Otherwise wrap in JSON-RPC response
        response_body = {"jsonrpc": "2.0", "id": request_id, "result": result}

        return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(response_body)}

    except Exception as e:
        import traceback

        print(f"Error: {e}")
        traceback.print_exc()
        error_body = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(e)}}
        return {"statusCode": 500, "headers": {"Content-Type": "application/json"}, "body": json.dumps(error_body)}
