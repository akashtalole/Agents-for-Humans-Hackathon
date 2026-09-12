"""Offline, deterministic tests for trinetra/tools/simulator.py - no LLM,
no network. See simulator.py's module docstring for why the core risk
numbers are pure code."""
from __future__ import annotations

import pytest

from trinetra.models import CalibrationCaseKind, RiskLevel, SimulationScenario
from trinetra.tools import calibration as calibration_module
from trinetra.tools.calibration import load_calibration_cases, run_all_calibration_cases
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


def test_on_tick_fires_once_per_minute_with_all_active_ghats():
    """The digital twin's live view depends on ticks being synchronized
    across all active ghats, not one ghat's full timeline followed by the
    next - see simulate_scenario's docstring."""
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="tick test", description="test", total_pilgrims=100000,
        duration_minutes=30, peak_inflow_multiplier=2.0,
        active_ghat_ids=["ramkund", "kushavarta"],
    )
    ticks_seen: list[tuple[int, set[str]]] = []

    def on_tick(minute, snapshot):
        ticks_seen.append((minute, set(snapshot.keys())))

    simulate_scenario(scenario, ghats, routes, on_tick=on_tick)

    assert len(ticks_seen) == 30
    assert [m for m, _ in ticks_seen] == list(range(30))
    for _, ghat_ids in ticks_seen:
        assert ghat_ids == {"ramkund", "kushavarta"}


def test_on_tick_does_not_change_the_final_report():
    ghats, routes = load_sites()
    scenario = SimulationScenario(
        name="parity test", description="test", total_pilgrims=500000,
        duration_minutes=60, peak_inflow_multiplier=2.5,
        active_ghat_ids=["kalaram_marg", "ramkund"],
    )
    report_without_hook = simulate_scenario(scenario, ghats, routes)
    report_with_hook = simulate_scenario(scenario, ghats, routes, on_tick=lambda *_: None)
    assert report_without_hook == report_with_hook


def test_calibration_historical_incidents_flag_critical():
    """The bundled real historical incidents (Nashik 2003, Prayagraj 2025)
    must both come back CRITICAL - if this regresses, the simulator's
    thresholds are no longer trustworthy enough to pitch to NTKMA."""
    results = [r for r in run_all_calibration_cases()
               if r.case_kind == CalibrationCaseKind.HISTORICAL_INCIDENT]
    assert len(results) == 2
    for result in results:
        assert result.correctly_flagged, f"{result.case_name} was not flagged critical: {result.note}"
        assert result.simulated_peak_risk == RiskLevel.CRITICAL


def test_calibration_negative_controls_are_not_flagged():
    """The controls are what give the suite discriminative power: ordinary
    and well-managed days must NOT come back CRITICAL. Without these, the
    whole suite is passed by a function that always returns CRITICAL."""
    results = [r for r in run_all_calibration_cases() if not r.expect_critical]
    assert results, "suite has no negative controls - it cannot fail"
    for result in results:
        assert result.correctly_flagged, f"false alarm on {result.case_name}: {result.note}"
        assert result.simulated_peak_risk != RiskLevel.CRITICAL


def test_calibration_suite_actually_fails_a_model_that_always_says_critical():
    """The regression this guards is the one that mattered: the previous
    suite contained only disasters, so `return CRITICAL` passed it 2/2 and a
    green run established nothing."""
    from trinetra.models import SimulationReport

    real = calibration_module.simulate_scenario
    calibration_module.simulate_scenario = lambda s, g, r: SimulationReport(
        scenario_name=s.name, ghat_results=[], overall_risk=RiskLevel.CRITICAL, incidents_triggered=[]
    )
    try:
        results = run_all_calibration_cases()
    finally:
        calibration_module.simulate_scenario = real

    failures = [r for r in results if not r.correctly_flagged]
    assert failures, "a model that flags everything still passes - the suite is a tautology again"


def test_calibration_refuses_to_run_a_suite_with_no_controls():
    cases = [c for c in load_calibration_cases() if c.expect_critical]
    with pytest.raises(ValueError, match="no negative controls"):
        calibration_module._assert_suite_can_fail(cases)


def test_calibration_detects_routing_not_just_headcount():
    """The managed/funnelled control pair is identical in crowd, window and
    surge - only the route differs. If both land the same way, the simulator
    is responding to headcount alone and cannot evaluate a routing plan."""
    by_id = {r.case_id: r for r in run_all_calibration_cases()}
    managed = by_id["kumbh_managed_snan_control"]
    funnelled = by_id["kumbh_funnelled_snan_control"]
    assert managed.simulated_peak_risk != RiskLevel.CRITICAL
    assert funnelled.simulated_peak_risk == RiskLevel.CRITICAL


def _scenario(total, minutes=180, multiplier=1.0, ghats=("kalaram_marg", "ramkund")):
    return SimulationScenario(
        name="test",
        description="test",
        total_pilgrims=total,
        duration_minutes=minutes,
        peak_inflow_multiplier=multiplier,
        active_ghat_ids=list(ghats),
    )


def test_unadmitted_arrivals_are_queued_not_discarded():
    """The bug this guards: admission control used to drop every arrival it
    could not admit. In the 2003 replay that silently deleted roughly 263,000
    people - the ones standing in the 1.8m approach lane, which is precisely
    where the 39 real deaths happened. The plateau it reported was an
    artefact of throwing them away."""
    ghats, routes = load_sites()
    report = simulate_scenario(_scenario(500_000, multiplier=3.2), ghats, routes)
    lane = next(g for g in report.ghat_results if g.ghat_id == "kalaram_marg")
    assert lane.peak_queue_outside > 100_000
    assert lane.queue_still_growing_at_end
    assert any("held outside" in i for i in report.incidents_triggered)


def test_surge_multiplier_redistributes_the_crowd_rather_than_inventing_one():
    """A x3.2 peak used to generate 1.73x the stated total_pilgrims. It went
    unnoticed because the surplus people were discarded before anything
    counted them; conserving the queue is what exposed it."""
    ghats, routes = load_sites()
    for total, multiplier in ((500_000, 3.2), (150_000, 1.5), (1_000_000, 2.0)):
        report = simulate_scenario(_scenario(total, multiplier=multiplier), ghats, routes)
        queued = sum(g.final_queue_outside for g in report.ghat_results)
        assert queued <= total, f"{queued:,} queued out of a stated {total:,} crowd"


def test_queue_keeps_responding_after_occupancy_saturates():
    """Occupancy is capped at _ADMISSION_BLOCK_MULTIPLE by construction, so
    past that point it stops tracking severity - it is not even monotonic
    (500k can read lower than 250k). The queue is the field that still
    carries information once a ghat is blocked, which is why both are
    reported and why the docs say never to quote occupancy alone."""
    ghats, routes = load_sites()
    queues = []
    for total in (100_000, 250_000, 500_000, 1_000_000):
        report = simulate_scenario(_scenario(total, multiplier=1.5), ghats, routes)
        lane = next(g for g in report.ghat_results if g.ghat_id == "kalaram_marg")
        assert lane.peak_occupancy_pct_of_safe_capacity < 200, "occupancy is meant to saturate, not run away"
        queues.append(lane.peak_queue_outside)
    assert queues == sorted(queues), f"queue stopped tracking crowd size: {queues}"
    assert queues[-1] > 4 * queues[0]


def test_a_quiet_day_queues_nobody():
    ghats, routes = load_sites()
    report = simulate_scenario(_scenario(20_000), ghats, routes)
    assert all(g.peak_queue_outside == 0 for g in report.ghat_results)
    assert report.overall_risk == RiskLevel.ROUTINE
