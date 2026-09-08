"""Godavari compound flood risk - pure deterministic code, no LLM.

The question this module answers is narrower and sharper than "will the
river rise": **can this ghat be cleared before the water reaches it, given
who is actually standing on it?**

That framing matters because the two halves of this hazard are individually
well understood and jointly ignored. Nashik's irrigation department knows
what a Gangapur Dam release does to the Godavari - Ramkund and Goda Ghat
have really gone underwater, temples submerged, Ramkund closed for two days
(see trinetra/data/godavari_hydrology.json's citations). NTKMA knows how
many people are on a ghat during a Shahi Snan. Nobody appears to be
multiplying the two together, and the product is the number that decides
whether a release is an inconvenience or a mass-casualty event.

The mobility term is the part a naive plan gets wrong. Kumbh crowds skew
heavily elderly. A ghat holding 8,000 mostly-elderly pilgrims does not
clear at the same rate as one holding 8,000 able-bodied adults, and an
evacuation plan built on the latter's arithmetic fails in the water.

Same architectural split as tools/simulator.py: every number below is
computed here, deterministically, so it is identical on every run.
agents/hydrology_advisor.py only interprets the finished assessment.
"""
from __future__ import annotations

import json
from pathlib import Path

from trinetra.models import (
    CompoundRiskAssessment,
    DamRelease,
    EvacuationFeasibility,
    Ghat,
    MobilityProfile,
    RiskLevel,
    RiverStage,
)

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "godavari_hydrology.json"

# A ghat must clear this many minutes BEFORE the water is estimated to
# arrive to count as feasible. Clearing with two minutes to spare is not a
# plan, it is a coincidence - real evacuations start late, communication
# lags, and the lead-time estimate itself is uncertain.
_REQUIRED_SAFETY_MARGIN_MINUTES = 30

_STAGE_ORDER = {
    RiverStage.NORMAL: 0,
    RiverStage.RISING: 1,
    RiverStage.WARNING: 2,
    RiverStage.DANGER: 3,
}

_RISK_ORDER = {RiskLevel.ROUTINE: 0, RiskLevel.ELEVATED: 1, RiskLevel.CRITICAL: 2}


def load_hydrology() -> dict:
    return json.loads(_DATA_PATH.read_text())


def verify_documented_observations(hydrology: dict | None = None) -> list[tuple[int, RiverStage, str]]:
    """Replays each real, cited discharge observation in the data file
    through this module's own banding, so the thresholds can be checked
    against what was actually reported rather than only against
    themselves.

    Same spirit as tools/calibration.py replaying the 2003/2025 stampedes
    through the crowd simulator: a model that can't reproduce the documented
    event isn't trustworthy enough to plan with. Returns (discharge, stage,
    observed_effect) per documented observation."""
    hydrology = hydrology or load_hydrology()
    return [
        (
            int(obs["discharge_cusecs"]),
            river_stage_for_discharge(int(obs["discharge_cusecs"]), hydrology),
            obs["observed_effect"],
        )
        for obs in hydrology["documented_discharge_observations"]
    ]


def river_stage_for_discharge(discharge_cusecs: int, hydrology: dict | None = None) -> RiverStage:
    """Which stage band a given Gangapur Dam discharge falls into. The
    'danger' boundary is anchored to real reporting (above roughly 20,000
    cusecs the Godavari crossed its danger mark at Nashik and Ramkund
    flooded); the intermediate boundaries are interpolated planning
    estimates - see the data file's own note."""
    hydrology = hydrology or load_hydrology()
    thresholds = hydrology["stage_thresholds_cusecs"]
    if discharge_cusecs >= thresholds["danger"]:
        return RiverStage.DANGER
    if discharge_cusecs >= thresholds["warning"]:
        return RiverStage.WARNING
    if discharge_cusecs >= thresholds["rising"]:
        return RiverStage.RISING
    return RiverStage.NORMAL


def flood_lead_time_minutes(stage: RiverStage, hydrology: dict | None = None) -> int:
    """Estimated minutes between a release at Gangapur Dam and the resulting
    rise reaching the Panchavati/Ramkund riverfront. ILLUSTRATIVE PLANNING
    ESTIMATE - see the data file. A larger release travels faster, so the
    lead time shrinks exactly when it is needed most."""
    hydrology = hydrology or load_hydrology()
    lead_times = hydrology["flood_lead_time_minutes"]
    if stage == RiverStage.NORMAL:
        # No release-driven rise to outrun; use the most generous documented
        # window so downstream arithmetic still has a number to work with.
        return int(lead_times["rising"])
    return int(lead_times[stage.value])


def effective_egress_rate(
    ghat: Ghat, mobility_mix: dict[MobilityProfile, float], hydrology: dict | None = None
) -> float:
    """People per minute this ghat can actually discharge during a staged
    evacuation, after weighting by who is standing on it.

    mobility_mix maps each profile to its share of the crowd (shares are
    normalized, so callers don't have to make them sum to exactly 1.0)."""
    hydrology = hydrology or load_hydrology()
    base_per_point = hydrology["egress_rate_per_access_point_per_min"]["value"]
    factors = hydrology["mobility_slowdown_factors"]

    total_share = sum(mobility_mix.values())
    if total_share <= 0:
        raise ValueError("mobility_mix shares must sum to a positive number")

    # A weighted harmonic-style slowdown: the crowd moves at the blended
    # rate of its parts, so a large slow minority drags the whole ghat's
    # clearance rate down rather than being averaged away.
    weighted_factor = sum(
        (share / total_share) * factors[profile.value] for profile, share in mobility_mix.items()
    )
    return ghat.access_points * base_per_point * weighted_factor


