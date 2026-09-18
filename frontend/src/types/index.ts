/**
 * Types TypeScript miroir des modèles backend NEXUS AI  Prompt 8.1.
 *
 * Chaque type ci-dessous est aligné sur un modèle Pydantic/SQLAlchemy RÉEL
 * (Prompts 7.1/7.2), pas deviné : les commentaires référencent le fichier
 * backend exact. Les noms de champs suivent le snake_case du JSON renvoyé
 * par FastAPI (pas de camelCase automatique côté backend), donc ces types
 * matchent le payload réseau tel quel, sans couche de transformation.
 */

// ── Campaign (backend/api/routes/campaigns.py: CampaignOut) ────────────────

export type CampaignStatus = "draft" | "active" | "paused" | "completed" | "archived";

/** `channel_allocations` (backend/db/models/campaigns.py) : répartition
 * budgétaire par canal, ex. {"seo": 0.2, "sea": 0.5, "social": 0.3}. */
export type ChannelAllocation = Record<string, number>;

export interface Campaign {
  id: string;
  client_id: string;
  name: string;
  objective: string;
  budget_total: number;
  budget_consumed: number;
  status: CampaignStatus;
  channel_allocations: ChannelAllocation | null;
  start_date: string | null;
  end_date: string | null;
  results: Record<string, unknown> | null;
  thread_id: string | null;
}

// ── Agent (backend/api/routes/agents.py: AgentStatus response) ─────────────

export type AgentType = "seo" | "sea" | "content" | "social" | "email" | "analytics" | "creative" | "reporting";

/**
 * Statut d'affichage synthétique pour les badges (spec 8.1 : "Badge avec
 * variants pour les statuts agents")  AUCUN champ `status` de ce type
 * n'existe dans la réponse réelle de GET /agents (backend/api/routes/
 * agents.py: AgentStatus, Prompt 7.1) : ce backend expose `queue_depth`/
 * `last_decision_at`, pas un état énuméré actif/idle/erreur/pause (rien
 * dans ce projet ne piste un flag "agent en pause" ni "en erreur" par
 * agent). C'est donc un type DÉRIVÉ côté client (voir
 * `getAgentDisplayStatus` ci-dessous), pas un miroir direct du backend 
 * documenté explicitement plutôt que fabriqué comme un vrai champ API.
 */
export type AgentStatus = "active" | "idle" | "error" | "paused";

/** Miroir exact de `agents.AgentStatus` (le modèle Pydantic de réponse,
 * malheureusement nommé pareil que le type d'affichage ci-dessus dans le
 * spec  distingués ici par `Agent` pour la donnée API réelle). */
export interface Agent {
  name: string;
  queue: string;
  queue_depth: number;
  last_decision_at: string | null;
  expected_trigger_kwargs: string[];
}

/** Seuil arbitraire (15 min) au-delà duquel un agent sans décision récente
 * est classé "idle" plutôt que "active"  heuristique documentée, pas une
 * règle métier backend (qui n'en définit aucune à ce jour). */
const AGENT_ACTIVE_WINDOW_MS = 15 * 60 * 1000;

export function getAgentDisplayStatus(agent: Agent): AgentStatus {
  if (agent.last_decision_at === null) return "idle";
  const elapsed = Date.now() - new Date(agent.last_decision_at).getTime();
  return elapsed <= AGENT_ACTIVE_WINDOW_MS ? "active" : "idle";
}

// ── Content (backend/api/routes/content.py: ContentOut) ─────────────────────

export type ContentType = "article" | "post" | "email" | "landing_page" | "visual";
export type ContentPlatform = "linkedin" | "meta" | "tiktok" | "email" | "web";
export type ContentStatus = "draft" | "review" | "published" | "archived";

export interface Content {
  id: string;
  client_id: string;
  campaign_id: string | null;
  agent_source: string;
  content_type: ContentType;
  title: string | null;
  body: string;
  platform: ContentPlatform;
  status: ContentStatus;
  performance_data: Record<string, unknown> | null;
  published_at: string | null;
  scheduled_at: string | null;
}

// ── HITL (backend/api/routes/hitl.py) ───────────────────────────────────────

export type HITLDecision = "approve" | "reject" | "modify";

/** Miroir de `hitl.PendingHITL`. */
export interface HITLRequest {
  campaign_id: string;
  client_id: string;
  thread_id: string;
  /** Payload passé à `interrupt()` par `hitl_checkpoint_node`  forme
   * libre ({"proposal", "context", "options"}, voir orchestrator/nodes.py),
   * non typée strictement ici (dépend de l'agent/nœud à l'origine). */
  payload: Record<string, unknown> | null;
}

// ── Analytics : deux familles de formes, PAS la même (voir commentaires) ───

/**
 * Miroir de `analytics.KPIOut` (backend/api/routes/analytics.py)  la forme
 * RÉELLE renvoyée par `GET /analytics/kpis` (une ligne PerformanceMetric,
 * channel="cross_channel").
 */
export interface KPIMetric {
  metric_name: string;
  metric_value: number;
  period_start: string;
  period_end: string;
}

/** Miroir de `analytics.ChannelPerformance` (GET /analytics/channels). */
export interface ChannelPerformance {
  channel: string;
  metrics: Record<string, number>;
}

/**
 * `KPIResult`/`WeeklyReport` (spec 8.1) : miroir de
 * `backend/agents/reporting/report_builder.py`, PAS de `analytics.py`  une
 * forme plus riche, utilisée dans le CONTENU d'un `Report` complet
 * (GET /analytics/reports/{id}, champ `content`), distincte de `KPIMetric`
 * ci-dessus (la liste "brute" de métriques de GET /analytics/kpis). Les deux
 * coexistent dans ce projet, ce n'est pas une duplication accidentelle.
 */
