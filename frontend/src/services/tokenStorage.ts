/**
 * Persistance des tokens JWT en localStorage  module séparé (pas dans
 * api.ts ni store/authStore.ts) pour que les deux puissent le consulter
 * sans dépendance circulaire : api.ts en a besoin pour son intercepteur de
 * requête (sans dépendre de Zustand), authStore.ts en a besoin pour
 * hydrater son état initial au chargement de l'app.
 */

const ACCESS_TOKEN_KEY = "nexus_access_token";
const REFRESH_TOKEN_KEY = "nexus_refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}
