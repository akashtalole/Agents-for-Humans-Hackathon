"""Maps Trinetra's own ghats onto live ThingsBoard telemetry from
github.com/akashtalole/KumbhDigiTwin, and cross-checks the two independent
data sources against each other.

Pure code, no LLM - same rule as everywhere else in tools/: a live reading
either comes back as a real number with its provenance, or the caller gets
an honest "could not be fetched" / "no ThingsBoard counterpart" message. Never
a fabricated number standing in for a missing one.

The mapping problem, stated plainly: Trinetra's sites.json and
KumbhDigiTwin's provisioned Ghat assets were built independently, from
different source data, and do not share entity names or ids. Only one of
Trinetra's four ghats currently has an unambiguous ThingsBoard counterpart -
see GHAT_ID_TO_THINGSBOARD_ASSET below. This module is honest about that
rather than guessing a fuzzy name match, which would risk silently reading
the wrong asset's telemetry into a crush-risk decision.
"""
from __future__ import annotations

from datetime import datetime, timezone

from trinetra.models import (
    Ghat,
    GhatLiveReading,
    LiveSignalCrossCheck,
    MonitoringBrief,
    RiverGaugeReading,
    RiverStage,
)
from trinetra.tools.thingsboard import (
    ThingsBoardConfig,
    ThingsBoardError,
    find_entity_id,
    get_latest_telemetry,
    get_server_attributes,
    load_config_from_env,
    login,
    post_server_attributes,
)

# Verified against github.com/akashtalole/KumbhDigiTwin's
# thingsboard/bulk-import/demo/assets/ghat.csv (checked 2026-09; the demo,
# core and full tiers all provision the same 8 ghat rows). KumbhDigiTwin
# aggregates the whole Ramkund riverfront - including the Kalaram Mandir
# Marg approach lane - into one asset, "Ramkund and near by Ghats"; it does
# not carry a separate entity for the 1.8m lane itself, which is the one
# structural hazard Trinetra's own calibration is built around (see
# TRINETRA.md's calibration section). Kushavarta (Trimbakeshwar) and
# Panchavati Godavari have no counterpart at all - KumbhDigiTwin's own
# README names Trimbakeshwar coverage as its largest open blocker (source
# data is 99.5% Nashik-side).
#
# Update this mapping if KumbhDigiTwin's provisioning changes; do not guess
# a name match at runtime.
GHAT_ID_TO_THINGSBOARD_ASSET: dict[str, str] = {
    "ramkund": "Ramkund and near by Ghats",
}

_LOS_RISK_BY_GRADE = {
    "A": "routine",
    "B": "routine",
    "C": "elevated",
    "D": "elevated",
    "E": "critical",
    "F": "critical",
}


class LiveSignalUnavailable(Exception):
    """Raised with an honest, specific reason - no ThingsBoard mapping,
    no credentials configured, or a real fetch failure. Callers (the
    monitoring agent's tools) catch this and report the gap rather than
    letting an exception surface as a generic tool error."""


def _connect(config: ThingsBoardConfig | None) -> tuple[ThingsBoardConfig, str | None]:
    config = config or load_config_from_env()
    if not config.configured:
        raise LiveSignalUnavailable(
            "ThingsBoard is not configured (set THINGSBOARD_USERNAME/PASSWORD or "
            "THINGSBOARD_API_KEY) - no live signal is available."
        )
    try:
        token = login(config)
    except ThingsBoardError as exc:
        raise LiveSignalUnavailable(f"could not authenticate to ThingsBoard ({exc})") from None
    return config, token


