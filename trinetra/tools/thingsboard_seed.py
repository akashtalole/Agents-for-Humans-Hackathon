"""Pushes reproducible, documented synthetic telemetry onto KumbhDigiTwin's
real ThingsBoard ghat entities - the counterpart to live_signals.py, which
only reads. See agents/scenario_director.py for the one place a model is
involved (deciding the qualitative ScenarioDirective); everything in this
module is pure, seeded, deterministic code.

Why this exists: Kshetra Netra's live tools are only as interesting as the
data behind them, and most of KumbhDigiTwin's demo tenant sits at whatever
value it was last left at - not a live feed. This module drives a plausible,
documented crowd/river curve so there is something changing to monitor,
labeled honestly as generated rather than measured (see SeedingRunSummary
and the CLI's own printed banner).

The known-ghats list below is intentionally NOT Trinetra's own sites.json -
KumbhDigiTwin's tenant has seven provisioned Ghat assets, of which Trinetra
maps only one (ramkund) onto its own site data (see live_signals.py). This
module targets ThingsBoard's entities directly, using ThingsBoard's OWN
safeCapacity/areaSqm attributes as the calibration input for each ghat's
curve, precisely so it can seed all seven rather than only the one Trinetra
otherwise knows about.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from trinetra.models import ScenarioDirective, SeedingRunSummary
from trinetra.tools.thingsboard import (
    ThingsBoardConfig,
    ThingsBoardError,
    find_entity_id,
    get_server_attributes,
    load_config_from_env,
    login,
    post_timeseries,
)

# Verified against github.com/akashtalole/KumbhDigiTwin's
# thingsboard/bulk-import/{demo,core,full}/assets/ghat.csv (all three tiers
# provision the same 7 rows) and re-confirmed against the live
# demo.thingsboard.io tenant (checked 2026-09). Update this list if
# KumbhDigiTwin's provisioning changes; do not discover it at runtime by
# name-searching, for the same reason live_signals.py doesn't - an
# approximate match risks writing to the wrong entity.
KNOWN_GHAT_ASSET_NAMES: tuple[str, ...] = (
    "Ramkund and near by Ghats",
    "Odha Ghat - Proposed",
    "Someshwar Ghat",
    "Lakshminarayan Ghat",
    "Kapila Sangam Ghat",
    "Laksminarayan Ghat D",
    "Takali Sangam Ghat",
)

# Of the above, only these have a provisioned "{name} :: level" WaterLevelGauge
# device on the tenant - verified live the same way. Ramkund does not (see
# TRINETRA.md's honest-limitations: this is a real provisioning gap, not a
# bug in this module).
GHAT_ASSET_NAMES_WITH_RIVER_GAUGE: frozenset[str] = frozenset(
    {"Odha Ghat - Proposed", "Someshwar Ghat", "Lakshminarayan Ghat", "Kapila Sangam Ghat"}
)


@dataclass(frozen=True)
class _GhatCalibration:
    asset_name: str
    asset_id: str
    safe_capacity: float
    area_sqm: float
    warning_level_m: float | None
    danger_level_m: float | None
    river_device_id: str | None


def _load_calibration(config: ThingsBoardConfig, token: str | None, asset_name: str) -> _GhatCalibration | None:
    asset_id = find_entity_id(config, token, "ASSET", asset_name)
    if asset_id is None:
        return None
    attrs = get_server_attributes(config, token, "ASSET", asset_id, keys=["safeCapacity", "areaSqm"])
    safe_capacity = attrs.get("safeCapacity")
    area_sqm = attrs.get("areaSqm")
    if not isinstance(safe_capacity, (int, float)) or not isinstance(area_sqm, (int, float)):
        return None

    river_device_id = None
    warning_level_m = danger_level_m = None
    if asset_name in GHAT_ASSET_NAMES_WITH_RIVER_GAUGE:
        river_device_id = find_entity_id(config, token, "DEVICE", f"{asset_name} :: level")
        if river_device_id is not None:
            river_attrs = get_server_attributes(
                config, token, "DEVICE", river_device_id, keys=["warningLevelM", "dangerLevelM"]
            )
            wl, dl = river_attrs.get("warningLevelM"), river_attrs.get("dangerLevelM")
            warning_level_m = wl if isinstance(wl, (int, float)) else None
            danger_level_m = dl if isinstance(dl, (int, float)) else None

    return _GhatCalibration(
        asset_name=asset_name, asset_id=asset_id, safe_capacity=float(safe_capacity), area_sqm=float(area_sqm),
        warning_level_m=warning_level_m, danger_level_m=danger_level_m, river_device_id=river_device_id,
    )


def _crowd_shape(minute: int, cycle_minutes: int) -> float:
    """0 at minute 0, 1 at minute == cycle_minutes - a monotonic build-up,
    not a rise-then-fall hump. This is a deliberate choice, not an
    oversight: run_seeding_cycle backdates its pushed points so minute ==
    cycle_minutes lands at "now" (see its own docstring), and a shape that
    peaked mid-cycle and receded back toward zero by the final tick would
    make the LATEST value - the one a dashboard widget actually shows -
    read as calm even after a run whose whole point was to simulate a
    building peak. A quarter-sine ramp keeps "now" meaning "the busiest
    point simulated so far." Documented choice, not a measured curve - see
    this module's docstring and TRINETRA.md's Anukaran Netra section."""
    if cycle_minutes <= 0:
        return 0.0
    fraction = max(0.0, min(1.0, minute / cycle_minutes))
    return math.sin(math.pi / 2 * fraction)


def _jitter(asset_name: str, minute: int, spread: float) -> float:
    """Bounded, SEEDED noise - reproducible for the same (asset_name,
    minute), not fresh randomness each call. A fixed per-tick seed is what
    makes a run's output checkable/debuggable rather than a black box; see
    the module docstring's "documented, not measured" framing, same rule
    hydrology.py's egress-rate constant follows."""
    rng = random.Random(f"{asset_name}::{minute}")
    return rng.uniform(-spread, spread)


