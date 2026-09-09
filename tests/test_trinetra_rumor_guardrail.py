"""Offline tests for trinetra/tools/rumor_guardrail.py - pure code, no LLM.

This guardrail is the safety-critical piece of the rumor desk: it is the
thing standing between a language model's draft and a loudspeaker pointed
at a dense crowd. These tests are deliberately adversarial about the ways a
well-meaning draft can be lethal.
"""
from __future__ import annotations

import pytest

from trinetra.tools.rumor_guardrail import scan_counter_message

SAFE_MESSAGE = (
    "Keep moving at a walking pace. Do not push, do not turn back. Follow the marked route and "
    "Kumbh Rakshak staff instructions. Help anyone who has fallen."
)


def test_safe_crowd_safety_message_passes():
    result = scan_counter_message(SAFE_MESSAGE)
    assert result.passed
    assert result.findings == []


@pytest.mark.parametrize(
    "draft",
    [
        "There is no danger at Ramkund, please continue to the ghat.",
        "Nothing has happened. Carry on as normal.",
        "Everything is fine, there is no need to move.",
        "The area is completely safe.",
        "No one has been hurt in this incident.",
        "Do not worry, continue toward the ghat.",
        "The rumour is false - please ignore it.",
    ],
)
def test_absolute_reassurance_is_blocked(draft: str):
    """The drafting agent cannot know the rumor is false. If it is wrong, a
    reassuring broadcast moves people toward the danger - see the module
    docstring's New Delhi 2025 reference."""
    result = scan_counter_message(draft)
    assert not result.passed
    assert any(f.rule == "absolute_reassurance" for f in result.findings)


@pytest.mark.parametrize(
    "draft",
    [
        "Run to the nearest exit immediately.",
        "Please hurry towards the north gate.",
        "Push through to the exit.",
        "Evacuate immediately.",
    ],
)
def test_unsafe_crowd_instructions_are_blocked(draft: str):
    result = scan_counter_message(draft)
    assert not result.passed
    assert any(f.rule == "unsafe_crowd_instruction" for f in result.findings)


def test_findings_include_an_excerpt_and_an_explanation():
    """An operator overriding a block needs to see exactly which words
    tripped it and why, not just a boolean."""
    result = scan_counter_message("There is no danger. Everyone is safe.")
    assert not result.passed
    for finding in result.findings:
        assert finding.excerpt.strip()
        assert len(finding.explanation) > 20


def test_multiple_violations_are_all_reported_not_just_the_first():
    result = scan_counter_message("There is no danger, everything is fine, run to the exit.")
    rules = {f.rule for f in result.findings}
    assert "absolute_reassurance" in rules
    assert "unsafe_crowd_instruction" in rules


def test_summary_tells_a_passing_draft_that_human_verification_is_still_required():
    """Passing the guardrail is not the same as being cleared to broadcast."""
    result = scan_counter_message(SAFE_MESSAGE)
    assert "verify" in result.summary.lower()


def test_detection_is_case_insensitive():
    result = scan_counter_message("THERE IS NO DANGER, EVERYTHING IS FINE.")
    assert not result.passed


def test_naming_the_official_channel_is_not_treated_as_reassurance():
    """A message may legitimately tell people whom to trust - that must not
    be confused with promising them safety."""
    result = scan_counter_message(
        "Follow only official announcements from Kumbh Rakshak staff and ghat loudspeakers."
    )
    assert result.passed
