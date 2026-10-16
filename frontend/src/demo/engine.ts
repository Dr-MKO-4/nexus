/**
 * Moteur de simulation de la démo : base en mémoire + bus d'événements.
 *
 * Tout est fictif (clients, campagnes, contenus, chiffres). La logique
 * reprend les règles réelles du backend :
 * - topologie du graphe principal (backend/agents/orchestrator/graph.py) :
 *   parse_objective -> plan_week -> route_to_cluster -> clusters ->
 *   consolidate_results -> check_performance -> (hitl_checkpoint) ->
 *   generate_report ;
 * - clusters `_ACQUISITION_AGENTS`/`_ENGAGEMENT_AGENTS`/`_MEASURE_AGENTS`
 *   (orchestrator/nodes.py) ;
 * - règle HITL de `_reallocation_is_significant` : écart > 50 % sur un KPI
 *   cible => validation humaine ; écart > 20 % (`_PERFORMANCE_GAP_THRESHOLD`)
 *   => réallocation automatique de 10 % (`shift_ratio`) ;
 * - payload d'`interrupt()` de `hitl_checkpoint_node` :
 *   {proposal, context, options: ["resume", "stop", "modify"]} ;
 * - noms de tâches Celery et de queues réels (tasks/workers/*.py,
 *   tasks/queues/redis_queue.py) ; noms de KPIs de `compute_kpis_node`.
 *
 * Aucun LLM n'est appelé : les textes « générés » sont des modèles écrits
 * à l'avance, choisis de façon déterministe.
 */
import type {
  Agent,
  Anomaly,
  Campaign,
  CampaignHistorySnapshot,
  ChannelPerformance,
  ClientDetail,
  Content,
  KPIMetric,
  Report,
  ReportDetail,
  User,
  WebSocketMessage,
  WeeklyReport,
} from "@/types";
import { EventType } from "@/types";

const DAY = 86_400_000;
const now = () => Date.now();
const iso = (t: number) => new Date(t).toISOString();
export const uid = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx".replace(/x/g, () => Math.floor(Math.random() * 16).toString(16));

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

// ── Référentiel réel (backend/api/routes/agents.py: _AGENT_DISPATCH) ──────

export const AGENT_DISPATCH: Record<string, { task: string; queue: string; kwargs: string[] }> = {
  seo: { task: "nexus.marketing.audit_seo_task", queue: "seo_tasks", kwargs: ["client_id"] },
  sea: { task: "nexus.marketing.update_sea_bids_task", queue: "seo_tasks", kwargs: ["client_id"] },
  content: { task: "nexus.llm.generate_content_task", queue: "llm_inference", kwargs: ["brief", "client_id"] },
  social: { task: "nexus.marketing.publish_social_post_task", queue: "social_publish", kwargs: ["content_id", "platforms"] },
  email: { task: "nexus.marketing.send_email_sequence_task", queue: "email_dispatch", kwargs: ["contact_ids", "sequence_name"] },
  analytics: { task: "nexus.marketing.collect_analytics_task", queue: "analytics", kwargs: ["client_id", "period"] },
  creative: { task: "nexus.image.generate_visual_task", queue: "image_generation", kwargs: ["brief", "client_id", "campaign_id"] },
  reporting: { task: "nexus.llm.run_agent_task", queue: "llm_inference", kwargs: ["state_dict"] },
};

const CLUSTERS: { node: string; agents: string[] }[] = [
  { node: "acquisition_cluster", agents: ["seo", "sea"] },
  { node: "engagement_cluster", agents: ["content", "social", "email"] },
  { node: "measure_cluster", agents: ["analytics", "reporting"] },
];

const SCHEDULED_TASKS = [
  { task: "nexus.scheduled.hourly_sea_performance_check", agent: "sea" },
  { task: "nexus.scheduled.daily_analytics_collection", agent: "analytics" },
  { task: "nexus.scheduled.weekly_seo_audit", agent: "seo" },
  { task: "nexus.scheduled.daily_email_sequence_processor", agent: "email" },
];

// ── Données fictives ────────────────────────────────────────────────────────

const C1 = "3f6b2a10-6c1e-4a51-9d1e-1c0de0000001";
const C2 = "3f6b2a10-6c1e-4a51-9d1e-1c0de0000002";

interface AgentRow {
  name: string;
  last_decision_at: string | null;
  queue_depth: number;
}

interface DecisionRow {
  id: string;
  agent_name: string;
  client_id: string;
  decision_type: string;
  decision_data: Record<string, unknown>;
  outcome: Record<string, unknown> | null;
  created_at: string;
}

interface CampaignRow extends Campaign {
  history: CampaignHistorySnapshot[];
  hitl_payload: Record<string, unknown> | null;
  run_timer?: number;
}

