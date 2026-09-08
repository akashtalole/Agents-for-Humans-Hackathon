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
    ghat_id: str
    ghat_name: str
    peak_occupancy: int
    peak_occupancy_pct_of_safe_capacity: float
    peak_tick_minute: int
    risk_level: RiskLevel
    bottleneck_routes: list[str]


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


class CalibrationCase(BaseModel):
    """A real, documented historical incident used to validate the
    simulator - if Bhavishya Netra doesn't flag conditions resembling one
    of these as elevated/critical, the simulator isn't trustworthy enough
    to pitch. See trinetra/data/calibration_cases.json."""

    case_id: str
    name: str
    year: int
    location: str
    deaths: int
    cause_summary: str
    source: str
    scenario: SimulationScenario


class CalibrationResult(BaseModel):
    case_id: str
    case_name: str
    real_world_deaths: int
    simulated_peak_risk: RiskLevel
    correctly_flagged: bool = Field(description="True if simulated_peak_risk is CRITICAL, matching the real outcome")
    note: str
