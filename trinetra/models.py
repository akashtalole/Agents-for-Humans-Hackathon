"""Structured data contracts for Trinetra.

Same discipline as bidwright/models.py, claimclarity/models.py, and
glacierwatch/models.py: every agent hand-off is a validated Pydantic model,
never free text one agent passes to the next and hopes is right. The
deterministic renderers in rendering.py turn these into the Markdown a
human (pilgrim, NTKMA/NMC operator, or judge) actually reads.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Ordered the same way as GlacierWatch's PriorityLevel - routine < elevated < critical -
    so "adopt the more cautious rating" comparisons are a simple ordering, not a semantic guess."""

    ROUTINE = "routine"
    ELEVATED = "elevated"
    CRITICAL = "critical"


class IndianLanguage(str, Enum):
    """Languages Yatri Sahayak is instructed to actually support, not an aspirational list.
    Kept short and honest rather than claiming "20+ languages" without being able to verify each one."""

    HINDI = "hindi"
    MARATHI = "marathi"
    ENGLISH = "english"
    GUJARATI = "gujarati"
    BHOJPURI = "bhojpuri"
    TAMIL = "tamil"
    TELUGU = "telugu"
    KANNADA = "kannada"
    BENGALI = "bengali"


class NetworkMode(str, Enum):
    """Which delivery channel a pilgrim interaction actually used - see
    TRINETRA.md's network-resilience section. Every pilgrim-facing response
    is generated once and rendered for whichever mode applies, never
    assumed to be a smartphone with a live connection."""

    APP_ONLINE = "app_online"
    APP_OFFLINE_QUEUED = "app_offline_queued"
    SMS = "sms"
    USSD = "ussd"
    KIOSK = "kiosk"


# --------------------------------------------------------------------------
# Geography: ghats, routes, zones
# --------------------------------------------------------------------------


class Ghat(BaseModel):
    """A bathing ghat or major assembly point. Nashik-Trimbakeshwar Kumbh's
    real named sites - not invented placeholders - see trinetra/data/sites.json
    and its own citations."""

    id: str
    name: str
    location: str = Field(description="Nashik or Trimbakeshwar")
    safe_capacity: int = Field(description="Estimated safe concurrent occupancy, people")
    access_points: int = Field(description="Number of distinct entry/exit points")
    narrowest_approach_m: float = Field(description="Width in meters of the narrowest approach lane")
    historical_note: str = Field(default="", description="Any documented past incident at/near this site")


class Route(BaseModel):
    """A corridor connecting ghats, gates, or transit points."""

    id: str
    name: str
    connects: list[str] = Field(description="Ghat/site ids this route connects")
    width_m: float
    one_way: bool
    capacity_per_minute: int = Field(description="Estimated safe throughput, people/minute")


# --------------------------------------------------------------------------
# Pilgrim-facing: Yatri Sahayak
# --------------------------------------------------------------------------


class PilgrimQuery(BaseModel):
    text: str
    language: IndianLanguage = IndianLanguage.HINDI
    network_mode: NetworkMode = NetworkMode.APP_ONLINE
    current_location: str | None = None


class PilgrimGuidance(BaseModel):
    """Yatri Sahayak's structured answer - rendered differently per NetworkMode
    (see rendering.py's render_guidance_sms, which truncates hard for SMS)."""

    answer: str = Field(description="The core answer, in the pilgrim's requested language")
    suggested_route: str | None = None
    ghat_crowd_advisory: str | None = Field(
        default=None, description="Plain-language crowd status if the query concerned a ghat"
    )
    safety_note: str | None = Field(default=None, description="Only set when genuinely safety-relevant")
    escalate_to_sos: bool = Field(default=False, description="True if this query itself describes an emergency")


# --------------------------------------------------------------------------
# Safety: Kumbh Rakshak (SOS + lost-person)
# --------------------------------------------------------------------------


