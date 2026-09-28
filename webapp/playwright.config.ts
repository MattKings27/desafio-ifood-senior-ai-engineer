import { defineConfig } from "@playwright/test";

/**
 * Testes ponta a ponta da interface, no Chromium de verdade.
 *
 * Sobem dois processos: o motor falso (`e2e/motor-falso/servidor.mjs`, que
 * serve as fixtures de `contratos/web/`) e o Next em produção
 * (`next build && next start`), com `MISE_API` apontando para o motor falso.
 * Assim, tanto os pedidos do servidor quanto os do navegador (pelo proxy
 * `/motor`) batem nele. O `next build` grava o destino do proxy: depois de
 * rodar estes testes, um `next start` comum precisa de um build novo (o
 * `make web` usa o `next dev`, que não é afetado).
 *
 * Quatro projetos: claro e escuro (pela emulação de `prefers-color-scheme`), a
 * 390 px (celular) e a 1280 px (computador). As capturas de página inteira
 * ficam em `e2e/resultados/`, que o CI guarda como artefato. Um quinto,
 * `por-ultimo`, roda depois dos quatro o que muda o estado de todos no motor
 * falso (o "Tenho tudo isso" da cozinha).
 */

const PORTA_WEB = Number(process.env.PORTA_WEB ?? 3210);
const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const NO_CI = Boolean(process.env.CI);

/** Os testes que mudam o estado de todos no motor falso: rodam sozinhos, no fim. */
const POR_ULTIMO = /por-ultimo\.spec\.ts$/;

const CELULAR = { width: 390, height: 844 };
const COMPUTADOR = { width: 1280, height: 900 };

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/resultados",
  fullyParallel: true,
  forbidOnly: NO_CI,
  retries: NO_CI ? 1 : 0,
  workers: NO_CI ? 2 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: NO_CI ? [["list"], ["github"]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORTA_WEB}`,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "claro-390", testIgnore: POR_ULTIMO, use: { viewport: CELULAR, colorScheme: "light", hasTouch: true } },
    { name: "escuro-390", testIgnore: POR_ULTIMO, use: { viewport: CELULAR, colorScheme: "dark", hasTouch: true } },
    { name: "claro-1280", testIgnore: POR_ULTIMO, use: { viewport: COMPUTADOR, colorScheme: "light" } },
    { name: "escuro-1280", testIgnore: POR_ULTIMO, use: { viewport: COMPUTADOR, colorScheme: "dark" } },
    // O que muda a cozinha de todos ("Tenho tudo isso") roda depois dos outros quatro.
    {
      name: "por-ultimo",
      testMatch: POR_ULTIMO,
      dependencies: ["claro-390", "escuro-390", "claro-1280", "escuro-1280"],
      use: { viewport: COMPUTADOR, colorScheme: "light" },
    },
  ],
  webServer: [
    {
      command: "node e2e/motor-falso/servidor.mjs",
      url: `http://127.0.0.1:${PORTA_MOTOR}/saude/vivo`,
      env: { PORTA: String(PORTA_MOTOR) },
      reuseExistingServer: !NO_CI,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `npx next build && npx next start -p ${PORTA_WEB} -H 127.0.0.1`,
      url: `http://127.0.0.1:${PORTA_WEB}/manifest.webmanifest`,
      env: { MISE_API: `http://127.0.0.1:${PORTA_MOTOR}`, NEXT_TELEMETRY_DISABLED: "1" },
      timeout: 600_000,
      reuseExistingServer: !NO_CI,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
