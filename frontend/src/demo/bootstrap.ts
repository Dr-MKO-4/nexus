/**
 * Amorçage de la démo, importé en premier par main.tsx (avant les stores) :
 * installe la garde `fetch` et ouvre une session fictive pour arriver
 * directement sur le tableau de bord. La page de connexion reste
 * accessible via « Déconnexion ».
 */
import { DEMO } from "./flag";
import { fakeToken } from "./adapter";
import { installFetchGuard } from "./fetchGuard";
import { getAccessToken, setTokens } from "@/services/tokenStorage";

if (DEMO) {
  installFetchGuard();
  try {
    if (!getAccessToken() && sessionStorage.getItem("nexus_demo_logged_out") !== "1") {
      setTokens(fakeToken(sessionStorage.getItem("nexus_demo_email") ?? "admin@exemple.org"), "demo-refresh");
    }
  } catch {
    /* stockage indisponible : la page de connexion s'affichera */
  }
}
