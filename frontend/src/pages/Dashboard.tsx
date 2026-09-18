import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AgentCard, AlertBanner, EmptyState, LoadingState, MetricCard, Progress } from "@/components/ui";
import { useActiveClientId, useAgents, useCampaigns, useKPIs, useWebSocket } from "@/hooks";
import { useAlertStore } from "@/store";
import { EventType, type KPIMetric } from "@/types";

/**
 * "trafic organique, leads, conversions, ROAS" (spec) : miroir des KPIs
 * RÉELLEMENT calculés par l'Agent Analytics (backend/agents/analytics/
 * nodes.py: compute_kpis_node)  `organic_traffic_growth`, `nb_conversions`,
 * `roas` existent tels quels ; AUCUN metric_name "leads" n'existe dans ce
 * backend. `goal_count` (complétions d'objectifs Matomo) est le proxy réel
 * le plus proche d'un concept de "leads" dans ce projet  substitué ici
 * plutôt qu'inventé un champ qui n'existe pas côté serveur.
 */
const CARD_METRICS: { key: string; label: string }[] = [
  { key: "organic_traffic_growth", label: "Trafic organique (croissance)" },
  { key: "goal_count", label: "Leads (objectifs atteints)" },
  { key: "nb_conversions", label: "Conversions" },
  { key: "roas", label: "ROAS" },
];

function findMetric(metrics: KPIMetric[] | undefined, name: string): number | undefined {
  return metrics?.find((m) => m.metric_name === name)?.metric_value;
}

function variationPct(current: number | undefined, previous: number | undefined): number | undefined {
  if (current === undefined || previous === undefined || previous === 0) return undefined;
  return ((current - previous) / Math.abs(previous)) * 100;
}

// Données simulées  AUCUN endpoint backend n'expose une série quotidienne
// de trafic sur 30 jours (PerformanceMetric n'est écrit qu'une fois par run
// de l'Agent Analytics, avec une fenêtre de 7 jours agrégée  voir
// store_metrics_node  jamais un point par jour calendaire). Affiché avec un
// libellé explicite plutôt que de prétendre à une vraie série temporelle.
const MOCK_TRAFFIC_SERIES = Array.from({ length: 30 }, (_, i) => ({
  day: `J-${29 - i}`,
  visits: Math.round(400 + Math.sin(i / 3) * 120 + i * 6),
}));

