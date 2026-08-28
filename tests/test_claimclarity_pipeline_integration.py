"""End-to-end test against a real model. Skipped unless explicitly opted into
with CLAIMCLARITY_RUN_INTEGRATION=1, since it makes live, billed API calls."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from claimclarity.pipeline import run_claim_case

RUN_INTEGRATION = os.environ.get("CLAIMCLARITY_RUN_INTEGRATION") == "1"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "claimclarity"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set CLAIMCLARITY_RUN_INTEGRATION=1 to run live-model tests")
def test_full_pipeline_on_example_claim(tmp_path: Path):
    result = run_claim_case(
        documents_paths=[
            str(EXAMPLES_DIR / "denial_notice.md"),
            str(EXAMPLES_DIR / "plan_summary_of_benefits.md"),
            str(EXAMPLES_DIR / "medical_record_excerpt.md"),
        ],
        output_dir=str(tmp_path / "output"),
    )

    case = result.case
    assert case.claim is not None
    assert case.findings is not None
    assert case.appeal is not None

    findings_by_code = {f.procedure_code: f for f in case.findings.findings}
    # The PT line item was billed with a deprecated, non-billable diagnosis code
    # (M54.5) against a plan that otherwise covers the service - this should be
    # caught as a fixable billing error.
    assert findings_by_code["97110"].classification.value == "billing_error"
    assert findings_by_code["97110"].worth_appealing is True
    # The massage therapy line item is excluded by the plan outright - this
    # should NOT be recommended for appeal.
    assert findings_by_code["97124"].worth_appealing is False

    for filename in (
        "claim_summary.md",
        "denial_findings.md",
        "decisions_needed.md",
        "appeal_package.md",
        "appeal_deadline.ics",
    ):
        assert (tmp_path / "output" / filename).exists(), f"{filename} was not written"
