"""State Department of Insurance (DOI) complaint process and independent
external review reference data.

This is what keeps the escalation advisor from inventing a deadline window
or a regulator name: every fact about a state's process comes from the
bundled reference set in data/state_doi_reference.json rather than a
language model's guess. The bundled set is a curated sample of 10 states
plus a federal-fallback DEFAULT entry (the genuine, stable ACA baseline -
45 CFR 147.136) - see that file's `_source_note` for what was and wasn't
independently verified. For production use, swap `_load_reference_data` for
a maintained/live source covering all 50 states + DC, the same way
claimclarity/tools/icd10.py documents doing for ICD-10 data - only this
module needs to be replaced.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from strands import tool

from claimclarity.models import StateDOIInfo

_DATA_PATH = Path(__file__).parent.parent / "data" / "state_doi_reference.json"


@lru_cache(maxsize=1)
def _load_reference_data() -> dict[str, dict]:
    raw = json.loads(_DATA_PATH.read_text())
    return raw["states"]


def lookup_state_doi_process(state: str) -> StateDOIInfo:
    """Look up the Department of Insurance complaint process and independent
    external review framework for a US state.

    Falls back to the federal-fallback DEFAULT entry (the general ACA
    external review baseline) when the state is blank, unrecognized, or not
    in the bundled sample - a patient always has *some* applicable
    framework, even when their exact state can't be determined.

    Args:
        state: A two-letter USPS state abbreviation, e.g. "CA". Case- and
            whitespace-insensitive.

    Returns:
        A StateDOIInfo - never None, so callers don't need to handle a
        missing-lookup case separately from an unknown state.
    """
    data = _load_reference_data()
    normalized = (state or "").strip().upper()
    entry = data.get(normalized) or data["DEFAULT"]
    return StateDOIInfo.model_validate(entry)


@tool
def lookup_state_doi_process_tool(state: str) -> str:
    """Look up the Department of Insurance complaint process and independent
    external review framework for a US state, as a plain-text report.

    Args:
        state: A two-letter USPS state abbreviation, e.g. "CA".

    Returns:
        A plain-language report of the state's DOI complaint process,
        external review process, deadline window, and where to find current
        official contact info.
    """
    info = lookup_state_doi_process(state)
    return (
        f"{info.state_name} ({info.state_code}): DOI/regulator: {info.doi_name}. "
        f"DOI complaint process: {info.doi_complaint_process} "
        f"External review process: {info.external_review_process} "
        f"Typical deadline window: {info.external_review_deadline_window} "
        f"Find current contact info: {info.doi_contact_instruction}"
    )