interface ReportRow extends Report {
  content: WeeklyReport | Record<string, unknown>;
}

export const db = {
  users: [] as (User & { password?: string })[],
  clients: [] as ClientDetail[],
  campaigns: [] as CampaignRow[],
  contents: [] as Content[],
  reports: [] as ReportRow[],
  decisions: [] as DecisionRow[],
  agents: [] as AgentRow[],
};

function snapshot(values: Record<string, unknown>, next: string[], t: number): CampaignHistorySnapshot {
  return { values, next, created_at: iso(t) };
}

function seededHistory(c: Campaign, t0: number, paused: boolean): CampaignHistorySnapshot[] {
  const base = { campaign_id: c.id, client_id: c.client_id, objective: c.objective, budget_total: c.budget_total };
  const steps: [string[], Record<string, unknown>][] = [
    [["plan_week"], { ...base, current_step: "parse_objective", target_kpis: { nb_conversions: 120, organic_traffic_growth: 0.15 } }],
    [["route_to_cluster"], { ...base, current_step: "plan_week", week_plan: ["audit SEO local", "annonces géolocalisées", "posts réseaux sociaux"] }],
    [["acquisition_cluster", "engagement_cluster", "measure_cluster"], { ...base, current_step: "route_to_cluster", active_clusters: ["acquisition", "engagement", "measure"] }],
    [["check_performance"], { ...base, current_step: "consolidate_results", budget_consumed: c.budget_consumed, channel_allocations: c.channel_allocations }],
    [paused ? ["hitl_checkpoint"] : ["generate_report"], { ...base, current_step: "check_performance", hitl_required: paused }],
  ];
  if (!paused) steps.push([[], { ...base, current_step: "generate_report", report_generated: true }]);
  return steps
    .map(([next, values], i) => snapshot(values, next, t0 + i * 90_000))
    .reverse();
}

