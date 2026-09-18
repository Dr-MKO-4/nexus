import { useState } from "react";
import { Archive, Clock, Pencil } from "lucide-react";

import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle,
  Dialog, DialogContent, DialogTitle,
  EmptyState, Input, LoadingState, Textarea,
} from "@/components/ui";
import {
  useActiveClientId, useArchiveCampaign, useCampaignHistory,
  useCampaigns, useCanMutate, useUpdateCampaign,
} from "@/hooks";
import type { Campaign, CampaignStatus } from "@/types";

/**
 * Écarts corrigés ici (audit frontend/backend) : `PATCH /campaigns/{id}`,
 * `DELETE /campaigns/{id}` (archivage) et `GET /campaigns/{id}/history`
 * existent côté backend depuis le Prompt 7.1 mais n'étaient exposés par
 * AUCUNE page — cette page comble ce manque avec une liste + édition +
 * archivage + historique (time-travel LangGraph) réels.
 */

const STATUS_VARIANT: Record<CampaignStatus, "default" | "active" | "paused" | "error" | "idle"> = {
  draft: "idle",
  active: "active",
  paused: "paused",
  completed: "default",
  archived: "error",
};

export default function Campaigns() {
  const clientId = useActiveClientId();
  const canMutate = useCanMutate();
  const { data: campaigns, isLoading } = useCampaigns(clientId ?? undefined);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [historyOf, setHistoryOf] = useState<Campaign | null>(null);

  if (!clientId) {
    return <EmptyState message="Aucun client actif — aucun endpoint de liste des clients n'existe pour les comptes admin." />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Campagnes</h1>

      {isLoading ? (
        <LoadingState />
      ) : !campaigns?.length ? (
        <EmptyState message="Aucune campagne pour ce client." />
      ) : (
        <div className="space-y-3">
          {campaigns.map((campaign) => (
            <Card key={campaign.id}>
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-medium text-neutral-900 dark:text-neutral-50">{campaign.name}</p>
                    <Badge variant={STATUS_VARIANT[campaign.status]}>{campaign.status}</Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-neutral-500">{campaign.objective}</p>
                  <p className="mt-1 text-xs text-neutral-400">
                    Budget : {campaign.budget_consumed.toLocaleString()} / {campaign.budget_total.toLocaleString()} €
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button variant="ghost" size="sm" onClick={() => setHistoryOf(campaign)}>
                    <Clock className="h-4 w-4" />
                  </Button>
                  {canMutate && campaign.status !== "archived" && (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => setEditing(campaign)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <ArchiveButton campaignId={campaign.id} />
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing && <EditCampaignDialog campaign={editing} onClose={() => setEditing(null)} />}
      {historyOf && <HistoryDialog campaign={historyOf} onClose={() => setHistoryOf(null)} />}
    </div>
  );
}

function ArchiveButton({ campaignId }: { campaignId: string }) {
  const archive = useArchiveCampaign();
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={archive.isPending}
      onClick={() => {
        if (window.confirm("Archiver cette campagne ? Cette action est réversible uniquement en base.")) {
          archive.mutate(campaignId);
        }
      }}
    >
      <Archive className="h-4 w-4" />
    </Button>
  );
}

function EditCampaignDialog({ campaign, onClose }: { campaign: Campaign; onClose: () => void }) {
  const update = useUpdateCampaign();
  const [name, setName] = useState(campaign.name);
  const [objective, setObjective] = useState(campaign.objective);
  const [budgetTotal, setBudgetTotal] = useState(String(campaign.budget_total));

  async function handleSave() {
    await update.mutateAsync({
      id: campaign.id,
      payload: { name, objective, budget_total: Number(budgetTotal) },
    });
    onClose();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>Modifier la campagne</DialogTitle>
        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">Nom</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">Objectif</label>
            <Textarea value={objective} onChange={(e) => setObjective(e.target.value)} rows={4} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">Budget total (€)</label>
            <Input type="number" min="1" value={budgetTotal} onChange={(e) => setBudgetTotal(e.target.value)} />
          </div>
          {update.isError && <p className="text-sm text-red-600">Échec de la mise à jour.</p>}
          <Button className="w-full" onClick={handleSave} disabled={update.isPending}>
            {update.isPending ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({ campaign, onClose }: { campaign: Campaign; onClose: () => void }) {
  const { data: history, isLoading } = useCampaignHistory(campaign.id);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogTitle>Historique — {campaign.name}</DialogTitle>
        <div className="mt-4 space-y-2">
          {isLoading ? (
            <LoadingState />
          ) : !history?.length ? (
            <EmptyState message="Aucun checkpoint LangGraph (campagne jamais lancée)." />
          ) : (
            history.map((snapshot, i) => (
              <Card key={i}>
                <CardHeader>
                  <CardTitle className="text-xs font-normal text-neutral-500">
                    {new Date(snapshot.created_at).toLocaleString()} — prochain(s) nœud(s) : {snapshot.next.join(", ") || "aucun (fin)"}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="max-h-40 overflow-auto text-xs text-neutral-600 dark:text-neutral-400">
                    {JSON.stringify(snapshot.values, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
