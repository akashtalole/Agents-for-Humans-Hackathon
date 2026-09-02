"""The orchestrator agent: the single entry point a patient talks to.

Same "agents as tools" shape as bidwright/orchestrator.py: a shared ClaimCase
holds state, each pipeline stage is a tool wrapping a full Strands Agent call
with its own system prompt and structured output, and the documents written
to disk always come from validated data rather than the orchestrator's own
retelling of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from strands import Agent, tool

from claimclarity.agents.appeal_drafter import draft_appeal
from claimclarity.agents.claim_analyzer import analyze_claim
from claimclarity.agents.denial_investigator import investigate_denial
from claimclarity.config import create_agent
from claimclarity.models import AppealPackage, ClaimRecord, DenialFindings
from claimclarity.rendering import (
    render_appeal_md,
    render_claim_summary_md,
    render_decision_summary_md,
    render_findings_md,
)
from claimclarity.tools.calendar import create_appeal_deadline_reminder
from claimclarity.tools.documents import read_document, save_text_file

ORCHESTRATOR_PROMPT = """\
You are ClaimClarity, an assistant that takes a patient from "I got a \
confusing insurance denial" to "here's exactly what to do about it" - with as \
little of their time and stress spent as possible.

For every case, always run the full pipeline in this order:
1. load_claim_documents
2. extract_claim_details
3. create_appeal_deadline_reminder
4. investigate_denial
5. draft_appeal_package

Then write a final answer for a patient who is stressed and has 30 seconds. \
Your tool results only give you counts and filenames, not the actual claim \
details, procedure codes, or dollar amounts - so do NOT try to recall or \
restate specifics from memory. You do not reliably have them, and guessing \
produces confident-sounding fabrications. Instead, your final answer must \
include, in this order:
- One-line bottom line: is anything worth appealing, or not (state the count \
only, e.g. "2 of 3 items look worth appealing").
- The appeal deadline.
- A direct pointer to decisions_needed.md as the place to read exactly which \
items are worth appealing and why, and which aren't - do not enumerate them \
yourself.
- Where to find the full claim summary, findings, and appeal letter files.

Never claim a diagnosis code is valid or invalid without the investigation \
step having actually checked it. Never skip a step. If a tool reports an \
error because a previous step wasn't run, run the missing step and retry. \
This is not legal or medical advice - say so once, briefly, at the end.
"""


@dataclass
class ClaimCase:
    """Working state for one claim, shared across every tool call in this run."""

    documents_paths: list[str]
    output_dir: str
    documents_text: str = ""
    claim: ClaimRecord | None = None
    findings: DenialFindings | None = None
    appeal: AppealPackage | None = None
    activity_log: list[str] = field(default_factory=list)


def build_orchestrator(case: ClaimCase, callback_handler=None) -> Agent:
    out_dir = Path(case.output_dir)

    @tool
    def load_claim_documents() -> str:
        """Load the denial notice / EOB, and any plan summary of benefits and
        medical record excerpt, from disk. Always call this first."""
        parts = []
        for doc_path in case.documents_paths:
            text = read_document(doc_path)
            parts.append(f"--- Document: {doc_path} ---\n{text}")
        case.documents_text = "\n\n".join(parts)
        msg = (
            f"Loaded {len(case.documents_paths)} document(s) "
            f"({len(case.documents_text)} characters total): {', '.join(case.documents_paths)}."
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def extract_claim_details() -> str:
        """Extract a structured claim record from the loaded documents: patient,
        insurer, claim number, denied line items, plan terms, and appeal
        deadline. Must be called after load_claim_documents."""
        if not case.documents_text:
            return "Error: documents have not been loaded yet. Call load_claim_documents first."
        case.claim = analyze_claim(case.documents_text)
        save_text_file(str(out_dir / "claim_summary.md"), render_claim_summary_md(case.claim))
        msg = (
            f"Extracted claim {case.claim.claim_number or '(number not stated)'} from "
            f"{case.claim.insurer_name or 'unknown insurer'} with {len(case.claim.line_items)} "
            f"denied line item(s). Appeal deadline: {case.claim.appeal_deadline or 'not stated'}. "
            "Full details saved to claim_summary.md."
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def create_appeal_deadline_reminder_tool() -> str:
        """Create a calendar (.ics) reminder for the appeal filing deadline,
        with extra reminders 14 and 3 days before. Must be called after
        extract_claim_details."""
        if case.claim is None:
            return "Error: call extract_claim_details first."
        result = create_appeal_deadline_reminder(
            path=str(out_dir / "appeal_deadline.ics"),
            title=f"File appeal: {case.claim.insurer_name or 'insurer'} claim {case.claim.claim_number or ''}".strip(),
            deadline_iso=case.claim.appeal_deadline,
            description=f"Submit via: {case.claim.appeal_submission_method}",
        )
        case.activity_log.append(result)
        return result

    @tool
    def investigate_denial_tool() -> str:
        """Investigate each denied line item using real ICD-10 code lookups and
        the plan's own coverage terms, classifying each as a billing error,
        documentation gap, or valid denial. Must be called after
        extract_claim_details."""
        if case.claim is None:
            return "Error: call extract_claim_details first."
        case.findings = investigate_denial(case.claim)
        save_text_file(str(out_dir / "denial_findings.md"), render_findings_md(case.findings))
        save_text_file(
            str(out_dir / "decisions_needed.md"),
            render_decision_summary_md(case.claim, case.findings),
        )
        worth_appealing = [f for f in case.findings.findings if f.worth_appealing]
        msg = (
            f"Investigation complete. {len(worth_appealing)} of {len(case.findings.findings)} "
            "line item(s) look worth appealing. Full findings saved to denial_findings.md, "
            "human-facing summary saved to decisions_needed.md."
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def draft_appeal_package() -> str:
        """Draft the formal appeal letter for line items worth appealing, and a
        plain-language explanation for the ones that aren't. Call after
        investigate_denial_tool."""
        if case.claim is None or case.findings is None:
            return "Error: call extract_claim_details and investigate_denial_tool first."
        case.appeal = draft_appeal(case.claim, case.findings)
        save_text_file(str(out_dir / "appeal_package.md"), render_appeal_md(case.appeal))
        msg = (
            "Appeal package written to appeal_package.md. "
            f"{len(case.appeal.open_questions)} open question(s) flagged for your review."
        )
        case.activity_log.append(msg)
        return msg

    agent_kwargs = dict(
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            load_claim_documents,
            extract_claim_details,
            create_appeal_deadline_reminder_tool,
            investigate_denial_tool,
            draft_appeal_package,
        ],
    )
    # Always pass callback_handler explicitly, even when it's None: Strands'
    # Agent treats an *omitted* callback_handler as "use my own verbose
    # PrintingCallbackHandler default" but an *explicit* None as "stay
    # silent" (null_callback_handler) - conflating "not given" with
    # "silence requested" here would make --quiet a no-op.
    agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