def compute_pax_count(calibration: _GhatCalibration, directive: ScenarioDirective, minute: int) -> int:
    multiplier = directive.baseline_multiplier
    if calibration.asset_name in directive.surge_asset_names:
        multiplier *= directive.surge_multiplier
    shape = _crowd_shape(minute, directive.cycle_minutes)
    raw = calibration.safe_capacity * multiplier * shape
    raw *= 1.0 + _jitter(calibration.asset_name, minute, spread=0.03)
    return max(0, round(raw))


def compute_river_reading(
    calibration: _GhatCalibration, directive: ScenarioDirective, minute: int
) -> tuple[float, float] | None:
    """Returns (level_m, trend_cm_per_hr), or None if this ghat has no
    river gauge or its threshold attributes aren't set. The base level is
    60% of the gauge's own warningLevelM (an ordinary, unremarkable river
    day); flood_intensity scales how far above that the cycle's peak
    reaches, capped so intensity 1.0 lands almost exactly at dangerLevelM -
    a documented choice, see this module's docstring. Uses the same
    monotonic build-up shape as compute_pax_count (see _crowd_shape's own
    docstring for why it does not rise-then-fall), so trend_cm_per_hr is
    always non-negative here - "now" is always the peak simulated so far,
    never a point already past a peak."""
    if calibration.warning_level_m is None or calibration.danger_level_m is None:
        return None
    base = calibration.warning_level_m * 0.6
    headroom = max(calibration.danger_level_m - base, 0.0)
    shape = _crowd_shape(minute, directive.cycle_minutes)
    level = base + headroom * min(directive.flood_intensity * shape, 1.3)
    trend = 12.0 * directive.flood_intensity * shape
    return round(level, 2), round(trend, 1)


