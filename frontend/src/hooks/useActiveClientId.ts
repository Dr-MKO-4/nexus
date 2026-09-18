import { useAuthStore, useUIStore } from "@/store";

/**
 * La plupart des endpoints backend sont scopés par `client_id` (voir
 * api.ts)  pour un utilisateur MANAGER/VIEWER, c'est simplement
 * `user.client_id`. Pour un ADMIN (`client_id` NULL, compte interne, voir
 * backend/db/models/users.py), c'est le client choisi via le sélecteur du
 * Header (`GET /clients`, backend/api/routes/clients.py, ajouté suite à un
 * audit  avant ce correctif, aucun endpoint "lister les clients" n'existait
 * et un admin ne pouvait rien afficher).
 */
export function useActiveClientId(): string | null {
  const user = useAuthStore((state) => state.user);
  const adminSelectedClientId = useUIStore((state) => state.adminSelectedClientId);
  if (user?.role === "admin") return adminSelectedClientId;
  return user?.client_id ?? null;
}
