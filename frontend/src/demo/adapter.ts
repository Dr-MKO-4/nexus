/**
 * Adaptateur axios de la démo : remplace le transport HTTP et sert les
 * mêmes routes que backend/api/routes/* à partir du moteur en mémoire.
 * Aucune requête réseau n'est émise.
 */
import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";

import * as engine from "./engine";
import type { ClientSummary, ContentStatus } from "@/types";

const ADMIN_ROLES = ["admin", "manager"];
const EMAIL_KEY = "nexus_demo_email";
let currentEmail = (() => {
  try {
    return sessionStorage.getItem(EMAIL_KEY) ?? "admin@exemple.org";
  } catch {
    return "admin@exemple.org";
  }
})();
function rememberEmail(email: string) {
  currentEmail = email;
  try {
    sessionStorage.setItem(EMAIL_KEY, email);
  } catch {
    /* stockage indisponible : sans effet */
  }
}

function b64url(obj: unknown): string {
  return btoa(unescape(encodeURIComponent(JSON.stringify(obj)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Jeton factice au format JWT (non signé), uniquement pour que le code
 * existant (tokenStorage, websocket.ts) fonctionne sans modification. */
export function fakeToken(email: string): string {
  const user = engine.db.users.find((u) => u.email === email) ?? engine.db.users[0];
  return `${b64url({ alg: "none", typ: "JWT" })}.${b64url({ sub: user.id, email: user.email, client_id: user.client_id, demo: true })}.demo`;
}

function me() {
  return engine.db.users.find((u) => u.email === currentEmail) ?? engine.db.users[0];
}

function body(config: InternalAxiosRequestConfig): Record<string, unknown> {
  const d = config.data;
  if (!d) return {};
  if (typeof d === "string") {
    try {
      return JSON.parse(d);
    } catch {
      return Object.fromEntries(new URLSearchParams(d));
    }
  }
  if (d instanceof URLSearchParams) return Object.fromEntries(d);
  return d as Record<string, unknown>;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function ok(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: "OK", headers: new AxiosHeaders({ "content-type": "application/json" }), config, request: {} };
}

function fail(config: InternalAxiosRequestConfig, status: number, detail: string): never {
  const response = { data: { detail }, status, statusText: String(status), headers: new AxiosHeaders(), config, request: {} };
  throw new AxiosError(detail, status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST, config, {}, response);
}

function pathOf(config: InternalAxiosRequestConfig): string {
  let url = config.url ?? "";
  url = url.replace(/^https?:\/\/[^/]+/, "");
  const base = (config.baseURL ?? "").replace(/^https?:\/\/[^/]+/, "");
  if (base && url.startsWith(base)) url = url.slice(base.length);
  url = url.replace(/^\/api(?=\/)/, "");
  return url.split("?")[0] || "/";
}

function requireMutate(config: InternalAxiosRequestConfig) {
  if (!ADMIN_ROLES.includes(me().role)) fail(config, 403, "Rôle insuffisant (admin ou manager requis).");
}

export const demoAdapter: AxiosAdapter = async (config) => {
  await delay(120 + Math.random() * 220);
  const method = (config.method ?? "get").toLowerCase();
  const path = pathOf(config);
  const params = (config.params ?? {}) as Record<string, string | undefined>;
  const seg = path.split("/").filter(Boolean);
  const data = body(config);

  // ── Auth
  if (path === "/auth/login" && method === "post") {
    const email = String(data.username ?? "").trim().toLowerCase();
    const user = engine.db.users.find((u) => u.email === email);
    if (!user || !user.is_active || !String(data.password ?? "")) fail(config, 401, "Identifiants invalides.");
    rememberEmail(user.email);
    return ok(config, { access_token: fakeToken(user.email), refresh_token: "demo-refresh", token_type: "bearer" });
  }
  if (path === "/auth/refresh") return ok(config, { access_token: fakeToken(currentEmail), token_type: "bearer" });
  if (path === "/auth/me") return ok(config, me());

  // ── Campaigns
  if (seg[0] === "campaigns") {
    if (seg.length === 1 && method === "get") {
      const list = engine.db.campaigns.filter((c) => c.client_id === params.client_id && c.status !== "archived").map(engine.publicCampaign);
      return ok(config, list);
    }
    if (seg.length === 1 && method === "post") {
      requireMutate(config);
      return ok(config, engine.createCampaign(data as never), 201);
    }
    const c = engine.campaignRow(seg[1]);
    if (!c) fail(config, 404, "Campagne introuvable.");
    if (seg.length === 2 && method === "get") return ok(config, engine.publicCampaign(c));
    if (seg.length === 2 && method === "patch") {
      requireMutate(config);
      Object.assign(c, data);
      return ok(config, engine.publicCampaign(c));
    }
    if (seg.length === 2 && method === "delete") {
      requireMutate(config);
      c.status = "archived";
      return ok(config, null, 204);
    }
    if (seg[2] === "history") return ok(config, c.history);
    if (seg[2] === "pause") return ok(config, engine.pauseCampaign(c.id));
    if (seg[2] === "resume") return ok(config, engine.resumeCampaign(c.id, (data.hitl_response as Record<string, unknown>) ?? { action: "resume" }));
  }

  // ── Agents
  if (seg[0] === "agents") {
    if (seg.length === 1) return ok(config, engine.getAgents());
    const agent = engine.getAgents().find((a) => a.name === seg[1]);
    if (!agent) fail(config, 404, `Agent inconnu : ${seg[1]}`);
    if (seg[2] === "status") return ok(config, agent);
    if (seg[2] === "logs") {
      requireMutate(config);
      return ok(config, engine.getAgentLogs(agent.name, Number(params.limit ?? 5)));
    }
    if (seg[2] === "trigger") {
      requireMutate(config);
      const missing = agent.name === "reporting" ? [] : agent.expected_trigger_kwargs.filter((k) => !(k in data));
      if (missing.length) fail(config, 400, `Payload invalide pour l'agent '${agent.name}' (attendu : ${JSON.stringify(agent.expected_trigger_kwargs)}) : argument(s) manquant(s) ${missing.join(", ")}`);
      const clientId = (data.client_id as string) ?? engine.DEMO_CLIENT_IDS.C1;
      const task_id = engine.runAgentTask(agent.name, clientId, (data.campaign_id as string) ?? null);
      return ok(config, { task_id, agent_name: agent.name, queue: agent.queue }, 202);
    }
  }

  // ── HITL
  if (seg[0] === "hitl") {
    if (seg[1] === "pending") {
      const user = me();
      return ok(config, engine.pendingHITL().filter((h) => user.role === "admin" || h.client_id === user.client_id));
    }
    requireMutate(config);
    const id = seg[1];
    const action = seg[2];
    const response =
      action === "approve" ? { action: "resume" } : action === "reject" ? { action: "stop", comment: data.comment ?? "" } : { action: "modify", modifications: data.modifications ?? {} };
    if (!engine.resolveHITL(id, response)) fail(config, 404, "Aucune validation en attente pour cet identifiant.");
    return ok(config, { status: action === "approve" ? "resuming" : action === "reject" ? "stopping" : "resuming_with_modifications" }, 202);
  }

  // ── Contents
  if (seg[0] === "contents") {
    if (seg[1] === "calendar") {
      const start = params.start ? new Date(params.start).getTime() : 0;
      const end = params.end ? new Date(params.end).getTime() : Infinity;
      return ok(
        config,
        engine.db.contents.filter((c) => {
          const d = c.scheduled_at ?? c.published_at;
          if (c.client_id !== params.client_id || !d) return false;
          const t = new Date(d).getTime();
          return t >= start && t <= end;
        }),
      );
    }
    if (seg.length === 1) {
      return ok(
        config,
        engine.db.contents.filter(
          (c) => c.client_id === params.client_id && (!params.content_type || c.content_type === params.content_type) && (!params.status || c.status === params.status),
        ),
      );
    }
    const content = engine.db.contents.find((c) => c.id === seg[1]);
    if (!content) fail(config, 404, "Contenu introuvable.");
    if (seg.length === 2 && method === "get") return ok(config, content);
    requireMutate(config);
    if (seg.length === 2 && method === "patch") {
      Object.assign(content, data as { title?: string; body?: string; status?: ContentStatus });
      return ok(config, content);
    }
    if (seg[2] === "publish") {
      Object.assign(content, { status: "published", published_at: new Date().toISOString(), scheduled_at: null, performance_data: { views: 0, clicks: 0 } });
      return ok(config, content);
    }
    if (seg[2] === "schedule") {
      content.scheduled_at = String(data.scheduled_at);
      return ok(config, content);
    }
  }

  // ── Analytics
  if (seg[0] === "analytics") {
    const clientId = params.client_id ?? "";
    if (seg[1] === "kpis") return ok(config, engine.getKPIs(clientId, params.period_end));
    if (seg[1] === "channels") return ok(config, engine.getChannels(clientId));
    if (seg[1] === "anomalies") return ok(config, engine.getAnomalies(clientId));
    if (seg[1] === "reports" && seg.length === 2) {
      return ok(
        config,
        engine.db.reports
          .filter((r) => r.client_id === clientId && (!params.report_type || r.report_type === params.report_type))
          .map(({ content: _c, ...r }) => r),
      );
    }
    if (seg[1] === "reports" && seg[2]) {
      const r = engine.getReportDetail(seg[2]);
      if (!r) fail(config, 404, "Rapport introuvable.");
      return ok(config, r);
    }
  }

  // ── Settings / providers (backend/api/routes/settings.py: _PROVIDERS)
  if (seg[0] === "settings" && seg[1] === "llm") {
    const providers = [
      { name: "groq", configured: true, default_model: "groq/llama-3.3-70b-versatile" },
      { name: "together_ai", configured: true, default_model: "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo" },
      { name: "fireworks_ai", configured: false, default_model: "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct" },
      { name: "mistral", configured: true, default_model: "mistral/mistral-large-latest" },
    ];
    if (seg.length === 3) return ok(config, providers);
    if (seg[4] === "test") {
      requireMutate(config);
      const p = providers.find((x) => x.name === seg[3]);
      if (!p) fail(config, 404, `Provider inconnu : '${seg[3]}'`);
      await delay(500);
      return ok(config, { name: p.name, success: p.configured, latency_ms: null, error: "Démo : test simulé, aucun appel réel au fournisseur LLM." });
    }
  }

  // ── Users
  if (seg[0] === "users") {
    requireMutate(config);
    if (seg.length === 1 && method === "get") {
      return ok(config, engine.db.users.filter((u) => !params.client_id || u.client_id === params.client_id));
    }
    if (seg.length === 1 && method === "post") {
      const email = String(data.email ?? "").toLowerCase();
      if (!email.endsWith("@exemple.org") && !email.includes(".exemple.org")) fail(config, 400, "Démo : utilisez une adresse en @exemple.org.");
      if (engine.db.users.some((u) => u.email === email)) fail(config, 409, "Un utilisateur avec cet e-mail existe déjà.");
      const user = { id: engine.uid(), email, role: data.role as "admin" | "manager" | "viewer", client_id: (data.client_id as string | null) ?? null, is_active: true };
      engine.db.users.push(user);
      return ok(config, { user, temporary_password: `demo-${Math.random().toString(36).slice(2, 10)}` }, 201);
    }
    const user = engine.db.users.find((u) => u.id === seg[1]);
    if (!user) fail(config, 404, "Utilisateur introuvable.");
    Object.assign(user, data);
    return ok(config, user);
  }

  // ── Clients
  if (seg[0] === "clients") {
    if (seg.length === 1) {
      return ok(config, engine.db.clients.map(({ id, name, industry, website }): ClientSummary => ({ id, name, industry, website })));
    }
    const client = engine.db.clients.find((c) => c.id === seg[1]);
    if (!client) fail(config, 404, "Client introuvable.");
    if (seg.length === 2) return ok(config, client);
    requireMutate(config);
    if (seg[2] === "brand") Object.assign(client, data);
    if (seg[2] === "integrations") client.integrations = { ...(client.integrations ?? {}), ...((data.integrations as Record<string, unknown>) ?? {}) };
    return ok(config, client);
  }

  return fail(config, 404, `Route non simulée dans la démo : ${method.toUpperCase()} ${path}`);
};

export function setDemoUser(email: string) {
  rememberEmail(email);
}
