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
