"""Normalizes remote invocation payloads (e.g. from AgentCore Runtime) into
local file paths for run_bid_job.

Kept separate from agentcore_app.py so it's importable and unit-testable
without the optional `bedrock_agentcore` runtime package installed.
"""
from __future__ import annotations

from pathlib import Path


def resolve_input_paths(payload: dict, workdir: str) -> tuple[str, str]:
    """Return (rfp_path, profile_path) for run_bid_job.

    Each of the RFP and the company profile can be provided either as
    `<field>_path` (a file already present on disk - e.g. the bundled example
    data) or `<field>_text` (inline content, written to a temp file). A real
    remote caller has no filesystem access to the deployed container, so
    `_text` is the shape that matters in production; `_path` mainly exists
    for local testing against the bundled examples.

    Raises:
        KeyError: if neither form is provided for a required document.
    """
    work_path = Path(workdir)
    work_path.mkdir(parents=True, exist_ok=True)

    rfp_path = _resolve_one(payload, "rfp", work_path)
    profile_path = _resolve_one(payload, "profile", work_path)
    return rfp_path, profile_path


def _resolve_one(payload: dict, field: str, work_path: Path) -> str:
    path_key, text_key = f"{field}_path", f"{field}_text"
    if payload.get(path_key):
        return payload[path_key]
    if payload.get(text_key) is not None:
        dest = work_path / f"{field}.md"
        dest.write_text(payload[text_key], encoding="utf-8")
        return str(dest)
    raise KeyError(
        f"Payload must include either '{path_key}' (a file path already present in this "
        f"deployment) or '{text_key}' (inline document text)."
    )
