/**
 * A certeza antes do aceite, no Chromium de verdade, contra o motor falso: o
 * checklist de produção no detalhe da receita, o "Confirmar a cozinha" que
 * libera o "Pôr preço", o "O que toda cozinha tem" da cozinha e a guarda do
 * "Vou cobrar" no pôr preço.
 *
 * Os testes rodam em paralelo contra o mesmo motor falso. Cada um usa a
 * própria receita (o marcador no nome) ou o próprio item: confirmar a cozinha
 * de uma receita não mexe no perfil que os outros conferem, e o "Não tenho" de
 * cada projeto é de um item só dele. O "Tenho tudo isso", que muda a cozinha
 * de todos, fica nos testes da tela (vitest).
 */

import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const MOTOR = `http://127.0.0.1:${PORTA_MOTOR}`;
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** Um marcador que só este teste, neste projeto, usa: vira uma palavra do nome. */
function marcador(info: TestInfo): string {
  const projeto = info.project.name.replace(/[^a-z0-9]/gi, "");
  return `m${projeto}${info.testId.replace(/[^a-z0-9]/gi, "").slice(-6)}${Date.now().toString(36)}`.toLowerCase();
}

async function trazer(request: APIRequestContext, prato: string, situacao: string): Promise<{ slug: string; nome: string }> {
  const url = `https://www.tudogostoso.com.br/receita/${prato}-${situacao}`;
  const resposta = await request.post(`${MOTOR}/api/receitas`, { data: { url } });
  expect(resposta.ok()).toBe(true);
  return ((await resposta.json()) as { dados: { slug: string; nome: string } }).dados;
}

async function abrir(page: Page, caminho: string) {
  await page.goto(caminho, { waitUntil: "networkidle" });
}

async function semViolacoesGraves(page: Page) {
  const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
  const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
  expect(graves, "violações sérias ou críticas do axe").toEqual([]);
}

/** Nada passa da largura da tela: nem texto cortado, nem rolagem de lado. */
async function semRolagemDeLado(page: Page) {
  const larguras = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, janela: window.innerWidth }));
  expect(larguras.pagina).toBeLessThanOrEqual(larguras.janela);
}

test.describe("o checklist de produção da receita", () => {
  test("a nota na grade, o checklist em lista, e o Confirmar a cozinha libera o Pôr preço", async ({ page, request }, info) => {
    const m = marcador(info);
    const arroz = await trazer(request, `arroz-de-forno-${m}`, "supostos");

    await abrir(page, `/receitas?q=${m}`);
    const card = page.getByRole("article").filter({ hasText: arroz.nome });
    await expect(card.getByText("Confirme a cozinha")).toBeVisible();

    await abrir(page, `/receitas/${arroz.slug}`);
    const checklist = page.getByRole("region", { name: "Checklist de produção" });
    await expect(checklist.getByRole("heading", { level: 3 })).toHaveText(["Equipamentos", "Técnicas", "Rotina", "Ingredientes", "Pré-determinados"]);
    await expect(checklist.getByText("Suposto: confirme")).toHaveCount(2);
    const pergunta = "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?";
    const confirmar = checklist.getByRole("group", { name: pergunta });
    await expect(confirmar).toBeVisible();

    // Gostar do prato não basta: o Pôr preço espera também a cozinha confirmada.
    await page.getByRole("group", { name: "Gosta de fazer?" }).getByRole("button", { name: "Sim" }).click();
    const porPreco = page.getByRole("button", { name: "Pôr preço" });
    await expect(porPreco).toHaveAccessibleDescription(/Confirmar que a senhora tem fogão e que sabe refogar\./);
    await expect(porPreco).toHaveAttribute("aria-disabled", "true");
    await semViolacoesGraves(page);
    await semRolagemDeLado(page);
    await page.screenshot({ path: info.outputPath("checklist-antes.png"), fullPage: true });

    await confirmar.getByRole("button", { name: "Confirmar a cozinha" }).click();
    await expect(page.getByText("Anotei: a senhora tem fogão e sabe refogar.")).toBeVisible();
    await expect(checklist.getByRole("group", { name: pergunta })).toHaveCount(0);
    await expect(checklist.getByText("Suposto: confirme")).toHaveCount(0);
    await expect(porPreco).not.toHaveAttribute("aria-disabled", "true");
    await page.screenshot({ path: info.outputPath("checklist-depois.png"), fullPage: true });
  });
});

