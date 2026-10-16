import { useState } from "react";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, LoadingState, Progress, StatusIndicator, Tabs, TabsContent, TabsList, TabsTrigger, Textarea } from "@/components/ui";
import { ActivityFeed, AgentGraphVisualizer } from "@/components/realtime";
import { useAgentLogs, useAgents, useCanMutate, useCanViewAgentLogs } from "@/hooks";
import { triggerAgent } from "@/services/api";
import { getAgentDisplayStatus, type Agent } from "@/types";
import { DEMO } from "@/demo/flag";

/** Démo : payload d'exemple pré-rempli avec les kwargs attendus. */
const DEMO_KWARGS: Record<string, unknown> = {
  client_id: "3f6b2a10-6c1e-4a51-9d1e-1c0de0000001",
  brief: "Post LinkedIn sur la formule brunch",
  content_id: "exemple",
  platforms: ["linkedin"],
  contact_ids: ["contact-1", "contact-2"],
  sequence_name: "bienvenue",
  period: "7d",
  campaign_id: null,
};

/**
 * Groupement par cluster  miroir EXACT de `_ACQUISITION_AGENTS`/
 * `_ENGAGEMENT_AGENTS`/`_MEASURE_AGENTS` (backend/agents/orchestrator/
 * nodes.py) : seuls seo/sea/content/social/email/analytics/reporting y
 * sont assignés par l'orchestrateur  "creative" n'appartient à AUCUN des
 * 3 clusters de fanout (déclenché indépendamment, voir tasks/workers/
 * image_worker.py), rattaché ici à "Engagement" par proximité de contenu,
 * pas une correspondance backend exacte.
 */
const CLUSTERS: Record<string, string[]> = {
  Acquisition: ["seo", "sea"],
  Engagement: ["content", "social", "email", "creative"],
  Mesure: ["analytics", "reporting"],
};

function TriggerDialog({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const [raw, setRaw] = useState(() =>
    DEMO ? JSON.stringify(Object.fromEntries(agent.expected_trigger_kwargs.map((k) => [k, DEMO_KWARGS[k] ?? {}])), null, 2) : "{}",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function handleSubmit() {
    setError(null);
    try {
      const payload = JSON.parse(raw);
      const res = await triggerAgent(agent.name, payload);
      setResult(`Tâche envoyée : ${res.task_id} (queue ${res.queue})`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Payload JSON invalide.");
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border border-neutral-200 p-2 dark:border-neutral-800">
      <p className="text-xs text-neutral-500">
        Kwargs attendus : <code>{agent.expected_trigger_kwargs.join(", ")}</code>
      </p>
      <Textarea value={raw} onChange={(e) => setRaw(e.target.value)} rows={4} className="font-mono text-xs" />
      {error && <p className="text-xs text-red-600">{error}</p>}
      {result && <p className="text-xs text-green-600">{result}</p>}
      <div className="flex gap-2">
        <Button size="sm" onClick={handleSubmit}>
          Envoyer
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Fermer
        </Button>
      </div>
    </div>
  );
}

function AgentDetailCard({ agent }: { agent: Agent }) {
  const [expanded, setExpanded] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const canMutate = useCanMutate();
  const canViewLogs = useCanViewAgentLogs();
  const logs = useAgentLogs(agent.name, 5, canViewLogs);
  const status = getAgentDisplayStatus(agent);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          <CardTitle className="capitalize">{agent.name}</CardTitle>
          <Badge variant={status}>{status}</Badge>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Réduire" : "Détails"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        <div>
          {/* "Tâche en cours (barre de progression)" (spec) : aucune tâche
           * Celery n'expose de pourcentage d'avancement dans ce backend (ni
           * task_monitor.py ni AgentDecision ne portent une telle valeur) 
           * substitué par la charge de la queue (nexus_queue_depth), le
           * proxy réel le plus proche d'une notion d'activité en cours,
           * PAS une vraie progression de tâche individuelle. */}
          <p className="text-xs text-neutral-500">Charge de la queue ({agent.queue})  pas une progression de tâche individuelle (non exposée par l'API)</p>
          <Progress value={Math.min(100, agent.queue_depth * 10)} />
        </div>
        {expanded && (
          <>
            <div>
              <p className="mb-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">Dernières actions</p>
              {!canViewLogs ? (
                <p className="text-xs text-neutral-400">Réservé aux rôles admin/manager (GET /agents/{"{"}name{"}"}/logs).</p>
              ) : logs.isLoading ? (
                <LoadingState label="Chargement des actions..." />
              ) : !logs.data?.length ? (
                <p className="text-xs text-neutral-400">Aucune décision enregistrée.</p>
              ) : (
                <ul className="space-y-1 text-xs">
                  {logs.data.map((entry) => (
                    <li key={entry.id} className="flex justify-between text-neutral-600 dark:text-neutral-400">
                      <span>{entry.decision_type}</span>
                      <span>{new Date(entry.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-neutral-600 dark:text-neutral-400">Prochaines tâches planifiées</p>
              <p className="text-xs text-neutral-400">Non exposé par l'API à ce jour (planification Celery Beat statique, aucun endpoint de lecture).</p>
            </div>
            {canMutate && (
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" disabled title="Aucune action de pause au niveau agent n'existe côté backend (seules les campagnes sont pausables).">
                  Pause
                </Button>
                <Button size="sm" onClick={() => setTriggering((v) => !v)}>
                  Déclencher manuellement
                </Button>
              </div>
            )}
            {triggering && <TriggerDialog agent={agent} onClose={() => setTriggering(false)} />}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function AgentControl() {
  const { data: agents, isLoading } = useAgents();
  const agentsByName = Object.fromEntries((agents ?? []).map((a) => [a.name, a]));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Centre de contrôle des agents</h1>

      <Card>
        <CardHeader>
          <CardTitle>Graphe LangGraph (temps réel)</CardTitle>
        </CardHeader>
        <CardContent>
          <AgentGraphVisualizer />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fil d'activité</CardTitle>
        </CardHeader>
        <CardContent>
          <ActivityFeed />
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingState />
      ) : (
        <Tabs defaultValue="Acquisition">
          <TabsList>
            {Object.keys(CLUSTERS).map((cluster) => (
              <TabsTrigger key={cluster} value={cluster}>
                {cluster}
              </TabsTrigger>
            ))}
          </TabsList>
          {Object.entries(CLUSTERS).map(([cluster, names]) => (
            <TabsContent key={cluster} value={cluster} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {names.map((name) => (agentsByName[name] ? <AgentDetailCard key={name} agent={agentsByName[name]} /> : null))}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