function seed(): void {
  const t = now();
  db.users = [
    { id: uid(), email: "admin@exemple.org", role: "admin", client_id: null, is_active: true },
    { id: uid(), email: "direction@kora-cafe.exemple.org", role: "manager", client_id: C1, is_active: true },
    { id: uid(), email: "stagiaire@kora-cafe.exemple.org", role: "viewer", client_id: C1, is_active: true },
    { id: uid(), email: "marketing@lumio.exemple.org", role: "manager", client_id: C2, is_active: true },
    { id: uid(), email: "ancien.compte@lumio.exemple.org", role: "viewer", client_id: C2, is_active: false },
  ];
  db.clients = [
    {
      id: C1,
      name: "Kora Café",
      industry: "Restauration",
      website: "https://kora-cafe.exemple.org",
      editorial_guidelines: { tone: "Chaleureux, convivial, tutoiement sur les réseaux", priority_topics: "brunch, produits locaux, événements du week-end" },
      brand_colors: { primary: "#7a3e1d", secondary: "#f2c14e" },
      logo_url: null,
      forbidden_topics: ["politique", "comparaison nominative avec des concurrents"],
      integrations: { Matomo: { api_key: "demo-xxxx", connected: true }, Mautic: { api_key: "demo-xxxx", connected: true }, Meta: { connected: false } },
    },
    {
      id: C2,
      name: "Lumio Énergie",
      industry: "Énergie solaire",
      website: "https://lumio.exemple.org",
      editorial_guidelines: { tone: "Pédagogique et rassurant", priority_topics: "kits solaires, économies d'énergie, installation" },
      brand_colors: { primary: "#0f6d5c", secondary: "#ffd23f" },
      logo_url: null,
      forbidden_topics: ["promesses de rendement chiffrées non vérifiées"],
      integrations: { "Google Search Console": { api_key: "demo-xxxx", connected: true }, "Google Ads": { connected: false } },
    },
  ];

  const mk = (
    client_id: string,
    name: string,
    objective: string,
    status: Campaign["status"],
    budget_total: number,
    budget_consumed: number,
    channel_allocations: Record<string, number>,
    startOffsetDays: number,
  ): CampaignRow => {
    const c: CampaignRow = {
      id: uid(),
      client_id,
      name,
      objective,
      budget_total,
      budget_consumed,
      status,
      channel_allocations,
      start_date: iso(t - startOffsetDays * DAY),
      end_date: iso(t + (30 - startOffsetDays) * DAY),
      results: status === "completed" ? { conversions: 74, report: "campaign" } : null,
      thread_id: status === "draft" ? null : uid(),
      history: [],
      hitl_payload: null,
    };
    if (c.thread_id) c.history = seededHistory(c, t - startOffsetDays * DAY, status === "paused");
    return c;
  };

  const paused = mk(C1, "Visibilité locale Google", "Doubler les réservations venant de la recherche locale d'ici fin du mois.", "paused", 1200, 980, { seo: 0.3, sea: 0.6, social: 0.1 }, 12);
  paused.hitl_payload = {
    proposal: {
      underperforming_channels: ["sea"],
      overperforming_channels: ["seo", "social"],
      reasoning:
        "**Écart de 58 %** entre les conversions cibles (120) et les conversions mesurées (50) : au-delà du seuil de 50 %, une réallocation exige votre accord.\n\nProposition : transférer **10 %** du budget SEA vers le SEO local et les posts sociaux, qui convertissent mieux cette semaine.",
    },
    context: {
      client_id: C1,
      campaign_id: paused.id,
      budget_total: paused.budget_total,
      budget_consumed: paused.budget_consumed,
      channel_allocations: paused.channel_allocations,
    },
    options: ["resume", "stop", "modify"],
  };

  db.campaigns = [
    mk(C1, "Lancement brunch du week-end", "Faire connaître la nouvelle formule brunch et remplir les créneaux du dimanche.", "active", 1500, 640, { seo: 0.2, sea: 0.35, social: 0.45 }, 9),
    mk(C1, "Fidélisation newsletter mensuelle", "Augmenter le taux de retour des clients inscrits à la newsletter.", "active", 600, 210, { email: 0.7, social: 0.3 }, 5),
    paused,
    mk(C1, "Promo rentrée", "Relancer la fréquentation en semaine après les vacances.", "completed", 800, 790, { sea: 0.5, social: 0.5 }, 40),
    mk(C1, "Menu de saison", "Préparer le lancement du menu de saison (brouillon).", "draft", 900, 0, { social: 0.6, email: 0.4 }, 0),
    mk(C2, "Kits solaires : génération de leads", "Obtenir des demandes de devis qualifiées pour les kits solaires résidentiels.", "active", 3000, 1320, { seo: 0.25, sea: 0.5, email: 0.25 }, 14),
    mk(C2, "Guide économies d'énergie", "Diffuser le guide pratique et collecter des contacts.", "active", 1200, 380, { seo: 0.4, social: 0.3, email: 0.3 }, 6),
  ];

  const contents: [string, Content["content_type"], Content["platform"], Content["status"], string, string, number][] = [
    [C1, "post", "meta", "published", "Le brunch arrive dimanche !", "Pancakes, jus pressés et produits du marché : découvre notre nouvelle formule brunch ce dimanche dès 10 h.", -6],
    [C1, "post", "linkedin", "published", "Nos producteurs partenaires", "Derrière chaque assiette, des producteurs locaux. Rencontre ceux qui fournissent nos fruits et légumes.", -4],
    [C1, "email", "email", "published", "Newsletter : les nouveautés du mois", "Ce mois-ci : formule brunch, soirée musique live et une surprise pour les abonnés fidèles.", -3],
    [C1, "article", "web", "review", "5 idées de brunch maison inspirées de notre carte", "Envie de reproduire l'ambiance Kora chez toi ? Voici cinq recettes simples inspirées de notre carte…", 1],
    [C1, "post", "tiktok", "draft", "Coulisses : la préparation du brunch", "Script vidéo 30 s : arrivée des produits, préparation des pancakes, dressage, sourire de l'équipe.", 2],
    [C1, "post", "meta", "review", "Soirée musique live", "Vendredi soir, musique live et cocktails sans alcool maison. Réserve ta table !", 4],
    [C1, "landing_page", "web", "draft", "Page réservation brunch", "Titre : Le brunch du dimanche. Sections : formule, horaires, réservation, avis clients.", 6],
    [C1, "email", "email", "draft", "Relance des abonnés inactifs", "Ça fait longtemps ! Un café offert pour ton prochain passage, sur présentation de cet e-mail.", 8],
    [C1, "visual", "meta", "review", "Visuel brunch carré", "Visuel 1080x1080 : table de brunch vue du dessus, tons chauds, logo en bas à droite.", 3],
    [C1, "visual", "web", "draft", "Bannière site web", "Bannière 1920x600 : terrasse ensoleillée, accroche « Le dimanche, on brunch ».", 5],
    [C1, "visual", "tiktok", "published", "Miniature vidéo coulisses", "Miniature 1080x1920 : main qui verse du sirop sur des pancakes.", -2],
    [C1, "post", "linkedin", "archived", "Offre rentrée (terminée)", "Offre de rentrée : -10 % sur les formules midi en semaine.", -20],
    [C2, "article", "web", "published", "Comment dimensionner un kit solaire ?", "Puissance, batterie, consommation : la méthode pas à pas pour choisir le bon kit.", -5],
    [C2, "email", "email", "review", "Séquence devis : relance J+3", "Vous avez demandé un devis : voici les trois questions à vous poser avant l'installation.", 2],
    [C2, "post", "linkedin", "draft", "Étude de cas installation", "Retour d'expérience d'une installation résidentielle (cas fictif).", 5],
  ];
  db.contents = contents.map(([client_id, content_type, platform, status, title, body, offset]) => {
    const date = new Date(t + offset * DAY);
    date.setHours(10 + Math.abs(offset % 7), 0, 0, 0);
    const campaign = db.campaigns.find((c) => c.client_id === client_id && c.status === "active");
    return {
      id: uid(),
      client_id,
      campaign_id: campaign?.id ?? null,
      agent_source: content_type === "visual" ? "creative" : content_type === "email" ? "email" : "content",
      content_type,
      title,
      body,
      platform,
      status,
      performance_data: status === "published" ? { views: Math.round(800 + hash(title) * 3200), clicks: Math.round(40 + hash(body) * 260) } : null,
      published_at: status === "published" || status === "archived" ? iso(date.getTime()) : null,
      scheduled_at: status === "published" || status === "archived" ? null : iso(date.getTime()),
    };
  });

  db.agents = Object.keys(AGENT_DISPATCH).map((name, i) => ({
    name,
    queue_depth: [1, 0, 3, 1, 0, 2, 0, 0][i],
    last_decision_at: ["seo", "content", "social", "analytics"].includes(name) ? iso(t - (2 + i) * 60_000) : iso(t - (3 + i) * 3_600_000),
  }));

  const decision = (agent_name: string, client_id: string, decision_type: string, data: Record<string, unknown>, ago: number): DecisionRow => ({
    id: uid(),
    agent_name,
    client_id,
    decision_type,
    decision_data: data,
    outcome: null,
    created_at: iso(t - ago),
  });
  db.decisions = [
    decision("analytics", C1, "anomaly_detected", {
      is_anomaly: true,
      score: 0.91,
      explanation: "Score de reconstruction au-dessus du 95e percentile de l'historique.",
      explanation_clear: "Le coût par acquisition SEA a fortement augmenté mardi alors que le trafic organique restait stable : probablement une enchère trop agressive sur des requêtes peu qualifiées.",
      requires_immediate_action: false,
    }, 2 * DAY),
    decision("analytics", C1, "anomaly_detected", {
      is_anomaly: true,
      score: 0.97,
      explanation: "Chute brutale des conversions sur la période.",
      explanation_clear: "Les réservations en ligne ont chuté samedi : le module de réservation du site semble avoir été indisponible quelques heures.",
      requires_immediate_action: true,
    }, 5 * DAY),
    decision("social", C1, "trend_detection", { topic: "brunch du dimanche", platform: "tiktok", momentum: "en hausse" }, 1 * DAY),
    decision("analytics", C2, "anomaly_detected", {
      is_anomaly: true,
      score: 0.88,
      explanation: "Hausse inhabituelle du taux de rebond.",
      explanation_clear: "Le taux de rebond de la page devis a doublé depuis la mise en ligne du nouveau formulaire.",
      requires_immediate_action: false,
    }, 3 * DAY),
  ];
  for (const a of db.agents) {
    if (a.last_decision_at && !db.decisions.some((d) => d.agent_name === a.name)) {
      db.decisions.push(decision(a.name, C1, AGENT_DISPATCH[a.name].task.split(".").pop()!, { simulated: true }, now() - new Date(a.last_decision_at).getTime()));
    }
  }

  db.reports = [];
  for (const client of db.clients) {
    for (let w = 1; w <= 3; w++) db.reports.push(buildWeeklyReport(client.id, w));
  }
}

