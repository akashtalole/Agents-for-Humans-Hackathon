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
from datetime import datetime, timezone
from pathlib import Path

from strands import Agent, tool

from bidwright.agents.amendment_analyzer import analyze_amendment
from bidwright.agents.compliance_checker import check_compliance
from bidwright.agents.proposal_drafter import draft_proposal
from bidwright.agents.rfp_analyzer import analyze_rfp
from bidwright.agents.teaming_advisor import draft_teaming_plan
from bidwright.config import create_agent
from bidwright.models import (
    AmendmentImpact,
    BidHistory,
    BidHistoryEntry,
    BidHistoryGap,
    ComplianceReport,
    ProposalDraft,
    RecurringGapInsight,
    RFPRequirements,
    TeamingPlan,
)
from bidwright.rendering import (
    render_amendment_impact_md,
    render_compliance_md,
    render_decision_summary_md,
    render_portfolio_insights_md,
    render_proposal_md,
    render_requirements_md,
    render_teaming_plan_md,
)
from bidwright.tools.calendar import create_deadline_reminder
from bidwright.tools.documents import read_document, save_text_file
from bidwright.tools.history import (
    DEFAULT_WINDOW_SIZE,
    append_entry,
    detect_recurring_gaps,
    load_history,
    save_history,
)

