import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark";

export interface UINotification {
  id: string;
  message: string;
  variant: "info" | "success" | "warning" | "error";
}

interface UIState {
  sidebarOpen: boolean;
  theme: Theme;
  notifications: UINotification[];
  /** Client sélectionné par un compte ADMIN (`client_id` NULL, voir
   * db/models/users.py)  MANAGER/VIEWER utilisent toujours leur propre
   * `user.client_id`, jamais cette valeur (voir useActiveClientId.ts).
   * `GET /clients` (backend/api/routes/clients.py) n'existait pas avant ce
   * correctif : un admin ne pouvait littéralement rien afficher. */
  adminSelectedClientId: string | null;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setTheme: (theme: Theme) => void;
  setAdminSelectedClientId: (clientId: string | null) => void;
  pushNotification: (notification: Omit<UINotification, "id">) => void;
  dismissNotification: (id: string) => void;
}

/** `persist` justifié ici (contrairement aux autres stores) : préférences
 * purement locales à l'utilisateur (thème, sidebar), sans équivalent
 * serveur à resynchroniser  aucun risque de double source de vérité. */
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      theme: "light",
      notifications: [],
      adminSelectedClientId: null,

      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setTheme: (theme) => set({ theme }),
      setAdminSelectedClientId: (clientId) => set({ adminSelectedClientId: clientId }),

      pushNotification: (notification) =>
        set((state) => ({ notifications: [...state.notifications, { ...notification, id: crypto.randomUUID() }] })),

      dismissNotification: (id) => set((state) => ({ notifications: state.notifications.filter((n) => n.id !== id) })),
    }),
    {
      name: "nexus-ui-preferences",
      partialize: (state) => ({
        sidebarOpen: state.sidebarOpen,
        theme: state.theme,
        adminSelectedClientId: state.adminSelectedClientId,
      }),
    },
  ),
);
