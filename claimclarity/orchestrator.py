"""The orchestrator agent: the single entry point a patient talks to.

Same "agents as tools" shape as bidwright/orchestrator.py: a shared ClaimCase
holds state, each pipeline stage is a tool wrapping a full Strands Agent call
with its own system prompt and structured output, and the documents written
to disk always come from validated data rather than the orchestrator's own
retelling of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from strands import Agent, tool

from claimclarity.agents.appeal_drafter import draft_appeal
from claimclarity.agents.appeal_reviewer import review_appeal
from claimclarity.agents.claim_analyzer import analyze_claim
from claimclarity.agents.denial_auditor import audit_denial, compare_denial_findings
from claimclarity.agents.denial_investigator import investigate_denial
from claimclarity.agents.escalation_advisor import prepare_escalation
from claimclarity.agents.evidence_request_builder import build_physician_evidence_request
from claimclarity.config import create_agent
from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimHistory,
    ClaimRecord,
    DenialCrossCheck,
    DenialFindings,
    EscalationPackage,
    GuardrailResult,
    InsurerPatternInsight,
    PhysicianEvidenceRequest,
    ReviewResult,
)
from claimclarity.rendering import (
    render_appeal_md,
    render_claim_summary_md,
    render_cross_check_md,
    render_decision_summary_md,
    render_escalation_md,
    render_findings_md,
    render_guardrail_md,
    render_insurer_pattern_report_md,
    render_physician_evidence_request_md,
    render_review_md,
)
from claimclarity.tools.calendar import create_appeal_deadline_reminder, create_external_review_deadline_reminder
from claimclarity.tools.documents import read_document, save_text_file
from claimclarity.tools.guardrail import run_guardrail_check
from claimclarity.tools.history import (
    append_entry,
    build_case_entry,
    detect_insurer_patterns,
    load_history,
    save_history,
)
from claimclarity.tools.state_doi import lookup_state_doi_process

ORCHESTRATOR_PROMPT = """\
You are ClaimClarity, an assistant that takes a patient from "I got a \
confusing insurance denial" to "here's exactly what to do about it" - with as \
little of their time and stress spent as possible.

For every case, always run the full pipeline in this order:
1. load_claim_documents
2. extract_claim_details
3. create_appeal_deadline_reminder
4. investigate_denial
5. cross_verify_denial_findings
6. record_case_and_check_insurer_patterns
7. build_physician_evidence_request
8. draft_appeal_package
9. review_appeal_package
10. check_appeal_guardrail
11. prepare_external_review_escalation

Step 5 gets a second, INDEPENDENT investigation of every denied line item \
from a separate auditor agent that has not seen step 4's conclusions - not \
a revision of step 4's work, a genuinely separate one, using the same real \
ICD-10 lookup tools independently. Any disagreement between the two is \
never silently resolved in either direction: it forces that line item to \
needs_review so a human looks at it directly, and marks it worth_appealing \
so it's never silently dropped from the list. Always call it right after \
investigate_denial, even when you expect the two to agree - the whole \
point is that you don't actually know that until you check.

After draft_appeal_package, always call review_appeal_package: a second, \
independent pass that fact-checks the drafted appeal against the denial \
findings it was supposed to come from - a wrong code, an unsupported claim, \
or an overstated certainty about the outcome, never prose style. If it finds \
real issues, revise by calling draft_appeal_package again incorporating that \
feedback, then call review_appeal_package once more to confirm the revision \
addressed them. This loop is capped at exactly one revision pass by plain \
code, not by your own judgment - a second call to review_appeal_package after \
a revision already happened returns immediately without reviewing again, so \
proceed to the next step at that point regardless of the verdict.

