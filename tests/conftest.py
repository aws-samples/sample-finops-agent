"""Shared fixtures for RAGAS agentic evals."""

import os
from pathlib import Path

import pytest
from langchain_aws import ChatBedrock
from ragas.llms import LangchainLLMWrapper

from tests.helpers.gateway_client import GatewayMCPClient
from tests.helpers.ground_truth import GroundTruthClient


ENV_FILE = Path(__file__).parent.parent / "terraform" / "config" / ".env"


def _load_env_file():
    """Load key=value pairs from terraform/config/.env into os.environ.

    Skips comments, blank lines, and does not override existing env vars.
    """
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Don't override vars already set in the environment
        if key not in os.environ:
            os.environ[key] = value


# Load .env at import time so all fixtures see the config
_load_env_file()


@pytest.fixture(scope="session")
def gateway() -> GatewayMCPClient:
    """MCP Gateway client — requires GATEWAY_ID and a cached JWT token."""
    gateway_id = os.environ.get("GATEWAY_ID")
    if not gateway_id:
        pytest.skip("GATEWAY_ID not set — run 'make test-setup' first")
    try:
        return GatewayMCPClient(gateway_id=gateway_id)
    except ValueError as e:
        pytest.skip(str(e))


@pytest.fixture(scope="session")
def ground_truth() -> GroundTruthClient:
    """Direct AWS API client for ground truth comparison.

    Uses GROUND_TRUTH_PROFILE (management account in cross-account setups).
    """
    return GroundTruthClient()


@pytest.fixture(scope="session")
def evaluator_llm() -> LangchainLLMWrapper:
    """Bedrock Claude as LLM judge for AspectCritic / AgentGoalAccuracy metrics."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    return LangchainLLMWrapper(
        ChatBedrock(
            model_id="anthropic.claude-sonnet-4-20250514",
            region_name=region,
        )
    )
