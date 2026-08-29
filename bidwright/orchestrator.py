"""The orchestrator agent: the single entry point a human talks to.

It owns a `BidJob` (the working state for one RFP), and exposes each stage of
the pipeline as a tool. The orchestrator LLM decides the order of operations
and writes the final human-facing summary, but the actual documents that get
saved to disk are always produced from validated, structured data — the
orchestrator never has to (and is not trusted to) retype numbers or gaps by
hand between steps.

This is the "agents as tools" multi-agent pattern: `analyze_rfp`,
`check_compliance`, and `draft_proposal` are themselves full Strands Agent
calls with their own system prompts and structured outputs, wrapped as tools
the orchestrator agent can call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from strands import Agent, tool

from bidwright.agents.compliance_checker import check_compliance
from bidwright.agents.proposal_drafter import draft_proposal
from bidwright.agents.rfp_analyzer import analyze_rfp
from bidwright.config import create_agent
from bidwright.models import ComplianceReport, ProposalDraft, RFPRequirements
from bidwright.rendering import (
    render_compliance_md,
    render_decision_summary_md,
    render_proposal_md,
    render_requirements_md,
)
from bidwright.tools.calendar import create_deadline_reminder
from bidwright.tools.documents import read_document, save_text_file

ORCHESTRATOR_PROMPT = """\
You are BidWright, an assistant that takes a small business from "here's an \
RFP" to "here's a compliant, tailored proposal draft and a clear list of what \
you still need to decide" — with as little of the owner's time spent as \
possible.

For every job, always run the full pipeline in this order:
1. load_rfp_and_profile
2. extract_rfp_requirements
3. check_company_compliance
4. create_submission_deadline_reminder
5. draft_proposal_document

Then write a final answer for a busy small business owner who has 30 seconds. \
Your tool results only give you counts and filenames, not the actual gap \
text - so do NOT try to recall or restate specific gap details, dollar \
amounts, or requirement names from memory. You do not reliably have them, \
and guessing produces confident-sounding fabrications. Instead, your final \
answer must include, in this order:
- One-line bottom line: are we ready to submit, or are there blocking gaps \
(state the count only, e.g. "3 blocking gaps").
- The submission deadline.
- A direct pointer to decisions_needed.md as the place to read the specific \
blocking gaps and recommended actions - do not enumerate them yourself.
- Where to find the full requirements, compliance report, and proposal draft \
files.

Never claim a gap is resolved unless the compliance report says so. Never \
skip a step. If a tool reports an error because a previous step wasn't run, \
run the missing step and retry.
"""


@dataclass
class BidJob:
    """Working state for one RFP, shared across every tool call in this run."""

    rfp_path: str
    profile_path: str
    output_dir: str
    rfp_text: str = ""
    profile_text: str = ""
    requirements: RFPRequirements | None = None
    compliance: ComplianceReport | None = None
    proposal: ProposalDraft | None = None
    activity_log: list[str] = field(default_factory=list)


def build_orchestrator(job: BidJob, callback_handler=None) -> Agent:
    """Build an orchestrator Agent bound to a specific BidJob's state via closures."""
    out_dir = Path(job.output_dir)

    @tool
    def load_rfp_and_profile() -> str:
        """Load and read the RFP document and the company capability profile
        from disk. Always call this first."""
        job.rfp_text = read_document(job.rfp_path)
        job.profile_text = read_document(job.profile_path)
        msg = (
            f"Loaded RFP ({len(job.rfp_text)} characters) from {job.rfp_path} and "
            f"company profile ({len(job.profile_text)} characters) from {job.profile_path}."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def extract_rfp_requirements() -> str:
        """Analyze the loaded RFP text and extract structured requirements:
        deadlines, certifications, licenses, insurance, eligibility, evaluation
        criteria, submission format rules, and a submission checklist. Must be
        called after load_rfp_and_profile."""
        if not job.rfp_text:
            return "Error: the RFP has not been loaded yet. Call load_rfp_and_profile first."
        job.requirements = analyze_rfp(job.rfp_text)
        save_text_file(str(out_dir / "requirements.md"), render_requirements_md(job.requirements))
        msg = (
            f"Extracted requirements for '{job.requirements.project_title}'. "
            f"Deadline: {job.requirements.submission_deadline or 'not stated'}. "
            f"{len(job.requirements.checklist)} checklist items, "
            f"{len(job.requirements.required_certifications)} certifications, "
            f"{len(job.requirements.insurance_requirements)} insurance requirements. "
            "Full details saved to requirements.md."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def check_company_compliance() -> str:
        """Compare the extracted RFP requirements against the company profile
        and identify compliance gaps that need a human decision, versus
        requirements already met. Must be called after
        extract_rfp_requirements."""
        if job.requirements is None:
            return "Error: call extract_rfp_requirements first."
        job.compliance = check_compliance(job.requirements, job.profile_text)
        save_text_file(str(out_dir / "compliance_report.md"), render_compliance_md(job.compliance))
        save_text_file(
            str(out_dir / "decisions_needed.md"),
            render_decision_summary_md(job.requirements, job.compliance),
        )
        blocking = [g for g in job.compliance.gaps if g.severity.value == "blocking"]
        msg = (
            f"Compliance check complete. Overall status: {job.compliance.overall_status}. "
            f"{len(job.compliance.met_requirements)} requirements met, "
            f"{len(job.compliance.gaps)} gap(s) found ({len(blocking)} blocking). "
            "Full report saved to compliance_report.md, human-facing summary saved to "
            "decisions_needed.md."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def draft_proposal_document() -> str:
        """Draft the proposal response document (cover letter, executive
        summary, technical approach, qualifications, compliance notes)
        tailored to this RFP and company profile. Call after
        check_company_compliance so known gaps are flagged as open items
        instead of false claims of compliance."""
        if job.requirements is None or job.compliance is None:
            return "Error: call extract_rfp_requirements and check_company_compliance first."
        job.proposal = draft_proposal(job.requirements, job.profile_text, job.compliance)
        save_text_file(str(out_dir / "proposal_draft.md"), render_proposal_md(job.proposal))
        msg = (
            "Draft proposal written to proposal_draft.md. "
            f"{len(job.proposal.open_questions)} open question(s) flagged for human review."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def create_submission_deadline_reminder() -> str:
        """Create a calendar (.ics) reminder file for the RFP submission
        deadline, with extra reminders 3 and 1 days before, so the deadline
        can't be missed. Must be called after extract_rfp_requirements."""
        if job.requirements is None:
            return "Error: call extract_rfp_requirements first."
        result = create_deadline_reminder(
            path=str(out_dir / "submission_deadline.ics"),
            title=f"Submit proposal: {job.requirements.project_title}",
            deadline_iso=job.requirements.submission_deadline,
            description=f"Submission method: {job.requirements.submission_method}",
        )
        job.activity_log.append(result)
        return result

    agent_kwargs = dict(
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            load_rfp_and_profile,
            extract_rfp_requirements,
            check_company_compliance,
            create_submission_deadline_reminder,
            draft_proposal_document,
        ],
    )
    if callback_handler is not None:
        agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