export default function Dashboard() {
  const clientId = useActiveClientId();
  const now = useMemo(() => new Date(), []);
  const weekAgo = useMemo(() => new Date(now.getTime() - 7 * 86_400_000), [now]);
  const twoWeeksAgo = useMemo(() => new Date(now.getTime() - 14 * 86_400_000), [now]);

  const currentWeek = useKPIs(clientId ?? undefined, { start: weekAgo.toISOString(), end: now.toISOString() });
  const previousWeek = useKPIs(clientId ?? undefined, { start: twoWeeksAgo.toISOString(), end: weekAgo.toISOString() });
  const campaigns = useCampaigns(clientId ?? undefined);
  const agents = useAgents();
  // BUG RÉEL corrigé (trouvé par un vrai test navigateur headless, pas par
  // tsc/eslint) : sélectionner `s.alerts.filter(...)` directement dans le
  // sélecteur Zustand crée un nouveau tableau à CHAQUE rendu  Zustand
  // compare par référence (Object.is), voit donc "un changement" à chaque
  // fois, et force un re-rendu, qui refait tourner le sélecteur, qui crée
  // un nouveau tableau... boucle infinie ("Maximum update depth exceeded",
  // React error #185, reproduit tel quel dans un vrai navigateur avant ce
  // correctif). Fix : sélectionner la référence stable `alerts` telle
  // qu'elle vit dans le store, filtrer dans un `useMemo` côté composant.
  const rawAlerts = useAlertStore((s) => s.alerts);
  const alerts = useMemo(() => rawAlerts.filter((a) => !a.read), [rawAlerts]);
  const queryClient = useQueryClient();

  // Spec : "Toutes les données via React Query + WebSocket pour les
  // statuts agents"  AGENT_STATUS ne pousse qu'un {agent_name, status}
  // partiel (voir agent_broadcaster.py), pas un Agent complet : plus sûr
  // d'invalider le cache React Query (re-fetch la forme exacte de l'API)
  // que de fusionner un payload partiel dans un type strict.
  //
  // Limite réelle (vérifiée) : aucun code backend n'appelle jamais
  // `AgentBroadcaster.broadcast_agent_status_change` à ce jour (recherche
  // exhaustive dans backend/, aucun résultat en dehors de sa définition) 
  // cet abonnement ne recevra donc jamais d'événement en pratique tant
  // qu'un point d'appel n'est pas ajouté côté backend ; le rafraîchissement
  // réel de cette section vient du polling 5s de `useAgents()`.
  useWebSocket(
    EventType.AGENT_STATUS,
    useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }, [queryClient]),
  );

  const activeCampaigns = useMemo(() => campaigns.data?.filter((c) => c.status === "active") ?? [], [campaigns.data]);

  const channelBudgetData = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const campaign of activeCampaigns) {
      const allocations = campaign.channel_allocations ?? {};
      for (const [channel, ratio] of Object.entries(allocations)) {
        totals[channel] = (totals[channel] ?? 0) + ratio * campaign.budget_total;
      }
    }
    return Object.entries(totals).map(([channel, budget]) => ({ channel, budget: Math.round(budget) }));
  }, [activeCampaigns]);

  if (!clientId) {
    return <EmptyState message="Aucun client actif  les comptes admin doivent sélectionner un client (sélecteur non disponible : aucun endpoint de liste des clients n'existe côté backend)." />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Tableau de bord</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CARD_METRICS.map(({ key, label }) => {
          const value = findMetric(currentWeek.data, key);
          const previous = findMetric(previousWeek.data, key);
          return (
            <MetricCard
              key={key}
              label={label}
              value={value !== undefined ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : ""}
              variation={variationPct(value, previous)}
              trend={variationPct(value, previous) === undefined ? undefined : (variationPct(value, previous)! >= 0 ? "up" : "down")}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
          <h2 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Objectif de la semaine</h2>
          {activeCampaigns.length === 0 ? (
            <EmptyState message="Aucune campagne active." />
          ) : (
            <ul className="space-y-3">
              {activeCampaigns.map((campaign) => {
                const pct = campaign.budget_total > 0 ? Math.min(100, (campaign.budget_consumed / campaign.budget_total) * 100) : 0;
                return (
                  <li key={campaign.id}>
                    <p className="text-sm font-medium text-neutral-800 dark:text-neutral-200">{campaign.name}</p>
                    <p className="mb-1 text-xs text-neutral-500">{campaign.objective}</p>
                    <Progress value={pct} />
                    <p className="mt-1 text-xs text-neutral-400">
                      {campaign.budget_consumed.toLocaleString()} / {campaign.budget_total.toLocaleString()} € ({pct.toFixed(0)}%)
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
          <h2 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Budget (allocation planifiée)</h2>
          {channelBudgetData.length === 0 ? (
            <EmptyState message="Aucune allocation de budget disponible." />
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <RadialBarChart
                  data={channelBudgetData}
                  innerRadius="20%"
                  outerRadius="90%"
                  startAngle={180}
                  endAngle={-180}
                >
                  <PolarAngleAxis type="number" domain={[0, Math.max(...channelBudgetData.map((d) => d.budget), 1)]} tick={false} />
                  <RadialBar dataKey="budget" background cornerRadius={4} />
                  <Legend />
                  <Tooltip />
                </RadialBarChart>
              </ResponsiveContainer>
              <p className="mt-1 text-center text-sm font-semibold text-neutral-700 dark:text-neutral-300">
                Total : {channelBudgetData.reduce((sum, d) => sum + d.budget, 0).toLocaleString()} €
              </p>
            </>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Répartition du budget par canal</h2>
        {channelBudgetData.length === 0 ? (
          <EmptyState message="Aucune allocation de budget disponible." />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={channelBudgetData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="channel" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="budget" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Alertes actives</h2>
        {alerts.length === 0 ? (
          <EmptyState message="Aucune alerte active." />
        ) : (
          <div className="space-y-2">
            {alerts.map((alert) => (
              <AlertBanner key={alert.id} alert={alert} />
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Santé des agents</h2>
        {agents.isLoading ? (
          <LoadingState />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {agents.data?.map((agent) => <AgentCard key={agent.name} agent={agent} />)}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="mb-1 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Évolution du trafic (30 jours)</h2>
        <p className="mb-3 text-xs text-amber-600">Données simulées  aucune série quotidienne réelle n'est exposée par le backend (voir commentaire de code).</p>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={MOCK_TRAFFIC_SERIES}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="day" tick={{ fontSize: 10 }} interval={4} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line type="monotone" dataKey="visits" stroke="#16a34a" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
