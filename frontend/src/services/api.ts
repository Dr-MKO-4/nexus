/**
 * Client API centralisé  Prompt 8.1.
 *
 * Chaque fonction ci-dessous cible un endpoint RÉEL de backend/api/routes/*
 * (Prompts 7.1/7.2)  méthode HTTP, forme du corps et query params vérifiés
 * contre le code backend, pas devinés.
 */

import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import type {
  Agent,
  Anomaly,
  Campaign,
  CampaignHistorySnapshot,
  CampaignStatus,
  ChannelAllocation,
  ChannelPerformance,
  ClientDetail,
  ClientSummary,
  Content,
  ContentStatus,
  ContentType,
  HITLRequest,
  KPIMetric,
  Report,
  ReportDetail,
  User,
  UserRole as UserRoleValue,
} from "@/types";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokenStorage";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({ baseURL: API_BASE_URL });

// ── Intercepteur de requête : injection du JWT ──────────────────────────────

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

// ── Intercepteur de réponse : refresh automatique sur 401 ──────────────────
//
// `_retry` (propriété ad hoc sur la config, pas un champ standard d'axios) :
// évite une boucle infinie si le refresh lui-même échoue avec un 401 (sinon
// la requête de refresh échouée redéclenche l'intercepteur indéfiniment).
// `_refreshPromise` module-level : dédoublonne les refresh concurrents 
// plusieurs requêtes en 401 simultanément ne déclenchent qu'UN SEUL appel
// à /auth/refresh, les autres attendent la même promesse.

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

let _refreshPromise: Promise<string> | null = null;

