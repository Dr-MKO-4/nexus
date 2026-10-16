import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Button, Input } from "@/components/ui";
import { useAuthStore } from "@/store";
import { DEMO } from "@/demo/flag";

/** Comptes fictifs de la démo (voir src/demo/engine.ts). */
const DEMO_ACCOUNTS = [
  { email: "admin@exemple.org", label: "Admin (tous les clients)" },
  { email: "direction@kora-cafe.exemple.org", label: "Manager · Kora Café" },
  { email: "stagiaire@kora-cafe.exemple.org", label: "Viewer · lecture seule" },
];

export default function Login() {
  const { login, isAuthenticated, isLoading } = useAuthStore();
  const [email, setEmail]       = useState(DEMO ? DEMO_ACCOUNTS[0].email : "");
  const [password, setPassword] = useState(DEMO ? "demo" : "");

  // Démo : mémorise la déconnexion pour ne pas rouvrir de session fictive
  // automatiquement au rechargement (voir src/demo/bootstrap.ts).
  useEffect(() => {
    if (!DEMO || isAuthenticated) return;
    try {
      sessionStorage.setItem("nexus_demo_logged_out", "1");
    } catch {
      /* sans effet */
    }
  }, [isAuthenticated]);
  const [error, setError]       = useState<string | null>(null);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      if (DEMO) {
        try {
          sessionStorage.removeItem("nexus_demo_logged_out");
        } catch {
          /* sans effet */
        }
      }
      await login(email, password);
    } catch {
      setError("Email ou mot de passe incorrect.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm border-2 border-border bg-card p-8 space-y-5"
      >
        {/* Brand */}
        <div className="border-b-2 border-border pb-5">
          <h1 className="text-4xl font-black tracking-tight">NEXUS AI</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Plateforme multi-agents IA pour le marketing digital
          </p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
              Email
            </label>
            <Input
              type="email"
              placeholder={DEMO ? "admin@exemple.org" : "admin@nexus.ai"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="rounded-none border-border focus-visible:ring-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
              Mot de passe
            </label>
            <Input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="rounded-none border-border focus-visible:ring-primary"
            />
          </div>
        </div>

        {DEMO && (
          <div className="border-2 border-dashed border-border p-3 text-xs text-muted-foreground">
            <p className="mb-2 font-semibold uppercase tracking-wide text-foreground">Comptes de démonstration</p>
            <ul className="space-y-1">
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.email}>
                  <button
                    type="button"
                    className="text-left hover:text-primary hover:underline"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword("demo");
                    }}
                  >
                    {account.label} : {account.email}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-2">Mot de passe : n'importe quelle valeur.</p>
          </div>
        )}

        {error && (
          <p className="border-l-2 border-destructive pl-3 text-sm text-destructive">
            {error}
          </p>
        )}

        <Button
          type="submit"
          disabled={isLoading}
          className="w-full rounded-none bg-primary text-primary-foreground font-black uppercase tracking-widest text-xs hover:bg-primary/90"
        >
          {isLoading ? "Connexion..." : "Se connecter"}
        </Button>
      </form>
    </div>
  );
}
