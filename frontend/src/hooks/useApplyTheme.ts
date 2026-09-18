import { useEffect } from "react";

import { useUIStore } from "@/store";

/** Applique la classe `.dark` sur `<html>` (voir index.css :
 * `@custom-variant dark (&:where(.dark, .dark *))`). Appelé depuis App.tsx
 * (racine, avant le routing) plutôt que depuis Header.tsx (Prompt 8.3
 * initial) : Header ne monte jamais sur /login (hors de AppLayout), donc le
 * thème sombre sauvegardé ne s'appliquait jamais sur l'écran de connexion 
 * corrigé en le remontant au niveau applicatif, indépendant de l'auth. */
export function useApplyTheme(): void {
  const theme = useUIStore((s) => s.theme);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
}
