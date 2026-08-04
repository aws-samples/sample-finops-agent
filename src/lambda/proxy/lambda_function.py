"""
Lambda proxy for Amazon Bedrock AgentCore MCP (Model Context Protocol) runtime.
Forwards MCP requests to the hosted runtime using InvokeAgentRuntime API.

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""

import contextlib
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials


RUNTIME_ARN = os.environ.get("RUNTIME_ARN")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ---- Managed AWS MCP Server mode (enabled when AWS_MCP_ENDPOINT is set) ----
AWS_MCP_ENDPOINT = os.environ.get("AWS_MCP_ENDPOINT", "")
AWS_MCP_SIGNING_REGION = os.environ.get("AWS_MCP_SIGNING_REGION", "us-east-1")
AWS_MCP_SIGNING_SERVICE = "aws-mcp"
MEMBER_ROLE_NAME = os.environ.get("MEMBER_ROLE_NAME", "finops-readonly")
MEMBER_ROLE_EXTERNAL_ID = os.environ.get("MEMBER_ROLE_EXTERNAL_ID", "")

# account_id -> (expiry_datetime, ReadOnlyCredentials); module-global for warm reuse
_CRED_CACHE: dict = {}

# (partition, account_id) of this Lambda's own identity; resolved once per container
_OWN_IDENTITY: list = []

# Store session ID per Lambda execution context for session continuity
session_id = None


def _own_identity():
    """Return (partition, account_id) for this Lambda, cached for warm reuse."""
    if not _OWN_IDENTITY:
        arn = boto3.client("sts").get_caller_identity()["Arn"]
        _OWN_IDENTITY.append((arn.split(":")[1], arn.split(":")[4]))
    return _OWN_IDENTITY[0]


def resolve_credentials(account_id):
    """AssumeRole into <account>/<MEMBER_ROLE_NAME> — the payer's own account when account_id is None.

    The proxy's execution role is a pure pipe (STS + Organizations only); all AWS
    read access comes from the per-account role, keeping one permission model for
    payer and member accounts alike.
    """
    partition, own_account = _own_identity()
    account_id = account_id or own_account
    cached = _CRED_CACHE.get(account_id)
    if cached and cached[0] - datetime.now(UTC) > timedelta(minutes=5):
        return cached[1]
    params = {
        "RoleArn": f"arn:{partition}:iam::{account_id}:role/{MEMBER_ROLE_NAME}",
        "RoleSessionName": "finops-mcp-proxy",
        "DurationSeconds": 3600,
    }
    if MEMBER_ROLE_EXTERNAL_ID:
        params["ExternalId"] = MEMBER_ROLE_EXTERNAL_ID
    c = boto3.client("sts").assume_role(**params)["Credentials"]
    creds = ReadOnlyCredentials(c["AccessKeyId"], c["SecretAccessKey"], c["SessionToken"])
    _CRED_CACHE[account_id] = (c["Expiration"], creds)
    return creds


class McpEndpointClient:
    """Minimal MCP streamable-HTTP client with SigV4 signing (stdlib + botocore only)."""

    def __init__(self, endpoint, creds, region=AWS_MCP_SIGNING_REGION, service=AWS_MCP_SIGNING_SERVICE):
        self.endpoint = endpoint
        self.creds = creds
        self.region = region
        self.service = service

    def _post(self, url, data, headers):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=110) as resp:
                return resp.status, dict(resp.headers), resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode()
        except urllib.error.URLError as e:
            raise RuntimeError(f"MCP endpoint unreachable ({e.reason})") from e

    def _signed_post(self, body, mcp_session_id=None):
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if mcp_session_id:
            headers["Mcp-Session-Id"] = mcp_session_id
        aws_req = AWSRequest(method="POST", url=self.endpoint, data=data, headers=headers)
        SigV4Auth(self.creds, self.service, self.region).add_auth(aws_req)
        return self._post(self.endpoint, data, dict(aws_req.headers))

    def call_tool(self, name, arguments):
        status, hdrs, body = self._signed_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "finops-mcp-proxy", "version": "1.0"},
                },
            }
        )
        if status != 200:
            raise RuntimeError(f"MCP initialize failed: HTTP {status}: {body[:300]}")
        sid = hdrs.get("Mcp-Session-Id") or hdrs.get("mcp-session-id")
        self._signed_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        status, _, body = self._signed_post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}, sid
        )
        if status != 200:
            raise RuntimeError(f"MCP tools/call failed: HTTP {status}: {body[:300]}")
        # The endpoint may answer in SSE framing (Accept includes text/event-stream);
        # extract the last `data:` payload before parsing.
        if body.lstrip().startswith(("data:", "event:")):
            data_lines = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
            body = data_lines[-1] if data_lines else body
        response = json.loads(body)
        if "error" in response:
            err = response["error"]
            return {"error": f"MCP error {err.get('code')}: {err.get('message', 'unknown')}", "isError": True}
        result = response.get("result", {})
        if "structuredContent" in result:
            return result["structuredContent"]
        for item in result.get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"text": item["text"], "isError": result.get("isError", False)}
        return result


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


def _managed_tool_name(event, context):
    try:
        name = context.client_context.custom["bedrockAgentCoreToolName"]
        return name.split("___")[1]
    except (AttributeError, KeyError, TypeError, IndexError):
        # Direct invocations (tests, smoke scripts) carry no Gateway tool header;
        # infer run_script only from an explicit 'code' argument — never guess
        # list_member_accounts, so misrouted events fail loudly instead of
        # silently enumerating the organization.
        if "code" in event:
            print("No bedrockAgentCoreToolName in client_context; inferred run_script from 'code' argument")
            return "run_script"
        return None


def _handle_list_member_accounts():
    orgs = boto3.client("organizations")
    accounts = [
        {"account_id": a["Id"], "name": a["Name"], "status": a["Status"]}
        for page in orgs.get_paginator("list_accounts").paginate()
        for a in page.get("Accounts", [])
    ]
    return {"accounts": accounts, "count": len(accounts)}


def _handle_run_script(event):
    args = dict(event)
    account_id = args.pop("account_id", None)
    if "code" not in args:
        return {"error": "run_script requires a 'code' argument"}
    try:
        creds = resolve_credentials(account_id)
    except Exception as e:
        # account_id is None for a local query, so name the account explicitly —
        # "account None" reads like a bug to whoever sees the error.
        target = account_id or _own_identity()[1]
        return {
            "error": f"Cannot assume role in account {target}: {e}. "
            f"Ensure role '{MEMBER_ROLE_NAME}' exists there and trusts this account."
        }
    client = McpEndpointClient(AWS_MCP_ENDPOINT, creds)
    try:
        return client.call_tool("aws___run_script", {"code": args["code"]})
    except (RuntimeError, json.JSONDecodeError) as e:
        return {"error": f"Managed MCP call failed: {e}", "isError": True}


# Knowledge tools read AWS documentation instead of the caller's resources, so
# they run under the proxy's own credentials — no member role, no account_id.
_KNOWLEDGE_TOOLS = {
    "search_documentation": "aws___search_documentation",
    "read_documentation": "aws___read_documentation",
    "get_aws_skill": "aws___retrieve_skill",
}


def _handle_knowledge_tool(tool, event):
    args = {k: v for k, v in event.items() if k != "account_id"}
    client = McpEndpointClient(AWS_MCP_ENDPOINT, resolve_credentials(None))
    try:
        return client.call_tool(_KNOWLEDGE_TOOLS[tool], args)
    except (RuntimeError, json.JSONDecodeError) as e:
        return {"error": f"Managed MCP call failed: {e}", "isError": True}


def _legacy_handler(event, context):
    """Legacy handler body — event is already the parsed request dict."""
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


def lambda_handler(event, context):
    """Lambda handler for MCP proxy requests."""
    print(f"Received event: {json.dumps(event)}")
    if "body" in event:
        body = event["body"]
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode("utf-8")
        event = json.loads(body) if isinstance(body, str) else body

    if AWS_MCP_ENDPOINT:
        tool = _managed_tool_name(event, context)
        print(f"Managed mode tool: {tool}")
        if tool == "list_member_accounts":
            return _handle_list_member_accounts()
        if tool == "run_script":
            return _handle_run_script(event)
        if tool in _KNOWLEDGE_TOOLS:
            return _handle_knowledge_tool(tool, event)
        return {
            "error": f"Unknown or unresolvable tool: {tool}",
            "available_tools": ["run_script", "list_member_accounts", *_KNOWLEDGE_TOOLS],
        }

    return _legacy_handler(event, context)
