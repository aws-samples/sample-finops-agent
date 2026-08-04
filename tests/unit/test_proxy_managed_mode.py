"""Offline unit tests for lambda-proxy managed-endpoint mode. No AWS calls."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


PROXY = Path(__file__).parents[2] / "src" / "lambda" / "proxy" / "lambda_function.py"


def load_proxy(monkeypatch, **env):
    for k in ("AWS_MCP_ENDPOINT", "MEMBER_ROLE_NAME", "MEMBER_ROLE_EXTERNAL_ID", "RUNTIME_ARN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("proxy_mod", PROXY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_credentials_none_assumes_role_in_own_account(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Arn": "arn:aws:sts::999988887777:assumed-role/proxy-role/x"}
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AK",
            "SecretAccessKey": "SK",
            "SessionToken": "ST",
            "Expiration": mod.datetime.now(mod.UTC) + mod.timedelta(hours=1),
        }
    }
    with patch.object(mod.boto3, "client", return_value=sts):
        mod._CRED_CACHE.clear()
        mod._OWN_IDENTITY.clear()
        creds = mod.resolve_credentials(None)
    # None -> assume the same role in the proxy's own account (partition derived, not hardcoded)
    assert sts.assume_role.call_args.kwargs["RoleArn"] == "arn:aws:iam::999988887777:role/finops-readonly"
    assert creds.access_key == "AK"


def test_resolve_credentials_assumes_member_role_with_external_id(monkeypatch):
    mod = load_proxy(
        monkeypatch,
        AWS_MCP_ENDPOINT="https://example.test/mcp",
        MEMBER_ROLE_NAME="finops-readonly",
        MEMBER_ROLE_EXTERNAL_ID="xyz",
    )
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Arn": "arn:aws:sts::999988887777:assumed-role/proxy-role/x"}
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AK",
            "SecretAccessKey": "SK",
            "SessionToken": "ST",
            "Expiration": mod.datetime.now(mod.UTC) + mod.timedelta(hours=1),
        }
    }
    with patch.object(mod.boto3, "client", return_value=sts):
        mod._CRED_CACHE.clear()
        mod._OWN_IDENTITY.clear()
        creds = mod.resolve_credentials("111122223333")
    kwargs = sts.assume_role.call_args.kwargs
    assert kwargs["RoleArn"] == "arn:aws:iam::111122223333:role/finops-readonly"
    assert kwargs["ExternalId"] == "xyz"
    assert creds.access_key == "AK" and creds.token == "ST"


def test_mcp_client_call_tool_signs_and_unwraps(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    responses = [
        (200, {"Mcp-Session-Id": "s1"}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}})),
        (202, {}, ""),
        (
            200,
            {},
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "content": [{"type": "text", "text": '{"ok": true}'}],
                        "structuredContent": {"ok": True},
                        "isError": False,
                    },
                }
            ),
        ),
    ]
    sent = []

    def fake_post(url, data, headers):
        sent.append((url, json.loads(data) if data else None, headers))
        return responses[len(sent) - 1]

    creds = mod.ReadOnlyCredentials("AK", "SK", "ST")
    client = mod.McpEndpointClient("https://example.test/mcp", creds)
    with patch.object(client, "_post", side_effect=fake_post):
        result = client.call_tool("aws___run_script", {"code": "result = 1"})
    assert result == {"ok": True}
    assert sent[0][1]["method"] == "initialize"
    assert sent[1][1]["method"] == "notifications/initialized"
    assert sent[1][2].get("Mcp-Session-Id") == "s1"
    assert sent[2][1]["params"] == {"name": "aws___run_script", "arguments": {"code": "result = 1"}}


def _ctx(tool):
    ctx = MagicMock()
    ctx.client_context.custom = {"bedrockAgentCoreToolName": f"aws-api-mcp___{tool}"}
    return ctx


def test_handler_list_member_accounts(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    orgs = MagicMock()
    orgs.get_paginator.return_value.paginate.return_value = [
        {"Accounts": [{"Id": "111122223333", "Name": "dev", "Status": "ACTIVE"}]}
    ]
    with patch.object(mod.boto3, "client", return_value=orgs):
        out = mod.lambda_handler({}, _ctx("list_member_accounts"))
    assert out == {"accounts": [{"account_id": "111122223333", "name": "dev", "status": "ACTIVE"}], "count": 1}


def test_handler_run_script_strips_account_id_and_forwards(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    with (
        patch.object(mod, "resolve_credentials", return_value="CREDS") as rc,
        patch.object(mod.McpEndpointClient, "call_tool", return_value={"ok": True}) as ct,
    ):
        out = mod.lambda_handler({"code": "result = 1", "account_id": "111122223333"}, _ctx("run_script"))
    rc.assert_called_once_with("111122223333")
    ct.assert_called_once_with("aws___run_script", {"code": "result = 1"})
    assert out == {"ok": True}


def test_handler_run_script_assume_failure_returns_structured_error(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    with patch.object(mod, "resolve_credentials", side_effect=Exception("AccessDenied")):
        out = mod.lambda_handler({"code": "x", "account_id": "111122223333"}, _ctx("run_script"))
    assert "error" in out and "111122223333" in out["error"]


def test_handler_legacy_mode_untouched(monkeypatch):
    mod = load_proxy(monkeypatch)  # AWS_MCP_ENDPOINT unset
    with patch.object(mod, "invoke_mcp_runtime", return_value={"jsonrpc": "2.0", "id": 1, "result": {}}) as im:
        out = mod.lambda_handler({"cli_command": "aws s3 ls"}, MagicMock())
    im.assert_called_once()
    assert out["statusCode"] == 200


def test_call_tool_surfaces_jsonrpc_error(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    responses = [
        (200, {"Mcp-Session-Id": "s1"}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})),
        (202, {}, ""),
        (200, {}, json.dumps({"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": "NameError: x"}})),
    ]
    client = mod.McpEndpointClient("https://example.test/mcp", mod.ReadOnlyCredentials("AK", "SK", "ST"))
    with patch.object(client, "_post", side_effect=lambda *a: responses.pop(0)):
        out = client.call_tool("aws___run_script", {"code": "x"})
    assert out["isError"] is True and "NameError" in out["error"]


def test_call_tool_parses_sse_framed_body(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    sse = 'data: {"jsonrpc": "2.0", "id": 2, "result": {"structuredContent": {"ok": 1}}}\n\n'
    responses = [
        (200, {"Mcp-Session-Id": "s1"}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})),
        (202, {}, ""),
        (200, {}, sse),
    ]
    client = mod.McpEndpointClient("https://example.test/mcp", mod.ReadOnlyCredentials("AK", "SK", "ST"))
    with patch.object(client, "_post", side_effect=lambda *a: responses.pop(0)):
        out = client.call_tool("aws___run_script", {"code": "x"})
    assert out == {"ok": 1}


def test_handler_run_script_mcp_failure_returns_structured_error(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    with (
        patch.object(mod, "resolve_credentials", return_value="CREDS"),
        patch.object(mod.McpEndpointClient, "call_tool", side_effect=RuntimeError("endpoint unreachable")),
    ):
        out = mod.lambda_handler({"code": "x"}, _ctx("run_script"))
    assert out["isError"] is True and "unreachable" in out["error"]


def test_handler_unresolvable_tool_fails_loudly(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    orgs_guard = MagicMock()
    with patch.object(mod.boto3, "client", return_value=orgs_guard):
        # No client_context tool name, no 'code' key -> must NOT silently list accounts
        out = mod.lambda_handler({"query": "list buckets"}, MagicMock(client_context=None))
    orgs_guard.get_paginator.assert_not_called()
    assert "error" in out


def test_handler_knowledge_tool_routes_without_account_id(monkeypatch):
    mod = load_proxy(monkeypatch, AWS_MCP_ENDPOINT="https://example.test/mcp")
    captured = {}

    def fake_call_tool(self, name, arguments):
        captured["name"] = name
        captured["arguments"] = arguments
        return {"content": "doc"}

    with (
        patch.object(mod, "resolve_credentials", return_value="creds"),
        patch.object(mod.McpEndpointClient, "call_tool", fake_call_tool),
    ):
        out = mod.lambda_handler(
            {"skill_name": "aws-billing-and-cost-management", "account_id": "999988887777"},
            _ctx("get_aws_skill"),
        )

    # Upstream tool name is prefixed, and account_id is stripped: knowledge tools
    # read documentation, not the caller's resources.
    assert captured["name"] == "aws___retrieve_skill"
    assert captured["arguments"] == {"skill_name": "aws-billing-and-cost-management"}
    assert out == {"content": "doc"}
