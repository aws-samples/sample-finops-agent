#!/usr/bin/env python3
"""
Update Gateway target tool schemas.

The Terraform AWS provider only supports 1 tool_schema per Lambda target at
create time, but the AgentCore API supports multiple. After Terraform creates
the targets with a single placeholder schema, this script overwrites each
target's schema with the full tool list from terraform/tool-schemas/*.json.

Sources of truth (no hardcoding here):
  - Target registry (name, description, schema_file, lambda_arn):
      `terraform output -json gateway_target_schemas`
  - Tool schemas:
      `terraform/tool-schemas/<schema_file>`

Usage (via Makefile - recommended):
    make update-schemas    # Auto-gets GATEWAY_ID from terraform output
    make deploy            # Runs apply + update-schemas

Usage (direct):
    GATEWAY_ID=<gateway-id> python3 scripts/update_tool_schemas.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
# GATEWAY_ID is set automatically by Makefile from terraform output.
GATEWAY_ID = os.environ.get("GATEWAY_ID", "")

REPO_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = REPO_ROOT / "terraform"
SCHEMA_DIR = TERRAFORM_DIR / "tool-schemas"


def load_target_registry() -> dict[str, dict]:
    """Read `gateway_target_schemas` from terraform output.

    Returns {target_name: {"schema_file", "description", "lambda_arn"}}.
    """
    result = subprocess.run(
        ["terraform", "output", "-json", "gateway_target_schemas"],
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def load_tools(schema_file: str) -> list[dict]:
    """Load a tool-schema JSON file (a bare list of tool objects)."""
    with (SCHEMA_DIR / schema_file).open() as f:
        return json.load(f)


def update_target(client, gateway_id: str, name_to_id: dict[str, str], name: str, meta: dict) -> bool:
    """Overwrite a gateway target's tool schema with the full tool list."""
    print(f"\nUpdating {name}...")
    target_id = name_to_id.get(name)
    if not target_id:
        print(f"  Target {name} not found!")
        return False

    tools = load_tools(meta["schema_file"])
    print(f"  Target ID: {target_id}")
    print(f"  Tools: {len(tools)}")

    try:
        client.update_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
            name=name,
            description=meta["description"],
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": meta["lambda_arn"],
                        "toolSchema": {"inlinePayload": tools},
                    }
                }
            },
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        print("  Updated successfully!")
        return True
    except ClientError as e:
        print(f"  Error: {e}")
        return False


def main():
    if not GATEWAY_ID:
        print("Error: GATEWAY_ID environment variable not set.")
        print("Run via 'make update-schemas' or 'make deploy' which sets it automatically.")
        print("Or set manually: GATEWAY_ID=<your-gateway-id> python scripts/update_tool_schemas.py")
        sys.exit(1)

    try:
        targets = load_target_registry()
    except subprocess.CalledProcessError as e:
        print(f"Error reading terraform output 'gateway_target_schemas': {e.stderr}")
        print("Run 'make apply' first so the output exists.")
        sys.exit(1)

    print("=" * 60)
    print("Updating Gateway Target Tool Schemas")
    print("=" * 60)

    session = boto3.Session(profile_name=AWS_PROFILE)
    client = session.client("bedrock-agentcore-control", region_name=AWS_REGION)

    # Resolve target names -> IDs once (the full list is stable across this run).
    listing = client.list_gateway_targets(gatewayIdentifier=GATEWAY_ID, maxResults=100)
    name_to_id = {t["name"]: t["targetId"] for t in listing.get("items", [])}

    success_count = sum(
        update_target(client, GATEWAY_ID, name_to_id, name, meta)
        for name, meta in targets.items()
    )

    print("\n" + "=" * 60)
    print(f"Updated {success_count}/{len(targets)} targets")
    print("=" * 60)

    print("\nVerifying targets...")
    for target in client.list_gateway_targets(gatewayIdentifier=GATEWAY_ID, maxResults=100).get("items", []):
        print(f"  {target['name']}: {target['status']}")


if __name__ == "__main__":
    main()