function weekLabel(weeksAgo: number): string {
  const end = new Date(now() - (weeksAgo - 1) * 7 * DAY);
  const start = new Date(end.getTime() - 7 * DAY);
  const f = (d: Date) => d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
  return `${f(start)} au ${f(end)}`;
}

function buildWeeklyReport(client_id: string, weeksAgo: number): ReportRow {
  const k = kpisFor(client_id, weeksAgo);
  const budget_total = db.campaigns.filter((c) => c.client_id === client_id).reduce((s, c) => s + c.budget_total, 0);
  const total_spend = db.campaigns.filter((c) => c.client_id === client_id).reduce((s, c) => s + c.budget_consumed, 0);
  const content: WeeklyReport = {
    period: weekLabel(weeksAgo),
    client_id,
    executive_summary:
      "Semaine portée par le SEO local et les réseaux sociaux. Le SEA reste le canal le plus coûteux par conversion ; une réallocation partielle est recommandée.",
    kpi_scorecard: {
      nb_conversions: { name: "nb_conversions", value: k.nb_conversions, target: 120, trend: "up" },
      roas: { name: "roas", value: k.roas, target: 3, trend: "stable" },
      organic_traffic_growth: { name: "organic_traffic_growth", value: k.organic_traffic_growth, target: 0.15, trend: "up" },
    },
    channel_performance: {
      seo: { channel: "seo", spend: 120, revenue: 980, roas: 8.2, conversions: 31, summary: "Positions en hausse sur les requêtes locales." },
      sea: { channel: "sea", spend: 410, revenue: 860, roas: 2.1, conversions: 22, summary: "CPA en hausse, enchères à revoir." },
      social: { channel: "social", spend: 150, revenue: 720, roas: 4.8, conversions: 26, summary: "Bon engagement sur les vidéos courtes." },
    },
    top_contents: db.contents
      .filter((c) => c.client_id === client_id && c.status === "published")
      .slice(0, 3)
      .map((c) => ({ content_id: c.id, title: c.title, platform: c.platform, engagement_score: Math.round(hash(c.id) * 100) / 100, views: Number(c.performance_data?.views ?? 0) })),
    anomalies_detected: [{ score: 0.91, explanation: "Hausse du CPA SEA mardi.", severity: "medium" }],
    decisions_taken: [
      { agent: "sea", decision_type: "update_sea_bids_task", timestamp: iso(now() - weeksAgo * 7 * DAY), summary: "Baisse des enchères sur les requêtes génériques." },
      { agent: "content", decision_type: "generate_content_task", timestamp: iso(now() - weeksAgo * 7 * DAY + DAY), summary: "Trois posts et une newsletter générés." },
    ],
    recommendations: [
      { action: "Transférer 10 % du budget SEA vers le SEO local", expected_impact: "Baisse du coût par conversion", effort: "low", priority: 1 },
      { action: "Tester un format vidéo court sur TikTok", expected_impact: "Hausse de la portée organique", effort: "medium", priority: 2 },
    ],
    budget_summary: { total_budget: budget_total, total_spend, remaining: budget_total - total_spend, utilization_pct: Math.round((total_spend / Math.max(1, budget_total)) * 1000) / 10 },
    next_week_plan: "Audit SEO des fiches locales, deux posts sociaux, relance e-mail des abonnés inactifs.",
  };
  return {
    id: uid(),
    client_id,
    report_type: "weekly",
    period: content.period,
    pdf_path: null,
    delivered_at: iso(now() - (weeksAgo - 1) * 7 * DAY - 3_600_000),
    content,
  };
}