def fetch_ghat_live_reading(
    ghat_id: str, config: ThingsBoardConfig | None = None
) -> GhatLiveReading:
    """Raises LiveSignalUnavailable (never returns a fabricated reading) if
    this ghat has no ThingsBoard counterpart, or the fetch itself fails."""
    asset_name = GHAT_ID_TO_THINGSBOARD_ASSET.get(ghat_id)
    if asset_name is None:
        raise LiveSignalUnavailable(
            f"'{ghat_id}' has no known ThingsBoard asset in the current KumbhDigiTwin "
            "provisioning - see GHAT_ID_TO_THINGSBOARD_ASSET's docstring."
        )
    config, token = _connect(config)
    try:
        asset_id = find_entity_id(config, token, "ASSET", asset_name)
        if asset_id is None:
            raise LiveSignalUnavailable(
                f"ThingsBoard asset '{asset_name}' was not found on this tenant - it may not be "
                "provisioned yet, or the tenant/credentials point at a different instance."
            )
        telemetry = get_latest_telemetry(
            config, token, "ASSET", asset_id,
            keys=["paxCount", "densityPaxPerSqm", "occupancyPct", "losGrade"],
        )
        attributes = get_server_attributes(
            config, token, "ASSET", asset_id, keys=["safeCapacity", "areaSqm"]
        )
    except ThingsBoardError as exc:
        raise LiveSignalUnavailable(f"live fetch for '{asset_name}' failed ({exc})") from None

    def _num(key: str) -> float | None:
        value = telemetry.get(key)
        return value[0] if value and isinstance(value[0], (int, float)) else None

    def _str(key: str) -> str | None:
        value = telemetry.get(key)
        return str(value[0]) if value else None

    return GhatLiveReading(
        ghat_id=ghat_id,
        thingsboard_asset_name=asset_name,
        fetched_at=datetime.now(timezone.utc),
        pax_count=int(_num("paxCount")) if _num("paxCount") is not None else None,
        density_pax_per_sqm=_num("densityPaxPerSqm"),
        occupancy_pct=_num("occupancyPct"),
        los_grade=_str("losGrade"),
        reported_safe_capacity=int(attributes["safeCapacity"]) if "safeCapacity" in attributes else None,
        reported_area_sqm=attributes.get("areaSqm") if isinstance(attributes.get("areaSqm"), float) else None,
    )


def fetch_river_gauge_reading(
    ghat_id: str, config: ThingsBoardConfig | None = None
) -> RiverGaugeReading:
    asset_name = GHAT_ID_TO_THINGSBOARD_ASSET.get(ghat_id)
    if asset_name is None:
        raise LiveSignalUnavailable(
            f"'{ghat_id}' has no known ThingsBoard asset, so its water-level gauge cannot be "
            "located either - see GHAT_ID_TO_THINGSBOARD_ASSET's docstring."
        )
    device_name = f"{asset_name} :: level"
    config, token = _connect(config)
    try:
        device_id = find_entity_id(config, token, "DEVICE", device_name)
        if device_id is None:
            raise LiveSignalUnavailable(f"ThingsBoard device '{device_name}' was not found on this tenant.")
        telemetry = get_latest_telemetry(config, token, "DEVICE", device_id, keys=["levelM", "trendCmPerHr"])
        attributes = get_server_attributes(
            config, token, "DEVICE", device_id, keys=["warningLevelM", "dangerLevelM"]
        )
    except ThingsBoardError as exc:
        raise LiveSignalUnavailable(f"live fetch for '{device_name}' failed ({exc})") from None

    level = telemetry.get("levelM", (None, None))[0]
    trend = telemetry.get("trendCmPerHr", (None, None))[0]
    warning_level = attributes.get("warningLevelM")
    danger_level = attributes.get("dangerLevelM")
    level = level if isinstance(level, (int, float)) else None
    trend = trend if isinstance(trend, (int, float)) else None
    warning_level = warning_level if isinstance(warning_level, (int, float)) else None
    danger_level = danger_level if isinstance(danger_level, (int, float)) else None

    stage = None
    if level is not None and danger_level is not None:
        if level >= danger_level:
            stage = RiverStage.DANGER
        elif warning_level is not None and level >= warning_level:
            stage = RiverStage.WARNING
        elif trend is not None and trend > 15.0:
            # Matches KumbhDigiTwin's own RiverLevelRising alarm threshold
            # (device-profiles/waterlevelgauge.json): a fast-rising level is
            # a leading indicator even below the warning mark.
            stage = RiverStage.RISING
        else:
            stage = RiverStage.NORMAL

    return RiverGaugeReading(
        ghat_id=ghat_id,
        thingsboard_device_name=device_name,
        fetched_at=datetime.now(timezone.utc),
        level_m=level,
        trend_cm_per_hr=trend,
        warning_level_m=warning_level,
        danger_level_m=danger_level,
        derived_stage=stage,
    )