def assess_evacuation_feasibility(
    ghat: Ghat,
    occupancy: int,
    lead_time_minutes: int,
    mobility_mix: dict[MobilityProfile, float] | None = None,
    hydrology: dict | None = None,
) -> EvacuationFeasibility:
    """Can this ghat be cleared before the water arrives, with margin?"""
    hydrology = hydrology or load_hydrology()
    mobility_mix = mobility_mix or {MobilityProfile.STANDARD: 1.0}

    egress = effective_egress_rate(ghat, mobility_mix, hydrology)
    clearance = occupancy / egress if egress > 0 else float("inf")
    margin = lead_time_minutes - clearance

    if margin < 0:
        risk = RiskLevel.CRITICAL
    elif margin < _REQUIRED_SAFETY_MARGIN_MINUTES:
        risk = RiskLevel.ELEVATED
    else:
        risk = RiskLevel.ROUTINE

    return EvacuationFeasibility(
        ghat_id=ghat.id,
        ghat_name=ghat.name,
        occupancy=occupancy,
        effective_egress_per_min=round(egress, 1),
        clearance_minutes=round(clearance, 1),
        lead_time_minutes=lead_time_minutes,
        margin_minutes=round(margin, 1),
        feasible=margin >= _REQUIRED_SAFETY_MARGIN_MINUTES,
        risk=risk,
    )


def assess_compound_risk(
    release: DamRelease,
    ghats: dict[str, Ghat],
    occupancy_by_ghat: dict[str, int],
    mobility_mix: dict[MobilityProfile, float] | None = None,
    recent_rainfall_mm: float | None = None,
    rainfall_note: str = "",
    hydrology: dict | None = None,
) -> CompoundRiskAssessment:
    """The whole judgment: river stage from the discharge, lead time from
    the stage, then per-ghat evacuation feasibility for every flood-exposed
    ghat that currently has people on it."""
    hydrology = hydrology or load_hydrology()

    stage = river_stage_for_discharge(release.discharge_cusecs, hydrology)
    lead_time = flood_lead_time_minutes(stage, hydrology)
    exposed_ids = set(hydrology["flood_exposed_ghats"]["exposed"])

    feasibility: list[EvacuationFeasibility] = []
    findings: list[str] = []

    for ghat_id, occupancy in sorted(occupancy_by_ghat.items()):
        ghat = ghats.get(ghat_id)
        if ghat is None:
            continue
        if ghat_id not in exposed_ids:
            # Explicitly recorded rather than silently dropped, so an
            # operator can see the tool considered this ghat and ruled it
            # out rather than forgetting about it.
            findings.append(
                f"{ghat.name} is not on the Gangapur release path and is not treated as flood-exposed "
                "(see godavari_hydrology.json's flood_exposed_ghats note)."
            )
            continue

        result = assess_evacuation_feasibility(ghat, occupancy, lead_time, mobility_mix, hydrology)
        feasibility.append(result)

        if result.risk == RiskLevel.CRITICAL:
            findings.append(
                f"CANNOT CLEAR IN TIME: {ghat.name} holds {occupancy:,} people and needs "
                f"{result.clearance_minutes:.0f} minutes to clear at {result.effective_egress_per_min:.0f} "
                f"people/min, but the rise is estimated to arrive in {lead_time} minutes "
                f"({abs(result.margin_minutes):.0f} minutes short)."
            )
        elif result.risk == RiskLevel.ELEVATED:
            findings.append(
                f"THIN MARGIN: {ghat.name} clears in {result.clearance_minutes:.0f} minutes against a "
                f"{lead_time}-minute lead time - only {result.margin_minutes:.0f} minutes of margin, below the "
                f"{_REQUIRED_SAFETY_MARGIN_MINUTES}-minute threshold this tool treats as the minimum for a plan."
            )

    if stage == RiverStage.NORMAL and not feasibility:
        overall = RiskLevel.ROUTINE
    elif feasibility:
        overall = max((f.risk for f in feasibility), key=lambda r: _RISK_ORDER[r])
        # A danger-stage release is never reported as merely routine even if
        # every exposed ghat happens to be empty enough to clear - the river
        # itself is over its danger mark and that is an operational fact.
        if stage == RiverStage.DANGER and overall == RiskLevel.ROUTINE:
            overall = RiskLevel.ELEVATED
            findings.append(
                "Every exposed ghat can currently be cleared in time, but the discharge is above the "
                "documented danger-mark threshold - treat the riverfront as an active hazard regardless."
            )
    else:
        overall = RiskLevel.ROUTINE if stage in (RiverStage.NORMAL, RiverStage.RISING) else RiskLevel.ELEVATED

    # Worst first. An operator reading this under time pressure scans from
    # the top, so the ghat that cannot be cleared must not sit below two that
    # can just because its name sorts later in the alphabet.
    feasibility.sort(key=lambda f: f.margin_minutes)

    return CompoundRiskAssessment(
        discharge_cusecs=release.discharge_cusecs,
        river_stage=stage,
        lead_time_minutes=lead_time,
        recent_rainfall_mm=recent_rainfall_mm,
        rainfall_note=rainfall_note,
        ghat_feasibility=feasibility,
        overall_risk=overall,
        findings=findings,
    )