export interface KPIResult {
  name: string;
  value: number;
  target: number | null;
  trend: "up" | "down" | "stable" | null;
}

export interface ChannelReport {
  channel: string;
  spend: number;
  revenue: number;
  roas: number;
  conversions: number;
  summary: string;
}

export interface ContentPerformance {
  content_id: string;
  title: string | null;
  platform: string;
  engagement_score: number;
  views: number;
}

export interface AnomalyReport {
  score: number;
  explanation: string;
  severity: "low" | "medium" | "high";
}

export interface DecisionLog {
  agent: string;
  decision_type: string;
  timestamp: string;
  summary: string;
}

export interface Recommendation {
  action: string;
  expected_impact: string;
  effort: "low" | "medium" | "high";
  priority: number;
}

export interface BudgetSummary {
  total_budget: number;
  total_spend: number;
  remaining: number;
  utilization_pct: number;
}

export interface WeeklyReport {
  period: string;
  client_id: string;
  executive_summary: string;
  kpi_scorecard: Record<string, KPIResult>;
  channel_performance: Record<string, ChannelReport>;
  top_contents: ContentPerformance[];
  anomalies_detected: AnomalyReport[];
  decisions_taken: DecisionLog[];
  recommendations: Recommendation[];
  budget_summary: BudgetSummary;
  next_week_plan: string;
}

/** Miroir de `analytics.ReportOut`/`ReportDetailOut` (backend/db/models/reports.py: Report). */
export interface Report {
  id: string;
  client_id: string;
  report_type: string;
  period: string | null;
  pdf_path: string | null;
  delivered_at: string | null;
}

export interface ReportDetail extends Report {
  /** Structure réelle selon `report_type` : WeeklyReport ci-dessus pour
   * "weekly", CampaignReport/CrisisReport (non listés par le spec 8.1) pour
   * les autres  laissé en `unknown` plutôt qu'un union imprécis, à affiner
   * quand ces pages seront construites (Prompt 8.x ultérieur). */
  content: WeeklyReport | Record<string, unknown>;
}

/** Miroir de `analytics.AnomalyOut` (backend/api/routes/analytics.py) : lu
 * depuis AgentDecision (decision_type="anomaly_detected"), distinct de
 * `AnomalyReport` ci-dessus (qui, lui, vit UNIQUEMENT dans le contenu JSON
 * d'un WeeklyReport déjà généré). */
export interface Anomaly {
  id: string;
  decision_data: Record<string, unknown>;
  outcome: Record<string, unknown> | null;
  created_at: string;
}

/** Miroir de `campaigns.get_campaign_history` (backend/api/routes/campaigns.py) :
 * un snapshot LangGraph par checkpoint, le plus récent en premier. */
export interface CampaignHistorySnapshot {
  values: Record<string, unknown>;
  next: string[];
  created_at: string;
}

// ── WebSocket (backend/api/websocket/events.py) ─────────────────────────────

/** Miroir EXACT de `EventType` (events.py)  mêmes 9 valeurs, même ordre. */
export enum EventType {
  AGENT_STATUS = "agent_status",
  TASK_PROGRESS = "task_progress",
  HITL_INTERRUPT = "hitl_interrupt",
  HITL_RESOLVED = "hitl_resolved",
  CONTENT_STREAM = "content_stream",
  ALERT = "alert",
  BUDGET_UPDATE = "budget_update",
  CAMPAIGN_UPDATE = "campaign_update",
  REPORT_READY = "report_ready",
}

/** Miroir de `WebSocketMessage` (events.py). */
export interface WebSocketMessage<TPayload = Record<string, unknown>> {
  event_type: EventType;
  campaign_id: string | null;
  agent_name: string | null;
  payload: TPayload;
  timestamp: string;
  trace_id: string;
}

// ── Auth (backend/api/auth.py: UserProfile) ─────────────────────────────────

export type UserRole = "admin" | "manager" | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  client_id: string | null;
  is_active: boolean;
}

// ── Client (backend/api/routes/clients.py: ClientOut/ClientDetailOut) ──────

export interface ClientSummary {
  id: string;
  name: string;
  industry: string | null;
  website: string | null;
}

export interface ClientDetail extends ClientSummary {
  editorial_guidelines: Record<string, unknown> | null;
  brand_colors: Record<string, string> | null;
  logo_url: string | null;
  forbidden_topics: string[] | null;
  /** Config/identifiants fournis par le client pour chaque service tiers
   * PAS un flux OAuth2 réel (voir clients.py). */
  integrations: Record<string, unknown> | null;
}

// ── Alert (backend/core/state/state_models.py: Alert) ───────────────────────

export type AlertLevel = "info" | "warning" | "critical";

export interface Alert {
  level: AlertLevel;
  source: string;
  message: string;
  timestamp: string;
  action_required: boolean;
}

// ── Visual/Template ──────────────────────────────────────────────────────────

/** Miroir de `state_models.VisualAsset` (Agent Créatif, ComfyUI). */
export interface VisualAsset {
  id: string;
  type: "image" | "video" | "carousel";
  format: "png" | "jpg" | "gif" | "mp4" | "webp";
  file_path: string;
  /** Ex. "1080x1080"  voir dimensions du modèle backend (chaîne libre, pas
   * une paire structurée : c'est le format tel qu'exposé par l'API). */
  dimensions: string;
  style_tags: string[];
}

/** Miroir de `backend/db/models/content.py: ContentTemplate` (nommé
 * "Template" par le spec, "ContentTemplate" côté backend). */
export interface Template {
  id: string;
  client_id: string;
  template_type: string;
  structure: Record<string, unknown>;
  figma_file_id: string | null;
  canva_template_id: string | null;
}