async function _refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error("Aucun refresh token disponible.");
  }
  const response = await axios.post<{ access_token: string; token_type: string }>(
    `${API_BASE_URL}/auth/refresh`,
    { refresh_token: refreshToken },
  );
  setTokens(response.data.access_token);
  return response.data.access_token;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetryableConfig | undefined;
    const isAuthEndpoint = config?.url?.includes("/auth/login") || config?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && config && !config._retry && !isAuthEndpoint) {
      config._retry = true;
      try {
        _refreshPromise ??= _refreshAccessToken().finally(() => {
          _refreshPromise = null;
        });
        const newAccessToken = await _refreshPromise;
        config.headers.set("Authorization", `Bearer ${newAccessToken}`);
        return apiClient(config);
      } catch (refreshError) {
        clearTokens();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);

// ── Auth (backend/api/auth.py) ──────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  // OAuth2PasswordRequestForm (backend) exige un corps form-urlencoded avec
  // les champs `username`/`password`  PAS du JSON, contrainte imposée par
  // `OAuth2PasswordBearer`/la compatibilité Swagger UI (voir auth.py).
  const body = new URLSearchParams({ username: email, password });
  const response = await axios.post<TokenResponse>(`${API_BASE_URL}/auth/login`, body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  setTokens(response.data.access_token, response.data.refresh_token);
  return response.data;
}

export async function refreshToken(): Promise<string> {
  return _refreshAccessToken();
}

export async function getMe(): Promise<User> {
  const response = await apiClient.get<User>("/auth/me");
  return response.data;
}

// ── Campaigns (backend/api/routes/campaigns.py) ─────────────────────────────

export interface CreateCampaignPayload {
  client_id: string;
  name: string;
  objective: string;
  budget_total: number;
  channel_allocations?: ChannelAllocation;
  start_date?: string;
  end_date?: string;
}

export async function createCampaign(payload: CreateCampaignPayload): Promise<Campaign> {
  const response = await apiClient.post<Campaign>("/campaigns", payload);
  return response.data;
}

export async function getCampaigns(clientId: string, params?: { limit?: number; offset?: number }): Promise<Campaign[]> {
  const response = await apiClient.get<Campaign[]>("/campaigns", { params: { client_id: clientId, ...params } });
  return response.data;
}

export async function getCampaign(id: string): Promise<Campaign> {
  const response = await apiClient.get<Campaign>(`/campaigns/${id}`);
  return response.data;
}

export async function pauseCampaign(id: string): Promise<Campaign> {
  const response = await apiClient.post<Campaign>(`/campaigns/${id}/pause`);
  return response.data;
}

export async function resumeCampaign(id: string, hitlResponse: Record<string, unknown>): Promise<Campaign> {
  const response = await apiClient.post<Campaign>(`/campaigns/${id}/resume`, { hitl_response: hitlResponse });
  return response.data;
}

export interface UpdateCampaignPayload {
  name?: string;
  objective?: string;
  budget_total?: number;
  channel_allocations?: ChannelAllocation;
  start_date?: string;
  end_date?: string;
}

export async function updateCampaign(id: string, payload: UpdateCampaignPayload): Promise<Campaign> {
  const response = await apiClient.patch<Campaign>(`/campaigns/${id}`, payload);
  return response.data;
}

export async function archiveCampaign(id: string): Promise<void> {
  await apiClient.delete(`/campaigns/${id}`);
}

export async function getCampaignHistory(id: string): Promise<CampaignHistorySnapshot[]> {
  const response = await apiClient.get<CampaignHistorySnapshot[]>(`/campaigns/${id}/history`);
  return response.data;
}

export type { CampaignStatus };

// ── Agents (backend/api/routes/agents.py) ───────────────────────────────────

export async function getAgents(): Promise<Agent[]> {
  const response = await apiClient.get<Agent[]>("/agents");
  return response.data;
}

export async function getAgentStatus(name: string): Promise<Agent> {
  const response = await apiClient.get<Agent>(`/agents/${name}/status`);
  return response.data;
}

export interface TriggerAgentResult {
  task_id: string;
  agent_name: string;
  queue: string;
}

export async function triggerAgent(name: string, payload: Record<string, unknown>): Promise<TriggerAgentResult> {
  const response = await apiClient.post<TriggerAgentResult>(`/agents/${name}/trigger`, payload);
  return response.data;
}

export interface AgentLogEntry {
  id: string;
  client_id: string;
  decision_type: string;
  decision_data: Record<string, unknown>;
  outcome: Record<string, unknown> | null;
  created_at: string;
}

/** Ajouté au-delà de la liste explicite du spec 8.1 (qui ne nommait pas
 * cette fonction) : Prompt 8.2 (AgentControl.tsx, "dernières 5 actions")
 * en a réellement besoin, et l'endpoint existe déjà côté backend
 * (GET /agents/{name}/logs, Prompt 7.1)  sans cette fonction, cette partie
 * du spec 8.2 serait irréalisable avec de vraies données. */
export async function getAgentLogs(name: string, limit = 5): Promise<AgentLogEntry[]> {
  const response = await apiClient.get<AgentLogEntry[]>(`/agents/${name}/logs`, { params: { limit } });
  return response.data;
}

// ── HITL (backend/api/routes/hitl.py) ───────────────────────────────────────

export async function getPendingValidations(): Promise<HITLRequest[]> {
  const response = await apiClient.get<HITLRequest[]>("/hitl/pending");
  return response.data;
}

export async function approveHITL(campaignId: string): Promise<{ status: string }> {
  const response = await apiClient.post<{ status: string }>(`/hitl/${campaignId}/approve`);
  return response.data;
}

export async function rejectHITL(campaignId: string, comment: string): Promise<{ status: string }> {
  const response = await apiClient.post<{ status: string }>(`/hitl/${campaignId}/reject`, { comment });
  return response.data;
}

export async function modifyHITL(campaignId: string, modifications: Record<string, unknown>): Promise<{ status: string }> {
  const response = await apiClient.post<{ status: string }>(`/hitl/${campaignId}/modify`, { modifications });
  return response.data;
}

// ── Content (backend/api/routes/content.py) ─────────────────────────────────

export interface GetContentsParams {
  client_id: string;
  content_type?: ContentType;
  status?: ContentStatus;
  limit?: number;
  offset?: number;
}

export async function getContents(params: GetContentsParams): Promise<Content[]> {
  const response = await apiClient.get<Content[]>("/contents", { params });
  return response.data;
}

export async function getContent(id: string): Promise<Content> {
  const response = await apiClient.get<Content>(`/contents/${id}`);
  return response.data;
}

export async function publishContent(id: string): Promise<Content> {
  const response = await apiClient.post<Content>(`/contents/${id}/publish`);
  return response.data;
}

/** Ajouté au-delà de la liste explicite du spec 8.1 : Prompt 8.2
 * (ContentManagement.tsx, onglet "Bibliothèque"  "modifier"/"archiver")
 * en a besoin ; l'endpoint PATCH /contents/{id} existe déjà (Prompt 7.1).
 * "Archiver" est un cas particulier de cette même fonction (status="archived"),
 * pas un endpoint séparé  Content n'a pas de DELETE dédié comme Campaign. */
export async function updateContent(id: string, patch: { title?: string; body?: string; status?: ContentStatus }): Promise<Content> {
  const response = await apiClient.patch<Content>(`/contents/${id}`, patch);
  return response.data;
}

/** Ajouté au-delà de la liste explicite du spec 8.1 : requis par l'onglet
 * "Calendrier" (drag & drop pour reprogrammer)  POST /contents/{id}/schedule
 * (Prompt 7.1). */
export async function scheduleContent(id: string, scheduledAt: string): Promise<Content> {
  const response = await apiClient.post<Content>(`/contents/${id}/schedule`, { scheduled_at: scheduledAt });
  return response.data;
}

/**
 * `GET /contents/calendar` (backend/api/routes/content.py) exige
 * `client_id`/`start`/`end` (bornes ISO 8601 explicites), PAS un `month`
 * (aucun paramètre de ce type côté backend)  le spec 8.1 nomme ce hook
 * "useCalendar(month)" côté React Query (voir hooks/useCalendar.ts) : c'est
 * CE hook qui traduit un mois en bornes `start`/`end`, pas cette fonction
 * API, qui reste un miroir fidèle du endpoint réel.
 */
export async function getCalendar(clientId: string, start: string, end: string): Promise<Content[]> {
  const response = await apiClient.get<Content[]>("/contents/calendar", { params: { client_id: clientId, start, end } });
  return response.data;
}

// ── Analytics (backend/api/routes/analytics.py) ─────────────────────────────

export interface GetKPIsParams {
  client_id: string;
  period_start?: string;
  period_end?: string;
}

export async function getKPIs(params: GetKPIsParams): Promise<KPIMetric[]> {
  const response = await apiClient.get<KPIMetric[]>("/analytics/kpis", { params });
  return response.data;
}

export async function getChannelPerformance(params: GetKPIsParams): Promise<ChannelPerformance[]> {
  const response = await apiClient.get<ChannelPerformance[]>("/analytics/channels", { params });
  return response.data;
}

export async function getReports(clientId: string, reportType?: string): Promise<Report[]> {
  const response = await apiClient.get<Report[]>("/analytics/reports", { params: { client_id: clientId, report_type: reportType } });
  return response.data;
}

export async function getReportDetail(reportId: string): Promise<ReportDetail> {
  const response = await apiClient.get<ReportDetail>(`/analytics/reports/${reportId}`);
  return response.data;
}

export async function getAnomalies(clientId: string, params?: { since?: string; limit?: number }): Promise<Anomaly[]> {
  const response = await apiClient.get<Anomaly[]>("/analytics/anomalies", { params: { client_id: clientId, ...params } });
  return response.data;
}

// ── Settings / statut LLM (backend/api/routes/settings.py) ──────────────────
//
// Ajouté suite à un audit : Settings.tsx affichait un statut de providers
// CODÉ EN DUR (aucun endpoint backend correspondant)  voir settings.py
// pour le détail de ce qui est réellement vérifiable ("configured" = clé
// API présente) vs testable à la demande (un vrai appel litellm).

export interface ProviderStatus {
  name: string;
  configured: boolean;
  default_model: string;
}

export interface ProviderTestResult {
  name: string;
  success: boolean;
  latency_ms: number | null;
  error: string | null;
}

export async function getProviderStatus(): Promise<ProviderStatus[]> {
  const response = await apiClient.get<ProviderStatus[]>("/settings/llm/providers");
  return response.data;
}

export async function testProvider(name: string): Promise<ProviderTestResult> {
  const response = await apiClient.post<ProviderTestResult>(`/settings/llm/providers/${name}/test`);
  return response.data;
}

// ── Users (backend/api/routes/users.py) ─────────────────────────────────────
//
// Ajouté suite à un audit : Settings.tsx (section "Utilisateurs") gérait une
// liste en useState LOCAL, aucun appel réseau, rien persisté.

export interface CreateUserPayload {
  email: string;
  role: UserRoleValue;
  client_id?: string | null;
}

export interface CreateUserResult {
  user: User;
  temporary_password: string;
}

export async function getUsers(clientId?: string): Promise<User[]> {
  const response = await apiClient.get<User[]>("/users", { params: clientId ? { client_id: clientId } : undefined });
  return response.data;
}

export async function createUser(payload: CreateUserPayload): Promise<CreateUserResult> {
  const response = await apiClient.post<CreateUserResult>("/users", payload);
  return response.data;
}

export async function updateUser(id: string, payload: { role?: UserRoleValue; is_active?: boolean }): Promise<User> {
  const response = await apiClient.patch<User>(`/users/${id}`, payload);
  return response.data;
}

// ── Clients (backend/api/routes/clients.py) ─────────────────────────────────
//
// Ajouté suite à un audit : aucun endpoint "lister les clients" n'existait,
// donc un compte ADMIN (client_id NULL) ne pouvait rien afficher ; et
// Settings.tsx ("Marque client"/"Intégrations") gérait ces sections en
// useState LOCAL alors que les colonnes existaient déjà en base.

export async function getClients(): Promise<ClientSummary[]> {
  const response = await apiClient.get<ClientSummary[]>("/clients");
  return response.data;
}

export async function getClientDetail(clientId: string): Promise<ClientDetail> {
  const response = await apiClient.get<ClientDetail>(`/clients/${clientId}`);
  return response.data;
}

export interface UpdateClientBrandPayload {
  editorial_guidelines?: Record<string, unknown> | null;
  brand_colors?: Record<string, string> | null;
  logo_url?: string | null;
  forbidden_topics?: string[] | null;
}

export async function updateClientBrand(clientId: string, payload: UpdateClientBrandPayload): Promise<ClientDetail> {
  const response = await apiClient.patch<ClientDetail>(`/clients/${clientId}/brand`, payload);
  return response.data;
}

export async function updateClientIntegrations(clientId: string, integrations: Record<string, unknown>): Promise<ClientDetail> {
  const response = await apiClient.patch<ClientDetail>(`/clients/${clientId}/integrations`, { integrations });
  return response.data;
}
