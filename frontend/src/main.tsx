import "./demo/bootstrap";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";
import { DEMO } from "./demo/flag";
import { DEMO_CLIENT_IDS } from "./demo/engine";
import { useUIStore } from "./store";

if (DEMO && !useUIStore.getState().adminSelectedClientId) {
  useUIStore.getState().setAdminSelectedClientId(DEMO_CLIENT_IDS.C1);
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
