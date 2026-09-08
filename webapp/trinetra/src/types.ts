export type RiskLevel = 'routine' | 'elevated' | 'critical'

export interface Ghat {
  id: string
  name: string
  location: string
  safe_capacity: number
  access_points: number
  narrowest_approach_m: number
  historical_note: string
}

export interface Route {
  id: string
  name: string
  connects: string[]
  width_m: number
  one_way: boolean
  capacity_per_minute: number
}

export interface SitesResponse {
  ghats: Ghat[]
  routes: Route[]
}

export interface PilgrimGuidance {
  answer: string
  suggested_route: string | null
  ghat_crowd_advisory: string | null
  safety_note: string | null
  escalate_to_sos: boolean
}

export interface SafetyTriage {
  incident_type: string
  severity: RiskLevel
  immediate_action: string
  dispatch_target: string
  rationale: string
}

export interface InterventionRecommendation {
  target_id: string
  target_name: string
  current_risk: RiskLevel
  action: string
  rationale: string
  urgency_minutes: number
}

export interface CommandBrief {
  generated_at: string
  overall_status: RiskLevel
  recommendations: InterventionRecommendation[]
  summary: string
}

export interface GhatSimResult {
  ghat_id: string
  ghat_name: string
  peak_occupancy: number
  peak_occupancy_pct_of_safe_capacity: number
  peak_tick_minute: number
  risk_level: RiskLevel
  bottleneck_routes: string[]
}

export interface SimulationReport {
  scenario_name: string
  ghat_results: GhatSimResult[]
  overall_risk: RiskLevel
  incidents_triggered: string[]
}

export interface NTKMAAdvisory {
  top_concerns: string[]
  recommended_capacity_changes: InterventionRecommendation[]
  narrative_summary: string
}

export interface TickGhatState {
  occupancy: number
  pct_of_capacity: number
}

export interface SimTickEvent {
  type: 'tick'
  minute: number
  ghats: Record<string, TickGhatState>
}

export interface SimReportEvent {
  type: 'report'
  report: SimulationReport
}

export interface SimAdvisoryEvent {
  type: 'advisory'
  advisory: NTKMAAdvisory
}

export interface SimErrorEvent {
  type: 'error'
  message: string
}

export interface SimDoneEvent {
  type: 'done'
}

export type SimEvent = SimTickEvent | SimReportEvent | SimAdvisoryEvent | SimErrorEvent | SimDoneEvent

export type RiverStage = 'normal' | 'rising' | 'warning' | 'danger'

export interface EvacuationFeasibility {
  ghat_id: string
  ghat_name: string
  occupancy: number
  effective_egress_per_min: number
  clearance_minutes: number
  lead_time_minutes: number
  margin_minutes: number
  feasible: boolean
  risk: RiskLevel
}

export interface CompoundRiskAssessment {
  discharge_cusecs: number
  river_stage: RiverStage
  lead_time_minutes: number
  recent_rainfall_mm: number | null
  rainfall_note: string
  ghat_feasibility: EvacuationFeasibility[]
  overall_risk: RiskLevel
  findings: string[]
}

export interface HydrologyAdvisory {
  headline: string
  ghats_to_clear_first: string[]
  recommended_actions: InterventionRecommendation[]
  narrative_summary: string
}

export interface FloodRiskResponse {
  assessment: CompoundRiskAssessment
  advisory: HydrologyAdvisory
}

export interface RumorAssessment {
  crush_risk: RiskLevel
  category: string
  why_dangerous: string
  verify_before_broadcast: string[]
  counter_message: string
  counter_message_local: string
  recommended_channels: string[]
}

export interface RumorGuardrailFinding {
  rule: string
  excerpt: string
  explanation: string
}

export interface RumorGuardrailResult {
  passed: boolean
  findings: RumorGuardrailFinding[]
  summary: string
}

export interface RumorResponse {
  assessment: RumorAssessment
  guardrail: RumorGuardrailResult
}

export interface CalibrationResult {
  case_id: string
  case_name: string
  real_world_deaths: number
  simulated_peak_risk: RiskLevel
  correctly_flagged: boolean
  note: string
}
