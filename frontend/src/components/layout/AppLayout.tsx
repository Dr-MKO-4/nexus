import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { X } from "lucide-react";

import Header from "./Header";
import Sidebar from "./Sidebar";
import { useWebSocket } from "@/hooks";
import { useAlertStore, useAuthStore } from "@/store";
import { websocketService } from "@/services/websocket";
import { EventType, type Alert, type WebSocketMessage } from "@/types";

export default function AppLayout() {
  const { token } = useAuthStore();
  const addAlert = useAlertStore((s) => s.addAlert);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    if (token) websocketService.connect(token);
    return () => websocketService.disconnect();
  }, [token]);

  useWebSocket(
    EventType.ALERT,
    useCallback(
      (message: WebSocketMessage) => {
        const payload = message.payload as Partial<Alert>;
        addAlert({
          level: payload.level ?? "info",
          source: payload.source ?? message.agent_name ?? "unknown",
          message: payload.message ?? "Alerte reçue.",
          timestamp: message.timestamp,
          action_required: payload.action_required ?? false,
        });
      },
      [addAlert],
    ),
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar desktop  240px, 2px right border */}
      <aside className="hidden w-60 shrink-0 border-r-2 border-border bg-background lg:block">
        <Sidebar />
      </aside>

      {/* Sidebar mobile drawer */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <div className="relative z-50 w-60 border-r-2 border-border bg-background">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(false)}
              className="absolute right-3 top-3 text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setMobileSidebarOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        <Header onOpenMobileSidebar={() => setMobileSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
