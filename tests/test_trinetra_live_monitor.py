"""Offline tests for Kshetra Netra's tool functions (agents/live_monitor.py).

These call the tools' underlying Python functions directly rather than
running the agent's model loop - the same "test the deterministic core
without an API key" split used everywhere else in this repo. What this
agent contributes over the others (deciding which of several tools to
call) is exactly the part that needs a real model and is out of scope for
an offline suite; see TRINETRA.md's honest-limitations section.
"""
from __future__ import annotations

import json

from trinetra.agents.live_monitor import build_live_monitor


def _tool_fn(agent, name):
    t = agent.tool_registry.registry[name]
    return getattr(t, "_tool_func", None) or getattr(t, "original_function")


def test_agent_registers_all_four_tools():
    agent = build_live_monitor()
    names = set(agent.tool_registry.registry.keys())
    assert names == {
        "get_live_ghat_crowd_signal",
        "get_live_river_gauge",
        "run_quick_lookahead_simulation",
        "check_simulator_is_calibrated",
    }


def test_get_live_ghat_crowd_signal_reports_unavailable_for_unmapped_ghat():
    agent = build_live_monitor()
    fn = _tool_fn(agent, "get_live_ghat_crowd_signal")
    result = json.loads(fn(ghat_id="kalaram_marg"))
    assert result["available"] is False
    assert "no known ThingsBoard asset" in result["reason"]


def test_get_live_river_gauge_reports_unavailable_for_unmapped_ghat():
    agent = build_live_monitor()
    fn = _tool_fn(agent, "get_live_river_gauge")
    result = json.loads(fn(ghat_id="kushavarta"))
    assert result["available"] is False


def test_check_simulator_is_calibrated_runs_the_real_suite():
    """No mocking needed - same as run_calibration elsewhere, this is pure
    deterministic code."""
    agent = build_live_monitor()
    fn = _tool_fn(agent, "check_simulator_is_calibrated")
    result = json.loads(fn())
    assert result["all_correct"] is True
    assert len(result["cases"]) >= 5  # 2 historical + 3 negative controls


def test_lookahead_simulation_uses_the_real_simulator():
    agent = build_live_monitor()
    fn = _tool_fn(agent, "run_quick_lookahead_simulation")
    # kalaram_marg's outflow cap is 2 access points x 35/min = 70/min (see
    # simulator.py's _outflow_capacity); a sustained rate above that must
    # eventually queue and flip critical, same math as the calibration/queue
    # tests elsewhere in this repo.
    result = json.loads(
        fn(ghat_id="kalaram_marg", sustained_inflow_per_min=100, duration_minutes=60, peak_inflow_multiplier=1.5)
    )
    assert result["available"] is True
    assert result["overall_risk"] == "critical"
    assert result["peak_queue_outside"] > 0

    # A rate comfortably under the outflow cap must stay routine - the tool
    # is not simply "always alarm" (mirrors calibration's negative controls).
    calm = json.loads(
        fn(ghat_id="kalaram_marg", sustained_inflow_per_min=60, duration_minutes=60, peak_inflow_multiplier=1.5)
    )
    assert calm["overall_risk"] == "routine"


def test_lookahead_simulation_unknown_ghat():
    agent = build_live_monitor()
    fn = _tool_fn(agent, "run_quick_lookahead_simulation")
    result = json.loads(fn(ghat_id="not_a_real_ghat", sustained_inflow_per_min=10))
    assert result["available"] is False
