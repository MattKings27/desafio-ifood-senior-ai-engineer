/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Configuração dos testes de interface.
 *
 * O limiar de cobertura fica aqui e não no CI de propósito: o mesmo número tem
 * que valer na máquina de quem escreve e no portão que reprova. Piso em dois
 * lugares é piso que diverge.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/teste/preparo.ts"],
    include: ["src/**/*.{test,a11y.test}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/componentes/**", "src/lib/**"],
      // O motor é exercitado pelos testes de Python; aqui interessa o que a
      // interface faz com a resposta dele.
      exclude: ["**/*.d.ts", "src/app/**"],
      // Pisos fixados no que o CI já provou alcançar, não num número
      // aspiracional: um piso que o próprio portão não atinge é portão
      // quebrado, e um piso que ninguém chega perto de tocar não é piso.
      thresholds: {
        statements: 95,
        branches: 95,
        functions: 95,
        lines: 95,
      },
    },
  },
});
