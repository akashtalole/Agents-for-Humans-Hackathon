"""Typed data contracts passed between BidWright's agents.

Every sub-agent produces one of these Pydantic models via Strands'
`structured_output_model=` so downstream code (and the orchestrator's other
tools) can rely on a schema instead of parsing free text.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class ChecklistItem(BaseModel):
    """A single item the submission must include or satisfy."""

    item: str = Field(description="Short label for the checklist item")
    required: bool = Field(default=True, description="Whether this item is mandatory")
    notes: str = Field(default="", description="Any detail, e.g. page limit or format")


class RFPRequirements(BaseModel):
    """Structured extraction of everything a bidder must know about an RFP."""

    project_title: str = Field(description="Title/name of the project or contract")
    issuing_organization: str = Field(description="The organization issuing the RFP")
    submission_deadline: str = Field(
        description=(
            "The submission deadline as stated in the document, normalized to "
            "'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM' when a time zone/time is given. "
            "If unstated, use an empty string."
        )
    )
    submission_method: str = Field(
        default="", description="How to submit, e.g. email address, portal, or mailing address"
    )
    required_certifications: list[str] = Field(default_factory=list)
    required_licenses: list[str] = Field(default_factory=list)
    insurance_requirements: list[str] = Field(
        default_factory=list,
        description="Each entry should state the coverage type and minimum amount, e.g. "
        "'General liability, minimum $2,000,000 per occurrence'",
    )
    eligibility_criteria: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(
        default_factory=list, description="How submissions will be scored/compared"
    )
    submission_format_rules: list[str] = Field(
        default_factory=list, description="Page limits, fonts, file formats, number of copies, etc."
    )
    checklist: list[ChecklistItem] = Field(default_factory=list)
    key_scope_summary: str = Field(
        default="", description="2-4 sentence plain-language summary of the scope of work"
    )


class ComplianceGap(BaseModel):
    requirement: str = Field(description="The specific requirement being evaluated")
    status: str = Field(description="One of: met, gap, needs_review")
    severity: Severity = Field(description="blocking, warning, or info")
    detail: str = Field(description="Why this is/isn't met, referencing the company profile")
    recommendation: str = Field(
        default="", description="Concrete next step to close the gap, if any"
    )


class ComplianceReport(BaseModel):
    overall_status: str = Field(description="One of: ready, gaps_found")
    met_requirements: list[str] = Field(default_factory=list)
    gaps: list[ComplianceGap] = Field(default_factory=list)


class ModifiedRequirement(BaseModel):
    """A requirement the amendment changed, not just added or removed."""

    item: str = Field(description="Which requirement or checklist item this amendment changes")
    previous: str = Field(description="What it said before the amendment")
    updated: str = Field(description="What it says now, per the amendment")
    notes: str = Field(default="", description="Any additional context, e.g. why it matters")


class AmendmentImpact(BaseModel):
    """Structured diff of an RFP amendment/addendum against the original
    requirements, and what it means for compliance and the proposal draft."""

    summary: str = Field(
        description="2-4 sentence plain-language summary of what this amendment changes"
    )
    urgency: Severity = Field(
        description="blocking if this invalidates prior compliance work or moves the "
        "deadline sooner; warning if it adds meaningful new obligations; info if it's a "
        "minor clarification"
    )
    deadline_changed: bool = Field(default=False)
    new_deadline: str | None = Field(
        default=None,
        description="The new submission deadline if changed, normalized like "
        "RFPRequirements.submission_deadline. None if unchanged.",
    )
    new_requirements: list[ChecklistItem] = Field(
        default_factory=list, description="Requirements this amendment adds that were not in the original RFP"
    )
    removed_requirements: list[ChecklistItem] = Field(
        default_factory=list, description="Requirements this amendment explicitly removes or waives"
    )
    modified_requirements: list[ModifiedRequirement] = Field(
        default_factory=list, description="Requirements this amendment changes rather than adds or removes"
    )
    compliance_impact: str = Field(
        default="",
        description="Whether this amendment invalidates any previously-met compliance item or "
        "previously-identified gap, and why. Empty string if there is no prior compliance "
        "report to reconsider or nothing is affected.",
    )
    proposal_sections_requiring_revision: list[str] = Field(
        default_factory=list,
        description="Which sections of an already-drafted proposal (e.g. 'technical_approach', "
        "'compliance_matrix_notes') need rework because of this amendment. Empty if none or no "
        "proposal has been drafted yet.",
    )
    recommendation: str = Field(
        description="Concrete next step for a busy owner, e.g. 'Update your insurance "
        "certificate reference before resubmitting - the amendment raised the minimum coverage.'"
    )


class TeamingRecommendation(BaseModel):
    """A single suggested teaming/subcontracting arrangement that would close
    one compliance gap the company can't plausibly close alone."""

    gap: ComplianceGap = Field(description="The specific compliance gap this recommendation addresses")
    capability_needed: str = Field(
        description="The specific capability, certification, or capacity a teaming partner "
        "would need to bring, e.g. 'Active 8(a) certification' or 'Bonding capacity for a "
        "$500,000 performance bond'"
    )
    partner_search_guidance: str = Field(
        description="Concrete, actionable places and search terms to find a real partner - "
        "e.g. SAM.gov's Subcontracting Network (SubNet), the SBA's SBIR/STTR partner "
        "directories, the relevant local PTAC/APEX Accelerator, a named trade association for "
        "this trade/NAICS code, or the awarding agency's small business liaison office. Never a "
        "vague instruction like 'find a partner' - always something the owner could act on this week."
    )
    outreach_email_draft: str = Field(
        description="A ready-to-send email a business owner could send with light edits to a "
        "prospective teaming partner, pitching the specific arrangement and what this company "
        "brings to it"
    )
    teaming_risk_note: str = Field(
        description="A risk to verify before relying on this arrangement - e.g. many "
        "solicitations cap the percentage of work that may be subcontracted, or require the "
        "prime to self-perform a minimum percentage. Flag this as something to check against "
        "the RFP's actual limit if it isn't stated in the extracted requirements."
    )


