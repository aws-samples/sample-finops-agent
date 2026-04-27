"""MCP client that calls tools through AgentCore Gateway via HTTP + JWT auth."""

import json
import os
import urllib.error
import urllib.request


class GatewayMCPClient:
    """MCP client that calls the Gateway endpoint with JWT Bearer token.

    The Gateway requires JWT auth from the configured IDP.
    Token is automatically obtained via OAuth2 PKCE flow if missing or expired.

    Tool names use the Gateway's `target___tool` format. The call_tool() method
    builds this automatically from the target and tool_name arguments.
    """

    def __init__(
        self,
        gateway_id: str | None = None,
        region: str | None = None,
        token: str | None = None,
    ):
        gateway_id = gateway_id or os.environ["GATEWAY_ID"]
        region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.gateway_url = f"https://{gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"

        # Token can be provided directly, from env, or auto-obtained
        self.token = token or os.environ.get("GATEWAY_TOKEN") or self._ensure_token()
        if not self.token:
            raise ValueError(
                "No Gateway JWT token available. Run 'make test-setup' first, "
                "then ensure GATEWAY_CLIENT_ID and related env vars are set."
            )

    @staticmethod
    def _ensure_token() -> str | None:
        """Get a valid token: return cached if valid, otherwise run OAuth flow."""
        from tests.helpers.oauth_token import get_cached_token, get_token_interactive

        cached = get_cached_token()
        if cached:
            return cached

        # Token missing or expired — run interactive flow
        try:
            return get_token_interactive()
        except RuntimeError:
            return None

    def _request(self, payload: dict) -> dict:
        """Make an HTTP POST to the Gateway with JWT auth."""
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.gateway_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                return json.loads(error_body)
            except json.JSONDecodeError:
                raise RuntimeError(f"Gateway returned HTTP {e.code}: {error_body}") from e

    def call_tool(self, target: str, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool through the Gateway.

        The Gateway expects tool names in `target___tool` format.
        Returns the parsed JSON-RPC response body.
        """
        gateway_tool_name = f"{target}___{tool_name}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": gateway_tool_name, "arguments": arguments},
        }
        return self._request(payload)

    def list_tools(self, target: str | None = None) -> list[dict]:
        """List available tools. Optionally filter by target prefix.

        When target is specified, filters to that target and strips the
        `target___` prefix from tool names for easier comparison.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        result = self._request(payload)
        tools = result.get("result", {}).get("tools", [])
        if target:
            prefix = f"{target}___"
            filtered = []
            for t in tools:
                if t["name"].startswith(prefix):
                    stripped = {**t, "name": t["name"][len(prefix) :]}
                    filtered.append(stripped)
            tools = filtered
        return tools

    def call_tool_extract(self, target: str, tool_name: str, arguments: dict) -> dict:
        """Call a tool and extract the content from the MCP response.

        The Gateway returns: result.content[0].text = stringified JSON.
        This method parses that inner JSON and returns it.
        """
        response = self.call_tool(target, tool_name, arguments)
        result = response.get("result", {})
        content_blocks = result.get("content", [])
        if not content_blocks:
            return result

        first_block = content_blocks[0]
        text = first_block.get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"text": text}
