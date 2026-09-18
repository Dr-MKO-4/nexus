import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  LoadingState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@/components/ui";
import {
  useActiveClientId, useCanMutate, useClientDetail, useCreateUser,
  useProviderStatus, useUpdateClientBrand, useUpdateClientIntegrations,
  useUpdateUser, useUsers,
} from "@/hooks";
import { testProvider, type ProviderTestResult } from "@/services/api";
import { useAuthStore } from "@/store";
import type { UserRole } from "@/types";

/** Noms réels des providers (backend/api/routes/settings.py, mêmes clés
 * que litellm_config._collect_provider_configs) → libellé d'affichage. */
const PROVIDER_LABELS: Record<string, string> = {
  groq: "Groq",
  together_ai: "Together AI",
  fireworks_ai: "Fireworks AI",
  mistral: "Mistral",
};

/**
 * "LLM & Modèles" (statut providers), "Marque client" (ligne éditoriale via
 * `PATCH /clients/{id}/brand`), "Intégrations" (`PATCH /clients/{id}/
 * integrations`) et "Utilisateurs" (`/users`) sont réellement connectés au
 * backend (ajoutés suite à un audit frontend/backend). "Agents &
 * Automatisation" reste une maquette locale (useState)  aucune route de
 * configuration n'existe pour les seuils HITL/l'autonomie/Celery Beat,
 * documenté explicitement plutôt que de simuler silencieusement une
 * sauvegarde qui n'existe pas. L'upload de fichiers (affiches/Figma) reste
 * désactivé, faute d'infrastructure de stockage.
 */
const NOT_PERSISTED_NOTICE =
  "\"LLM & Modèles\" (statut des providers), \"Marque client\" (ligne éditoriale) et \"Utilisateurs\" sont réellement connectés au backend et persistés. \"Agents & Automatisation\" reste local (aucune route de configuration n'existe). \"Intégrations\" enregistre réellement la clé API saisie, mais sans flux OAuth2 (aucune infrastructure de callback n'existe) — la connexion n'est jamais vérifiée par un handshake réel. L'upload de fichiers (affiches/Figma) reste désactivé, faute de stockage.";

