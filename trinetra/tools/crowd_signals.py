"""Synthetic crowd-signal generation for demo/CLI use.

Honest limitation, stated plainly: Trinetra has no live integration with
NTKMA's actual CCTV/footfall-counter infrastructure - no such public API
exists for this repo to call. This module derives CrowdSignal objects
either from a finished SimulationReport (for demoing Prashasan Command
against a scenario) or from a manually-specified occupancy level (for
demoing it against an arbitrary "what if" reading). A real deployment
replaces this module's callers with NTKMA's actual sensor feed - the
CrowdSignal/CommandBrief contract downstream of it does not need to change.
"""
from __future__ import annotations

from datetime import datetime

from trinetra.models import CrowdSignal, Ghat, SimulationReport


def signals_from_simulation(report: SimulationReport, ghats: dict[str, Ghat]) -> list[CrowdSignal]:
    """One CrowdSignal per simulated ghat, using its peak occupancy - i.e.
    "what Prashasan Command would have seen at the worst moment of this
    scenario"."""
    signals = []
    for result in report.ghat_results:
        ghat = ghats.get(result.ghat_id)
        if ghat is None:
            continue
        # A crude but honestly-labeled inflow/outflow split derived from the
        # peak occupancy: at peak, inflow and outflow are assumed roughly
        # balanced (that's what "peak" means in the simulator's tick loop),
        # so both are approximated from the ghat's access-point throughput.
        approx_flow = ghat.access_points * 35
        signals.append(
            CrowdSignal(
                ghat_id=result.ghat_id,
                timestamp=datetime.utcnow(),
                estimated_occupancy=result.peak_occupancy,
                inflow_rate_per_min=approx_flow,
                outflow_rate_per_min=approx_flow,
            )
        )
    return signals


def manual_signal(ghat: Ghat, estimated_occupancy: int, inflow_rate_per_min: int, outflow_rate_per_min: int) -> CrowdSignal:
    return CrowdSignal(
        ghat_id=ghat.id,
        timestamp=datetime.utcnow(),
        estimated_occupancy=estimated_occupancy,
        inflow_rate_per_min=inflow_rate_per_min,
        outflow_rate_per_min=outflow_rate_per_min,
    )