class IncidentType(str, Enum):
    LOST_PERSON = "lost_person"
    MEDICAL = "medical"
    CROWD_PRESSURE = "crowd_pressure"
    LOST_ITEM = "lost_item"
    HARASSMENT = "harassment"
    OTHER = "other"


class SOSReport(BaseModel):
    incident_type: IncidentType
    reporter_description: str
    location: str
    reported_at: datetime = Field(default_factory=datetime.utcnow)
    involves_children_or_elderly: bool = False


class SafetyTriage(BaseModel):
    """Kumbh Rakshak's structured assessment of one SOSReport."""

    incident_type: IncidentType
    severity: RiskLevel
    immediate_action: str = Field(description="What the reporting pilgrim should do right now")
    dispatch_target: str = Field(description="Which responder this routes to, e.g. 'nearest Kumbh Rakshak post', 'NTKMA medical control room'")
    rationale: str


class LostPersonRecord(BaseModel):
    """A person reported missing. Reunification matching is deliberately
    pure code (match_lost_person_reports in tools/reunification.py), never
    an LLM guessing at whether two descriptions refer to the same person -
    see TRINETRA.md's honest-limitations section on why."""

    record_id: str
    name: str
    age_estimate: int | None = None
    description: str
    last_seen_location: str
    last_seen_time: datetime = Field(default_factory=datetime.utcnow)
    reporter_contact: str
    status: str = Field(default="open", description="open | matched | closed")


class ReunificationMatch(BaseModel):
    missing_record_id: str
    found_record_id: str
    confidence: str = Field(description="strong | possible - never 'certain', a human always confirms in person")
    shared_attributes: list[str]


# --------------------------------------------------------------------------
# Administration: Prashasan Command
# --------------------------------------------------------------------------


class CrowdSignal(BaseModel):
    """One reading of a ghat's current state. In this build these are
    simulated/synthetic (see tools/crowd_signals.py's honest docstring) -
    Trinetra has no live sensor feed integration; a real deployment wires
    this to NTKMA's actual CCTV/footfall-counter pipeline."""

    ghat_id: str
    timestamp: datetime
    estimated_occupancy: int
    inflow_rate_per_min: int
    outflow_rate_per_min: int


# --------------------------------------------------------------------------
# Live ThingsBoard telemetry (github.com/akashtalole/KumbhDigiTwin).
#
# This is a second, independent source of ghat/river state - not a
# replacement for CrowdSignal/RiverStage above, which stay as the
# simulator-facing contract. The point of a second source is the same as
# the twin's own stated design philosophy: "two models, neither
# authoritative." Where they agree, that is corroboration. Where they
# disagree, LiveSignalCrossCheck reports the disagreement rather than
# picking a winner - see tools/live_signals.py.
# --------------------------------------------------------------------------


class GhatLiveReading(BaseModel):
    """One ghat's live telemetry as reported by a ThingsBoard Ghat asset
    (KumbhDigiTwin's asset-profiles/ghat.json + calculated-fields.json).

    los_grade is the Fruin pedestrian Level-of-Service scale (A best, F
    worst; grade boundaries are density in people/sqm: A<1, B<2, C<3, D<4,
    E<5, F>=5) - a different, and more physically grounded, crush-risk
    measure than Trinetra's own occupancy-percentage-of-safe-capacity. It is
    reported alongside occupancy_pct rather than converted into it, because
    the two can disagree (a ghat can be under its stated safe_capacity while
    already at LOS F if that capacity figure is generous) and that
    disagreement is itself useful information.
    """

    ghat_id: str
    thingsboard_asset_name: str
    fetched_at: datetime
    pax_count: int | None
    density_pax_per_sqm: float | None
    occupancy_pct: float | None
    los_grade: str | None
    reported_safe_capacity: int | None
    reported_area_sqm: float | None


