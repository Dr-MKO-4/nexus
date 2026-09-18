import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // API/WebSocket du backend NEXUS AI (backend/api/main.py, port 8000)
      // évite les soucis de CORS/URL absolue en développement local.
      "/api": { target: "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Sépare les libs vendor volumineuses (React + écosystème) du chunk
        // racine (`index-*.js`, >500kB avant ce découpage, seuil par défaut
        // de Rollup)  les pages restent déjà en lazy() (App.tsx), ce
        // découpage-ci cible spécifiquement le code tiers chargé au premier
        // paint, jamais retiré par le lazy-loading des routes.
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-query": ["@tanstack/react-query", "axios", "zustand"],
          "vendor-radix": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-select",
            "@radix-ui/react-slider",
            "@radix-ui/react-switch",
            "@radix-ui/react-tabs",
          ],
        },
      },
    },
  },
});
