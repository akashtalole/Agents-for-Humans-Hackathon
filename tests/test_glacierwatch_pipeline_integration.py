"""End-to-end test against real APIs and a real model. Skipped unless
explicitly opted into with GLACIERWATCH_RUN_INTEGRATION=1, since it makes
live, billed model calls plus live calls to Open-Meteo and USGS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from glacierwatch.pipeline import run_watchlist

RUN_INTEGRATION = os.environ.get("GLACIERWATCH_RUN_INTEGRATION") == "1"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set GLACIERWATCH_RUN_INTEGRATION=1 to run live-model tests")
def test_full_pipeline_against_real_apis_and_model(tmp_path: Path):
    result = run_watchlist(output_dir=str(tmp_path / "output"))

    run = result.run
    assert len(run.sites) == 4
    assert len(run.briefs) == 4
    assert run.report is not None

    # Historical case-study sites must never be classified as if actively
    # building toward another failure - this is the specific honesty
    # guarantee risk_assessor's system prompt is instructed to uphold.
    briefs_by_id = {b.site_id: b for b in run.briefs}
    for site in run.sites:
        if site.status == "historical_case_study":
            assert briefs_by_id[site.id].priority_level.value == "routine"

    for filename in ("watchlist_report.md",):
        assert (tmp_path / "output" / filename).exists(), f"{filename} was not written"