class RiverGaugeReading(BaseModel):
    """Live water-level telemetry from a ThingsBoard WaterLevelGauge device
    attached to a ghat asset (one gauge per ghat in KumbhDigiTwin, named
    "{asset name} :: level"). This measures river STAGE at the ghat, not
    Gangapur Dam discharge volume - it is a different point in the same
    causal chain as DamRelease (a dam release raises stage at the ghats,
    with a travel-time lag), not the same quantity in different units. See
    tools/live_signals.py for how the two are cross-checked rather than
    conflated.

    derived_stage applies the RiverStage ordering to the live level/trend
    reading using the gauge's own warning_level_m/danger_level_m attributes
    - both explicitly labeled "UNCALIBRATED placeholder" in KumbhDigiTwin's
    own provisioning data, the same honesty this repo applies to its own
    numbers, so this is a structural cross-check (does the live reading
    cross a threshold) rather than a claim that either threshold is the
    real one.
    """

    ghat_id: str
    thingsboard_device_name: str
    fetched_at: datetime
    level_m: float | None
    trend_cm_per_hr: float | None
    warning_level_m: float | None
    danger_level_m: float | None
    derived_stage: RiverStage | None


class LiveSignalCrossCheck(BaseModel):
    """Compares Trinetra's own bundled ghat data (sites.json) against a live
    GhatLiveReading for the same ghat. Both figures are estimates from
    independent sources - this never picks one as correct, it reports
    whether they agree and by how much, so a human decides which (if
    either) to trust."""

    ghat_id: str
    trinetra_safe_capacity: int
    thingsboard_safe_capacity: int | None
    capacity_ratio: float | None = Field(
        description="thingsboard_safe_capacity / trinetra_safe_capacity, if both are known. "
        "1.0 means they agree; far from 1.0 means the two sources disagree about how many "
        "people this ghat can safely hold."
    )
    agrees_within_20pct: bool | None


class InterventionAction(str, Enum):
    ROUTE_DIVERSION = "route_diversion"
    GATE_CLOSURE = "gate_closure"
    CAPACITY_THROTTLE = "capacity_throttle"
    DEPLOY_PERSONNEL = "deploy_personnel"
    PUBLIC_ADVISORY = "public_advisory"
    NONE = "none"


class InterventionRecommendation(BaseModel):
    """Prashasan Command's structured recommendation for one ghat/route.
    Always a recommendation to a human operator, never an auto-executed
    action - see TRINETRA.md's human-authority framing."""

    target_id: str
    target_name: str
    current_risk: RiskLevel
    action: InterventionAction
    rationale: str
    urgency_minutes: int = Field(description="Recommended response window in minutes; 0 means immediate")


