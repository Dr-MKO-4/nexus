import { useLocation } from "react-router-dom";
import { Bell, Menu, Moon, Sun } from "lucide-react";

import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui";
import { useClients } from "@/hooks";
import { useAlertStore, useAuthStore, useUIStore } from "@/store";

const PAGE_TITLES: Record<string, string> = {
  "/":            "Tableau de bord",
  "/objectifs":   "Nouvel objectif",
  "/campagnes":   "Campagnes",
  "/agents":      "Centre de contrôle des agents",
  "/validations": "Validation humaine",
  "/contenus":    "Gestion des campagnes et contenus",
  "/analytics":   "Analyses",
  "/settings":    "Configuration",
};

export default function Header({
  onOpenMobileSidebar,
}: {
  onOpenMobileSidebar: () => void;
}) {
  const location = useLocation();
  const title = PAGE_TITLES[location.pathname] ?? "NEXUS AI";

  const { theme, setTheme } = useUIStore();
  const adminSelectedClientId = useUIStore((s) => s.adminSelectedClientId);
  const setAdminSelectedClientId = useUIStore((s) => s.setAdminSelectedClientId);
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const { data: clients } = useClients(isAdmin);
  const alerts       = useAlertStore((s) => s.alerts);
  const unreadCount  = useAlertStore((s) => s.unreadCount);
  const markAsRead   = useAlertStore((s) => s.markAsRead);
  const markAllAsRead = useAlertStore((s) => s.markAllAsRead);

  return (
    <header className="flex h-[60px] shrink-0 items-center justify-between border-b-2 border-border bg-background px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileSidebar}
          className="text-muted-foreground hover:text-foreground lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        {/* Modernist: small-caps uppercase page title */}
        <h6 className="text-[11px] font-black tracking-[0.08em] uppercase text-foreground m-0">
          {title}
        </h6>
      </div>

      <div className="flex items-center gap-4">
        {isAdmin && (
          <Select value={adminSelectedClientId ?? undefined} onValueChange={setAdminSelectedClientId}>
            <SelectTrigger className="hidden w-44 sm:flex">
              <SelectValue placeholder="Choisir un client" />
            </SelectTrigger>
            <SelectContent>
              {clients?.map((client) => (
                <SelectItem key={client.id} value={client.id}>{client.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {/* Alerts bell */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="relative text-muted-foreground hover:text-foreground"
            >
              <Bell className="h-5 w-5" />
              {unreadCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center bg-primary text-[9px] font-black text-primary-foreground">
                  {unreadCount}
                </span>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="rounded-none border-2">
            <DropdownMenuLabel className="flex items-center justify-between font-black uppercase tracking-wide text-[11px]">
              Alertes
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={markAllAsRead}
                  className="text-[10px] font-normal text-primary hover:underline normal-case tracking-normal"
                >
                  Tout marquer lu
                </button>
              )}
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="h-[2px] bg-border" />
            {alerts.length === 0 ? (
              <p className="px-3 py-4 text-center text-xs text-muted-foreground">
                Aucune alerte.
              </p>
            ) : (
              alerts.slice(0, 10).map((alert) => (
                <DropdownMenuItem
                  key={alert.id}
                  onSelect={() => markAsRead(alert.id)}
                  className={alert.read ? "opacity-60" : ""}
                >
                  <div className="w-full">
                    <p className="truncate text-xs font-semibold">{alert.message}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {alert.source} · {new Date(alert.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                </DropdownMenuItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Theme toggle */}
        <button
          type="button"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          className="text-muted-foreground hover:text-foreground"
          title="Changer de thème"
        >
          {theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
        </button>
      </div>
    </header>
  );
}
