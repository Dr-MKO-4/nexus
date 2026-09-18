import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  EmptyState,
  Input,
  LoadingState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@/components/ui";
import { useActiveClientId, useCalendar, useCampaigns, useCanMutate, useChannelPerformanceQuery, useContentsQuery } from "@/hooks";
import { publishContent, scheduleContent, updateContent } from "@/services/api";
import { pauseCampaign, resumeCampaign } from "@/services/api";
import type { Content, ContentPlatform, ContentStatus, ContentType } from "@/types";

const PLATFORM_COLOR: Record<ContentPlatform, string> = {
  linkedin: "bg-blue-100 text-blue-800",
  meta: "bg-red-100 text-red-800",
  tiktok: "bg-neutral-800 text-white",
  email: "bg-neutral-100 text-neutral-700",
  web: "bg-purple-100 text-purple-800",
};

// ── Onglet Calendrier ────────────────────────────────────────────────────────

function CalendarTab({ clientId }: { clientId: string }) {
  const [view, setView] = useState<"month" | "week">("month");
  const [month, setMonth] = useState(new Date());
  const [weekStart, setWeekStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - d.getDay());
    return d;
  });
  const { data, isLoading } = useCalendar(clientId, view === "month" ? month : weekStart);
  const [selected, setSelected] = useState<Content | null>(null);
  const queryClient = useQueryClient();
  // POST /contents/{id}/schedule exige ADMIN/MANAGER  sans cette garde, un
  // VIEWER pouvait glisser une carte et déclencher un appel voué à un 403
  // silencieux (promesse rejetée, aucun retour visuel).
  const canMutate = useCanMutate();

  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const firstWeekday = new Date(month.getFullYear(), month.getMonth(), 1).getDay();
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  });

  function sameDay(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  const byDay = useMemo(() => {
    const map: Record<number, Content[]> = {};
    for (const content of data ?? []) {
      const dateStr = content.scheduled_at ?? content.published_at;
      if (!dateStr) continue;
      const date = new Date(dateStr);
      if (view === "month") {
        if (date.getMonth() !== month.getMonth() || date.getFullYear() !== month.getFullYear()) continue;
        map[date.getDate()] = [...(map[date.getDate()] ?? []), content];
      } else {
        const dayIndex = weekDays.findIndex((d) => sameDay(d, date));
        if (dayIndex === -1) continue;
        map[dayIndex] = [...(map[dayIndex] ?? []), content];
      }
    }
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- weekDays est dérivé de weekStart, déjà dans les deps.
  }, [data, month, view, weekStart]);

  async function handleDrop(targetDate: Date, event: React.DragEvent) {
    event.preventDefault();
    if (!canMutate) return;
    const contentId = event.dataTransfer.getData("text/content-id");
    if (!contentId) return;
    const newDate = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate(), 12, 0, 0);
    await scheduleContent(contentId, newDate.toISOString());
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
  }

  if (isLoading) return <LoadingState />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            view === "month"
              ? setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
              : setWeekStart(new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() - 7))
          }
        >
          ← Précédent
        </Button>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">
            {view === "month" ? month.toLocaleDateString(undefined, { month: "long", year: "numeric" }) : `Semaine du ${weekDays[0].toLocaleDateString()}`}
          </p>
          <Button size="sm" variant={view === "month" ? "default" : "outline"} onClick={() => setView("month")}>
            Mois
          </Button>
          <Button size="sm" variant={view === "week" ? "default" : "outline"} onClick={() => setView("week")}>
            Semaine
          </Button>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            view === "month"
              ? setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
              : setWeekStart(new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + 7))
          }
        >
          Suivant →
        </Button>
      </div>

      {view === "month" ? (
        <div className="grid grid-cols-7 gap-1 text-xs">
          {Array.from({ length: firstWeekday }).map((_, i) => (
            <div key={`pad-${i}`} />
          ))}
          {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => (
            <div
              key={day}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleDrop(new Date(month.getFullYear(), month.getMonth(), day), e)}
              className="min-h-20 rounded-md border border-neutral-200 p-1 dark:border-neutral-800"
            >
              <p className="mb-1 text-neutral-400">{day}</p>
              {(byDay[day] ?? []).map((content) => (
                <button
                  key={content.id}
                  draggable={canMutate}
                  onDragStart={(e) => e.dataTransfer.setData("text/content-id", content.id)}
                  onClick={() => setSelected(content)}
                  className={`mb-0.5 w-full truncate rounded px-1 py-0.5 text-left ${PLATFORM_COLOR[content.platform]}`}
                >
                  {content.title ?? content.content_type}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-7 gap-1 text-xs">
          {weekDays.map((day, i) => (
            <div
              key={i}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleDrop(day, e)}
              className="min-h-32 rounded-md border border-neutral-200 p-1 dark:border-neutral-800"
            >
              <p className="mb-1 text-neutral-400">{day.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}</p>
              {(byDay[i] ?? []).map((content) => (
                <button
                  key={content.id}
                  draggable={canMutate}
                  onDragStart={(e) => e.dataTransfer.setData("text/content-id", content.id)}
                  onClick={() => setSelected(content)}
                  className={`mb-0.5 w-full truncate rounded px-1 py-0.5 text-left ${PLATFORM_COLOR[content.platform]}`}
                >
                  {content.title ?? content.content_type}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          {selected && (
            <>
              <DialogTitle>{selected.title ?? selected.content_type}</DialogTitle>
              <DialogDescription>
                {selected.platform} · {selected.status}
              </DialogDescription>
              <p className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap text-sm text-neutral-700 dark:text-neutral-300">{selected.body}</p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Onglet Bibliothèque ──────────────────────────────────────────────────────

function LibraryTab({ clientId }: { clientId: string }) {
  const [contentType, setContentType] = useState<ContentType | "all">("all");
  const [platformFilter, setPlatformFilter] = useState<ContentPlatform | "all">("all");
  const [statusFilter, setStatusFilter] = useState<ContentStatus | "all">("all");
  const { data, isLoading } = useContentsQuery(clientId, {
    content_type: contentType === "all" ? undefined : contentType,
    status: statusFilter === "all" ? undefined : statusFilter,
  });
  const queryClient = useQueryClient();
  const [viewing, setViewing] = useState<Content | null>(null);
  const [editing, setEditing] = useState<Content | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  // PATCH/POST /contents/{id}/* exigent ADMIN/MANAGER côté backend
  // (_MUTATE_ROLES, routes/content.py)  trouvé manquant lors d'un audit
  // frontend/backend : ces boutons étaient affichés à tout utilisateur.
  const canMutate = useCanMutate();

  const filtered = (data ?? []).filter((c) => platformFilter === "all" || c.platform === platformFilter);

  async function handlePublish(id: string) {
    await publishContent(id);
    queryClient.invalidateQueries({ queryKey: ["contents"] });
  }

  async function handleArchive(id: string) {
    await updateContent(id, { status: "archived" });
    queryClient.invalidateQueries({ queryKey: ["contents"] });
  }

  function openEdit(content: Content) {
    setEditing(content);
    setEditTitle(content.title ?? "");
    setEditBody(content.body);
  }

  async function saveEdit() {
    if (!editing) return;
    await updateContent(editing.id, { title: editTitle, body: editBody });
    queryClient.invalidateQueries({ queryKey: ["contents"] });
    setEditing(null);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Select value={contentType} onValueChange={(v) => setContentType(v as ContentType | "all")}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous types</SelectItem>
            {(["article", "post", "email", "landing_page", "visual"] as ContentType[]).map((t) => (
              <SelectItem key={t} value={t}>{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={platformFilter} onValueChange={(v) => setPlatformFilter(v as ContentPlatform | "all")}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Plateforme" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toutes plateformes</SelectItem>
            {(["linkedin", "meta", "tiktok", "email", "web"] as ContentPlatform[]).map((p) => (
              <SelectItem key={p} value={p}>{p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as ContentStatus | "all")}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Statut" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous statuts</SelectItem>
            {(["draft", "review", "published", "archived"] as ContentStatus[]).map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <LoadingState />
      ) : filtered.length === 0 ? (
        <EmptyState message="Aucun contenu ne correspond aux filtres." />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((content) => (
            <Card key={content.id}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <Badge className={PLATFORM_COLOR[content.platform]}>{content.platform}</Badge>
                <Badge variant="outline">{content.status}</Badge>
              </CardHeader>
              <CardContent className="space-y-2">
                {content.content_type === "visual" ? (
                  // Pas de vraie miniature : `Content.body` pour un visuel
                  // est un chemin de fichier serveur (voir VisualAsset.
                  // file_path), pas une URL HTTP publique servable par un
                  // <img>  aucune route de fichiers statiques n'expose ces
                  // chemins dans ce backend.
                  <div className="flex h-24 items-center justify-center rounded-md bg-neutral-100 text-xs text-neutral-400 dark:bg-neutral-800">
                    Visuel : {content.body.slice(0, 40)}
                  </div>
                ) : (
                  <p className="line-clamp-3 text-sm text-neutral-600 dark:text-neutral-400">{content.body}</p>
                )}
                {content.status === "published" && (
                  <p className="text-xs text-neutral-400">
                    Vues : {String((content.performance_data as Record<string, unknown> | null)?.views ?? "")} · Clics :{" "}
                    {String((content.performance_data as Record<string, unknown> | null)?.clicks ?? "")}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setViewing(content)}>
                    Voir détail
                  </Button>
                  {canMutate && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => openEdit(content)}>
                        Modifier
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => handlePublish(content.id)} disabled={content.status === "published"}>
                        Publier
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleArchive(content.id)} disabled={content.status === "archived"}>
                        Archiver
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={viewing !== null} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent>
          {viewing && (
            <>
              <DialogTitle>{viewing.title ?? viewing.content_type}</DialogTitle>
              <DialogDescription>{viewing.platform} · {viewing.status} · {viewing.agent_source}</DialogDescription>
              <p className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap text-sm text-neutral-700 dark:text-neutral-300">{viewing.body}</p>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          {editing && (
            <>
              <DialogTitle>Modifier le contenu</DialogTitle>
              <div className="mt-3 space-y-2">
                <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} placeholder="Titre" />
                <Textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} rows={6} placeholder="Corps" />
                <Button size="sm" onClick={saveEdit}>Enregistrer</Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Onglet Campagnes SEA ─────────────────────────────────────────────────────

/**
 * Ce projet n'a AUCUN endpoint "campagnes SEA" dédié : `Campaign` est
 * générique (pas de distinction de canal au niveau du modèle), et les
 * détails SEA (ad_variants, bid_adjustments) ne vivent que dans l'état
 * LangGraph d'un run, jamais exposés via une route REST (recherché dans
 * backend/api/routes/*, absent). Cet onglet utilise donc les campagnes
 * génériques du client comme liste, et `/analytics/channels` (channel="sea")
 * pour les métriques  réel, mais actuellement proche de zéro en pratique
 * car `ad_spend` est câblé en dur à 0.0 dans compute_kpis_node (comptes
 * publicitaires pas encore branchés, voir ce fichier) : les chiffres
 * affichés sont donc honnêtes, pas fabriqués, mais peu significatifs tant
 * que cette intégration n'existe pas.
 */
function SEATab({ clientId }: { clientId: string }) {
  const campaigns = useCampaigns(clientId);
  const activeCampaigns = useMemo(() => campaigns.data?.filter((c) => c.status === "active") ?? [], [campaigns.data]);
  const channelPerf = useChannelPerformanceQuery(clientId);
  const seaMetrics = channelPerf.data?.find((c) => c.channel === "sea")?.metrics ?? {};
  const queryClient = useQueryClient();
  // POST /campaigns/{id}/pause|resume exigent ADMIN/MANAGER côté backend.
  const canMutate = useCanMutate();

  // Données simulées : `/analytics/channels` ne renvoie qu'UNE valeur ROAS
  // agrégée pour la période courante (PerformanceMetric n'a pas de
  // granularité quotidienne, même limite que le line chart trafic du
  // Dashboard)  cette "série" est une variation fabriquée autour de cette
  // seule valeur réelle, pas 7 points réellement mesurés.
  const roasSeries = useMemo(
    () => Array.from({ length: 7 }, (_, i) => ({ day: `J-${6 - i}`, roas: (seaMetrics.roas ?? 0) * (0.9 + i * 0.03) })),
    [seaMetrics.roas],
  );

  async function togglePause(campaignId: string, currentStatus: string) {
    if (currentStatus === "active") {
      await pauseCampaign(campaignId);
    } else {
      await resumeCampaign(campaignId, { action: "resume" });
    }
    queryClient.invalidateQueries({ queryKey: ["campaigns"] });
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-amber-600">
        Aucun endpoint "campagnes SEA" dédié n'existe côté backend  liste des campagnes génériques du client, métriques via
        /analytics/channels (canal "sea", voir commentaire de code).
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card><CardContent className="p-3"><p className="text-xs text-neutral-500">Dépense du jour</p><p className="text-lg font-semibold">{seaMetrics.spend ?? 0}</p></CardContent></Card>
        <Card><CardContent className="p-3"><p className="text-xs text-neutral-500">ROAS</p><p className="text-lg font-semibold">{seaMetrics.roas ?? 0}</p></CardContent></Card>
        <Card><CardContent className="p-3"><p className="text-xs text-neutral-500">CPA</p><p className="text-lg font-semibold">{seaMetrics.cpa ?? 0}</p></CardContent></Card>
        <Card><CardContent className="p-3"><p className="text-xs text-neutral-500">CTR</p><p className="text-lg font-semibold">{seaMetrics.ctr ?? 0}</p></CardContent></Card>
      </div>

      <Card>
        <CardHeader><CardTitle>ROAS sur 7 jours</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-amber-600">Données simulées  une seule valeur ROAS réelle existe par période (voir commentaire de code), pas une série quotidienne.</p>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={roasSeries}>
              <XAxis dataKey="day" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="roas" stroke="#2563eb" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {campaigns.isLoading ? (
        <LoadingState />
      ) : activeCampaigns.length === 0 ? (
        <EmptyState message="Aucune campagne active." />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500 dark:border-neutral-800">
              <th className="py-2">Nom</th>
              <th>Statut</th>
              <th>Budget</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {activeCampaigns.map((campaign) => (
              <tr key={campaign.id} className="border-b border-neutral-100 dark:border-neutral-900">
                <td className="py-2">{campaign.name}</td>
                <td><Badge variant="outline">{campaign.status}</Badge></td>
                <td>{campaign.budget_consumed} / {campaign.budget_total} €</td>
                <td>
                  {canMutate && (
                    <Button size="sm" variant="outline" onClick={() => togglePause(campaign.id, campaign.status)}>
                      {campaign.status === "active" ? "Pause" : "Reprendre"}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Onglet Visuels ───────────────────────────────────────────────────────────

function VisualsTab({ clientId }: { clientId: string }) {
  const { data, isLoading } = useContentsQuery(clientId, { content_type: "visual" });
  const [generationId, setGenerationId] = useState("");
  const [tokens, setTokens] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);

  /**
   * PAS `EventSource` natif : son API ne permet aucun en-tête `Authorization`
   * custom (limite du navigateur, voir backend/api/sse/streams.py qui le
   * documente déjà)  or GET /sse/content-stream/{id} exige exactement cet
   * en-tête (`Depends(get_current_user)`), aucun fallback par query param
   * côté backend. Utiliser `EventSource` ici recevrait systématiquement un
   * 401 avant même d'atteindre le problème de producteur manquant. `fetch`
   * + lecture manuelle du flux `ReadableStream` (parsing `data: ...\n\n`)
   * est la façon correcte de consommer un SSE authentifié depuis un
   * navigateur.
   */
  async function watchGeneration() {
    if (!generationId) return;
    setTokens([]);
    setStreaming(true);
    const token = localStorage.getItem("nexus_access_token");
    const base = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
    try {
      const response = await fetch(`${base}/sse/content-stream/${generationId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(5).trim());
            setTokens((prev) => [...prev, String(payload.token ?? "")]);
            if (payload.done) {
              setStreaming(false);
              return;
            }
          } catch {
            // ping/heartbeat non-JSON, ignoré
          }
        }
      }
    } catch {
      // connexion perdue/refusée  pas d'affichage d'erreur bloquant, le
      // bandeau ci-dessous explique déjà l'absence de producteur réel.
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Suivre une génération en cours</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-amber-600">
            Ce flux SSE consomme un canal réel (GET /sse/content-stream/&#123;id&#125;), mais aucun code backend ne publie
            actuellement de tokens sur ce canal (producteur manquant, voir backend/api/sse/streams.py)  rien ne s'affichera
            tant que cette pièce n'est pas construite ailleurs.
          </p>
          <div className="flex gap-2">
            <Input placeholder="generation_id" value={generationId} onChange={(e) => setGenerationId(e.target.value)} />
            <Button size="sm" onClick={watchGeneration} disabled={streaming}>
              {streaming ? "En écoute..." : "Suivre"}
            </Button>
          </div>
          {tokens.length > 0 && <p className="rounded-md bg-neutral-100 p-2 text-sm dark:bg-neutral-800">{tokens.join("")}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Upload templates Figma / affiches de référence</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-amber-600">Aucun endpoint d'upload de fichier n'existe côté backend à ce jour  formulaire désactivé.</p>
          <Input type="file" disabled />
          <Input placeholder="Figma file key" disabled />
        </CardContent>
      </Card>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Galerie</h3>
        {isLoading ? (
          <LoadingState />
        ) : !data?.length ? (
          <EmptyState message="Aucun visuel généré." />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {data.map((visual) => (
              <div key={visual.id} className="flex h-28 items-center justify-center rounded-md border border-neutral-200 p-2 text-center text-xs text-neutral-500 dark:border-neutral-800">
                {visual.body.slice(0, 60)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ContentManagement() {
  const clientId = useActiveClientId();
  if (!clientId) {
    return <EmptyState message="Aucun client actif  aucun endpoint de liste des clients n'existe pour les comptes admin." />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Gestion des campagnes et contenus</h1>
      <Tabs defaultValue="calendar">
        <TabsList>
          <TabsTrigger value="calendar">Calendrier</TabsTrigger>
          <TabsTrigger value="library">Bibliothèque</TabsTrigger>
          <TabsTrigger value="sea">Campagnes SEA</TabsTrigger>
          <TabsTrigger value="visuals">Visuels</TabsTrigger>
        </TabsList>
        <TabsContent value="calendar"><CalendarTab clientId={clientId} /></TabsContent>
        <TabsContent value="library"><LibraryTab clientId={clientId} /></TabsContent>
        <TabsContent value="sea"><SEATab clientId={clientId} /></TabsContent>
        <TabsContent value="visuals"><VisualsTab clientId={clientId} /></TabsContent>
      </Tabs>
    </div>
  );
}