function LLMModelsSection() {
  const [mode, setMode] = useState<"local" | "api" | "hybrid">("hybrid");
  const [dailyBudget, setDailyBudget] = useState(50);
  const [gpuThreshold, setGpuThreshold] = useState(80);

  // Statut RÉEL (GET /settings/llm/providers, ajouté suite à un audit 
  // remplace les 4 valeurs codées en dur Groq/Together/Fireworks/Mistral
  // qui n'avaient aucun endpoint backend correspondant).
  const { data: providers, isLoading: providersLoading } = useProviderStatus();
  const canTestProvider = useCanMutate();
  const [testResults, setTestResults] = useState<Record<string, ProviderTestResult>>({});
  const [testingProvider, setTestingProvider] = useState<string | null>(null);

  async function handleTestProvider(name: string) {
    setTestingProvider(name);
    try {
      const result = await testProvider(name);
      setTestResults((prev) => ({ ...prev, [name]: result }));
    } catch {
      setTestResults((prev) => ({ ...prev, [name]: { name, success: false, latency_ms: null, error: "Échec de la requête de test." } }));
    } finally {
      setTestingProvider(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Mode LLM</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
            <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="local">Local (vLLM/Ollama uniquement)</SelectItem>
              <SelectItem value="api">API (providers cloud uniquement)</SelectItem>
              <SelectItem value="hybrid">Hybride (routage automatique)</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-neutral-500">
            {mode === "local" && "Tout tourne sur le moteur d'inférence local  aucun coût API, latence dépendante du GPU."}
            {mode === "api" && "Tout passe par les providers API (Groq/Together/Fireworks)  coût au token, pas de contrainte GPU locale."}
            {mode === "hybrid" && "Le HybridRouter choisit dynamiquement local vs API selon la charge GPU et la sensibilité des données."}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Seuils de routage hybride</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-xs text-neutral-500">Budget journalier (USD) : {dailyBudget}</label>
            <Slider value={[dailyBudget]} onValueChange={([v]) => setDailyBudget(v)} min={0} max={200} step={5} />
          </div>
          <div>
            <label className="text-xs text-neutral-500">Charge GPU locale max avant repli API : {gpuThreshold}%</label>
            <Slider value={[gpuThreshold]} onValueChange={([v]) => setGpuThreshold(v)} min={0} max={100} step={5} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Statut des providers</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {providersLoading ? (
            <LoadingState label="Vérification des providers..." />
          ) : (
            providers?.map((p) => {
              const tested = testResults[p.name];
              // "Disponible" affiché = résultat du dernier test si on en a
              // un (un vrai appel litellm), sinon simple présence de clé
              // API  jamais un statut inventé.
              const online = tested ? tested.success : p.configured;
              const label = tested ? (tested.success ? "testé OK" : "échec du test") : p.configured ? "clé configurée" : "non configurée";
              return (
                <div key={p.name} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    {online ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : <XCircle className="h-4 w-4 text-red-600" />}
                    {PROVIDER_LABELS[p.name] ?? p.name}
                    <span className="text-xs text-neutral-400">({p.default_model})</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge variant={online ? "active" : "error"}>{label}</Badge>
                    {canTestProvider && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={testingProvider === p.name || !p.configured}
                        onClick={() => handleTestProvider(p.name)}
                        title={!p.configured ? "Aucune clé API configurée pour ce provider." : undefined}
                      >
                        {testingProvider === p.name ? "..." : "Tester"}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
          {testResults &&
            Object.values(testResults).some((r) => r.error) &&
            Object.values(testResults)
              .filter((r) => r.error)
              .map((r) => (
                <p key={r.name} className="text-xs text-red-600">
                  {PROVIDER_LABELS[r.name] ?? r.name} : {r.error}
                </p>
              ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Clés API</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-neutral-500">
            Les valeurs des clés ne sont jamais exposées par l'API (aucun endpoint ne renvoie une clé en clair)  seule leur
            présence ("configurée"/"non configurée", voir carte ci-dessus) est vérifiable depuis cette interface.
          </p>
          {(["groq", "together_ai", "fireworks_ai", "mistral"] as const).map((name) => (
            <div key={name} className="flex items-center gap-2">
              <span className="w-32 text-xs text-neutral-500">{PROVIDER_LABELS[name]}</span>
              <Input type="password" value="••••••••••••" readOnly className="max-w-xs" />
              {canTestProvider && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={testingProvider === name || !providers?.find((p) => p.name === name)?.configured}
                  onClick={() => handleTestProvider(name)}
                >
                  {testingProvider === name ? "..." : "Tester"}
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

const AGENT_NAMES = ["seo", "sea", "content", "social", "email", "analytics", "creative", "reporting"];

function AgentsAutomationSection() {
  const [thresholds, setThresholds] = useState<Record<string, number>>(Object.fromEntries(AGENT_NAMES.map((a) => [a, 500])));
  const [autonomy, setAutonomy] = useState<Record<string, number>>(Object.fromEntries(AGENT_NAMES.map((a) => [a, 70])));
  // Noms RÉELS des 7 tâches Celery Beat enregistrées (backend/tasks/workers/
  // scheduled_tasks.py), pas des exemples inventés.
  const [beatTasks, setBeatTasks] = useState<Record<string, boolean>>({
    daily_analytics_collection: true,
    weekly_seo_audit: true,
    weekly_report_generation: true,
    hourly_sea_performance_check: true,
    daily_email_sequence_processor: true,
    daily_budget_reset: true,
    weekly_memory_cleanup: true,
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Seuils de validation HITL par agent (€)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {AGENT_NAMES.map((agent) => (
            <div key={agent} className="flex items-center justify-between gap-2">
              <span className="w-24 text-sm capitalize">{agent}</span>
              <Input
                type="number"
                value={thresholds[agent]}
                onChange={(e) => setThresholds((prev) => ({ ...prev, [agent]: Number(e.target.value) }))}
                className="max-w-32"
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Autonomie par agent</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {AGENT_NAMES.map((agent) => (
            <div key={agent}>
              <label className="text-xs text-neutral-500 capitalize">
                {agent}  {autonomy[agent]}% autonome
              </label>
              <Slider value={[autonomy[agent]]} onValueChange={([v]) => setAutonomy((prev) => ({ ...prev, [agent]: v }))} min={0} max={100} step={5} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Tâches périodiques (Celery Beat)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(beatTasks).map(([task, enabled]) => (
            <div key={task} className="flex items-center justify-between text-sm">
              <span>{task}</span>
              <Switch checked={enabled} onCheckedChange={(v) => setBeatTasks((prev) => ({ ...prev, [task]: v }))} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function BrandSection() {
  const clientId = useActiveClientId();
  const canMutate = useCanMutate();
  const { data: client, isLoading } = useClientDetail(clientId ?? undefined);
  const updateBrand = useUpdateClientBrand();

  const [tone, setTone] = useState("");
  const [forbidden, setForbidden] = useState("");
  const [priorityTopics, setPriorityTopics] = useState("");
  const [figmaKey, setFigmaKey] = useState("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!client || hydrated) return;
    setTone((client.editorial_guidelines?.tone as string) ?? "");
    setForbidden((client.forbidden_topics ?? []).join(", "));
    setPriorityTopics((client.editorial_guidelines?.priority_topics as string) ?? "");
    setHydrated(true);
  }, [client, hydrated]);

  async function save() {
    if (!clientId) return;
    await updateBrand.mutateAsync({
      clientId,
      payload: {
        editorial_guidelines: { tone, priority_topics: priorityTopics },
        forbidden_topics: forbidden.split(",").map((t) => t.trim()).filter(Boolean),
      },
    });
  }

  if (!clientId) {
    return <p className="text-sm text-neutral-500">Aucun client actif.</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Affiches de référence stylistique</CardTitle></CardHeader>
        <CardContent>
          <Input type="file" accept="image/*" multiple disabled />
          <p className="mt-1 text-xs text-neutral-400">
            Aucune infrastructure de stockage de fichiers n'existe dans ce backend (pas de route multipart) — non fonctionnel,
            volontairement désactivé plutôt que simulé.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Templates Figma</CardTitle></CardHeader>
        <CardContent className="flex gap-2">
          <Input placeholder="File key Figma" value={figmaKey} onChange={(e) => setFigmaKey(e.target.value)} disabled />
          <Button size="sm" disabled>Ajouter</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ligne éditoriale</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {isLoading ? (
            <LoadingState />
          ) : (
            <>
              <Input placeholder="Ton (ex. professionnel, direct, chaleureux)" value={tone} onChange={(e) => setTone(e.target.value)} disabled={!canMutate} />
              <Textarea placeholder="Mots-clés interdits (séparés par des virgules)" value={forbidden} onChange={(e) => setForbidden(e.target.value)} rows={2} disabled={!canMutate} />
              <Textarea placeholder="Sujets prioritaires" value={priorityTopics} onChange={(e) => setPriorityTopics(e.target.value)} rows={2} disabled={!canMutate} />
              {canMutate && (
                <Button size="sm" onClick={save} disabled={updateBrand.isPending}>
                  {updateBrand.isPending ? "Enregistrement..." : "Enregistrer"}
                </Button>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const INTEGRATIONS = ["Google Search Console", "Google Ads", "Meta", "Mautic", "Matomo", "n8n"];

function IntegrationsSection() {
  const clientId = useActiveClientId();
  const canMutate = useCanMutate();
  const { data: client, isLoading } = useClientDetail(clientId ?? undefined);
  const updateIntegrations = useUpdateClientIntegrations();
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({});

  if (!clientId) {
    return <p className="text-sm text-neutral-500">Aucun client actif.</p>;
  }

  const integrations = (client?.integrations ?? {}) as Record<string, { api_key?: string; connected?: boolean }>;

  async function toggle(name: string) {
    const current = integrations[name] ?? {};
    await updateIntegrations.mutateAsync({
      clientId: clientId!,
      integrations: { [name]: { ...current, api_key: apiKeyDrafts[name] ?? current.api_key, connected: !current.connected } },
    });
  }

  return (
    <Card>
      <CardHeader><CardTitle>Intégrations</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-neutral-500">
          Aucun flux OAuth2 réel n'existe dans ce backend (pas d'infrastructure de callback) — la clé API saisie ici est
          enregistrée telle quelle (`Client.integrations`), pas vérifiée par un handshake réel.
        </p>
        {isLoading ? (
          <LoadingState />
        ) : (
          INTEGRATIONS.map((integration) => {
            const state = integrations[integration];
            return (
              <div key={integration} className="flex items-center justify-between border-b border-neutral-100 py-2 text-sm last:border-0 dark:border-neutral-800">
                <span className="flex items-center gap-2">
                  {state?.connected ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : <XCircle className="h-4 w-4 text-neutral-400" />}
                  {integration}
                </span>
                <div className="flex gap-2">
                  {canMutate && !state?.connected && (
                    <Input
                      placeholder="Clé API"
                      className="h-8 w-32 text-xs"
                      value={apiKeyDrafts[integration] ?? ""}
                      onChange={(e) => setApiKeyDrafts((prev) => ({ ...prev, [integration]: e.target.value }))}
                    />
                  )}
                  {canMutate && (
                    <Button size="sm" onClick={() => toggle(integration)} disabled={updateIntegrations.isPending}>
                      {state?.connected ? "Déconnecter" : "Enregistrer"}
                    </Button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

function UsersSection() {
  const currentUser = useAuthStore((s) => s.user);
  const canMutate = useCanMutate();
  const { data: users, isLoading } = useUsers(currentUser?.role === "admin" ? undefined : (currentUser?.client_id ?? undefined));
  const createUserMutation = useCreateUser();
  const updateUserMutation = useUpdateUser();

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<UserRole>("viewer");
  const [lastTemporaryPassword, setLastTemporaryPassword] = useState<string | null>(null);

  if (currentUser?.role !== "admin" && currentUser?.role !== "manager") {
    return (
      <Card>
        <CardHeader><CardTitle>Utilisateurs</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-neutral-500">Réservé aux rôles admin/manager (GET /users, backend/api/routes/users.py).</p>
        </CardContent>
      </Card>
    );
  }

  async function invite() {
    if (!inviteEmail) return;
    const result = await createUserMutation.mutateAsync({
      email: inviteEmail,
      role: inviteRole,
      client_id: currentUser?.role === "admin" ? null : currentUser?.client_id,
    });
    setLastTemporaryPassword(result.temporary_password);
    setInviteEmail("");
  }

  return (
    <Card>
      <CardHeader><CardTitle>Utilisateurs</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {lastTemporaryPassword && (
          <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
            Mot de passe temporaire (à communiquer manuellement — aucun envoi d'email n'est configuré) : <code className="font-mono">{lastTemporaryPassword}</code>
          </p>
        )}
        {isLoading ? (
          <LoadingState />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500 dark:border-neutral-800">
                <th className="py-1">Email</th>
                <th>Rôle</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="py-1">{u.email}</td>
                  <td>
                    <Select
                      value={u.role}
                      disabled={!canMutate}
                      onValueChange={(role) => updateUserMutation.mutate({ id: u.id, role: role as UserRole })}
                    >
                      <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">admin</SelectItem>
                        <SelectItem value="manager">manager</SelectItem>
                        <SelectItem value="viewer">viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!canMutate}
                      onClick={() => updateUserMutation.mutate({ id: u.id, is_active: !u.is_active })}
                    >
                      {u.is_active ? "Actif" : "Désactivé"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {canMutate && (
          <div className="flex gap-2">
            <Input placeholder="email@exemple.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
            <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as UserRole)}>
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">admin</SelectItem>
                <SelectItem value="manager">manager</SelectItem>
                <SelectItem value="viewer">viewer</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" onClick={invite} disabled={createUserMutation.isPending}>
              {createUserMutation.isPending ? "Envoi..." : "Inviter"}
            </Button>
          </div>
        )}
        {createUserMutation.isError && <p className="text-sm text-red-600">Échec de la création du compte.</p>}
      </CardContent>
    </Card>
  );
}

export default function Settings() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Configuration</h1>
      <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        {NOT_PERSISTED_NOTICE}
      </p>
      <Tabs defaultValue="llm">
        <TabsList>
          <TabsTrigger value="llm">LLM & Modèles</TabsTrigger>
          <TabsTrigger value="agents">Agents & Automatisation</TabsTrigger>
          <TabsTrigger value="brand">Marque client</TabsTrigger>
          <TabsTrigger value="integrations">Intégrations</TabsTrigger>
          <TabsTrigger value="users">Utilisateurs</TabsTrigger>
        </TabsList>
        <TabsContent value="llm"><LLMModelsSection /></TabsContent>
        <TabsContent value="agents"><AgentsAutomationSection /></TabsContent>
        <TabsContent value="brand"><BrandSection /></TabsContent>
        <TabsContent value="integrations"><IntegrationsSection /></TabsContent>
        <TabsContent value="users"><UsersSection /></TabsContent>
      </Tabs>
    </div>
  );
}