/** KPIs de `compute_kpis_node` (backend/agents/analytics/nodes.py), valeurs fictives. */
function kpisFor(client_id: string, weeksAgo: number): Record<string, number> {
  const s = client_id === C1 ? 1 : 2.4;
  const f = 1 - 0.08 * weeksAgo;
  const visits = Math.round(3840 * s * f);
  const conversions = Math.round(96 * s * f);
  const revenue = Math.round(4210 * s * f);
  const spend = Math.round(1320 * s);
  return {
    cac: Math.round((spend / conversions) * 100) / 100,
    roas: Math.round((revenue / spend) * 100) / 100,
    cpa: Math.round((spend / conversions) * 0.9 * 100) / 100,
    email_roi: Math.round((2.4 - 0.1 * weeksAgo) * 100) / 100,
    organic_traffic_growth: Math.round((0.124 - 0.02 * weeksAgo) * 1000) / 1000,
    nb_visits: visits,
    nb_conversions: conversions,
    revenue,
    goal_count: 4,
  };
}

export function getKPIs(client_id: string, period_end?: string): KPIMetric[] {
  const end = period_end ? new Date(period_end).getTime() : now();
  const weeksAgo = Math.max(0, Math.round((now() - end) / (7 * DAY)));
  const k = kpisFor(client_id, weeksAgo);
  return Object.entries(k).map(([metric_name, metric_value]) => ({
    metric_name,
    metric_value,
    period_start: iso(end - 7 * DAY),
    period_end: iso(end),
  }));
}

export function getChannels(client_id: string): ChannelPerformance[] {
  const s = client_id === C1 ? 1 : 2.4;
  return [
    { channel: "seo", metrics: { nb_visits: Math.round(2150 * s), avg_position: 7.4, keywords_top10: Math.round(18 * s) } },
    { channel: "sea", metrics: { spend: Math.round(58 * s), roas: 2.1, cpa: 18.6, ctr: 3.2, clicks: Math.round(310 * s) } },
    { channel: "social", metrics: { impressions: Math.round(12400 * s), engagement_rate: 4.6, followers_gained: Math.round(85 * s) } },
    { channel: "email", metrics: { sent: Math.round(1800 * s), open_rate: 38.5, click_rate: 6.1 } },
  ];
}

