/**
 * O modo minimalista no Chromium de verdade: ligado nas Preferências, o card
 * de receitas perde a linha do "usa 6 de 6"; a escolha continua depois de
 * recarregar, marcada no <html> antes da primeira pintura; desligar traz a
 * linha de volta. Início, Receitas e Despensa passam pelo axe no modo ligado,
 * sem rolagem para os lados, e as capturas dos dois modos ficam em
 * `e2e/resultados/`.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const MOTOR = `http://127.0.0.1:${PORTA_MOTOR}`;
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

function marcador(info: TestInfo): string {
  const projeto = info.project.name.replace(/[^a-z0-9]/gi, "");
  return `m${projeto}${info.testId.replace(/[^a-z0-9]/gi, "").slice(-6)}${Date.now().toString(36)}`.toLowerCase();
}

/** Liga ou desliga o modo pelas Preferências, como ela faria, e fecha a folha. */
async function modoMinimalista(page: Page, ligado: boolean) {
  await page.getByRole("button", { name: "Preferências" }).click();
  const folha = page.getByRole("dialog", { name: "Preferências" });
  const interruptor = folha.getByRole("switch", { name: "Modo minimalista" });
  await expect(interruptor).toBeChecked({ checked: !ligado });
  await folha.getByText("Modo minimalista", { exact: true }).click();
  await expect(interruptor).toBeChecked({ checked: ligado });
  await page.keyboard.press("Escape");
  await expect(folha).toBeHidden();
}

test("ligado, o card de receitas esconde a conta; continua depois de recarregar; desligado, a conta volta", async ({
  page,
  request,
}, info) => {
  const m = marcador(info);
  const resposta = await request.post(`${MOTOR}/api/receitas`, {
    data: { url: `https://www.tudogostoso.com.br/receita/bolo-de-fuba-${m}-com-o-que-tem` },
  });
  expect(resposta.ok()).toBe(true);
  const { dados: bolo } = (await resposta.json()) as { dados: { nome: string } };

  await page.goto(`/receitas?q=${m}`, { waitUntil: "networkidle" });
  const card = page.getByRole("article").filter({ has: page.getByRole("link", { name: bolo.nome }) });
  const conta = card.getByText(/^usa \d+ de \d+ ingredientes/);
  await expect(conta).toBeVisible();

  await modoMinimalista(page, true);
  await expect(page.locator("html")).toHaveAttribute("data-minimalista", "ligado");
  await expect(conta).toBeHidden();
  await expect(card.getByRole("link", { name: bolo.nome })).toBeVisible();
  await expect(card.getByText("Com o que a senhora tem")).toBeVisible();

  await page.reload({ waitUntil: "commit" });
  // Antes de o React carregar, o script do <head> já marcou o <html>.
  await page.waitForSelector("body");
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-minimalista"))).toBe("ligado");
  await page.waitForLoadState("networkidle");
  await expect(conta).toBeHidden();

  await modoMinimalista(page, false);
  await expect(page.locator("html")).toHaveAttribute("data-minimalista", "desligado");
  await expect(conta).toBeVisible();
});

test("Início, Receitas e Despensa no modo minimalista: sem problema sério no axe, sem rolagem para os lados", async ({
  page,
}, info) => {
  for (const modo of ["desligado", "ligado"] as const) {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.evaluate((valor) => localStorage.setItem("minimalista", valor), modo);
    for (const [nome, rota] of [
      ["inicio", "/"],
      ["receitas", "/receitas"],
      ["despensa", "/despensa"],
    ] as const) {
      await page.goto(rota, { waitUntil: "networkidle" });
      await expect(page.locator("html")).toHaveAttribute("data-minimalista", modo);
      await page.screenshot({ path: info.outputPath(`${nome}-minimalista-${modo}.png`), fullPage: true });
      if (modo === "desligado") continue;
      const larguras = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, janela: window.innerWidth }));
      expect(larguras.pagina, `${rota} rola para os lados`).toBeLessThanOrEqual(larguras.janela);
      const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
      const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
      expect(graves, `${rota}: violações sérias ou críticas do axe`).toEqual([]);
    }
  }
});
