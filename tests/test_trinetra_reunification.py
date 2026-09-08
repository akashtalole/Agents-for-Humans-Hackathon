"""Offline, deterministic tests for trinetra/tools/reunification.py - no
LLM. See that module's docstring for why lost-person matching is
deliberately pure code, never a semantic-similarity model."""
from __future__ import annotations

from trinetra.models import LostPersonRecord
from trinetra.tools.reunification import find_candidate_matches


def _record(record_id: str, name: str, age: int | None, description: str, location: str) -> LostPersonRecord:
    return LostPersonRecord(
        record_id=record_id,
        name=name,
        age_estimate=age,
        description=description,
        last_seen_location=location,
        reporter_contact="test-contact",
    )


def test_strong_match_same_location_and_age_band():
    missing = _record("m1", "unknown", 6, "wearing a red shirt and blue shorts", "Kushavarta Ghat")
    found = _record("f1", "unknown child", 6, "red shirt, found alone", "Kushavarta Ghat")
    matches = find_candidate_matches(missing, [found])
    assert len(matches) == 1
    assert matches[0].confidence == "strong"
    assert matches[0].found_record_id == "f1"


def test_possible_match_shared_terms_only_no_location_agreement():
    missing = _record("m1", "unknown", 6, "wearing a red shirt and blue shorts", "Kushavarta Ghat")
    found = _record("f2", "unknown child", 7, "red shirt, found near Ramkund", "Ramkund")
    matches = find_candidate_matches(missing, [found])
    assert len(matches) == 1
    assert matches[0].confidence == "possible"


def test_no_shared_attributes_produces_no_match():
    missing = _record("m1", "unknown", 6, "wearing a red shirt and blue shorts", "Kushavarta Ghat")
    found = _record("f3", "unknown adult", 45, "elderly man in white kurta", "Panchavati")
    matches = find_candidate_matches(missing, [found])
    assert matches == []


def test_never_returns_certain_confidence():
    """Reunification confidence must always require a human to confirm in
    person - see reunification.py's docstring."""
    missing = _record("m1", "unknown", 6, "red shirt blue shorts", "Kushavarta Ghat")
    found = _record("f1", "unknown", 6, "red shirt blue shorts", "Kushavarta Ghat")
    matches = find_candidate_matches(missing, [found])
    assert all(m.confidence in ("strong", "possible") for m in matches)


def test_self_is_never_matched_against_itself():
    missing = _record("m1", "unknown", 6, "red shirt", "Kushavarta Ghat")
    matches = find_candidate_matches(missing, [missing])
    assert matches == []


def test_results_ordered_strongest_first():
    missing = _record("m1", "unknown", 6, "red shirt blue shorts sandals", "Kushavarta Ghat")
    weak = _record("f_weak", "unknown", 40, "sandals only", "Ramkund")
    strong = _record("f_strong", "unknown", 6, "red shirt blue shorts", "Kushavarta Ghat")
    matches = find_candidate_matches(missing, [weak, strong])
    assert matches[0].found_record_id == "f_strong"
    assert matches[0].confidence == "strong"
