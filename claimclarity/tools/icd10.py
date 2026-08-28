"""ICD-10-CM diagnosis code grounding.

This is what keeps ClaimClarity's coding analysis from being an LLM's guess:
every diagnosis code on a claim gets checked against real code data instead
of being reasoned about from the model's training data alone (which is a
common source of confidently wrong billing advice - deprecated codes like
M54.5 "look" fine to a model that isn't checking).

The bundled reference set in data/icd10_reference.json is a small, curated
subset of the FY2026 ICD-10-CM code set, verified against an authoritative
ICD-10 lookup service during development (see README for how each entry was
sourced). It intentionally covers only the code families used in this
project's example scenario. For production use, swap `_load_reference_data`
for a live ICD-10 API or MCP-backed lookup - the two functions below are
written so that's a drop-in change; only this module needs to be replaced.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from strands import tool

_DATA_PATH = Path(__file__).parent.parent / "data" / "icd10_reference.json"


@lru_cache(maxsize=1)
def _load_reference_data() -> dict[str, dict]:
    raw = json.loads(_DATA_PATH.read_text())
    return {entry["code"]: entry for entry in raw["codes"]}


@tool
def lookup_icd10_code(code: str) -> str:
    """Look up a specific ICD-10-CM diagnosis code and report whether it is
    valid/billable, or if it's a non-billable category header (a common,
    entirely mechanical cause of claim denials).

    Args:
        code: The ICD-10-CM code as it appears on the claim, e.g. "M54.5".

    Returns:
        A plain-language report of the code's status.
    """
    data = _load_reference_data()
    normalized = code.strip().upper()
    entry = data.get(normalized)
    if entry is None:
        return (
            f"'{code}' is not in ClaimClarity's bundled reference set (which covers only this "
            "project's demo code families). Treat this as inconclusive rather than a denial finding - "
            "verify against a full ICD-10 source before drawing a conclusion."
        )
    if entry["billable"]:
        return f"{normalized} ({entry['short_description']}) is a valid, billable ICD-10-CM code."
    return (
        f"{normalized} ({entry['short_description']}) is NOT billable - "
        f"{entry.get('note', 'it is a category header, not a specific billable code.')}"
    )


@tool
def search_icd10_codes(query: str) -> str:
    """Search ClaimClarity's bundled ICD-10-CM reference set for billable
    codes matching a diagnosis description, to find the correct specific code
    when a claim was billed with an invalid or non-specific one.

    Args:
        query: A diagnosis description to search for, e.g. "low back pain".

    Returns:
        A list of matching billable codes with their descriptions.
    """
    data = _load_reference_data()
    query_lower = query.strip().lower()
    matches = [
        entry
        for entry in data.values()
        if entry["billable"] and query_lower in entry["short_description"].lower()
    ]
    if not matches:
        return (
            f"No billable codes matching '{query}' found in ClaimClarity's bundled reference set "
            "(a small demo subset, not the full code system)."
        )
    lines = [f"- {m['code']}: {m['short_description']}" for m in matches]
    return "Billable codes matching '" + query + "':\n" + "\n".join(lines)
