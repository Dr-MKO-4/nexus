import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, LoadingState, Textarea } from "@/components/ui";
import { useCanMutate, useHITLPending, useWebSocket } from "@/hooks";
import { approveHITL, modifyHITL, rejectHITL } from "@/services/api";
import { EventType, type HITLRequest, type WebSocketMessage } from "@/types";

/**
 * Toutes les demandes HITL de ce backend viennent d'UN SEUL nœud
 * (orchestrator.nodes.hitl_checkpoint_node)  il n'existe pas de HITL par
 * agent individuel, contrairement à ce qu'implique "agent source" (spec) :
 * affiché honnêtement comme "orchestrator" plutôt qu'un champ inventé.
 */
const AGENT_SOURCE_LABEL = "orchestrator";

interface DecisionHistoryEntry {
  campaignId: string;
  decision: "approve" | "reject" | "modify";
  detail: string;
  at: string;
}

function ValidationCard({
  request,
  onDecided,
}: {
  request: HITLRequest;
  onDecided: (entry: DecisionHistoryEntry) => void;
}) {
  const [comment, setComment] = useState("");
  const [modifications, setModifications] = useState("{}");
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // POST /hitl/{id}/approve|reject|modify exige ADMIN/MANAGER côté backend
  // (_ACTION_ROLES, routes/hitl.py)  trouvé manquant lors d'un audit
  // frontend/backend : ces boutons étaient affichés à tout utilisateur
  // authentifié, y compris VIEWER, qui recevrait un 403 au clic.
  const canMutate = useCanMutate();

  const context = (request.payload?.context as Record<string, unknown>) ?? {};
  const proposal = (request.payload?.proposal as Record<string, unknown>) ?? {};
  const reasoning = typeof proposal.reasoning === "string" ? proposal.reasoning : "_Aucun raisonnement fourni._";

  async function handle(action: "approve" | "reject" | "modify") {
    setSubmitting(action);
    setError(null);
    try {
      if (action === "approve") {
        await approveHITL(request.campaign_id);
        onDecided({ campaignId: request.campaign_id, decision: "approve", detail: "Approuvé", at: new Date().toISOString() });
      } else if (action === "reject") {
        await rejectHITL(request.campaign_id, comment);
        onDecided({ campaignId: request.campaign_id, decision: "reject", detail: comment || "(sans commentaire)", at: new Date().toISOString() });
      } else {
        const parsed = JSON.parse(modifications);
        await modifyHITL(request.campaign_id, parsed);
        onDecided({ campaignId: request.campaign_id, decision: "modify", detail: modifications, at: new Date().toISOString() });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de la décision.");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Campagne {request.campaign_id.slice(0, 8)}</CardTitle>
          <Badge variant="outline">{AGENT_SOURCE_LABEL}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="mb-1 text-xs font-medium text-neutral-500">Contexte</p>
          <div className="prose prose-sm max-w-none text-neutral-700 dark:text-neutral-300">
            <ReactMarkdown>{reasoning}</ReactMarkdown>
          </div>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-neutral-500">Proposition</p>
          <ul className="text-sm text-neutral-700 dark:text-neutral-300">
            <li>Canaux sous-performants : {((proposal.underperforming_channels as string[]) ?? []).join(", ") || ""}</li>
            <li>Canaux surperformants : {((proposal.overperforming_channels as string[]) ?? []).join(", ") || ""}</li>
          </ul>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-neutral-500">Impact estimé</p>
          <ul className="text-sm text-neutral-700 dark:text-neutral-300">
            <li>Budget : {String(context.budget_consumed ?? "")} / {String(context.budget_total ?? "")}</li>
            <li>Allocations par canal : {context.channel_allocations ? JSON.stringify(context.channel_allocations) : ""}</li>
            <li>Risques : non fourni par cet agent (aucun champ de risque structuré dans ce backend).</li>
          </ul>
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        {canMutate ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Button size="sm" onClick={() => handle("approve")} disabled={submitting !== null}>
              {submitting === "approve" ? "..." : "Approuver"}
            </Button>
            <div className="space-y-1">
              <Textarea placeholder="Commentaire de rejet" value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
              <Button size="sm" variant="destructive" onClick={() => handle("reject")} disabled={submitting !== null} className="w-full">
                {submitting === "reject" ? "..." : "Rejeter"}
              </Button>
            </div>
            <div className="space-y-1">
              <Textarea placeholder='Modifications JSON, ex. {"channel_allocations": {...}}' value={modifications} onChange={(e) => setModifications(e.target.value)} rows={2} className="font-mono" />
              <Button size="sm" variant="outline" onClick={() => handle("modify")} disabled={submitting !== null} className="w-full">
                {submitting === "modify" ? "..." : "Modifier"}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Rôle "viewer" : lecture seule (approuver/rejeter/modifier exige un rôle admin ou manager côté backend).
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function HITLValidation() {
  const { data, isLoading } = useHITLPending();
  const queryClient = useQueryClient();
  const [history, setHistory] = useState<DecisionHistoryEntry[]>([]);
  const [confirmations, setConfirmations] = useState<string[]>([]);

  const handleDecided = useCallback((entry: DecisionHistoryEntry) => {
    setHistory((prev) => [entry, ...prev]);
    queryClient.invalidateQueries({ queryKey: ["hitl-pending"] });
  }, [queryClient]);

  // Confirmation WebSocket de reprise du workflow (spec)  HITL_RESOLVED.
  useWebSocket(
    EventType.HITL_RESOLVED,
    useCallback((message: WebSocketMessage) => {
      setConfirmations((prev) => [`Campagne ${message.campaign_id?.slice(0, 8)} reprise (${new Date(message.timestamp).toLocaleTimeString()})`, ...prev].slice(0, 5));
      queryClient.invalidateQueries({ queryKey: ["hitl-pending"] });
    }, [queryClient]),
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Validation humaine</h1>

      {confirmations.length > 0 && (
        <div className="rounded-md border border-green-200 bg-green-50 p-2 text-xs text-green-800 dark:border-green-900 dark:bg-green-950 dark:text-green-200">
          {confirmations.map((c, i) => (
            <p key={i}>{c}</p>
          ))}
        </div>
      )}

      {isLoading ? (
        <LoadingState />
      ) : !data?.length ? (
        <EmptyState message="Aucune validation en attente." />
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-amber-600">
            "Triées par priorité/date" (spec) : ni priorité ni horodatage n'existent sur `PendingHITL` (backend/api/routes/hitl.py)
            ou sur le payload d'`interrupt()` (voir hitl_checkpoint_node)  non triable avec des données réelles, ordre renvoyé
            par l'API affiché tel quel plutôt qu'un tri fabriqué sur un champ absent.
          </p>
          {data.map((request) => (
            <ValidationCard key={request.campaign_id} request={request} onDecided={handleDecided} />
          ))}
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Historique des décisions (session en cours)</h2>
        <p className="mb-2 text-xs text-amber-600">
          Le backend ne persiste aucun historique des décisions HITL passées (aucune table dédiée)  cette liste ne couvre que les
          décisions prises depuis l'ouverture de cette page.
        </p>
        {history.length === 0 ? (
          <EmptyState message="Aucune décision prise pour l'instant." />
        ) : (
          <ul className="space-y-1 text-sm">
            {history.map((entry, i) => (
              <li key={i} className="flex justify-between border-b border-neutral-100 py-1 dark:border-neutral-800">
                <span>
                  {entry.campaignId.slice(0, 8)}  <strong>{entry.decision}</strong> {entry.detail}
                </span>
                <span className="text-neutral-400">{new Date(entry.at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
