#!/usr/bin/env python3
"""End-to-end smoke test: fetch Cognito token, call Gateway /mcp, assert 200."""

import json
import os
import subprocess
import sys

import httpx


def tf_out(name: str) -> str:
    r = subprocess.run(
        ["terraform", "-chdir=terraform", "output", "-raw", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    gateway_url = os.environ.get("GATEWAY_MCP_URL") or tf_out("gateway_endpoint")
    client_id = tf_out("gateway_cognito_client_id")
    client_secret = tf_out("gateway_cognito_client_secret")
    token_url = tf_out("gateway_cognito_token_url")
    scope = tf_out("gateway_cognito_scope")

    for k, v in {
        "gateway_url": gateway_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_url": token_url,
        "scope": scope,
    }.items():
        if not v:
            print(f"ERROR: missing {k} (run `make apply` first?)", file=sys.stderr)
            return 2

    tok_resp = httpx.post(
        token_url,
        data={"grant_type": "client_credentials", "scope": scope},
        auth=(client_id, client_secret),
        timeout=30,
    )
    if tok_resp.status_code != 200:
        print(f"Token fetch failed: {tok_resp.status_code} {tok_resp.text}", file=sys.stderr)
        return 1
    access_token = tok_resp.json()["access_token"]
    print(f"Got access_token (len={len(access_token)})")

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
    )
    resp = httpx.post(
        gateway_url,
        content=body,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        timeout=30,
    )
    print(f"Gateway status: {resp.status_code}")
    print(f"Gateway body:   {resp.text[:400]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
