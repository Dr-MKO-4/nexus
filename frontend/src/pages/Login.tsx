import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Button, Input } from "@/components/ui";
import { useAuthStore } from "@/store";

export default function Login() {
  const { login, isAuthenticated, isLoading } = useAuthStore();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
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
              placeholder="admin@nexus.ai"
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
