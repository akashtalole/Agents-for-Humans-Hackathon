"""Validates the simulator against documented Kumbh crowd-crush incidents
*and* against controls that must not flag.

Pure code, no LLM - see simulator.py's module docstring for why.

Why the controls matter. An earlier version of this module ran only the two
historical disasters and asserted each came back CRITICAL. Both scenarios sit
far above every threshold in the model, so that suite was passed in full by a
function whose entire body was `return CRITICAL`. It could not fail, which
means passing it established nothing. The negative controls below are what
give the suite discriminative power: they are ordinary and well-managed days
that must come back not-CRITICAL, so a model that simply shouts CRITICAL at
everything now fails loudly.

The sharpest of them is the pair kumbh_managed_snan_control /
kumbh_funnelled_snan_control: identical crowd, identical window, identical
surge, differing only in whether the 1.8m Kalaram Mandir lane is on the route.
One must stay routine and the other must flag. That pair is the only evidence
in this repo that the simulator responds to an *intervention* rather than
merely to headcount - which is the whole premise of using it to rehearse a
plan.

What this still does not establish: the controls are synthetic, and every
capacity figure they run against is Trinetra's own estimate (see
sites.json's _citation_note). Passing means the model is internally
consistent and responds to routing in the expected direction. It does not
mean the thresholds are right for the real Nashik ghats. Only NTKMA's
surveyed capacities and their own record of non-incident days can establish
that. See TRINETRA.md's honest-limitations section.
"""
from __future__ import annotations

import json
from pathlib import Path

from trinetra.models import CalibrationCase, CalibrationCaseKind, CalibrationResult, RiskLevel
from trinetra.tools.geography import load_sites
from trinetra.tools.simulator import simulate_scenario

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "calibration_cases.json"


def load_calibration_cases() -> list[CalibrationCase]:
    raw = json.loads(_DATA_PATH.read_text())
    cases = [CalibrationCase(**c) for c in raw["cases"]]
    _assert_suite_can_fail(cases)
    return cases


def _assert_suite_can_fail(cases: list[CalibrationCase]) -> None:
    """A calibration suite with no negative controls is a tautology. Refuse to
    run one rather than report a meaningless pass."""
    if not any(c.expect_critical for c in cases):
        raise ValueError("Calibration suite has no historical incidents to detect - nothing is being validated.")
    if not any(not c.expect_critical for c in cases):
        raise ValueError(
            "Calibration suite has no negative controls: every case expects CRITICAL, so `return CRITICAL` "
            "would pass it. Add at least one case with expect_critical=false before trusting a passing run."
        )


def run_calibration_case(case: CalibrationCase) -> CalibrationResult:
    ghats, routes = load_sites()
    report = simulate_scenario(case.scenario, ghats, routes)
    was_critical = report.overall_risk == RiskLevel.CRITICAL
    correctly_flagged = was_critical == case.expect_critical

    if correctly_flagged and case.expect_critical:
        note = f"Simulator returned {report.overall_risk.value} risk (matches the documented outcome)."
    elif correctly_flagged:
        note = (
            f"Control held: simulator returned {report.overall_risk.value}, correctly declining to flag a "
            f"day this model should consider manageable."
        )
    elif case.expect_critical:
        note = (
            f"MISS: simulator returned {report.overall_risk.value} risk but the real incident caused "
            f"{case.deaths} deaths - thresholds need retuning before this scenario type is trusted."
        )
    else:
        note = (
            "FALSE ALARM: simulator returned CRITICAL for a day it should treat as manageable. A model that "
            "flags everything gives a control room no way to tell a real warning from noise."
        )

    return CalibrationResult(
        case_id=case.case_id,
        case_name=case.name,
        real_world_deaths=case.deaths,
        simulated_peak_risk=report.overall_risk,
        correctly_flagged=correctly_flagged,
        note=note,
        case_kind=case.case_kind,
        expect_critical=case.expect_critical,
    )


def run_all_calibration_cases() -> list[CalibrationResult]:
    return [run_calibration_case(c) for c in load_calibration_cases()]
