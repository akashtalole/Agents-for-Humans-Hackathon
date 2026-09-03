"""Typed data contracts passed between ClaimClarity's agents."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ClaimLineItem(BaseModel):
    """One denied service on the EOB/denial notice."""

    procedure_code: str = Field(description="CPT/HCPCS procedure code as billed")
    procedure_description: str = Field(default="")
    diagnosis_code_billed: str = Field(
        default="", description="ICD-10-CM diagnosis code exactly as it appears on the claim"
    )
    billed_amount: str = Field(default="", description="Dollar amount billed for this line item")
    denial_reason_text: str = Field(default="", description="The denial reason as written on the EOB")
    carc_code: str = Field(default="", description="Claim Adjustment Reason Code, if stated (e.g. 'CO-16')")
    rarc_code: str = Field(default="", description="Remittance Advice Remark Code, if stated (e.g. 'M76')")


class ClaimRecord(BaseModel):
    """Structured extraction of an EOB/denial notice plus supporting documents."""

    patient_name: str = Field(default="")
    member_id: str = Field(default="")
    insurer_name: str = Field(default="")
    provider_name: str = Field(default="")
    claim_number: str = Field(default="")
    date_of_service: str = Field(default="", description="YYYY-MM-DD if determinable")
    notice_date: str = Field(default="", description="Date the denial notice was issued, YYYY-MM-DD if determinable")
    appeal_deadline: str = Field(
        default="", description="Deadline to file an appeal, normalized to YYYY-MM-DD if determinable"
    )
    appeal_submission_method: str = Field(default="", description="Address/portal/fax for filing an appeal")
    state: str = Field(
        default="",
        description="Patient's US state, normalized to a two-letter USPS abbreviation (e.g. 'CA') if "
        "determinable from the documents - used only to point to the right state's external review/DOI "
        "process, never guessed",
    )
    line_items: list[ClaimLineItem] = Field(default_factory=list)
    relevant_plan_terms: list[str] = Field(
        default_factory=list, description="Excerpts from the plan's summary of benefits relevant to the denied services"
    )
    clinical_notes_summary: str = Field(
        default="", description="2-4 sentence summary of the relevant medical record findings"
    )


class Classification(str, Enum):
    BILLING_ERROR = "billing_error"
    DOCUMENTATION_GAP = "documentation_gap"
    VALID_DENIAL = "valid_denial"
    NEEDS_REVIEW = "needs_review"


class LineItemFinding(BaseModel):
    procedure_code: str
    classification: Classification
    evidence: str = Field(
        description="What the ICD-10 validation and/or plan terms actually show - be specific and factual"
    )
    corrected_diagnosis_code: str = Field(
        default="", description="If the issue is an invalid/wrong diagnosis code, the corrected billable code to use"
    )
    recommendation: str = Field(description="The concrete next step, or why appealing isn't worth it")
    worth_appealing: bool


class DenialFindings(BaseModel):
    findings: list[LineItemFinding] = Field(default_factory=list)
    overall_recommendation: str = Field(
        description="One or two sentences a patient can read in ten seconds: what to do next, overall"
    )


class AppealPackage(BaseModel):
    appeal_letter: str = Field(
        default="", description="Formal appeal letter covering every line item worth appealing. Empty if none."
    )
    non_appeal_explanation: str = Field(
        default="", description="Plain-language explanation of any line items not worth appealing, and why"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="Decisions only the patient can make, e.g. whether to still appeal a long shot"
    )


class StateDOIInfo(BaseModel):
    """State Department of Insurance / external review reference data, loaded
    from data/state_doi_reference.json - never model-generated, so it can
    never invent a citation, deadline, or contact detail."""

    state_code: str = Field(description="Two-letter USPS abbreviation, or 'DEFAULT' for the federal fallback")
    state_name: str
    doi_name: str = Field(description="The regulator(s) that handle insurance complaints for this state")
    doi_complaint_process: str = Field(description="Plain-language summary of how to file a DOI complaint")
    external_review_process: str = Field(description="Plain-language summary of the independent external review process")
    external_review_deadline_window: str = Field(
        description="The typical deadline window to request external review, in words - not a fabricated exact date"
    )
    doi_contact_instruction: str = Field(
        description="Where to find current, official contact info - a search term or stable directory URL, never a "
        "specific phone number, which cannot be verified offline and goes stale"
    )
    regulatory_note: str = Field(
        default="", description="Plain-language description of the legal framework - never a fabricated statute citation"
    )


class EvidenceRequestItem(BaseModel):
    """One denied line item where physician-supplied clinical documentation
    could plausibly change the outcome - never generated for a line item
    whose denial is a pure billing-code error or a plan-eligibility
    exclusion, since physician evidence can't fix either of those."""

    procedure_code: str
    evidence_needed: str = Field(
        description="The specific clinical documentation this denial's medical necessity criteria would need - "
        "concrete, e.g. 'documented failure of at least 6 weeks of physical therapy prior to imaging', never vague "
        "filler like 'more documentation'"
    )
    why_insurer_requires_it: str = Field(
        description="Why the insurer likely requires this - tied to the plan's own stated medical necessity "
        "criteria if present in relevant_plan_terms, otherwise general standard-of-care reasoning clearly labeled "
        "as such rather than presented as this plan's own language"
    )
    physician_office_justification: str = Field(
        description="A short justification a physician's office can read and act on quickly - what to pull from "
        "the chart and why it supports medical necessity for this diagnosis/procedure"
    )