def cross_check_ghat_capacity(ghat: Ghat, live_reading: GhatLiveReading) -> LiveSignalCrossCheck:
    """Compares sites.json's safe_capacity against ThingsBoard's reported
    safeCapacity for the same physical ghat. Both are estimates from
    independent, honestly-labeled sources (see sites.json's and
    KumbhDigiTwin's own citation notes) - this reports disagreement, it does
    not resolve it."""
    reported = live_reading.reported_safe_capacity
    ratio = (reported / ghat.safe_capacity) if reported and ghat.safe_capacity else None
    agrees = (0.8 <= ratio <= 1.2) if ratio is not None else None
    return LiveSignalCrossCheck(
        ghat_id=ghat.id,
        trinetra_safe_capacity=ghat.safe_capacity,
        thingsboard_safe_capacity=reported,
        capacity_ratio=round(ratio, 2) if ratio is not None else None,
        agrees_within_20pct=agrees,
    )


def los_grade_to_risk_label(los_grade: str | None) -> str | None:
    """Maps a Fruin LOS grade to the same routine/elevated/critical
    vocabulary Trinetra's own RiskLevel uses.

    The grade itself is KumbhDigiTwin's, computed by density thresholds
    that are not this repo's invention (calculated-fields.json's "Ghat LOS
    grade" field: A<1 pax/sqm, B<2, C<3, D<4, E<5, F>=5 - the published
    Fruin pedestrian LOS scale). The three-bucket collapse into
    routine/elevated/critical below (A-B routine, C-D elevated, E-F
    critical) IS this repo's own judgment call, made explicit here rather
    than left implicit, so it can be argued with. Returns None for an
    unrecognized/missing grade rather than guessing."""
    if los_grade is None:
        return None
    return _LOS_RISK_BY_GRADE.get(los_grade.strip().upper())


# --------------------------------------------------------------------------
# Inbound: ThingsBoard alarm -> Trinetra ghat_id, and writing a result back.
#
# Everything above this point is Trinetra PULLING a reading on demand (a
# tool call, a CLI run). This direction is ThingsBoard PUSHING when one of
# its own alarm rules fires - see api.py's /api/webhooks/thingsboard-alarm
# and TRINETRA.md's Kshetra Netra section for the rule-chain configuration
# this expects on the ThingsBoard side.
# --------------------------------------------------------------------------

_THINGSBOARD_ASSET_TO_GHAT_ID: dict[str, str] = {v: k for k, v in GHAT_ID_TO_THINGSBOARD_ASSET.items()}


def ghat_id_from_thingsboard_asset_name(asset_name: str) -> str | None:
    """The reverse of GHAT_ID_TO_THINGSBOARD_ASSET. Returns None for an
    entity name Trinetra has no ghat for - KumbhDigiTwin's alarms fire on
    many entity types (SanitationBlock, ParkingZone, UtilityPlant, ...)
    Trinetra has no opinion about, and that is an expected, silent no-op
    here, not an error - see api.py's webhook handler."""
    return _THINGSBOARD_ASSET_TO_GHAT_ID.get(asset_name)


def write_back_monitoring_result(
    ghat_id: str, brief: MonitoringBrief, config: ThingsBoardConfig | None = None
) -> None:
    """Posts Kshetra Netra's assessment back onto the ThingsBoard asset that
    triggered it, as SERVER_SCOPE attributes - so an operator's ThingsBoard
    dashboard can show a result without leaving ThingsBoard.

    Best-effort and silent on failure BY DESIGN: this runs after the
    MonitoringBrief already exists and (in the webhook path) after the
    caller has already been told the request was accepted. A write-back
    failure - including not being able to log in at all - must never look
    like the monitoring itself failed, and must never raise into a
    background task with no one watching for the exception. Never raises.
    Callers that want to know about a postponed failure should wrap this
    call themselves (see api.py's _run_alarm_triggered_monitoring, which
    logs but does not re-raise).
    """
    asset_name = GHAT_ID_TO_THINGSBOARD_ASSET.get(ghat_id)
    if asset_name is None:
        return
    try:
        config, token = _connect(config)
        asset_id = find_entity_id(config, token, "ASSET", asset_name)
        if asset_id is None:
            return
        post_server_attributes(
            config, token, "ASSET", asset_id,
            {
                "kshetraNetraStatus": brief.overall_status.value,
                "kshetraNetraSummary": brief.summary,
                "kshetraNetraRecommendedAction": brief.recommended_action,
                "kshetraNetraCheckedAt": brief.generated_at.isoformat(),
            },
        )
    except (ThingsBoardError, LiveSignalUnavailable):
        return