export function getAnomalies(client_id: string): Anomaly[] {
  return db.decisions
    .filter((d) => d.client_id === client_id && d.decision_type === "anomaly_detected")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .map((d) => ({ id: d.id, decision_data: d.decision_data, outcome: d.outcome, created_at: d.created_at }));
}

export function getAgents(): Agent[] {
  return db.agents.map((a) => ({
    name: a.name,
    queue: AGENT_DISPATCH[a.name].queue,
    queue_depth: a.queue_depth,
    last_decision_at: a.last_decision_at,
    expected_trigger_kwargs: AGENT_DISPATCH[a.name].kwargs,
  }));
}

export function getAgentLogs(name: string, limit: number) {
  return db.decisions
    .filter((d) => d.agent_name === name)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit)
    .map(({ id, client_id, decision_type, decision_data, outcome, created_at }) => ({ id, client_id, decision_type, decision_data, outcome, created_at }));
}

export function getReportDetail(id: string): ReportDetail | undefined {
  return db.reports.find((r) => r.id === id);
}

export function publicCampaign(c: CampaignRow): Campaign {
  const { history: _h, hitl_payload: _p, run_timer: _r, ...rest } = c;
  return rest;
}

// ── Bus d'événements (équivalent du ConnectionManager WebSocket) ─────────

type Listener = (m: WebSocketMessage) => void;
const listeners = new Set<Listener>();
export function onMessage(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
function emit(event_type: EventType, payload: Record<string, unknown>, opts: { campaign_id?: string | null; agent_name?: string | null } = {}) {
  const message: WebSocketMessage = {
    event_type,
    campaign_id: opts.campaign_id ?? null,
    agent_name: opts.agent_name ?? null,
    payload,
    timestamp: iso(now()),
    trace_id: uid(),
  };
  for (const l of listeners) l(message);
}

function touchAgent(name: string, client_id: string, depthDelta = 0) {
  const a = db.agents.find((x) => x.name === name);
  if (!a) return;
  a.queue_depth = Math.max(0, a.queue_depth + depthDelta);
  if (depthDelta <= 0) {
    a.last_decision_at = iso(now());
    db.decisions.push({
      id: uid(),
      agent_name: name,
      client_id,
      decision_type: AGENT_DISPATCH[name].task.split(".").pop()!,
      decision_data: { simulated: true },
      outcome: { status: "success" },
      created_at: a.last_decision_at,
    });
  }
}

function celery(task: string, type: string, agent: string, campaign_id: string | null, task_id: string) {
  emit(EventType.TASK_PROGRESS, { task_id, task_name: task, celery_event_type: type, hostname: `celery@worker-${AGENT_DISPATCH[agent]?.queue ?? "default"}` }, { agent_name: agent, campaign_id });
}

/** Exécute une tâche Celery simulée : received -> started -> succeeded. */
export function runAgentTask(agent: string, client_id: string, campaign_id: string | null, delay = 0): string {
  const task_id = uid();
  const task = AGENT_DISPATCH[agent].task;
  setTimeout(() => {
    touchAgent(agent, client_id, +1);
    celery(task, "task-received", agent, campaign_id, task_id);
    emit(EventType.AGENT_STATUS, { status: "running" }, { agent_name: agent, campaign_id });
  }, delay);
  setTimeout(() => celery(task, "task-started", agent, campaign_id, task_id), delay + 600);
  setTimeout(() => {
    touchAgent(agent, client_id, -1);
    celery(task, "task-succeeded", agent, campaign_id, task_id);
    emit(EventType.AGENT_STATUS, { status: "idle" }, { agent_name: agent, campaign_id });
    if (agent === "content" || agent === "creative") emit(EventType.CONTENT_STREAM, { generation_id: task_id, done: true }, { agent_name: agent, campaign_id });
  }, delay + 1800);
  return task_id;
}

// ── Exécution du graphe principal pour une campagne ─────────────────────────

function pushHistory(c: CampaignRow, step: string, next: string[], extra: Record<string, unknown> = {}) {
  c.history.unshift(
    snapshot(
      {
        campaign_id: c.id,
        client_id: c.client_id,
        objective: c.objective,
        budget_total: c.budget_total,
        budget_consumed: c.budget_consumed,
        channel_allocations: c.channel_allocations,
        current_step: step,
        ...extra,
      },
      next,
      now(),
    ),
  );
}

function step(c: CampaignRow, name: string, next: string[], extra?: Record<string, unknown>) {
  pushHistory(c, name, next, extra);
  emit(EventType.CAMPAIGN_UPDATE, { step: name, status: c.status }, { agent_name: "orchestrator", campaign_id: c.id });
}

function allocationsFromObjective(objective: string): Record<string, number> {
  const o = objective.toLowerCase();
  const w: Record<string, number> = { seo: 1, sea: 1, social: 1, email: 0.6 };
  if (/seo|référencement|google|recherche/.test(o)) w.seo += 1.2;
  if (/annonce|ads|sea|publicit/.test(o)) w.sea += 1.2;
  if (/linkedin|instagram|tiktok|facebook|réseau|social/.test(o)) w.social += 1.2;
  if (/mail|newsletter|fidélis/.test(o)) w.email += 1.2;
  const total = Object.values(w).reduce((s, v) => s + v, 0);
  return Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Math.round((v / total) * 100) / 100]));
}

