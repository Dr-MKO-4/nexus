/**
 * Mode démo (branche `demo`) : activé au build par `VITE_DEMO=true`
 * (voir `.env.demo` et `npm run build:demo`). Quand il est actif, aucune
 * requête ne part vers le backend FastAPI : l'adaptateur axios, le service
 * WebSocket et le flux SSE sont remplacés par une simulation en mémoire
 * (src/demo/engine.ts) qui reproduit les routes, les formes de réponse et
 * les règles métier du backend réel.
 */
export const DEMO = import.meta.env.VITE_DEMO === "true";
