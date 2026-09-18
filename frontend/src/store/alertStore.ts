import { create } from "zustand";

import type { Alert } from "@/types";

interface StoredAlert extends Alert {
  id: string;
  read: boolean;
}

interface AlertState {
  alerts: StoredAlert[];
  unreadCount: number;
  addAlert: (alert: Alert) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
}

export const useAlertStore = create<AlertState>((set) => ({
  alerts: [],
  unreadCount: 0,

  addAlert: (alert) =>
    set((state) => {
      const stored: StoredAlert = { ...alert, id: crypto.randomUUID(), read: false };
      const alerts = [stored, ...state.alerts];
      return { alerts, unreadCount: state.unreadCount + 1 };
    }),

  markAsRead: (id) =>
    set((state) => {
      let changed = false;
      const alerts = state.alerts.map((alert) => {
        if (alert.id === id && !alert.read) {
          changed = true;
          return { ...alert, read: true };
        }
        return alert;
      });
      return changed ? { alerts, unreadCount: Math.max(0, state.unreadCount - 1) } : state;
    }),

  markAllAsRead: () => set((state) => ({ alerts: state.alerts.map((a) => ({ ...a, read: true })), unreadCount: 0 })),
}));
