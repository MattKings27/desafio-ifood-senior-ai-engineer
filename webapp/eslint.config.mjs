import js from "@eslint/js";
import a11y from "eslint-plugin-jsx-a11y";
import globals from "globals";
import ts from "typescript-eslint";

/**
 * Flat config do ESLint 9.
 *
 * Não uso `eslint-config-next` porque ele aplica um patch no ESLint que falha
 * na flat config desta versão ("Failed to patch ESLint"). O que importa aqui é
 * a checagem estática de acessibilidade (o próprio time do iFood a declara
 * obrigatória em todo componente do design system deles), e ela vem direto do
 * `jsx-a11y`.
 */
export default [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "jsx-a11y": a11y },
    rules: {
      ...a11y.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
];
