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
