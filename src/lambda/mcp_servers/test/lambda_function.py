"""
Simple Test Lambda MCP Server

A minimal Lambda function to verify Gateway integration.
Implements two simple tools: hello and echo.
"""

import json


def lambda_handler(event, context):
    """
    Main Lambda handler for Gateway MCP tools.

    Gateway passes tool name via context.client_context.custom["bedrockAgentCoreToolName"]
    in format: <target_name>___<tool_name>
    """
    print(f"Event: {event}")
    print(f"Context: {context}")
    print(f"Client Context: {context.client_context}")

    # Get tool name from Gateway context
    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]

    # Extract actual tool name (format: targetname___toolname)
    tool_name = extended_tool_name.split("___")[1]

    print(f"Extended tool name: {extended_tool_name}")
    print(f"Tool name: {tool_name}")

    # Route to appropriate tool
    if tool_name == "hello":
        name = event.get("name", "World")
        result = {"message": f"Hello, {name}!", "tool": "hello", "gateway_integration": "working"}
    elif tool_name == "echo":
        message = event.get("message", "")
        if not message:
            return {"statusCode": 400, "body": json.dumps({"error": "message parameter is required"})}
        result = {"echoed_message": message, "tool": "echo", "message_length": len(message)}
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": f"Unknown tool: {tool_name}", "available_tools": ["hello", "echo"]}),
        }

    print(f"Result: {result}")
    return result
