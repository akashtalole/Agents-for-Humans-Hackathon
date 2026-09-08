"""Deterministic scan of a drafted counter-message before any human
broadcasts it. Pure code, no LLM - mirrors bidwright/tools/guardrail.py.

Why this exists: the obvious way to kill a rumor is to deny it flatly
("there has been no stampede, everything is fine"). That is also the single
most dangerous thing this system could ever emit, because the drafting
agent has no way to know whether the rumor is false. At the New Delhi
railway station in 2025, "rumours of a stampede-like situation" among Kumbh
travellers preceded a crush that killed 18 - a broadcast asserting nothing
was happening, made while something was in fact happening, would have moved
people toward the danger rather than away from it.

So this guardrail blocks absolute reassurance and absolute denial outright.
A counter-message may give crowd-safety instruction ("keep walking, do not
push, follow the marked exit"), may state what officials have actually
confirmed, and may direct people to an official channel. It may not promise
safety it cannot verify.

This is a hard block on the DRAFT reaching a broadcast queue, not a hard
block on human judgment: an official who has genuinely verified the facts
can still broadcast a denial. The guardrail's job is to make sure that
decision is made by a human who checked, not by a language model that
guessed.
"""
from __future__ import annotations

import re

from trinetra.models import RumorGuardrailFinding, RumorGuardrailResult

# Phrases asserting that nothing is wrong / nothing happened. The drafting
# agent cannot know this, so it may never assert it.
_ABSOLUTE_REASSURANCE_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(there is|there's)\s+no\s+(danger|emergency|stampede|risk|threat)\b",
        "Asserts there is no danger. The drafting agent cannot verify this; if it is wrong, the message moves people toward harm.",
    ),
    (
        r"\bnothing\s+(has\s+)?happened\b",
        "Asserts nothing has happened. Only an official with on-scene confirmation can say this.",
    ),
    (
        r"\b(everything|everyone)\s+is\s+(fine|safe|okay|ok)\b",
        "Blanket assurance of safety that the drafting agent has no basis for.",
    ),
    (
        r"\b(completely|totally|entirely)\s+safe\b",
        "Absolute safety claim - not something any automated draft may assert to a crowd.",
    ),
    (
        r"\bno\s+one\s+(has\s+been\s+)?(hurt|injured|died)\b",
        "Casualty claim requiring on-scene verification before broadcast.",
    ),
    (
        r"\bdo\s+not\s+worry\b",
        "Instructs a crowd not to worry, which functions as an assurance of safety the draft cannot back.",
    ),
    (
        r"\b(the\s+)?rumou?r\s+is\s+(false|untrue)\b",
        "Declares the rumor false. Whether it is false is precisely what a human must verify first.",
    ),
]

# Instructions that are actively unsafe in a dense crowd, regardless of
# whether the rumor turns out to be true - same reasoning as
# agents/safety_triage.py's crowd-safety rules.
_UNSAFE_INSTRUCTION_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(run|rush|hurry)\s+(to|toward|towards|for)\b",
        "Tells a dense crowd to run/rush, which is how a crowd movement becomes a crush.",
    ),
    (
        r"\bpush\s+(through|forward|ahead)\b",
        "Tells people to push through a crowd - directly dangerous in high density.",
    ),
    (
        r"\bevacuate\s+immediately\b",
        "An unqualified immediate-evacuation instruction can trigger the very surge it is trying to prevent; staged, directed evacuation language is required instead.",
    ),
]


def scan_counter_message(text: str) -> RumorGuardrailResult:
    """Scan a drafted counter-message for absolute reassurance and unsafe
    crowd instructions."""
    findings: list[RumorGuardrailFinding] = []
    lowered = text.lower()

    for pattern, explanation in _ABSOLUTE_REASSURANCE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            findings.append(
                RumorGuardrailFinding(
                    rule="absolute_reassurance",
                    excerpt=text[max(0, match.start() - 30) : match.end() + 30].strip(),
                    explanation=explanation,
                )
            )

    for pattern, explanation in _UNSAFE_INSTRUCTION_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            findings.append(
                RumorGuardrailFinding(
                    rule="unsafe_crowd_instruction",
                    excerpt=text[max(0, match.start() - 30) : match.end() + 30].strip(),
                    explanation=explanation,
                )
            )

    if findings:
        summary = (
            f"{len(findings)} issue(s) found - this draft must be revised or explicitly overridden by an "
            "official who has verified the underlying facts before it is broadcast."
        )
    else:
        summary = (
            "No absolute-reassurance or unsafe-instruction patterns found. A human must still verify the "
            "facts listed in verify_before_broadcast before this goes out."
        )

    return RumorGuardrailResult(passed=not findings, findings=findings, summary=summary)
