import { NavLink } from "react-router-dom";
import {
  BarChart2, Bot, CheckSquare, FileText,
  LayoutDashboard, LogOut, Megaphone, Settings as SettingsIcon, Sparkles,
} from "lucide-react";

import { useAgents, useHITLPending, useWebSocketStatus } from "@/hooks";
import { useAuthStore } from "@/store";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/",            label: "Dashboard",      icon: LayoutDashboard },
  { to: "/objectifs",   label: "Nouvel objectif", icon: Sparkles       },
  { to: "/campagnes",   label: "Campagnes",      icon: Megaphone       },
  { to: "/agents",      label: "Agents",         icon: Bot             },
  { to: "/validations", label: "Validations",    icon: CheckSquare     },
  { to: "/contenus",    label: "Contenus",       icon: FileText        },
  { to: "/analytics",   label: "Analyses",       icon: BarChart2       },
  { to: "/settings",    label: "Paramètres",     icon: SettingsIcon    },
];

function AgentStatusBadge() {
  const { isError, isLoading } = useAgents();
  if (isLoading) return null;
  return (
    <span className="ml-auto bg-primary text-primary-foreground text-[10px] font-black px-1.5 py-px">
      {isError ? "ERR" : "OK"}
    </span>
  );
}

function SystemStatus() {
  const status = useWebSocketStatus();
  const active = status === "connected";
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
      <span className="relative flex h-2 w-2">
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75",
            active ? "bg-[#16a34a]" : "bg-destructive",
          )}
          style={{ animation: active ? "ping-dot 2s ease-out infinite" : "none" }}
        />
        <span className={cn(
          "relative inline-flex h-2 w-2 rounded-full",
          active ? "bg-[#16a34a]" : "bg-destructive",
        )} />
      </span>
      {active ? "Système actif" : "Système inactif"}
    </div>
  );
}

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuthStore();
  const { data: pending } = useHITLPending();

  return (
    <div className="flex h-full flex-col">
      {/* Brand  wordmark aligné sur le logo réel (public/logo_nexus.png) :
          même poids/geste géométrique (font-black, tracking serré, comme le
          réseau anguleux du logo) et mêmes couleurs (noir charbon --foreground,
          accent rouge --primary repris du cœur hexagonal du logo). */}
      <div className="px-6 py-6 border-b-2 border-border">
        <div className="flex items-center gap-3">
          <img src="/logo_nexus.png" alt="NEXUS AI" className="h-12 w-12 shrink-0 object-contain" />
          <span className="font-black text-2xl tracking-tight text-foreground">
            NEXUS AI<span className="text-primary">.</span>
          </span>
        </div>
        <SystemStatus />
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col py-4">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-6 py-2.5 text-sm font-semibold",
                "border-l-[3px] transition-colors",
                isActive
                  ? "border-l-primary bg-orange-50 text-primary dark:bg-orange-950/30"
                  : "border-l-transparent text-foreground hover:bg-muted",
              )
            }
          >
            <Icon className="h-4 w-4 flex-shrink-0" />
            <span>{label}</span>
            {to === "/agents" && <AgentStatusBadge />}
            {to === "/validations" && !!pending?.length && (
              <span className="ml-auto bg-primary text-primary-foreground text-[10px] font-black px-1.5 py-px">
                {pending.length}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User footer */}
      <div className="border-t-2 border-border px-6 py-4 space-y-2">
        <p className="truncate text-xs text-muted-foreground" title={user?.email}>
          {user?.email}
        </p>
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-1.5 text-xs text-primary font-semibold hover:underline"
        >
          <LogOut className="h-3.5 w-3.5" />
          Déconnexion
        </button>
      </div>
    </div>
  );
}
