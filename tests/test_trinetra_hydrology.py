"""Offline, deterministic tests for trinetra/tools/hydrology.py - no LLM,
no network. See that module's docstring for why the compound-risk numbers
are pure code."""
from __future__ import annotations

import pytest

from trinetra.models import DamRelease, MobilityProfile, RiskLevel, RiverStage
from trinetra.tools.geography import load_sites
from trinetra.tools.hydrology import (
    assess_compound_risk,
    assess_evacuation_feasibility,
    effective_egress_rate,
    flood_lead_time_minutes,
    river_stage_for_discharge,
    verify_documented_observations,
)


def test_river_stage_bands():
    assert river_stage_for_discharge(0) == RiverStage.NORMAL
    assert river_stage_for_discharge(4999) == RiverStage.NORMAL
    assert river_stage_for_discharge(5000) == RiverStage.RISING
    assert river_stage_for_discharge(12000) == RiverStage.WARNING
    assert river_stage_for_discharge(20000) == RiverStage.DANGER
    assert river_stage_for_discharge(35000) == RiverStage.DANGER


def test_documented_observations_reproduce_reported_severity():
    """The two real, cited Gangapur discharge observations must band the way
    they were actually reported - the ~20,000 cusecs release that put the
    Godavari over its danger mark and submerged Ramkund must come back
    DANGER. Same spirit as the crowd simulator's stampede calibration: a
    model that can't reproduce the documented event isn't safe to plan
    with."""
    observations = verify_documented_observations()
    assert len(observations) == 2

    by_discharge = {discharge: stage for discharge, stage, _ in observations}
    # The lower, sustained-release observation should not read as danger...
    assert by_discharge[8160] != RiverStage.DANGER
    # ...and the one that actually flooded Ramkund must.
    assert by_discharge[20000] == RiverStage.DANGER


def test_lead_time_shrinks_as_stage_worsens():
    """A bigger release travels faster, so the time available to clear a
    ghat shrinks exactly when it is needed most."""
    rising = flood_lead_time_minutes(RiverStage.RISING)
    warning = flood_lead_time_minutes(RiverStage.WARNING)
    danger = flood_lead_time_minutes(RiverStage.DANGER)
    assert rising > warning > danger


def test_elderly_crowd_clears_more_slowly_than_able_bodied():
    """The load-bearing insight of this whole module: an evacuation plan
    built on able-bodied egress rates overestimates how fast a Kumbh ghat
    actually clears."""
    ghats, _ = load_sites()
    ramkund = ghats["ramkund"]

    able_bodied = effective_egress_rate(ramkund, {MobilityProfile.STANDARD: 1.0})
    elderly_heavy = effective_egress_rate(
        ramkund,
        {MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.75, MobilityProfile.STANDARD: 0.25},
    )
    assert elderly_heavy < able_bodied


def test_mobility_mix_can_flip_a_plan_from_feasible_to_impossible():
    """The specific failure mode this module exists to catch: the same ghat,
    same occupancy, same lead time - feasible on paper for an able-bodied
    crowd, impossible for a realistic Kumbh one."""
    ghats, _ = load_sites()
    ramkund = ghats["ramkund"]

    naive = assess_evacuation_feasibility(ramkund, 8000, 80, {MobilityProfile.STANDARD: 1.0})
    realistic = assess_evacuation_feasibility(
        ramkund,
        8000,
        80,
        {MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.4, MobilityProfile.STANDARD: 0.6},
    )
    assert naive.margin_minutes > realistic.margin_minutes
    assert realistic.margin_minutes < 0
    assert realistic.risk == RiskLevel.CRITICAL


def test_mobility_mix_shares_are_normalized_not_required_to_sum_to_one():
    ghats, _ = load_sites()
    ramkund = ghats["ramkund"]
    halves = effective_egress_rate(
        ramkund, {MobilityProfile.STANDARD: 0.5, MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.5}
    )
    tens = effective_egress_rate(
        ramkund, {MobilityProfile.STANDARD: 10.0, MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 10.0}
    )
    assert halves == pytest.approx(tens)


def test_empty_mobility_mix_raises_rather_than_dividing_by_zero():
    ghats, _ = load_sites()
    with pytest.raises(ValueError):
        effective_egress_rate(ghats["ramkund"], {MobilityProfile.STANDARD: 0.0})


def test_non_exposed_ghat_is_recorded_as_considered_not_silently_dropped():
    """Kushavarta is at Trimbakeshwar, not on the Gangapur release path. An
    operator must be able to see the tool considered it and ruled it out."""
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=22000),
        ghats,
        {"kushavarta": 5000},
    )
    assert not any(f.ghat_id == "kushavarta" for f in assessment.ghat_feasibility)
    assert any("Kushavarta" in finding for finding in assessment.findings)


def test_quiet_river_with_crowded_ghats_is_routine():
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=1000),
        ghats,
        {"ramkund": 2000},
    )
    assert assessment.river_stage == RiverStage.NORMAL
    assert assessment.overall_risk == RiskLevel.ROUTINE


def test_danger_stage_never_reports_routine_even_if_every_ghat_clears():
    """A near-empty riverfront during a danger-mark release is still an
    active hazard - the tool must not report that as routine."""
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=25000),
        ghats,
        {"ramkund": 50},
    )
    assert assessment.river_stage == RiverStage.DANGER
    assert assessment.overall_risk != RiskLevel.ROUTINE


def test_critical_finding_names_the_shortfall_in_minutes():
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=22000),
        ghats,
        {"ramkund": 8000},
        mobility_mix={MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.4, MobilityProfile.STANDARD: 0.6},
    )
    assert assessment.overall_risk == RiskLevel.CRITICAL
    assert any("CANNOT CLEAR IN TIME" in f for f in assessment.findings)


def test_ghats_are_ordered_worst_first_not_alphabetically():
    """An operator reads this top-down under time pressure. The ghat that
    cannot be cleared must lead, even when its id sorts last - 'ramkund'
    alphabetically follows both of the other exposed ghats, and with these
    occupancies it is the only one in trouble."""
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=22000),
        ghats,
        {"ramkund": 8000, "panchavati_godavari": 5000, "kalaram_marg": 1500},
        mobility_mix={MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.4, MobilityProfile.STANDARD: 0.6},
    )
    ordered_ids = [f.ghat_id for f in assessment.ghat_feasibility]
    assert ordered_ids[0] == "ramkund"
    assert ordered_ids != sorted(ordered_ids)
    margins = [f.margin_minutes for f in assessment.ghat_feasibility]
    assert margins == sorted(margins)


def test_rainfall_absence_is_recorded_honestly_not_defaulted_to_zero():
    """A failed rainfall fetch must never look like 'it was dry' - see
    tools/rainfall.py's docstring."""
    ghats, _ = load_sites()
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=8000),
        ghats,
        {"ramkund": 1000},
        recent_rainfall_mm=None,
        rainfall_note="Live rainfall could not be fetched (ConnectTimeout).",
    )
    assert assessment.recent_rainfall_mm is None
    assert "could not be fetched" in assessment.rainfall_note