export function createCampaign(input: { client_id: string; name: string; objective: string; budget_total: number; channel_allocations?: Record<string, number> }): Campaign {
  const c: CampaignRow = {
    id: uid(),
    client_id: input.client_id,
    name: input.name,
    objective: input.objective,
    budget_total: input.budget_total,
    budget_consumed: 0,
    status: "active",
    channel_allocations: input.channel_allocations ?? null,
    start_date: iso(now()),
    end_date: iso(now() + 30 * DAY),
    results: null,
    thread_id: uid(),
    history: [],
    hitl_payload: null,
  };
  db.campaigns.unshift(c);
  runGraph(c);
  return publicCampaign(c);
}

function runGraph(c: CampaignRow) {
  const T = 1400;
  let t = 300;
  const at = (fn: () => void) => {
    setTimeout(fn, t);
    t += T;
  };
  const r = hash(c.objective + c.id);
  const target = { nb_conversions: 100 + Math.round(r * 80), organic_traffic_growth: 0.2 };
  at(() => step(c, "parse_objective", ["plan_week"], { target_kpis: target }));
  at(() => {
    c.channel_allocations = c.channel_allocations ?? allocationsFromObjective(c.objective);
    step(c, "plan_week", ["route_to_cluster"], { week_plan: ["audit SEO", "annonces ciblées", "posts sociaux", "séquence e-mail"] });
  });
  at(() => step(c, "route_to_cluster", CLUSTERS.map((k) => k.node), { active_clusters: ["acquisition", "engagement", "measure"] }));
  for (const cluster of CLUSTERS) {
    at(() => {
      cluster.agents.forEach((a, i) => runAgentTask(a, c.client_id, c.id, i * 250));
      step(c, cluster.node, ["consolidate_results"]);
    });
  }
  at(() => {
    c.budget_consumed = Math.round(c.budget_total * (0.25 + r * 0.2));
    emit(EventType.BUDGET_UPDATE, { consumed: c.budget_consumed, total: c.budget_total, percentage: (c.budget_consumed / c.budget_total) * 100 }, { campaign_id: c.id });
    step(c, "consolidate_results", ["check_performance"]);
  });
  at(() => {
    // Règle réelle : écart > 50 % sur un KPI cible => HITL ; > 20 % => réallocation automatique.
    const gap = 0.3 + r * 0.55;
    const current = { nb_conversions: Math.round(target.nb_conversions * (1 - gap)) };
    const allocations = c.channel_allocations ?? {};
    const sorted = Object.entries(allocations).sort((a, b) => a[1] - b[1]);
    const under = sorted.slice(-1).map(([k]) => k);
    const over = sorted.slice(0, 2).map(([k]) => k);
    if (gap > 0.5) {
      c.status = "paused";
      c.hitl_payload = {
        proposal: {
          underperforming_channels: under,
          overperforming_channels: over,
          reasoning: `**Écart de ${Math.round(gap * 100)} %** entre les conversions cibles (${target.nb_conversions}) et mesurées (${current.nb_conversions}) : au-delà du seuil de 50 %, la réallocation proposée exige une validation humaine.\n\nProposition : déplacer **10 %** du budget de ${under.join(", ")} vers ${over.join(", ")}.`,
        },
        context: { client_id: c.client_id, campaign_id: c.id, budget_total: c.budget_total, budget_consumed: c.budget_consumed, channel_allocations: c.channel_allocations },
        options: ["resume", "stop", "modify"],
      };
      step(c, "check_performance", ["hitl_checkpoint"], { hitl_required: true, current_kpis: current, target_kpis: target });
      emit(EventType.HITL_INTERRUPT, c.hitl_payload, { agent_name: "orchestrator", campaign_id: c.id });
      emit(EventType.ALERT, { level: "warning", source: "orchestrator", message: `Validation requise : « ${c.name} »`, action_required: true }, { agent_name: "orchestrator", campaign_id: c.id });
    } else {
      const shifted = { ...allocations };
      if (under[0] && over[0]) {
        const delta = Math.round((shifted[under[0]] ?? 0) * 0.1 * 100) / 100;
        shifted[under[0]] = Math.round(((shifted[under[0]] ?? 0) - delta) * 100) / 100;
        shifted[over[0]] = Math.round(((shifted[over[0]] ?? 0) + delta) * 100) / 100;
      }
      c.channel_allocations = shifted;
      step(c, "check_performance", ["generate_report"], { hitl_required: false, reallocated: gap > 0.2, current_kpis: current, target_kpis: target });
      setTimeout(() => finish(c), T);
    }
  });
}

