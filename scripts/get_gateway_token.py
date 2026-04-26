#!/usr/bin/env python3
"""Fetch an access token from Cognito using client_credentials grant."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx


CACHE_PATH = Path(__file__).resolve().parents[1] / ".gateway-token.json"


def tf_out(name: str) -> str:
    r = subprocess.run(
        ["terraform", "-chdir=terraform", "output", "-raw", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--client-id", default=os.environ.get("GATEWAY_CLIENT_ID") or tf_out("gateway_cognito_client_id"))
    p.add_argument(
        "--client-secret", default=os.environ.get("GATEWAY_CLIENT_SECRET") or tf_out("gateway_cognito_client_secret")
    )
    p.add_argument("--token-url", default=os.environ.get("GATEWAY_TOKEN_URL") or tf_out("gateway_cognito_token_url"))
    p.add_argument("--scope", default=os.environ.get("GATEWAY_SCOPE") or tf_out("gateway_cognito_scope"))
    args = p.parse_args()

    missing = [k for k, v in vars(args).items() if not v]
    if missing:
        print(f"ERROR: missing required values: {missing}", file=sys.stderr)
        return 2

    resp = httpx.post(
        args.token_url,
        data={"grant_type": "client_credentials", "scope": args.scope},
        auth=(args.client_id, args.client_secret),
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"ERROR: token endpoint returned {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    body = resp.json()
    CACHE_PATH.write_text(json.dumps(body, indent=2))
    print(f"access_token (expires in {body.get('expires_in')}s):")
    print(body["access_token"])
    print(f"\nCached to: {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