class PhysicianEvidenceRequest(BaseModel):
    """What to ask the treating physician's office for before the appeal is
    filed, so the appeal can cite the specific documentation the insurer's
    own medical necessity criteria actually require - not generic notes. See
    agents/evidence_request_builder.py's system prompt for the evidence
    discipline this model is meant to enforce."""

    items: list[EvidenceRequestItem] = Field(default_factory=list)
    cover_letter_to_physician: str = Field(
        default="",
        description="Ready-to-send draft the patient can hand to their doctor's office, listing exactly what's "
        "being requested and why. Empty if no line items qualified.",
    )
    patient_followup_checklist: list[str] = Field(
        default_factory=list,
        description="What the patient should personally track/confirm, e.g. confirm the office received the "
        "request, follow up if no response within a stated number of business days",
    )
    rationale: str = Field(
        description="Plain-language explanation for a stressed patient: which items were flagged and why, or - "
        "honestly - why none were"
    )


class DeniedItemSummary(BaseModel):
    """One denied line item's compact, non-clinical fingerprint, recorded to
    the persistent cross-run insurer accountability history
    (claimclarity/tools/history.py) after every case. Deliberately narrow -
    no diagnosis code, billed amount, or clinical detail - just enough to
    match recurrence, the same discipline glacierwatch/models.py's
    HistoryEntry uses to keep its own persisted history small."""

    procedure_code: str
    procedure_description: str = ""
    denial_reason_category: str = Field(
        description="The recurrence-matching key for this denial: the claim's own CARC code if stated, else its "
        "literal denial reason text, else the investigation's classification - see "
        "claimclarity/tools/history.py's docstring for why this is an exact/near-exact string match, not "
        "semantic matching"
    )
    worth_appealing: bool


class ClaimHistoryEntry(BaseModel):
    """One completed case's compact record, appended to the persistent
    cross-run history file after investigate_denial_tool runs."""

    insurer_name: str
    recorded_at: str = Field(description="ISO timestamp this case was recorded")
    claim_number: str = ""
    denied_items: list[DeniedItemSummary] = Field(default_factory=list)


class ClaimHistory(BaseModel):
    """The full cross-run insurer accountability history file: every
    ClaimHistoryEntry recorded across all past cases, in the order they were
    appended (oldest first)."""

    entries: list[ClaimHistoryEntry] = Field(default_factory=list)


class InsurerPatternInsight(BaseModel):
    """A pure-code-detected recurrence: the same insurer denying the same
    kind of thing on the same stated basis across 2+ separate recorded
    cases - never an LLM judgment call. See
    claimclarity/tools/history.py:detect_insurer_patterns for the exact,
    documented (and deliberately conservative) matching rule."""

    insurer_name: str
    denial_reason_category: str
    procedure_description: str = Field(
        default="", description="A representative denied procedure description for this pattern, for readability"
    )
    occurrence_count: int = Field(description="Number of separate recorded cases this denial reason recurred in")
    dates: list[str] = Field(default_factory=list, description="Timestamps of each recorded case this pattern spans")
    claim_numbers: list[str] = Field(default_factory=list)


class EscalationPackage(BaseModel):
    """What to do after the internal appeal: independent External Review, and,
    only where the findings actually support it, a state DOI complaint about
    how the claim was handled. Not legal advice - see
    agents/escalation_advisor.py's system prompt for the evidence discipline
    this model is meant to enforce."""

    eligible_for_external_review: bool = Field(
        description="True when at least one denied line item was found worth appealing and the internal appeal "
        "doesn't fully resolve the denial - i.e. there is a genuine unresolved dispute to escalate"
    )
    external_review_deadline: str | None = Field(
        default=None,
        description="Deadline to request independent external review, normalized to YYYY-MM-DD only if an actual "
        "date can be derived from the dates given; otherwise a plain-language description of the deadline window "
        "(e.g. 'within 4 months of the internal appeal decision'). Never a fabricated exact date.",
    )
    external_review_request_letter: str = Field(
        default="",
        description="Drafted, ready-to-send letter requesting independent external review, referencing the "
        "specific denied line items and the prior internal appeal. Empty if not eligible.",
    )
    state_doi_complaint_letter: str | None = Field(
        default=None,
        description="Drafted only when the findings show a genuine process failure (e.g. a billing error or "
        "documentation gap the insurer should have caught) - never filed reflexively for a valid denial. Null "
        "when there is no such basis.",
    )
    regulatory_basis: list[str] = Field(
        default_factory=list,
        description="Plain-language citations for the rights described, grounded in the provided reference data - "
        "never a fabricated citation",
    )
    escalation_checklist: list[str] = Field(
        default_factory=list, description="Concrete, ordered next steps the patient can actually follow"
    )
    rationale: str = Field(description="Plain-language explanation of the recommendation, for a stressed patient")
