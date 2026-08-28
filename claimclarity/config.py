"""Model provider selection for every agent in ClaimClarity.

Mirrors bidwright/config.py deliberately - ClaimClarity is a separate,
independently deployable project, so it doesn't import from bidwright.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from strands import Agent

load_dotenv()

DEFAULT_ANTHROPIC_MODEL_ID = "claude-sonnet-4-5-20250929"
DEFAULT_BEDROCK_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"


def get_model():
    """Return a Strands model object/id, or None to let Strands use its own default.

    Resolution order:
      1. CLAIMCLARITY_MODEL_PROVIDER=anthropic|bedrock forces the provider.
      2. Otherwise, an ANTHROPIC_API_KEY in the environment selects Anthropic direct.
      3. Otherwise, AWS credentials being present selects Bedrock.
      4. Otherwise, None (Strands' own default resolution applies).
    """
    provider = os.environ.get("CLAIMCLARITY_MODEL_PROVIDER", "").strip().lower()
    has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_aws_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"))

    use_anthropic = provider == "anthropic" or (not provider and has_anthropic_key)
    use_bedrock = provider == "bedrock" or (not provider and not has_anthropic_key and has_aws_creds)

    if use_anthropic:
        from strands.models import AnthropicModel

        model_id = os.environ.get("CLAIMCLARITY_MODEL_ID", DEFAULT_ANTHROPIC_MODEL_ID)
        return AnthropicModel(
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
            model_id=model_id,
            max_tokens=4096,
        )

    if use_bedrock:
        return os.environ.get("CLAIMCLARITY_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

    return None


def create_agent(**kwargs) -> Agent:
    """Build a Strands Agent using ClaimClarity's configured model, unless the
    caller already specified one."""
    if "model" not in kwargs:
        model = get_model()
        if model is not None:
            kwargs["model"] = model
    return Agent(**kwargs)


def model_status() -> str:
    """Human-readable description of which provider/model will be used, for UI/CLI display."""
    provider = os.environ.get("CLAIMCLARITY_MODEL_PROVIDER", "").strip().lower()
    if provider == "anthropic" or (not provider and os.environ.get("ANTHROPIC_API_KEY")):
        model_id = os.environ.get("CLAIMCLARITY_MODEL_ID", DEFAULT_ANTHROPIC_MODEL_ID)
        return f"Anthropic API direct ({model_id})"
    if provider == "bedrock" or (
        not provider
        and not os.environ.get("ANTHROPIC_API_KEY")
        and (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"))
    ):
        model_id = os.environ.get("CLAIMCLARITY_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
        return f"Amazon Bedrock ({model_id})"
    return "No credentials found (set ANTHROPIC_API_KEY or configure AWS credentials)"
