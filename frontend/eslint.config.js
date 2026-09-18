import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import { globalIgnores } from "eslint/config";

// Config plate ESLint 9  absente jusqu'ici malgré les dépendances déjà
// listées dans package.json (`npm run lint` échouait faute de fichier de
// config, constaté en l'exécutant réellement) : template standard Vite
// React+TS (react-hooks recommended + react-refresh en mode Vite).
export default tseslint.config([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended, reactHooks.configs["recommended-latest"], reactRefresh.configs.vite],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { window: "readonly", document: "readonly" },
    },
  },
]);
