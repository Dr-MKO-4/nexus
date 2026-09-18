import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAgents, useHITLPending, useWebSocket } from "@/hooks";
import { EventType, getAgentDisplayStatus, type Agent } from "@/types";

/**
 * Topologie du graphe principal  miroir de backend/agents/orchestrator/
 * graph.py : les 3 nœuds de cluster (fanout réel vers les agents, voir
 * `_ACQUISITION_AGENTS`/`_ENGAGEMENT_AGENTS`/`_MEASURE_AGENTS` dans
 * orchestrator/nodes.py) et `hitl_checkpoint` (le seul nœud avec un statut
 * "en attente HITL" réel, via `interrupt()`) portent un vrai statut dérivé
 * de données API ; les autres nœuds (parse_objective, plan_week,
 * route_to_cluster, consolidate_results, check_performance,
 * generate_report) sont des étapes internes de l'orchestrateur SANS statut
 * agent propre  affichées en gris fixe, jamais colorées à tort.
 */
const GRAPH_NODES = [
  { id: "parse_objective", x: 40, y: 20, kind: "step" as const },
  { id: "plan_week", x: 40, y: 90, kind: "step" as const },
  { id: "route_to_cluster", x: 40, y: 160, kind: "step" as const },
  { id: "acquisition_cluster", x: 190, y: 60, kind: "cluster" as const, agents: ["seo", "sea"] },
  { id: "engagement_cluster", x: 190, y: 160, kind: "cluster" as const, agents: ["content", "social", "email", "creative"] },
  { id: "measure_cluster", x: 190, y: 260, kind: "cluster" as const, agents: ["analytics", "reporting"] },
  { id: "consolidate_results", x: 340, y: 160, kind: "step" as const },
  { id: "check_performance", x: 460, y: 160, kind: "step" as const },
  { id: "hitl_checkpoint", x: 460, y: 240, kind: "hitl" as const },
  { id: "generate_report", x: 580, y: 160, kind: "step" as const },
] as const;

const GRAPH_EDGES: [string, string][] = [
  ["parse_objective", "plan_week"],
  ["plan_week", "route_to_cluster"],
  ["route_to_cluster", "acquisition_cluster"],
  ["route_to_cluster", "engagement_cluster"],
  ["route_to_cluster", "measure_cluster"],
  ["acquisition_cluster", "consolidate_results"],
  ["engagement_cluster", "consolidate_results"],
  ["measure_cluster", "consolidate_results"],
  ["consolidate_results", "check_performance"],
  ["check_performance", "hitl_checkpoint"],
  ["check_performance", "generate_report"],
  ["hitl_checkpoint", "generate_report"],
];

type NodeColor = "green" | "gray" | "orange" | "red";

const COLOR_HEX: Record<NodeColor, string> = {
  green: "#16a34a",
  gray: "#a3a3a3",
  orange: "#d97706",
  red: "#dc2626",
};

interface NodeState {
  color: NodeColor;
  tooltip: string;
}

function computeNodeState(
  node: (typeof GRAPH_NODES)[number],
  agentsByName: Record<string, Agent>,
  agentsIsError: boolean,
  pendingCount: number,
): NodeState {
  if (agentsIsError) {
    return { color: "red", tooltip: "Erreur : le statut des agents n'a pas pu être récupéré (GET /agents en échec)." };
  }

  if (node.kind === "hitl") {
    return pendingCount > 0
      ? { color: "orange", tooltip: `${pendingCount} validation(s) HITL en attente.` }
      : { color: "gray", tooltip: "Aucune validation en attente." };
  }

  if (node.kind === "cluster") {
    const clusterAgents = node.agents.map((name) => agentsByName[name]).filter((a): a is Agent => Boolean(a));
    const active = clusterAgents.filter((a) => getAgentDisplayStatus(a) === "active");
    const tooltip =
      clusterAgents.length === 0
        ? "Aucune donnée d'agent disponible."
        : clusterAgents
            .map((a) => `${a.name} : ${a.last_decision_at ? new Date(a.last_decision_at).toLocaleString() : "aucune action"}`)
            .join("\n");
    return { color: active.length > 0 ? "green" : "gray", tooltip };
  }

  return { color: "gray", tooltip: "Étape interne de l'orchestrateur (pas de statut agent propre)." };
}