After review_appeal_package, always call check_appeal_guardrail: a \
deterministic and agent-based check of the CURRENT appeal_package.md for \
language that promises a guaranteed outcome, states an unsupported medical \
fact, or gives legal advice. This always runs exactly once, after whatever \
revision happened above - it is not part of the bounded revision loop and \
does not get re-run if it finds something; a human reviews its findings \
before the appeal is sent.

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
- One line noting how many line items an independent second investigation \
disagreed on (state the count only, from cross_verify_denial_findings's \
result - never invent which ones) and a pointer to denial_cross_check.md.
- One line noting that insurer_pattern_report.md shows whether this same \
insurer has a recorded pattern of denying similar claims on the same basis \
before - a materially stronger fact pattern for an appeal or regulatory \
complaint when it exists - without inventing any specifics yourself.
- One line noting that physician_evidence_request.md lists any specific \
documentation worth asking your doctor's office for before the appeal is \
sent, if this denial turns on medical necessity - without inventing any \
specifics yourself.
- One line noting how many issues (a count only, from appeal_review.md) an \
independent review pass found in the drafted appeal, and that it's in \
appeal_review.md.
- One line noting how many guardrail findings (a count only, from \
appeal_guardrail.md) were found in the appeal letter, and that it's in \
appeal_guardrail.md.
- One line noting that decisions_needed.md and escalation_package.md also \
cover what to do if the internal appeal doesn't fully resolve this - \
independent external review, and possibly a state Department of Insurance \
complaint - without inventing any specifics yourself.
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
    history_file: str = "claimclarity_history.json"
    documents_text: str = ""
    claim: ClaimRecord | None = None
    findings: DenialFindings | None = None
    cross_check: DenialCrossCheck | None = None
    appeal: AppealPackage | None = None
    escalation: EscalationPackage | None = None
    physician_evidence_request: PhysicianEvidenceRequest | None = None
    review: ReviewResult | None = None
    review_revision_count: int = 0
    guardrail: GuardrailResult | None = None
    history: ClaimHistory = field(default_factory=ClaimHistory)
    insurer_pattern_insights: list[InsurerPatternInsight] = field(default_factory=list)
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
    def cross_verify_denial_findings() -> str:
        """Get a second, independent investigation of every denied line item
        from a separate auditor agent that has NOT seen the first
        investigation's conclusions (it uses the same real ICD-10 lookup
        tools, independently), then compare the two by procedure_code - a
        plain-code diff, not an LLM judgment, since both findings lists are
        already structured. A genuine disagreement is never silently
        resolved in favor of either investigation: it forces that line
        item's classification to needs_review (and worth_appealing=True, so
        a disputed item is never silently dropped from the appeal-worthy
        list) regardless of what either investigation concluded alone.
        Every line item's comparison is written to denial_cross_check.md.
        Must be called after investigate_denial_tool."""
        if case.claim is None or case.findings is None:
            return "Error: call investigate_denial_tool first."
        audit = audit_denial(case.claim)
        case.cross_check = compare_denial_findings(case.findings, audit)

        if case.cross_check.disagreement_count:
            disputed_codes = {item.procedure_code for item in case.cross_check.items if not item.agrees}
            for finding in case.findings.findings:
                if finding.procedure_code in disputed_codes and finding.classification != Classification.NEEDS_REVIEW:
                    finding.classification = Classification.NEEDS_REVIEW
                    finding.worth_appealing = True
            save_text_file(str(out_dir / "denial_findings.md"), render_findings_md(case.findings))
            save_text_file(
                str(out_dir / "decisions_needed.md"),
                render_decision_summary_md(case.claim, case.findings, case.escalation, case.physician_evidence_request),
            )

        save_text_file(str(out_dir / "denial_cross_check.md"), render_cross_check_md(case.cross_check))
        msg = (
            f"Independent audit complete: {case.cross_check.disagreement_count} of "
            f"{len(case.cross_check.items)} line item(s) disagreed"
            + (
                " - forced to needs_review, see denial_cross_check.md."
                if case.cross_check.disagreement_count
                else ". See denial_cross_check.md."
            )
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def record_case_and_check_insurer_patterns() -> str:
        """Record this case's denied line items and denial reasons to the
        persistent cross-run insurer accountability history file
        (case.history_file), then scan that history for denial-reason
        patterns from the SAME insurer that have recurred across 2+
        separate recorded cases - by plain code, never an LLM judgment.
        Always writes insurer_pattern_report.md, even on the very first
        case ever recorded for this insurer (a graceful "no prior history"
        message, not an error). Must be called after investigate_denial_tool,
        and should run before build_physician_evidence_request_tool and
        draft_appeal_package so a real pattern can be cited as supporting
        context in either."""
        if case.claim is None or case.findings is None:
            return "Error: call extract_claim_details and investigate_denial_tool first."
        prior_history = load_history(case.history_file)
        new_entry = build_case_entry(case.claim, case.findings, datetime.now(timezone.utc).isoformat())
        case.history = append_entry(prior_history, new_entry)
        save_history(case.history_file, case.history)

        insurer_key = (case.claim.insurer_name or "").strip().lower()
        case.insurer_pattern_insights = [
            insight
            for insight in detect_insurer_patterns(case.history)
            if insight.insurer_name.strip().lower() == insurer_key
        ]
        save_text_file(
            str(out_dir / "insurer_pattern_report.md"),
            render_insurer_pattern_report_md(case.claim.insurer_name, case.insurer_pattern_insights),
        )

        if case.insurer_pattern_insights:
            pattern_note = (
                f"{len(case.insurer_pattern_insights)} recurring denial pattern(s) found from "
                f"{case.claim.insurer_name or 'this insurer'} across your recorded case history."
            )
        else:
            pattern_note = f"No recurring pattern found yet for {case.claim.insurer_name or 'this insurer'}."
        msg = f"Recorded this case to {case.history_file}. {pattern_note} See insurer_pattern_report.md."
        case.activity_log.append(msg)
        return msg

    @tool
    def build_physician_evidence_request_tool() -> str:
        """Work out what specific clinical documentation, if any, the
        patient's treating physician's office should be asked to send to
        support the appeal, and draft that request. Only denied line items
        that turn on medical necessity need this - a pure billing-code fix
        or a plan exclusion doesn't. Must be called after
        investigate_denial_tool, and should run before draft_appeal_package
        so the appeal's open questions can point to it."""
        if case.claim is None or case.findings is None:
            return "Error: call extract_claim_details and investigate_denial_tool first."
        case.physician_evidence_request = build_physician_evidence_request(case.claim, case.findings)
        save_text_file(
            str(out_dir / "physician_evidence_request.md"),
            render_physician_evidence_request_md(case.physician_evidence_request),
        )
        save_text_file(
            str(out_dir / "decisions_needed.md"),
            render_decision_summary_md(case.claim, case.findings, case.escalation, case.physician_evidence_request),
        )
        n = len(case.physician_evidence_request.items)
        if n:
            msg = (
                f"Physician evidence request written to physician_evidence_request.md. "
                f"{n} line item(s) need specific documentation from your doctor's office before appealing."
            )
        else:
            msg = (
                "Physician evidence request written to physician_evidence_request.md. "
                "Nothing here turns on missing physician documentation - none needed."
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
        case.appeal = draft_appeal(case.claim, case.findings, insurer_pattern_insights=case.insurer_pattern_insights)
        save_text_file(str(out_dir / "appeal_package.md"), render_appeal_md(case.appeal))
        msg = (
            "Appeal package written to appeal_package.md. "
            f"{len(case.appeal.open_questions)} open question(s) flagged for your review."
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def review_appeal_package() -> str:
        """Review the drafted appeal package against the denial investigation
        findings for accuracy - does it cite the wrong code, claim something
        the findings don't support, or overstate certainty about the outcome.
        Call after draft_appeal_package. If it finds real issues, revise by
        calling draft_appeal_package again with this feedback in mind, then
        call this tool again - but this is capped at ONE revision pass;
        calling it again after a revision already happened returns
        immediately without re-reviewing, so the loop cannot run away."""
        if case.appeal is None:
            return "Error: call draft_appeal_package first."
        if case.review_revision_count >= 1:
            msg = "Maximum review-revision pass (1) already used; proceeding without a further review."
            case.activity_log.append(msg)
            return msg
        case.review = review_appeal(case.appeal, case.findings)
        save_text_file(str(out_dir / "appeal_review.md"), render_review_md(case.review))
        if not case.review.approved:
            case.review_revision_count += 1
            msg = (
                f"Review found {len(case.review.issues)} issue(s) - revise appeal_package.md by "
                "calling draft_appeal_package again incorporating this feedback, then call "
                "review_appeal_package once more. Issues saved to appeal_review.md."
            )
        else:
            msg = "Review passed with no issues. See appeal_review.md."
        case.activity_log.append(msg)
        return msg

    @tool
    def check_appeal_guardrail() -> str:
        """Run guardrail checks (deterministic pattern scan plus a focused
        agent check) against the CURRENT appeal_package.md content, looking
        for language that promises a guaranteed outcome, states an
        unsupported medical fact, or gives legal advice. Must be called after
        review_appeal_package, once - a human reviews any findings before the
        appeal is sent."""
        appeal_path = out_dir / "appeal_package.md"
        if case.appeal is None or not appeal_path.exists():
            return "Error: call draft_appeal_package (and review_appeal_package) first."
        appeal_text = appeal_path.read_text(encoding="utf-8")
        case.guardrail = run_guardrail_check(appeal_text)
        save_text_file(str(out_dir / "appeal_guardrail.md"), render_guardrail_md(case.guardrail))
        msg = (
            f"Guardrail check complete: {len(case.guardrail.findings)} finding(s). See appeal_guardrail.md."
        )
        case.activity_log.append(msg)
        return msg

    @tool
    def prepare_external_review_escalation() -> str:
        """Determine whether this denial is worth escalating past the internal
        appeal - to an independent External Review and, where the findings
        actually show a process failure, a state Department of Insurance
        complaint - and draft the request letter(s). This is always the final
        pipeline step; call it after check_appeal_guardrail."""
        if case.claim is None or case.findings is None or case.appeal is None:
            return "Error: call extract_claim_details, investigate_denial_tool, and draft_appeal_package first."
        # A patient's state not being extractable (or not being in the bundled
        # sample) still has an applicable framework - lookup_state_doi_process
        # falls back to the federal DEFAULT entry rather than erroring, so this
        # step runs unconditionally like every other pipeline step.
        doi_info = lookup_state_doi_process(case.claim.state)
        case.escalation = prepare_escalation(
            case.claim, case.findings, case.appeal, doi_info, insurer_pattern_insights=case.insurer_pattern_insights
        )
        save_text_file(str(out_dir / "escalation_package.md"), render_escalation_md(case.escalation))
        save_text_file(
            str(out_dir / "decisions_needed.md"),
            render_decision_summary_md(case.claim, case.findings, case.escalation, case.physician_evidence_request),
        )
        ics_message = create_external_review_deadline_reminder(
            path=str(out_dir / "external_review_deadline.ics"),
            title=f"File external review: {case.claim.insurer_name or 'insurer'} "
            f"claim {case.claim.claim_number or ''}".strip(),
            deadline_iso=case.escalation.external_review_deadline or "",
            description=f"State DOI: {doi_info.doi_name}. {doi_info.doi_contact_instruction}",
        )
        recommended = "recommended" if case.escalation.eligible_for_external_review else "not recommended"
        msg = (
            f"Escalation package written to escalation_package.md (external review {recommended}). "
            f"{ics_message}"
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
            cross_verify_denial_findings,
            record_case_and_check_insurer_patterns,
            build_physician_evidence_request_tool,
            draft_appeal_package,
            review_appeal_package,
            check_appeal_guardrail,
            prepare_external_review_escalation,
        ],
    )
    # Always pass callback_handler explicitly, even when it's None: Strands'
    # Agent treats an *omitted* callback_handler as "use my own verbose
    # PrintingCallbackHandler default" but an *explicit* None as "stay
    # silent" (null_callback_handler) - conflating "not given" with
    # "silence requested" here would make --quiet a no-op.
    agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
