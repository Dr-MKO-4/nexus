import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Loader2, Send, Sparkles } from "lucide-react";

import { Button, EmptyState, Textarea } from "@/components/ui";
import { useActiveClientId, useCampaign, useCanMutate } from "@/hooks";
import { createCampaign } from "@/services/api";
import type { Campaign } from "@/types";

/**
 * Interface conversationnelle : l'utilisateur décrit un objectif en langage
 * naturel dans un fil de discussion, transmis à l'Orchestrateur
 * (POST /campaigns → MainGraph.run(), voir backend/api/routes/campaigns.py)
 * qui planifie et exécute seul — l'utilisateur n'intervient qu'au moment
 * d'une validation HITL (page Validations).
 *
 * Aucun message "assistant" n'est un texte généré par un LLM conversationnel
 * (l'Orchestrateur n'en produit pas) : chaque message système reflète un
 * VRAI événement (campagne créée, statut réel via polling, pause HITL).
 * Ne jamais fabriquer de réponse conversationnelle qui n'existe pas côté
 * backend.
 */

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "system"; campaign: Campaign; kind: "created" | "status" };

function defaultBudget(): number {
  // Pas de budget structuré dans le fil de discussion : l'Orchestrateur
  // (`parse_objective_node`) décompose lui-même l'objectif via LLM. Un
  // budget par défaut raisonnable est transmis ; l'utilisateur peut affiner
  // via une validation HITL si l'Orchestrateur le juge nécessaire.
  return 1000;
}

export default function NewObjective() {
  const clientId = useActiveClientId();
  const canMutate = useCanMutate();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCampaignId, setActiveCampaignId] = useState<string | undefined>(undefined);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Suit le statut de la campagne juste créée — poll court le temps que
  // l'orchestrateur avance (aucun événement WebSocket fiable pour ça :
  // CAMPAIGN_UPDATE n'est émis par aucun code backend, voir l'audit — le
  // polling reste donc le seul mécanisme réel de suivi ici).
  const { data: liveCampaign } = useCampaign(activeCampaignId, {
    refetchInterval: (query) => (query.state.data?.status === "active" ? 3000 : false),
  });

  useEffect(() => {
    if (!liveCampaign) return;
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === "system" && last.campaign.status === liveCampaign.status) return prev;
      return [...prev, { id: `status-${liveCampaign.id}-${liveCampaign.status}-${Date.now()}`, role: "system", campaign: liveCampaign, kind: "status" }];
    });
  }, [liveCampaign]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!clientId || !input.trim()) return;
    const objective = input.trim();
    setError(null);
    setSubmitting(true);
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: "user", text: objective }]);
    setInput("");
    try {
      const campaign = await createCampaign({
        client_id: clientId,
        name: objective.slice(0, 60),
        objective,
        budget_total: defaultBudget(),
      });
      setActiveCampaignId(campaign.id);
      setMessages((prev) => [...prev, { id: `created-${campaign.id}`, role: "system", campaign, kind: "created" }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de la création de la campagne.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!clientId) {
    return <EmptyState message="Aucun client actif — aucun endpoint de liste des clients n'existe pour les comptes admin." />;
  }

  if (!canMutate) {
    return <EmptyState message="Rôle « viewer » : la création d'un objectif exige un rôle admin ou manager côté backend (POST /campaigns)." />;
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-2xl flex-col">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-neutral-900 dark:text-neutral-50">
          <Sparkles className="h-5 w-5" />
          Nouvel objectif
        </h1>
        <p className="mt-1 text-sm text-neutral-500">
          Décrivez votre objectif en langage naturel. L'Orchestrateur planifie et exécute automatiquement (SEO, SEA, contenu,
          social, email, analytics...) — vous n'aurez qu'à valider si une décision importante nécessite votre accord.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-border bg-card p-4">
        {messages.length === 0 && (
          <p className="text-sm text-neutral-400">
            Exemple : « Augmenter les leads qualifiés de 30% ce trimestre en renforçant notre présence SEO et en lançant une
            campagne social media sur LinkedIn. »
          </p>
        )}
        {messages.map((message) => (
          <div key={message.id} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
            {message.role === "user" ? (
              <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">{message.text}</div>
            ) : (
              <SystemMessage message={message} />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <form onSubmit={handleSubmit} className="mt-3 flex items-end gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Décrivez votre objectif..."
          rows={2}
          className="flex-1 resize-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <Button type="submit" disabled={submitting || !input.trim()}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
    </div>
  );
}

function SystemMessage({ message }: { message: Extract<ChatMessage, { role: "system" }> }) {
  const { campaign, kind } = message;

  if (kind === "created") {
    return (
      <div className="max-w-[80%] rounded-lg border border-border bg-muted px-3 py-2 text-sm text-neutral-700 dark:text-neutral-300">
        Campagne « {campaign.name} » créée. L'Orchestrateur a démarré son analyse.
      </div>
    );
  }

  if (campaign.status === "active") {
    return (
      <div className="flex max-w-[80%] items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 text-xs text-neutral-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        L'orchestrateur travaille sur « {campaign.name} »...
      </div>
    );
  }

  if (campaign.status === "paused") {
    return (
      <div className="max-w-[80%] rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <p className="mb-2">L'orchestrateur a suspendu l'exécution de « {campaign.name} » : une validation humaine est requise.</p>
        <Link to="/validations" className="inline-flex items-center gap-1 font-medium underline">
          Aller aux validations <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    );
  }

  if (campaign.status === "completed") {
    return (
      <div className="max-w-[80%] rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800 dark:border-green-900 dark:bg-green-950 dark:text-green-300">
        Campagne « {campaign.name} » terminée — consultez l'onglet Analyses pour les résultats.
      </div>
    );
  }

  return (
    <div className="max-w-[80%] rounded-lg border border-border bg-muted px-3 py-2 text-sm text-neutral-600 dark:text-neutral-400">
      Statut de « {campaign.name} » : {campaign.status}
    </div>
  );
}
