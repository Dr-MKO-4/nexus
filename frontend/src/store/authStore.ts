import { create } from "zustand";

import * as api from "@/services/api";
import { clearTokens, getAccessToken } from "@/services/tokenStorage";
import type { User } from "@/types";

/**
 * Pas de middleware `persist` zustand ici : `tokenStorage.ts` (localStorage)
 * est DÉJÀ la persistance du token, utilisée par l'intercepteur axios
 * (api.ts)  dupliquer via `persist` créerait deux sources de vérité à
 * resynchroniser. `token`/`isAuthenticated` sont simplement HYDRATÉS depuis
 * `tokenStorage` à la création du store (lu une fois, au chargement de
 * l'app) ; `user` doit être re-fetché via `getMe()` après un rechargement
 * de page (pas caché, il peut changer côté serveur entre deux sessions).
 */
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Hydrate `user` depuis /auth/me si un token existe déjà (ex. après un
   * rechargement de page)  à appeler une fois au montage de l'app. */
  restoreSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: getAccessToken(),
  isAuthenticated: getAccessToken() !== null,
  isLoading: false,

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const tokens = await api.login(email, password);
      const user = await api.getMe();
      set({ token: tokens.access_token, user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    clearTokens();
    set({ token: null, user: null, isAuthenticated: false });
  },

  restoreSession: async () => {
    const token = getAccessToken();
    if (!token) return;
    try {
      const user = await api.getMe();
      set({ token, user, isAuthenticated: true });
    } catch {
      clearTokens();
      set({ token: null, user: null, isAuthenticated: false });
    }
  },
}));
