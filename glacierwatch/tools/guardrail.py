"""Enforced guardrail check on drafted community alert bulletin text:
GlacierWatch's single non-negotiable rule is that it must never claim to
predict if, when, or where an avalanche or glacial lake outburst flood will
occur. This module is the last, code-enforced line of defense for that rule
before a bulletin ever reaches a village-level disaster committee.

Same "pure code where it matters" discipline as glacierwatch/tools/history.py
and bidwright/tools/guardrail.py (the sibling project's identical pattern):
the deterministic half of this check is either actually there in the text or
it isn't, never a model's fuzzy recollection of what it wrote. It's combined
with a small, separate agent-based check for subtler phrasing a keyword
scanner would miss.
"""
from __future__ import annotations

import re

from strands import Agent

from glacierwatch.config import create_agent
from glacierwatch.models import GuardrailFinding, GuardrailResult
from glacierwatch.rendering import DISCLAIMER

# Prediction-language patterns, matched case-insensitively. Every match
# unconditionally produces a finding - unlike bidwright's overclaim scan,
# there's no "only when X" gate here, because GlacierWatch's non-prediction
# rule has no exceptions.
_PREDICTION_PATTERNS = [
    r"will occur",
    r"is going to (happen|occur)",
    r"will breach",
    r"will flood",
    r"expect (a|an) (flood|avalanche|glof|outburst)",
    r"guaranteed (safe|not to)",
    r"will not (occur|happen)",
    r"is certain to",
    r"about to (breach|fail|collapse)",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _PREDICTION_PATTERNS]


def scan_prediction_language(alert_text: str) -> list[GuardrailFinding]:
    """Deterministic (no LLM, no network) scan of `alert_text` for concrete
    prediction-language phrases. Offline-testable and safe to run on every
    run's current community_alert_<site_id>.md content."""
    findings: list[GuardrailFinding] = []
    for pattern in _COMPILED_PATTERNS:
        for match in pattern.finditer(alert_text):
            findings.append(
                GuardrailFinding(
                    rule="prediction_language",
                    excerpt=match.group(0),
                    explanation=(
                        "GlacierWatch is decision-support triage, not a prediction system - this "
                        "phrase implies a forecast of a specific event."
                    ),
                )
            )
    return findings


GUARDRAIL_SYSTEM_PROMPT = f"""\
You are a safety guardrail reviewer for GlacierWatch, a decision-support \
triage tool. Its non-negotiable policy, stated verbatim to every reader of \
its output, is:

{DISCLAIMER}

Flag any sentence in this community alert that implies a forecast, \
prediction, or certainty about whether, when, or where an avalanche or \
glacial lake outburst flood will occur - including subtler phrasing a \
keyword scanner would miss (an implied timeline, a false-certainty safety \
claim, or language that reads as "this will happen" even if hedged \
elsewhere). Do not flag appropriately hedged language describing documented \
risk level or recommending precaution.

For each real violation, produce a GuardrailFinding with `rule` set to \
"prediction_language", `excerpt` as the exact offending sentence or phrase, \
and `explanation` for why it violates the policy. If there are no \
violations, findings must be empty.
"""


def build_guardrail_agent() -> Agent:
    return create_agent(system_prompt=GUARDRAIL_SYSTEM_PROMPT)


def agent_guardrail_check(alert_text: str) -> GuardrailResult:
    """Small, separate agent-based check for prediction language the
    deterministic regex scan can't catch (paraphrased forecasts, subtler
    implied-certainty phrasing). Kept as its own tiny Agent with a narrow,
    explicit policy rather than folded into a bigger sub-agent's prompt."""
    agent = build_guardrail_agent()
    prompt = f"COMMUNITY ALERT TEXT:\n{alert_text}\n\nApply the guardrail policy now."
    result = agent(prompt, structured_output_model=GuardrailResult)
    return result.structured_output


def run_guardrail_check(alert_text: str) -> GuardrailResult:
    """Union of the deterministic prediction-language scan and the
    agent-based check. passed is true only when neither half found
    anything."""
    findings = scan_prediction_language(alert_text)
    findings += agent_guardrail_check(alert_text).findings
    return GuardrailResult(passed=len(findings) == 0, findings=findings)