ORCHESTRATOR_PROMPT = """\
You are BidWright, an assistant that takes a small business from "here's an \
RFP" to "here's a compliant, tailored proposal draft and a clear list of what \
you still need to decide" — with as little of the owner's time spent as \
possible.

For every job, always run the full pipeline in this order:
1. load_rfp_and_profile
2. extract_rfp_requirements
3. check_company_compliance
4. record_bid_and_check_portfolio_trends
5. draft_teaming_plan_tool
6. create_submission_deadline_reminder
7. analyze_rfp_amendment
8. draft_proposal_document

Step 4 records this bid's compliance outcome to a persistent cross-bid \
history file and checks whether any of this run's gaps have also shown up \
on this company's recent past bids - a pattern invisible from any single \
bid's compliance report. Always call it right after the compliance check, \
even on the very first bid ever recorded (it reports "not enough history \
yet" cleanly, that is not a failure).

Step 5 looks at whatever compliance gaps step 3 found and recommends where \
teaming with a subcontractor or joint-venture partner could close the ones \
this company can't plausibly fix alone - always call it right after the \
compliance check, even if there are zero gaps (it still reports that cleanly, \
that is not a failure).

Step 7 only matters when an amendment/addendum document was provided for \
this job - always call it anyway, right after the compliance check and before \
drafting the proposal, so a changed requirement can't slip into a stale \
proposal draft. If it reports back that no amendment is configured, that is \
not a failure - just move on to draft_proposal_document.

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
    amendment_path: str | None = None
    history_file: str = "bidwright_history.json"
    rfp_text: str = ""
    profile_text: str = ""
    requirements: RFPRequirements | None = None
    compliance: ComplianceReport | None = None
    amendment_impact: AmendmentImpact | None = None
    teaming_plan: TeamingPlan | None = None
    proposal: ProposalDraft | None = None
    history: BidHistory = field(default_factory=BidHistory)
    portfolio_insights: list[RecurringGapInsight] = field(default_factory=list)
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
    def record_bid_and_check_portfolio_trends() -> str:
        """Append this run's compliance outcome (RFP identity, overall
        status, and each gap's requirement description + severity - not
        full gap detail) to the persistent cross-bid history file, then
        scan recent history for gap requirements that have recurred across
        multiple of this company's past bids - a pattern invisible from any
        single bid's compliance report. Always writes portfolio_insights.md,
        even on the very first run ever recorded (a graceful "not enough
        bid history yet" message, not an error). Must be called after
        check_company_compliance."""
        if job.compliance is None:
            return "Error: call check_company_compliance first."

        entry = BidHistoryEntry(
            project_title=job.requirements.project_title,
            issuing_organization=job.requirements.issuing_organization,
            run_at=datetime.now(timezone.utc).isoformat(),
            overall_status=job.compliance.overall_status,
            gaps=[
                BidHistoryGap(requirement=gap.requirement, severity=gap.severity)
                for gap in job.compliance.gaps
            ],
        )

        prior_history = load_history(job.history_file)
        job.history = append_entry(prior_history, entry)
        save_history(job.history_file, job.history)
        job.portfolio_insights = detect_recurring_gaps(job.history)
        save_text_file(
            str(out_dir / "portfolio_insights.md"),
            render_portfolio_insights_md(
                job.portfolio_insights, len(job.history.entries), DEFAULT_WINDOW_SIZE
            ),
        )

        msg = (
            f"Recorded this bid to portfolio history ({job.history_file}); "
            f"{len(job.history.entries)} bid(s) on record. "
            f"{len(job.portfolio_insights)} recurring gap(s) detected across recent bids. "
            "See portfolio_insights.md."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def draft_teaming_plan_tool() -> str:
        """Look at the compliance gaps found by check_company_compliance and
        recommend, for each gap that is plausibly fillable this way, teaming
        with a subcontractor or joint-venture partner instead of the company
        abandoning a bid it can't fully meet alone: concrete search guidance
        (SAM.gov SubNet, PTAC/APEX centers, trade associations - never a
        fabricated company name), a draft outreach email, and the
        subcontracting-limit risk to verify against the RFP. Must be called
        after check_company_compliance. If there are zero compliance gaps,
        it still succeeds and reports that plainly - that is not an error."""
        if job.compliance is None:
            return "Error: call check_company_compliance first."
        if not job.compliance.gaps:
            job.teaming_plan = TeamingPlan(
                recommendations=[],
                summary="No compliance gaps were found in this run, so there is nothing to team on.",
            )
        else:
            job.teaming_plan = draft_teaming_plan(job.requirements, job.compliance, job.profile_text)
        save_text_file(str(out_dir / "teaming_plan.md"), render_teaming_plan_md(job.teaming_plan))
        msg = (
            f"Teaming plan complete. {len(job.teaming_plan.recommendations)} gap(s) have a "
            "teaming recommendation. Full details saved to teaming_plan.md."
        )
        job.activity_log.append(msg)
        return msg

    @tool
    def analyze_rfp_amendment() -> str:
        """Diff a newly issued RFP amendment/addendum against the already
        extracted requirements and (if available) the prior compliance
        report: what's new, removed, or modified, whether the deadline moved,
        and what it means for compliance and any drafted proposal. Must be
        called after extract_rfp_requirements. If this job has no amendment
        document configured, it reports that and does nothing - that's an
        expected, normal outcome, not an error, for the common case where no
        amendment was ever issued."""
        if job.requirements is None:
            return "Error: call extract_rfp_requirements first."
        if not job.amendment_path:
            return "No amendment document was provided for this job - nothing to do."
        amendment_text = read_document(job.amendment_path)
        job.amendment_impact = analyze_amendment(job.requirements, job.compliance, amendment_text)
        save_text_file(
            str(out_dir / "amendment_impact.md"), render_amendment_impact_md(job.amendment_impact)
        )
        if job.compliance is not None:
            save_text_file(
                str(out_dir / "decisions_needed.md"),
                render_decision_summary_md(job.requirements, job.compliance, job.amendment_impact),
            )
        msg = (
            f"Amendment analyzed. Urgency: {job.amendment_impact.urgency.value}. "
            f"Deadline changed: {job.amendment_impact.deadline_changed}. "
            f"{len(job.amendment_impact.new_requirements)} new, "
            f"{len(job.amendment_impact.removed_requirements)} removed, "
            f"{len(job.amendment_impact.modified_requirements)} modified requirement(s). "
            "Full details saved to amendment_impact.md."
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
        if job.teaming_plan is not None and job.teaming_plan.recommendations:
            # Appended in code, not by re-prompting the drafter, so this pointer
            # is guaranteed present whenever a teaming plan exists rather than
            # depending on the drafter agent to remember to mention it.
            job.proposal.open_questions.append(
                "Some open compliance gaps may be fillable by teaming with a subcontractor "
                "or joint-venture partner instead of fixing them in-house - see "
                "teaming_plan.md for search guidance and a draft outreach email."
            )
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
            record_bid_and_check_portfolio_trends,
            draft_teaming_plan_tool,
            create_submission_deadline_reminder,
            analyze_rfp_amendment,
            draft_proposal_document,
        ],
    )
    # Always pass callback_handler explicitly, even when it's None: Strands'
    # Agent treats an *omitted* callback_handler as "use my own verbose
    # PrintingCallbackHandler default" but an *explicit* None as "stay
    # silent" (null_callback_handler) - conflating "not given" with
    # "silence requested" here would make --quiet a no-op.
    agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
