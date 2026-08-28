"""End-to-end test against a real model. Skipped unless explicitly opted into
with BIDWRIGHT_RUN_INTEGRATION=1, since it makes live, billed API calls and
requires real model access (a present-but-unauthorized AWS/Anthropic
credential is not enough to make this pass)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from bidwright.pipeline import run_bid_job

RUN_INTEGRATION = os.environ.get("BIDWRIGHT_RUN_INTEGRATION") == "1"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set BIDWRIGHT_RUN_INTEGRATION=1 to run live-model tests")
def test_full_pipeline_on_example_rfp(tmp_path: Path):
    result = run_bid_job(
        rfp_path=str(EXAMPLES_DIR / "sample_rfp.md"),
        profile_path=str(EXAMPLES_DIR / "company_profile.json"),
        output_dir=str(tmp_path / "output"),
    )

    job = result.job
    assert job.requirements is not None
    assert job.compliance is not None
    assert job.proposal is not None

    # The example profile has $1M general liability against a stated $2M
    # requirement, so at least one blocking gap should be found.
    blocking = [g for g in job.compliance.gaps if g.severity.value == "blocking"]
    assert blocking, "Expected the known insurance gap to be flagged as blocking"

    for filename in (
        "requirements.md",
        "compliance_report.md",
        "decisions_needed.md",
        "proposal_draft.md",
        "submission_deadline.ics",
    ):
        assert (tmp_path / "output" / filename).exists(), f"{filename} was not written"