class CommandBrief(BaseModel):
    """The single document an NTKMA/NMC control-room operator actually reads."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_status: RiskLevel
    recommendations: list[InterventionRecommendation]
    summary: str


# --------------------------------------------------------------------------
# Kshetra Netra: live monitoring agent (see agents/live_monitor.py)
#
# Unlike every other agent in this repo, this one is a genuine multi-step
# tool user rather than a single structured-extraction call: it is handed
# tools that hit live ThingsBoard telemetry and Trinetra's own deterministic
# simulator/conflict/calibration code, and decides for itself which to call
# before producing this brief. It still never executes anything - see
# checked_signals/data_gaps below, which exist so a human reviewing the
# brief can tell what it actually looked at versus what it is inferring.
# --------------------------------------------------------------------------


class MonitoringFinding(BaseModel):
    """One thing Kshetra Netra checked and what it found. severity follows
    the same RiskLevel ordering as everywhere else in this repo."""

    signal_source: str = Field(description='e.g. "thingsboard:ramkund", "simulator", "conflict_scan"')
    observation: str = Field(description="What the tool call actually returned - cite numbers, not vibes.")
    severity: RiskLevel


class MonitoringBrief(BaseModel):
    """Kshetra Netra's output: a live-monitoring pass across whichever
    signals it decided to check, given to a human operator to act on."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_status: RiskLevel
    findings: list[MonitoringFinding]
    checked_signals: list[str] = Field(
        description="Every tool call the agent actually made this pass - lets a human verify it did not "
        "just answer from the prompt without checking anything live."
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Signals the agent wanted but could not get (e.g. a ghat with no ThingsBoard mapping, "
        "a failed live fetch) - never silently treated as 'all clear'.",
    )
    recommended_action: str = Field(
        description="A recommendation for a human operator. Never a claim that anything was or will be "
        "auto-executed - see TRINETRA.md's human-authority framing, which applies to this agent too."
    )
    summary: str


# --------------------------------------------------------------------------
# Bhavishya Netra: crowd digital-twin simulator
# --------------------------------------------------------------------------


class PersonaArchetype(BaseModel):
    """One behavioral archetype sampled to populate the crowd simulation.
    A small, LLM-authored set of archetypes (see agents/persona_modeler.py)
    drives a much larger deterministic agent-based simulation - not one LLM
    call per simulated pilgrim, which would be both unaffordable and
    unnecessary. See TRINETRA.md's "how the simulator actually works"
    section for why this hybrid design was chosen over either extreme."""

    name: str
    share_of_crowd: float = Field(description="Fraction of total simulated crowd, 0-1")
    walking_speed_mps: float
    group_size_avg: float
    risk_tolerance: str = Field(description="low | medium | high - affects whether the archetype pushes into a dense area")
    mobility_note: str = Field(default="", description="e.g. 'elderly, may need mobility assistance'")


class SimulationScenario(BaseModel):
    name: str
    description: str
    based_on_real_incident: str | None = Field(
        default=None, description="Citation if this scenario is calibrated against a real documented event"
    )
    total_pilgrims: int
    duration_minutes: int
    peak_inflow_multiplier: float = Field(default=1.0, description="Multiplier applied during a Shahi Snan-style peak window")
    active_ghat_ids: list[str]


class GhatSimResult(BaseModel):
    """One ghat's outcome in a simulated window.

    Read peak_occupancy_pct_of_safe_capacity together with the queue fields,
    never alone. Occupancy saturates by construction - the simulator blocks
    admission at 150% of safe capacity - so past that point the percentage
    stops responding to how many more people arrive. Between roughly 100k and
    1M pilgrims in the same scenario it moves only from ~160% to ~181%. The
    queue fields are where the rest of the crowd actually shows up, and in a
    narrow approach lane they are the more dangerous number of the two: the
    2003 Kalaram Mandir deaths happened on the approach, not at the ghat.
    """

    ghat_id: str
    ghat_name: str
    peak_occupancy: int
    peak_occupancy_pct_of_safe_capacity: float
    peak_tick_minute: int
    risk_level: RiskLevel
    bottleneck_routes: list[str]
    peak_queue_outside: int = Field(
        default=0,
        description="Most people held in the approach lane at once, unable to be admitted.",
    )
    final_queue_outside: int = Field(
        default=0,
        description="People still waiting outside when the simulated window ended.",
    )
    queue_still_growing_at_end: bool = Field(
        default=False,
        description=(
            "True if the queue was larger at the end of the window than at its midpoint - "
            "the backlog is unbounded as far as this model can see, so no clearance time can be quoted."
        ),
    )
    queue_clear_minutes: float = Field(
        default=0.0,
        description=(
            "Minutes to drain final_queue_outside at this ghat's own throughput assuming no further "
            "arrivals. Meaningless when queue_still_growing_at_end is True."
        ),
    )


class SimulationReport(BaseModel):
    """Bhavishya Netra's deterministic simulation output - the trusted
    artifact. render_simulation_md never lets an LLM restate these numbers;
    the LLM advisor layer (below) only interprets them."""

    scenario_name: str
    ghat_results: list[GhatSimResult]
    overall_risk: RiskLevel
    incidents_triggered: list[str] = Field(default_factory=list)


class NTKMAAdvisory(BaseModel):
    """The LLM advisor's read of a SimulationReport - recommendations only,
    never a restatement of the numbers themselves (those are quoted
    verbatim by rendering.py directly from SimulationReport)."""

    top_concerns: list[str]
    recommended_capacity_changes: list[InterventionRecommendation]
    narrative_summary: str


class CalibrationCaseKind(str, Enum):
    """Why a calibration case exists.

    HISTORICAL_INCIDENT cases replay documented Kumbh disasters and must come
    back CRITICAL. SYNTHETIC_CONTROL cases are constructed, not historical -
    they exist so the suite can fail. A calibration set made only of disasters
    is passed by `return CRITICAL`, which is exactly as useful as it sounds.
    """

    HISTORICAL_INCIDENT = "historical_incident"
    SYNTHETIC_CONTROL = "synthetic_control"


class CalibrationCase(BaseModel):
    """One case the simulator must get right.

    See trinetra/data/calibration_cases.json. `expect_critical` is what makes
    this a test rather than an assertion: controls that must NOT flag are the
    only reason a passing run means anything.
    """

    case_id: str
    name: str
    year: int
    location: str
    deaths: int
    cause_summary: str
    source: str
    scenario: SimulationScenario
    case_kind: CalibrationCaseKind = CalibrationCaseKind.HISTORICAL_INCIDENT
    expect_critical: bool = True


class CalibrationResult(BaseModel):
    case_id: str
    case_name: str
    real_world_deaths: int
    simulated_peak_risk: RiskLevel
    correctly_flagged: bool = Field(
        description="True if the simulated risk matched what this case expects (CRITICAL, or not-CRITICAL for a control)"
    )
    note: str
    case_kind: CalibrationCaseKind = CalibrationCaseKind.HISTORICAL_INCIDENT
    expect_critical: bool = True


# --------------------------------------------------------------------------
# Godavari compound risk: a dam release into a crowded riverfront ghat
#
# The hazard nobody models: Ramkund and the Panchavati ghats have really
# gone underwater when Gangapur Dam released heavily (see
# trinetra/data/godavari_hydrology.json's citations). During Kumbh those
# same ghats hold tens of thousands of people. The question that decides
# whether that is an inconvenience or a disaster is not "will the river
# rise" - it is "can this ghat be cleared before the water arrives", and
# that depends on who is standing on it.
# --------------------------------------------------------------------------


class RiverStage(str, Enum):
    """Ordered normal < rising < warning < danger, same "more cautious wins"
    ordering convention as RiskLevel."""

    NORMAL = "normal"
    RISING = "rising"
    WARNING = "warning"
    DANGER = "danger"


class MobilityProfile(str, Enum):
    """Who is actually standing on the ghat. Kumbh crowds skew heavily
    elderly, and an evacuation plan built on able-bodied walking speeds is
    the kind of plan that looks fine on paper and fails in the water."""

    STANDARD = "standard"
    ELDERLY_OR_MOBILITY_LIMITED = "elderly_or_mobility_limited"
    WITH_SMALL_CHILDREN = "with_small_children"


class DamRelease(BaseModel):
    """A reported/planned release from Gangapur Dam. In this build these are
    operator-supplied or synthetic - Trinetra has no live feed from the
    irrigation department's gauge telemetry."""

    discharge_cusecs: int
    reported_at: datetime = Field(default_factory=datetime.utcnow)
    note: str = ""


class EvacuationFeasibility(BaseModel):
    """The core deterministic judgment: can this ghat be cleared in time?

    clearance_minutes is computed from occupancy and a mobility-adjusted
    egress rate; lead_time_minutes is how long the water is estimated to
    take to arrive. margin_minutes is the difference - negative means the
    water arrives before the ghat is empty."""

    ghat_id: str
    ghat_name: str
    occupancy: int
    effective_egress_per_min: float = Field(description="Access-point capacity after mobility slowdown")
    clearance_minutes: float
    lead_time_minutes: int
    margin_minutes: float
    feasible: bool = Field(description="True if the ghat clears with a safety margin above the required threshold")
    risk: RiskLevel


class CompoundRiskAssessment(BaseModel):
    """River stage plus per-ghat evacuation feasibility - the deterministic
    artifact the LLM advisor interprets but never recomputes."""

    discharge_cusecs: int
    river_stage: RiverStage
    lead_time_minutes: int
    recent_rainfall_mm: float | None = Field(
        default=None, description="Live observed rainfall near Nashik, if it was fetched successfully"
    )
    rainfall_note: str = Field(default="", description="Honest note if live rainfall could not be fetched")
    ghat_feasibility: list[EvacuationFeasibility]
    overall_risk: RiskLevel
    findings: list[str] = Field(default_factory=list)


class HydrologyAdvisory(BaseModel):
    """The LLM advisor's read of a CompoundRiskAssessment - recommendations
    only; every number it cites must come from the assessment it was given."""

    headline: str = Field(description="The single most important fact, for a control-room operator with 30 seconds")
    ghats_to_clear_first: list[str] = Field(description="Ghat names in the order they should be cleared, most urgent first")
    recommended_actions: list[InterventionRecommendation]
    narrative_summary: str


# --------------------------------------------------------------------------
# Rumor triage: the crush trigger that isn't a barricade
#
# 18 people died at New Delhi railway station when a fainting incident
# spawned "rumours of a stampede-like situation" among Kumbh travellers.
# A rumor moving through a dense crowd is a crowd-safety event, and the
# counter-message is a crowd-safety intervention - which is exactly why
# broadcasting a false reassurance is its own lethal failure mode.
# --------------------------------------------------------------------------


class RumorReport(BaseModel):
    text: str = Field(description="What is being said in the crowd, as reported by field staff")
    location: str
    reported_at: datetime = Field(default_factory=datetime.utcnow)
    reported_by: str = Field(default="field staff", description="Who reported it, e.g. 'Kumbh Rakshak post 4'")
    spreading_fast: bool = Field(default=False, description="Field staff's read on whether it's propagating")


class RumorAssessment(BaseModel):
    """Kumbh Rakshak's structured read of a rumor plus a DRAFT counter-message.

    The counter-message is never auto-broadcast - see
    tools/rumor_guardrail.py and TRINETRA.md. verify_before_broadcast is the
    load-bearing field: it names what a human must actually confirm before
    the message goes out, because a broadcast that falsely reassures a crowd
    during a real emergency is worse than saying nothing."""

    crush_risk: RiskLevel = Field(description="How likely this rumor is to trigger crowd movement that injures people")
    category: str = Field(description="e.g. 'false stampede report', 'false closure report', 'medical panic'")
    why_dangerous: str
    verify_before_broadcast: list[str] = Field(
        description="Specific facts a human official must confirm before any counter-message is broadcast"
    )
    counter_message: str = Field(description="DRAFT plain-language message for loudspeaker/SMS, in English")
    counter_message_local: str = Field(description="The same draft message in Hindi or Marathi")
    recommended_channels: list[str] = Field(description="e.g. 'ghat loudspeakers', 'SMS broadcast', 'Kumbh Rakshak posts'")


class RumorGuardrailFinding(BaseModel):
    rule: str
    excerpt: str
    explanation: str


class RumorGuardrailResult(BaseModel):
    """Pure-code scan of a drafted counter-message. Mirrors BidWright's
    overclaim guardrail: a deterministic check that a drafted message does
    not make an absolute promise the drafter had no basis to make."""

    passed: bool
    findings: list[RumorGuardrailFinding] = Field(default_factory=list)
    summary: str


# --------------------------------------------------------------------------
# Sankat Nirnay: multi-hazard incident command
#
# Every agent above answers ONE question in isolation. A real NTKMA control
# room during a Shahi Snan faces all of them at once - a dam release, several
# SOS incidents, a spreading rumor, and two ghats going critical - competing
# for the same finite responder units. Two failure modes emerge from that
# concurrency that no single-hazard advisor can see:
#
#   1. Resource over-commitment. Each advisor independently says "deploy
#      personnel now". Summed, they can request more units than exist, and an
#      operator following all of them has silently under-resourced the worst
#      incident.
#   2. Contradictory directives. The flood advisor clears Ramkund toward
#      Panchavati while the crowd advisor calls Panchavati critical. Both are
#      correct alone; executing both pushes a flood evacuation into a crush -
#      which is how the 1.8m Kalaram Mandir Marg lane killed 39 people in 2003.
#
# Both are detected in pure code below, before any model is asked to judge.
# --------------------------------------------------------------------------


class ResponderType(str, Enum):
    """Kinds of finite unit an NTKMA control room actually dispatches."""

    POLICE = "police"
    MEDICAL = "medical"
    AMBULANCE = "ambulance"
    RESCUE = "rescue"
    ANNOUNCER = "announcer"


class ResourcePool(BaseModel):
    """How many units of each type are available right now.

    ILLUSTRATIVE PLANNING FIGURES, not NTKMA's actual deployment strength -
    same standing caveat as sites.json's capacities. The point of the module
    is the contention arithmetic, which holds at any pool size.
    """

    units: dict[ResponderType, int]
    note: str = Field(
        default="Illustrative pool; replace with NTKMA's real per-shift deployment strength.",
    )


class ResourceDemand(BaseModel):
    """One responder request, derived deterministically from an advisory."""

    demand_id: str
    source: str = Field(description="Which desk raised it, e.g. 'flood_advisory', 'command_brief'")
    target_id: str
    target_name: str
    responder_type: ResponderType
    units_requested: int
    severity: RiskLevel
    urgency_minutes: int
    rationale: str


class ResourceAllocation(BaseModel):
    """What a demand actually got. A partially-met or unmet demand always
    carries an explicit reason - the module never silently under-allocates."""

    demand_id: str
    source: str
    target_name: str
    responder_type: ResponderType
    units_requested: int
    units_granted: int
    severity: RiskLevel
    fully_met: bool
    shortfall_reason: str = ""


class AllocationPlan(BaseModel):
    pool: dict[ResponderType, int]
    allocations: list[ResourceAllocation]
    remaining: dict[ResponderType, int]
    contended_types: list[ResponderType] = Field(
        default_factory=list, description="Types where demand exceeded supply"
    )
    unmet_critical: list[str] = Field(
        default_factory=list,
        description="Human-readable lines for CRITICAL demands that could not be fully met - "
        "the decisions a human commander must make personally",
    )
    summary: str = ""


class ConflictKind(str, Enum):
    EVACUATION_INTO_CONGESTION = "evacuation_into_congestion"
    NARROW_LANE_EVACUATION = "narrow_lane_evacuation"
    CLOSURE_TRAPS_EVACUATION = "closure_traps_evacuation"
    RESOURCE_CONTENTION = "resource_contention"


class DirectiveConflict(BaseModel):
    """Two individually-correct recommendations that cannot both be executed."""

    kind: ConflictKind
    severity: RiskLevel
    target_name: str
    sources: list[str]
    detail: str


class ConflictScanResult(BaseModel):
    conflicts: list[DirectiveConflict] = Field(default_factory=list)
    summary: str = ""

    @property
    def has_critical(self) -> bool:
        return any(c.severity == RiskLevel.CRITICAL for c in self.conflicts)


class CommandDecision(BaseModel):
    """One resolved call. `contested` marks a decision the deterministic layer
    could only flag, not settle - the ones a human commander owns."""

    sequence: int = Field(description="Execution order, 1 = first")
    target_name: str
    directive: str = Field(description="What to do, concretely")
    responder_types: list[ResponderType] = Field(default_factory=list)
    within_minutes: int
    justification: str
    contested: bool = Field(
        default=False, description="True when this resolves a detected conflict or an unmet critical demand"
    )


class IncidentCommandPlan(BaseModel):
    """Sankat Nirnay's reconciled operational picture across every live hazard."""

    headline: str = Field(description="For an operator with 30 seconds")
    overall_risk: RiskLevel
    decisions: list[CommandDecision]
    accepted_risks: list[str] = Field(
        default_factory=list,
        description="What this plan knowingly leaves unresourced or unaddressed, stated plainly",
    )
    escalate_to_human: list[str] = Field(
        default_factory=list, description="Calls the commander must make personally"
    )
    narrative_summary: str


class PlanWeakness(BaseModel):
    weakness: str
    breaks_under: str = Field(description="The concrete condition that makes this plan fail")
    severity: RiskLevel
    suggested_mitigation: str


class PlanCritique(BaseModel):
    """An adversarial review of a finished command plan - the same
    independent-cross-check discipline the other three projects apply to
    their reports, aimed at an operational plan instead of a document."""

    weaknesses: list[PlanWeakness] = Field(default_factory=list)
    single_points_of_failure: list[str] = Field(default_factory=list)
    overall_verdict: str = Field(description="Whether the plan is sound enough to execute, and why")


# --------------------------------------------------------------------------
# A2A: talking to agents Trinetra does not own
#
# At a Kumbh the agencies are genuinely separate - Central Railway, the
# municipal hospitals, the irrigation department that operates Gangapur Dam,
# the police, and initiatives like KumbhDoot. Each has information Trinetra
# cannot compute: how many ICU beds are free, which train is arriving early,
# what the dam is actually about to release.
#
# The Agent2Agent protocol is how that connection is made. The design problem
# it creates is the one these models exist to handle: a peer agent's output is
# UNTRUSTED INPUT. It may be wrong, stale, compromised, or carrying text
# shaped like instructions to Trinetra. So a peer claim is never a fact here -
# it is an assertion, tagged with who made it and when, and it is structurally
# barred from entering the deterministic layers (hydrology, simulator,
# allocator) that Trinetra's own safety numbers come from.
# --------------------------------------------------------------------------


class TrustLevel(str, Enum):
    """How much weight a peer's assertion may carry. This is about the
    OPERATOR, not the transport - a verified authority reached over an
    unauthenticated URL is still not verified."""

    VERIFIED_AUTHORITY = "verified_authority"
    KNOWN_PARTNER = "known_partner"
    UNVERIFIED = "unverified"


class PeerAgent(BaseModel):
    """A third-party A2A agent Trinetra is permitted to talk to.

    Registration is an allowlist, not a directory: Trinetra will not call a
    URL that is not in it, because agent discovery on an open network is
    exactly how an incident commander ends up quoting a stranger.
    """

    peer_id: str
    name: str
    operator: str = Field(description="The real organisation behind it, e.g. 'Central Railway'")
    base_url: str
    trust: TrustLevel = TrustLevel.UNVERIFIED
    capabilities: list[str] = Field(
        default_factory=list, description="What this peer claims it can answer, for routing"
    )
    note: str = ""


class PeerFinding(BaseModel):
    rule: str
    excerpt: str
    explanation: str


class PeerResponseScan(BaseModel):
    """Result of the deterministic scan over a peer's reply."""

    safe_to_surface: bool
    findings: list[PeerFinding] = Field(default_factory=list)
    summary: str = ""


class PeerResponse(BaseModel):
    """One peer's answer, permanently tagged with its provenance.

    `authoritative` is not a field a caller may set. It is always False, and a
    test pins it: nothing arriving over A2A is allowed to become a number
    Trinetra plans with. Peer input is context for a human and for the
    commander agent's judgment - never an input to the deterministic core.
    """

    peer_id: str
    peer_name: str
    operator: str
    trust: TrustLevel
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    question: str
    text: str = Field(default="", description="The peer's reply, verbatim and unedited")
    error: str = ""
    scan: PeerResponseScan | None = None

    @property
    def authoritative(self) -> bool:
        """Always False. See the class docstring - this is a structural
        guarantee, not a policy someone can flip."""
        return False

    @property
    def usable(self) -> bool:
        return not self.error and bool(self.text) and (self.scan is None or self.scan.safe_to_surface)


class PeerConsultation(BaseModel):
    """What every peer said about one question, for a human to read."""

    question: str
    responses: list[PeerResponse] = Field(default_factory=list)
    summary: str = ""
