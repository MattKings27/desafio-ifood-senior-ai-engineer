/**
 * A mãozinha no Chromium de verdade: tudo o que se clica (botão, link, chip,
 * opção, seletor, "Chat", "Responder", "Responder no chat", "Tenho", "Não
 * tenho", "Não sei") mostra `cursor: pointer`, e o que está desligado mostra
 * `not-allowed`. Conferido pelo estilo calculado em cada tela, no painel da
 * conversa e nas Preferências. Só no computador: no celular não há cursor.
 */

import type { BrowserContext, Locator, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const TELAS = [
  "/",
  "/despensa",
  "/receitas",
  "/receitas?aba=falta_resposta",
  "/receitas/f8fc24c7f065125e",
  "/cozinha",
  "/precificar",
  "/cardapio",
  "/trilha",
];

/** O que se clica: o seletor que a conferência percorre. */
const CLICAVEIS = [
  "button",
  "[role='button']",
  "a[href]",
  "summary",
  "select",
  "[role='tab']",
  "[role='switch']",
  "[role='option']",
  "[role='menuitem']",
  "label:has(> input[type='radio'])",
  "label:has(> input[type='checkbox'])",
  "input[type='range']",
].join(", ");

async function sessaoPropria(context: BrowserContext, info: TestInfo) {
  const sessao = `${info.project.name}-${info.testId}-${Date.now()}`.replace(/[^\w-]/g, "");
  await context.addCookies([{ name: "e2e-sessao", value: sessao, url: info.project.use.baseURL ?? "http://127.0.0.1:3210" }]);
}

/** Cada clicável visível dentro de `raiz` com o cursor errado, dito em texto para o relatório. */
async function cursoresErrados(raiz: Locator): Promise<string[]> {
  return raiz.evaluate((elemento, seletor) => {
    const errados: string[] = [];
    let vistos = 0;
    for (const alvo of elemento.querySelectorAll<HTMLElement>(seletor)) {
      const caixa = alvo.getBoundingClientRect();
      const estilo = getComputedStyle(alvo);
      // O que não aparece (sr-only, recolhido, folha fechada) não recebe o mouse.
      if (caixa.width < 2 || caixa.height < 2 || estilo.visibility === "hidden") continue;
      vistos += 1;
      const desligado =
        alvo.matches(":disabled") ||
        alvo.getAttribute("aria-disabled") === "true" ||
        alvo.closest("fieldset:disabled") !== null ||
        alvo.matches("label:has(> input:disabled)");
      const esperado = desligado ? "not-allowed" : "pointer";
      // Ocupado (a resposta indo para a API) mostra a espera, e é também um "não dá agora".
      const aceito = estilo.cursor === esperado || (desligado && ["progress", "wait"].includes(estilo.cursor));
      if (!aceito) {
        const nome = (alvo.getAttribute("aria-label") ?? alvo.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 50);
        errados.push(`<${alvo.tagName.toLowerCase()}> "${nome}": ${estilo.cursor} (esperado ${esperado})`);
      }
    }
    if (vistos === 0) errados.push("nenhum clicável visível: a conferência não conferiu nada");
    return errados;
  }, CLICAVEIS);
}

test.describe("a mãozinha em tudo o que se clica", () => {
  // Os projetos do celular têm toque, e no toque não há cursor.
  test.skip(({ hasTouch }) => hasTouch, "no celular não há cursor");

  for (const tela of TELAS) {
    test(`em ${tela}`, async ({ page }) => {
      await page.goto(tela, { waitUntil: "networkidle" });
      expect(await cursoresErrados(page.locator("body"))).toEqual([]);
    });
  }

  test("o desligado mostra que não dá", async ({ page }) => {
    await page.goto("/precificar", { waitUntil: "networkidle" });
    const botao = page.getByRole("button", { name: "Conferir se dá pra fazer" });
    await botao.evaluate((alvo) => alvo.setAttribute("disabled", ""));
    expect(await botao.evaluate((alvo) => getComputedStyle(alvo).cursor)).toBe("not-allowed");
    await botao.evaluate((alvo) => alvo.removeAttribute("disabled"));
    expect(await botao.evaluate((alvo) => getComputedStyle(alvo).cursor)).toBe("pointer");
  });

  test("no painel da conversa e nas Preferências", async ({ page, context }, info) => {
    await sessaoPropria(context, info);
    await page.goto("/despensa", { waitUntil: "networkidle" });
    await page.getByRole("link", { name: "Conversar com o agente" }).click();
    const painel = page.getByRole("complementary", { name: "Conversa com o agente" });
    await expect(painel).toBeVisible();
    await expect(painel.getByRole("textbox", { name: "Mensagem para o agente" })).toBeVisible();
    expect(await cursoresErrados(painel)).toEqual([]);

    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Preferências" }).click();
    const folha = page.getByRole("dialog", { name: "Preferências" });
    await expect(folha).toBeVisible();
    expect(await cursoresErrados(folha)).toEqual([]);
  });
});
