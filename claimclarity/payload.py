"""Normalizes remote invocation payloads (e.g. from AgentCore Runtime) into
local file paths for run_claim_case.

Kept separate from agentcore_app_claimclarity.py so it's importable and
unit-testable without the optional `bedrock_agentcore` runtime package
installed.
"""
from __future__ import annotations

from pathlib import Path


def resolve_document_paths(payload: dict, workdir: str) -> list[str]:
    """Return a list of document paths for run_claim_case.

    Documents can be provided as `document_paths` (files already present on
    disk - e.g. the bundled example data), `document_texts` (a list of inline
    document text, each written to its own temp file), or both together. A
    real remote caller has no filesystem access to the deployed container, so
    `document_texts` is the shape that matters in production; `document_paths`
    mainly exists for local testing against the bundled examples.

    Raises:
        ValueError: if neither is provided.
    """
    paths = list(payload.get("document_paths") or [])
    texts = payload.get("document_texts") or []

    if not paths and not texts:
        raise ValueError(
            "Payload must include 'document_paths' (files already present in this "
            "deployment) and/or 'document_texts' (a list of inline document text)."
        )

    if texts:
        work_path = Path(workdir)
        work_path.mkdir(parents=True, exist_ok=True)
        for index, text in enumerate(texts):
            dest = work_path / f"document_{index}.md"
            dest.write_text(text, encoding="utf-8")
            paths.append(str(dest))

    return paths
