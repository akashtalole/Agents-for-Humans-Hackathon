"""Validates the simulator against real, documented Kumbh crowd-crush incidents.

Pure code, no LLM - see simulator.py's module docstring for why. If
run_calibration() doesn't come back correctly_flagged=True for both bundled
cases, the simulator's thresholds need retuning before Trinetra is pitched
to anyone as a planning tool - a simulator that misses documented disasters
is worse than no simulator, because it would create false confidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from trinetra.models import CalibrationCase, CalibrationResult, RiskLevel
from trinetra.tools.geography import load_sites
from trinetra.tools.simulator import simulate_scenario

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "calibration_cases.json"


def load_calibration_cases() -> list[CalibrationCase]:
    raw = json.loads(_DATA_PATH.read_text())
    return [CalibrationCase(**c) for c in raw["cases"]]


def run_calibration_case(case: CalibrationCase) -> CalibrationResult:
    ghats, routes = load_sites()
    report = simulate_scenario(case.scenario, ghats, routes)
    correctly_flagged = report.overall_risk == RiskLevel.CRITICAL
    note = (
        f"Simulator returned {report.overall_risk.value} risk (matches the documented outcome)."
        if correctly_flagged
        else (
            f"Simulator returned {report.overall_risk.value} risk but the real incident caused "
            f"{case.deaths} deaths - thresholds need retuning before this scenario type is trusted."
        )
    )
    return CalibrationResult(
        case_id=case.case_id,
        case_name=case.name,
        real_world_deaths=case.deaths,
        simulated_peak_risk=report.overall_risk,
        correctly_flagged=correctly_flagged,
        note=note,
    )


def run_all_calibration_cases() -> list[CalibrationResult]:
    return [run_calibration_case(c) for c in load_calibration_cases()]