def run_seeding_cycle(
    directive: ScenarioDirective,
    tick_minutes: int = 5,
    config: ThingsBoardConfig | None = None,
) -> SeedingRunSummary:
    """Pushes one telemetry point per known ghat every tick_minutes of
    simulated time across directive.cycle_minutes, with ts_millis backdated
    so the resulting chart reads as a real time series ending now, in a
    single tight loop (no real-time sleeping - see TRINETRA.md for why this
    suits a request/response AgentCore invocation rather than a long-lived
    daemon)."""
    started_at = datetime.now(timezone.utc)
    config = config or load_config_from_env()
    assets_touched: list[str] = []
    river_gauges_touched: list[str] = []
    skipped: list[str] = []
    skipped_river_gauges: list[str] = []
    errors: list[str] = []
    ticks_pushed = 0

    if not config.configured:
        errors.append("ThingsBoard is not configured (THINGSBOARD_USERNAME/PASSWORD or THINGSBOARD_API_KEY unset).")
        return SeedingRunSummary(
            started_at=started_at, finished_at=datetime.now(timezone.utc), directive=directive,
            ticks_pushed=0, assets_touched=[], river_gauges_touched=[], skipped_assets=list(KNOWN_GHAT_ASSET_NAMES),
            skipped_river_gauges=[], errors=errors,
        )

    try:
        token = login(config)
    except ThingsBoardError as exc:
        errors.append(f"could not authenticate to ThingsBoard ({exc})")
        return SeedingRunSummary(
            started_at=started_at, finished_at=datetime.now(timezone.utc), directive=directive,
            ticks_pushed=0, assets_touched=[], river_gauges_touched=[], skipped_assets=list(KNOWN_GHAT_ASSET_NAMES),
            skipped_river_gauges=[], errors=errors,
        )

    minutes = list(range(0, directive.cycle_minutes + 1, max(tick_minutes, 1)))
    now_millis = int(started_at.timestamp() * 1000)
    span_millis = directive.cycle_minutes * 60_000

    for asset_name in KNOWN_GHAT_ASSET_NAMES:
        try:
            calibration = _load_calibration(config, token, asset_name)
        except ThingsBoardError as exc:
            errors.append(f"{asset_name}: could not load calibration ({exc})")
            skipped.append(asset_name)
            continue
        if calibration is None:
            skipped.append(f"{asset_name} (not provisioned or missing safeCapacity/areaSqm)")
            continue

        touched_this_asset = False
        river_gauge_reported_missing = False
        for minute in minutes:
            # Backdated so the LAST tick lands at "now" and the run reads as
            # a real time series ending at the moment of the request, not a
            # future forecast.
            ts_millis = now_millis - span_millis + int(minute / directive.cycle_minutes * span_millis)
            pax = compute_pax_count(calibration, directive, minute)
            try:
                post_timeseries(config, token, "ASSET", calibration.asset_id, {"paxCount": pax}, ts_millis=ts_millis)
                ticks_pushed += 1
                touched_this_asset = True
            except ThingsBoardError as exc:
                errors.append(f"{asset_name} minute {minute}: crowd push failed ({exc})")

            if calibration.river_device_id is not None:
                river = compute_river_reading(calibration, directive, minute)
                if river is not None:
                    level_m, trend = river
                    try:
                        post_timeseries(
                            config, token, "DEVICE", calibration.river_device_id,
                            {"levelM": level_m, "trendCmPerHr": trend}, ts_millis=ts_millis,
                        )
                        ticks_pushed += 1
                        if asset_name not in river_gauges_touched:
                            river_gauges_touched.append(asset_name)
                    except ThingsBoardError as exc:
                        errors.append(f"{asset_name} minute {minute}: river push failed ({exc})")
                elif not river_gauge_reported_missing:
                    # A provisioned device exists (river_device_id is set)
                    # but compute_river_reading declined - its own
                    # warningLevelM/dangerLevelM attributes aren't set on
                    # this tenant. Report this ONCE per ghat, not once per
                    # tick, and never as a silent no-op - see
                    # SeedingRunSummary.skipped_river_gauges's docstring.
                    skipped_river_gauges.append(
                        f"{asset_name} (device exists but warningLevelM/dangerLevelM attributes are not set)"
                    )
                    river_gauge_reported_missing = True

        if touched_this_asset:
            assets_touched.append(asset_name)
        else:
            skipped.append(f"{asset_name} (every push failed)")

    return SeedingRunSummary(
        started_at=started_at, finished_at=datetime.now(timezone.utc), directive=directive,
        ticks_pushed=ticks_pushed, assets_touched=assets_touched, river_gauges_touched=river_gauges_touched,
        skipped_assets=skipped, skipped_river_gauges=skipped_river_gauges, errors=errors,
    )