/** O item de "O que toda cozinha tem" que cada projeto responde: um só dele. */
const ITEM_DO_PROJETO: Record<string, string> = {
  "claro-390": "Ralador",
  "escuro-390": "Peneira",
  "claro-1280": "Tábua de corte",
  "escuro-1280": "Faca",
};

test.describe("o que toda cozinha tem", () => {
  test("cada item com a foto e o estado; o Não tenho grava só ele", async ({ page }, info) => {
    const nome = ITEM_DO_PROJETO[info.project.name];
    if (!nome) throw new Error(`projeto sem item: ${info.project.name}`);
    await abrir(page, "/cozinha");
    const cartao = page.getByRole("region", { name: "O que toda cozinha tem" });
    await expect(cartao).toBeVisible();
    await expect(cartao.getByRole("button", { name: "Tenho tudo isso" })).toBeVisible();
    const fogao = cartao.getByRole("listitem").filter({ hasText: "Fogão" });
    await expect(fogao.getByRole("img", { name: "Foto ilustrativa: Fogão" })).toHaveAttribute("src", /^\/motor\/imagens\/[0-9a-f]{32}$/);

    const linha = cartao.getByRole("listitem").filter({ hasText: nome });
    const naoTenho = linha.getByRole("button", { name: `Não tenho: ${nome}` });
    // Numa segunda tentativa o item já foi respondido: o estado é o mesmo.
    if (await naoTenho.isVisible()) await naoTenho.click();
    await expect(linha.getByText("A senhora não tem")).toBeVisible();
    await expect(linha.getByRole("button", { name: `Não tenho: ${nome}` })).toHaveCount(0);
    await semViolacoesGraves(page);
    await semRolagemDeLado(page);
    await page.screenshot({ path: info.outputPath("toda-cozinha.png"), fullPage: true });
  });
});

test.describe("a guarda do Vou cobrar", () => {
  test("o preço aparece, o Vou cobrar espera a cozinha, e Sim, tenho tudo isso libera", async ({ page, request }, info) => {
    const prato = `Galinhada supostos ${marcador(info)}`;
    await abrir(page, "/precificar");
    await page.getByRole("textbox", { name: /Nome do prato/ }).fill(prato);
    await page.getByRole("textbox", { name: /Ingredientes, um por linha/ }).fill("500 g de frango\n2 xícaras de arroz");
    await page.getByRole("textbox", { name: /Quanto tempo fica no fogo/ }).fill("40");
    await page.getByRole("button", { name: "Conferir se dá pra fazer" }).click();
    await expect(page.getByText("Três caminhos de preço")).toBeVisible();

    const guarda = page.getByRole("region", { name: "Antes de cobrar, falta confirmar" });
    await expect(guarda.getByText("Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?")).toBeVisible();
    const caminho = page.getByRole("region", { name: "Três caminhos de preço" }).getByRole("button", { name: /^Vou cobrar/ }).first();
    await expect(caminho).toHaveAttribute("aria-disabled", "true");
    await expect(caminho).toHaveAccessibleDescription(/Confirmar que a senhora tem fogão e que sabe refogar\./);
    await semViolacoesGraves(page);
    await semRolagemDeLado(page);
    await page.screenshot({ path: info.outputPath("guarda-do-preco.png"), fullPage: true });

    const confirmacao = page.waitForRequest((req) => req.url().endsWith("/motor/perfil/supostos/confirmar") && req.method() === "POST");
    await guarda.getByRole("button", { name: "Sim, tenho tudo isso" }).click();
    expect((await confirmacao).postDataJSON()).toEqual({ receita: prato.toLowerCase().replace(/[^a-z0-9]+/g, "-") });
    await expect(page.getByRole("region", { name: "Antes de cobrar, falta confirmar" })).toHaveCount(0);
    await expect(caminho).not.toHaveAttribute("aria-disabled", "true");
    const decisao = page.waitForRequest((req) => req.url().endsWith("/motor/decisao") && req.method() === "POST");
    await caminho.click();
    expect((await decisao).postDataJSON()).toMatchObject({ prato, decisao: "aceito" });
    await expect(page.getByRole("heading", { name: "Anotado" })).toBeVisible();

    // O prato deste teste sai do cardápio do motor falso, que é de todos os testes.
    expect((await request.post(`${MOTOR}/api/decisao`, { data: { prato, decisao: "recusado" } })).ok()).toBe(true);
  });
});
