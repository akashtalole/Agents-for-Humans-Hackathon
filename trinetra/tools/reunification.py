"""Lost-person matching - deliberately pure code, no LLM.

Matching two free-text descriptions of a person is exactly the kind of
fuzzy task an LLM call could plausibly help with, but a false "match" here
sends a stressed family to the wrong person, and a missed match leaves a
real match undiscovered. This module does the safest thing available:
exact/near-exact matching on a small set of structured, comparable
attributes (age band, last-seen location, explicit distinguishing terms in
the description), and NEVER returns "certain" - only "strong" or
"possible", with a human always confirming a match in person before
anyone is told their family member has been found. See models.py's
ReunificationMatch.confidence field and TRINETRA.md's honest-limitations
section for why this is deliberately conservative.
"""
from __future__ import annotations

from trinetra.models import LostPersonRecord, ReunificationMatch

_AGE_BAND_WIDTH = 5


def _age_band(age: int | None) -> int | None:
    if age is None:
        return None
    return age // _AGE_BAND_WIDTH


def _shared_description_terms(a: str, b: str) -> list[str]:
    """Plain substring overlap on lowercased words 4+ characters long -
    deliberately simple and predictable rather than a semantic similarity
    model whose behavior would be hard to explain to a search-and-rescue
    operator relying on it."""
    words_a = {w for w in a.lower().split() if len(w) >= 4}
    words_b = {w for w in b.lower().split() if len(w) >= 4}
    return sorted(words_a & words_b)


def find_candidate_matches(
    missing: LostPersonRecord, found_pool: list[LostPersonRecord]
) -> list[ReunificationMatch]:
    """Returns candidate matches for one missing-person record against a
    pool of "found" records (people reported as located but not yet
    reunited with family) - ordered strongest first."""
    matches: list[ReunificationMatch] = []

    for candidate in found_pool:
        if candidate.record_id == missing.record_id:
            continue

        shared_terms = _shared_description_terms(missing.description, candidate.description)
        same_age_band = (
            missing.age_estimate is not None
            and candidate.age_estimate is not None
            and _age_band(missing.age_estimate) == _age_band(candidate.age_estimate)
        )
        same_location = missing.last_seen_location.strip().lower() == candidate.last_seen_location.strip().lower()

        shared_attributes: list[str] = []
        if same_age_band:
            shared_attributes.append(f"similar age (~{missing.age_estimate} vs ~{candidate.age_estimate})")
        if same_location:
            shared_attributes.append(f"same last-seen location: {missing.last_seen_location}")
        if shared_terms:
            shared_attributes.append(f"shared description terms: {', '.join(shared_terms)}")

        if not shared_attributes:
            continue

        # "Strong" requires location agreement plus at least one other
        # signal - never based on description-term overlap alone, since
        # short free-text descriptions collide easily by chance.
        confidence = "strong" if same_location and (same_age_band or shared_terms) else "possible"

        matches.append(
            ReunificationMatch(
                missing_record_id=missing.record_id,
                found_record_id=candidate.record_id,
                confidence=confidence,
                shared_attributes=shared_attributes,
            )
        )

    order = {"strong": 0, "possible": 1}
    matches.sort(key=lambda m: order[m.confidence])
    return matches