function finish(c: CampaignRow) {
  runAgentTask("reporting", c.client_id, c.id);
  setTimeout(() => {
    c.status = "completed";
    c.results = { report: "campaign", budget_consumed: c.budget_consumed };
    const report = buildWeeklyReport(c.client_id, 0);
    report.report_type = "campaign";
    report.period = c.name;
    db.reports.unshift(report);
    step(c, "generate_report", [], { report_id: report.id });
    emit(EventType.REPORT_READY, { report_id: report.id }, { agent_name: "reporting", campaign_id: c.id });
    emit(EventType.ALERT, { level: "info", source: "reporting", message: `Rapport disponible : « ${c.name} »`, action_required: false }, { agent_name: "reporting", campaign_id: c.id });
  }, 2200);
}

export function pendingHITL() {
  return db.campaigns
    .filter((c) => c.status === "paused" && c.thread_id && c.hitl_payload)
    .map((c) => ({ campaign_id: c.id, client_id: c.client_id, thread_id: c.thread_id!, payload: c.hitl_payload }));
}

/** Équivalent de `_resume_with_response` (routes/hitl.py). */
export function resolveHITL(campaign_id: string, response: Record<string, unknown>): boolean {
  const c = db.campaigns.find((x) => x.id === campaign_id);
  if (!c || c.status !== "paused" || !c.thread_id) return false;
  c.status = "active";
  c.hitl_payload = null;
  pushHistory(c, "hitl_checkpoint", response.action === "stop" ? [] : ["generate_report"], { hitl_response: response, hitl_required: false });
  setTimeout(() => emit(EventType.HITL_RESOLVED, response, { agent_name: "orchestrator", campaign_id }), 500);
  if (response.action === "stop") {
    setTimeout(() => {
      c.status = "completed";
      c.results = { stopped_by_human: true, comment: response.comment ?? null };
      step(c, "end", []);
    }, 1500);
  } else {
    if (response.action === "modify") {
      const mods = (response.modifications ?? {}) as Record<string, unknown>;
      if (mods.channel_allocations && typeof mods.channel_allocations === "object") c.channel_allocations = mods.channel_allocations as Record<string, number>;
      if (typeof mods.budget_total === "number") c.budget_total = mods.budget_total;
    }
    setTimeout(() => finish(c), 1200);
  }
  return true;
}

export function pauseCampaign(id: string): Campaign | undefined {
  const c = db.campaigns.find((x) => x.id === id);
  if (!c) return undefined;
  c.status = "paused";
  return publicCampaign(c);
}

export function resumeCampaign(id: string, hitl: Record<string, unknown>): Campaign | undefined {
  const c = db.campaigns.find((x) => x.id === id);
  if (!c) return undefined;
  if (c.hitl_payload) resolveHITL(id, hitl);
  else c.status = "active";
  return publicCampaign(c);
}

export function campaignRow(id: string): CampaignRow | undefined {
  return db.campaigns.find((x) => x.id === id);
}

// ── Activité de fond (Celery Beat simulé) ───────────────────────────────────

let tickerStarted = false;
export function startBackgroundActivity(): void {
  if (tickerStarted) return;
  tickerStarted = true;
  let i = 0;
  const tick = () => {
    const job = SCHEDULED_TASKS[i % SCHEDULED_TASKS.length];
    i++;
    const task_id = uid();
    const clientId = i % 3 === 0 ? C2 : C1;
    celery(job.task, "task-received", job.agent, null, task_id);
    setTimeout(() => celery(job.task, "task-started", job.agent, null, task_id), 700);
    setTimeout(() => {
      celery(job.task, "task-succeeded", job.agent, null, task_id);
      touchAgent(job.agent, clientId);
    }, 1900);
    for (const a of db.agents) a.queue_depth = Math.max(0, Math.min(9, a.queue_depth + Math.round(Math.random() * 2 - 1)));
    if (i % 5 === 0) {
      emit(EventType.ALERT, { level: "info", source: "sea", message: "Enchères SEA ajustées sur les requêtes génériques (simulation).", action_required: false }, { agent_name: "sea" });
    }
    setTimeout(tick, 5000 + Math.random() * 3000);
  };
  setTimeout(tick, 1500);
}

export const DEMO_CLIENT_IDS = { C1, C2 };

seed();