class TeamingPlan(BaseModel):
    """Teaming/subcontracting recommendations for the compliance gaps that are
    plausibly fillable that way, rather than gaps the company should simply
    fix itself."""

    recommendations: list[TeamingRecommendation] = Field(default_factory=list)
    summary: str = Field(
        description="2-4 plain-language sentences for a busy owner: how many gaps could be "
        "filled by teaming, and the single most important next step. If no gaps are "
        "teaming-fillable, say so plainly and explain why (e.g. the gaps are all easy in-house "
        "fixes, or the remaining gap requires something only the prime itself can hold)."
    )


class BidHistoryGap(BaseModel):
    """One compliance gap's compact record within a BidHistoryEntry - just
    the requirement description and severity, not full ComplianceGap detail
    (e.g. no `detail`, which is often instance-specific like "you carry
    $1,000,000, need $2,000,000" and would rarely match itself run to run
    even for the same underlying problem)."""

    requirement: str
    severity: Severity


class BidHistoryEntry(BaseModel):
    """One completed bid run's compact record, appended to the persistent
    cross-bid history file (bidwright/tools/history.py) after every run's
    compliance check. Deliberately narrow - project identity, overall
    status, and just the gap descriptions/severities - so a small
    business's history file stays small and easy to reason about even after
    years of bids."""

    project_title: str
    issuing_organization: str
    run_at: str = Field(description="ISO timestamp this run's compliance check was recorded")
    overall_status: str = Field(description="The ComplianceReport.overall_status recorded for this run")
    gaps: list[BidHistoryGap] = Field(default_factory=list)


class BidHistory(BaseModel):
    """The full cross-bid history file: every BidHistoryEntry recorded
    across all past runs, in the order they were appended (oldest first)."""

    entries: list[BidHistoryEntry] = Field(default_factory=list)


class RecurringGapInsight(BaseModel):
    """A compliance gap requirement description that has recurred across
    multiple past bids, detected by exact-string match over a recent window
    of recorded runs - see bidwright/tools/history.py:detect_recurring_gaps
    for the exact logic. A plain frequency count over BidHistoryEntry
    records, never an LLM judgment call."""

    requirement: str = Field(description="The gap requirement description, exactly as recorded")
    severity: Severity = Field(description="The severity of the most recent occurrence of this gap")
    occurrences: int = Field(description="How many runs in the scanned window this gap appeared in")
    runs_considered: int = Field(description="How many recent runs were scanned (the window size)")
    first_seen_rfp: str = Field(
        description="Project title and issuing organization where this gap first appeared, "
        "within the scanned window"
    )
    most_recent_rfp: str = Field(
        description="Project title and issuing organization of the most recent run where this "
        "gap appeared"
    )


class ReviewResult(BaseModel):
    """A skeptical second-pass review of a drafted proposal against the
    compliance report it was drafted from - catches the proposal claiming
    something is compliant that the compliance report says is a gap,
    inventing a certification/capability not in the company profile, or
    quietly omitting an open blocking gap. Never a prose-style critique."""

    approved: bool
    issues: list[str] = Field(default_factory=list)
    summary: str


class ComplianceDisagreement(BaseModel):
    """One requirement where the first compliance check and the independent
    second audit reached different conclusions - always surfaced to a human,
    never silently resolved in favor of either agent."""

    requirement: str = Field(
        description="The requirement text, copied EXACTLY (verbatim) as it appears in the "
        "first report's gaps or met_requirements list, so it can be matched programmatically"
    )
    first_assessment: str = Field(description="What the first compliance check concluded")
    second_assessment: str = Field(description="What the independent audit concluded")
    explanation: str = Field(description="Why the two assessments disagree, in plain language")


class ComplianceCrossCheck(BaseModel):
    """The result of comparing two independently-produced compliance reports
    for the same RFP and company - a genuine second opinion, not a revision
    of the first agent's own work."""

    agreement_count: int = Field(description="Number of requirements both reports substantively agree on")
    disagreements: list[ComplianceDisagreement] = Field(default_factory=list)
    summary: str


class GuardrailFinding(BaseModel):
    """One concrete, checkable problem found in the drafted proposal text by
    `bidwright/tools/guardrail.py` - either a deterministic pattern match or
    a subtler violation an agent-based check caught."""

    rule: str
    excerpt: str
    explanation: str


class GuardrailResult(BaseModel):
    """The combined result of running every guardrail check (deterministic
    pattern scan + agent-based check) against a drafted proposal's text."""

    passed: bool
    findings: list[GuardrailFinding] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    cover_letter: str
    executive_summary: str
    technical_approach: str
    qualifications_past_performance: str
    compliance_matrix_notes: str = Field(
        description="Short note per major requirement on how the proposal addresses it, "
        "explicitly flagging anything still open instead of claiming compliance it can't back up"
    )
    pricing_notes: str = Field(
        description="Guidance for the human on how to complete pricing; never invent numbers"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions or decisions only a human at the company can resolve",
    )