export default function AgentGraphVisualizer() {
  const { data: agents, isError: agentsIsError } = useAgents();
  const { data: pending } = useHITLPending();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Spec : "Mise à jour via WebSocket (événements AGENT_STATUS)"  le
  // payload AGENT_STATUS est partiel ({agent_name, status}, voir
  // agent_broadcaster.py) : invalide le cache React Query plutôt que de
  // fusionner un payload partiel dans le type `Agent` strict (même choix
  // que Dashboard.tsx).
  //
  // LIMITE RÉELLE, vérifiée (pas supposée) : `AgentBroadcaster.
  // broadcast_agent_status_change` (backend/api/websocket/agent_broadcaster.py)
  // n'est appelé NULLE PART ailleurs dans ce backend (recherche exhaustive
  // dans backend/ : aucun résultat en dehors de sa propre définition). Cet
  // abonnement est donc correctement câblé côté client mais ne recevra
  // jamais réellement d'événement AGENT_STATUS tant qu'un point d'appel
  // n'est pas ajouté côté backend (ex. dans les workers Celery à chaque
  // changement d'état de tâche)  le graphe reste à jour en pratique
  // uniquement via le polling de `useAgents()` (5s, voir hooks/useAgents.ts).
  useWebSocket(
    EventType.AGENT_STATUS,
    useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }, [queryClient]),
  );

  const agentsByName = Object.fromEntries((agents ?? []).map((a) => [a.name, a]));
  const pendingCount = pending?.length ?? 0;
  const selectedNode = GRAPH_NODES.find((n) => n.id === selectedNodeId) ?? null;

  return (
    <div className="flex gap-4">
      <svg viewBox="0 0 640 300" className="w-full flex-1" role="img" aria-label="Graphe LangGraph de l'orchestrateur">
        {GRAPH_EDGES.map(([from, to]) => {
          const a = GRAPH_NODES.find((n) => n.id === from)!;
          const b = GRAPH_NODES.find((n) => n.id === to)!;
          return <line key={`${from}-${to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#d4d4d4" strokeWidth={1.5} />;
        })}
        {GRAPH_NODES.map((node) => {
          const { color, tooltip } = computeNodeState(node, agentsByName, agentsIsError, pendingCount);
          return (
            <g
              key={node.id}
              onClick={() => setSelectedNodeId(node.id)}
              className="cursor-pointer"
            >
              {color === "green" && (
                <circle cx={node.x} cy={node.y} r={10} fill={COLOR_HEX.green} opacity={0.4}>
                  <animate attributeName="r" values="10;16;10" dur="1.6s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.4;0;0.4" dur="1.6s" repeatCount="indefinite" />
                </circle>
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={10}
                fill={COLOR_HEX[color]}
                stroke={selectedNodeId === node.id ? "#1d4ed8" : "none"}
                strokeWidth={2}
              >
                <title>{`${node.id}\n${tooltip}`}</title>
              </circle>
              <text x={node.x + 14} y={node.y + 4} fontSize={11} fill="currentColor" className="pointer-events-none select-none text-foreground">
                {node.id}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="w-56 shrink-0 rounded-md border border-border p-3 text-xs">
        {selectedNode ? (
          <>
            <p className="mb-1 font-semibold text-foreground">{selectedNode.id}</p>
            {selectedNode.kind === "cluster" ? (
              <ul className="space-y-1">
                {selectedNode.agents.map((name) => {
                  const agent = agentsByName[name];
                  return (
                    <li key={name} className="flex justify-between text-muted-foreground">
                      <span className="capitalize">{name}</span>
                      <span>{agent ? getAgentDisplayStatus(agent) : ""}</span>
                    </li>
                  );
                })}
              </ul>
            ) : selectedNode.kind === "hitl" ? (
              <p className="text-muted-foreground">{pendingCount} validation(s) en attente.</p>
            ) : (
              <p className="text-muted-foreground">Étape interne de l'orchestrateur (parse/plan/route/consolidate/check/report).</p>
            )}
          </>
        ) : (
          <p className="text-muted-foreground">Cliquez sur un nœud pour voir son détail.</p>
        )}
      </div>
    </div>
  );
}
