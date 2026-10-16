import { useState } from "react";
import { Info, X } from "lucide-react";

/** Bandeau discret « Démo · données simulées », dépliable. */
export default function DemoBanner() {
  const [open, setOpen] = useState(false);
  return (
    <div className="fixed bottom-3 right-3 z-[60] max-w-[calc(100vw-1.5rem)] text-xs">
      {open ? (
        <div role="dialog" aria-label="À propos de la démo" className="w-80 max-w-full border-2 border-border bg-card p-3 text-foreground shadow-lg">
          <div className="mb-1 flex items-center justify-between">
            <strong className="uppercase tracking-wide">Démo · données simulées</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="Fermer" className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="text-muted-foreground">
            Cette version tourne entièrement dans le navigateur : clients, campagnes, contenus et chiffres sont fictifs. Les agents,
            le graphe LangGraph, les tâches Celery et la validation humaine sont simulés selon les règles du code (seuil HITL de 50 %,
            clusters, noms de tâches). Aucun LLM n'est appelé et aucune donnée ne quitte votre navigateur.
          </p>
          <p className="mt-2 text-muted-foreground">Rechargez la page pour réinitialiser la démo.</p>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 border-2 border-border bg-card/95 px-2.5 py-1 font-semibold text-foreground shadow-sm hover:bg-muted"
        >
          <Info className="h-3.5 w-3.5 text-primary" />
          Démo · données simulées
        </button>
      )}
    </div>
  );
}
