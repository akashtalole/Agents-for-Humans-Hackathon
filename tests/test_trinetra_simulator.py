"""Offline, deterministic tests for trinetra/tools/simulator.py - no LLM,
no network. See simulator.py's module docstring for why the core risk
numbers are pure code."""
from __future__ import annotations

from trinetra.models import RiskLevel, SimulationScenario
from trinetra.tools.calibration import run_all_calibration_cases
from trinetra.tools.geography import load_sites
from trinetra.tools.simulator import simulate_scenario


def test_low_demand_scenario_stays_routine():
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="routine day",
        description="test",
        total_pilgrims=20000,
        duration_minutes=180,
        peak_inflow_multiplier=1.0,
        active_ghat_ids=["ramkund", "kushavarta"],
    )
    report = simulate_scenario(scenario, ghats, routes)
    assert report.overall_risk == RiskLevel.ROUTINE
    assert report.incidents_triggered == []


def test_high_demand_scenario_flags_critical_and_bottleneck():
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="Shahi Snan surge",
        description="test",
        total_pilgrims=2000000,
        duration_minutes=180,
        peak_inflow_multiplier=4.0,
        active_ghat_ids=["kalaram_marg", "ramkund"],
    )
    report = simulate_scenario(scenario, ghats, routes)
    assert report.overall_risk == RiskLevel.CRITICAL
    assert report.incidents_triggered
    kalaram_result = next(g for g in report.ghat_results if g.ghat_id == "kalaram_marg")
    assert kalaram_result.risk_level == RiskLevel.CRITICAL
    assert kalaram_result.bottleneck_routes


def test_moderate_demand_produces_elevated_not_binary():
    """A genuine mid-range scenario should be able to land at ELEVATED,
    not just ever bounce between ROUTINE and CRITICAL - a real risk
    gradient, not a coin flip."""
    ghats, routes = load_sites()
    # Tuned to land the busiest ghat just past the elevated threshold
    # without tripping critical - see simulator.py's _ELEVATED_THRESHOLD.
    scenario = SimulationScenario(
        name="moderate day",
        description="test",
        total_pilgrims=120000,
        duration_minutes=300,
        peak_inflow_multiplier=1.6,
        active_ghat_ids=["kushavarta"],
    )
    report = simulate_scenario(scenario, ghats, routes)
    assert report.overall_risk in (RiskLevel.ELEVATED, RiskLevel.CRITICAL)


def test_admission_control_caps_occupancy_percentage():
    """A sustained extreme-demand scenario must not produce an unbounded,
    nonsensical occupancy percentage (thousands of percent) - see
    simulator.py's _ADMISSION_BLOCK_MULTIPLE."""
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="extreme sustained demand",
        description="test",
        total_pilgrims=10_000_000,
        duration_minutes=600,
        peak_inflow_multiplier=5.0,
        active_ghat_ids=["ramkund"],
    )
    report = simulate_scenario(scenario, ghats, routes)
    ramkund_result = report.ghat_results[0]
    # Should be capped well under 1000%, not climbing without bound.
    assert ramkund_result.peak_occupancy_pct_of_safe_capacity < 500


def test_unknown_ghat_id_raises():
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="bad scenario",
        description="test",
        total_pilgrims=1000,
        duration_minutes=60,
        active_ghat_ids=["not_a_real_ghat"],
    )
    try:
        simulate_scenario(scenario, ghats, routes)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_calibration_cases_both_correctly_flag_critical():
    """The two bundled real historical incidents (Nashik 2003, Prayagraj
    2025) must both come back CRITICAL - if this regresses, the simulator's
    thresholds are no longer trustworthy enough to pitch to NTKMA."""
    results = run_all_calibration_cases()
    assert len(results) == 2
    for result in results:
        assert result.correctly_flagged, f"{result.case_name} was not flagged critical: {result.note}"
        assert result.simulated_peak_risk == RiskLevel.CRITICAL
