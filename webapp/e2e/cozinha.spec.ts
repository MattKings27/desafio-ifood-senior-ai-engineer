/**
 * A cozinha no Chromium de verdade, contra o motor falso: mudar um item grava
 * sozinho e mostra o que mudou nas receitas, "não sei" continua "não sei"
 * depois de recarregar, os limites da rotina gravam com + e −, e a busca com o
 * filtro pela situação ficam na URL.
 *
 * O estado do motor falso é um só para os quatro projetos, que rodam juntos:
 * cada projeto mexe no seu próprio item (e no seu próprio limite), e escolhe a
 * resposta que ainda não está marcada, para a mudança ser sempre de verdade.
 */

import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

/** O item de cada projeto, com a receita que ele muda no motor falso. */
const ITEM_DO_PROJETO: Record<string, { nome: string; receita: string }> = {
  "claro-390": { nome: "Forno", receita: "Frango assado" },
  "escuro-390": { nome: "Liquidificador", receita: "Bolo de fubá" },
  "claro-1280": { nome: "Panela de pressão", receita: "Feijão tropeiro" },
  "escuro-1280": { nome: "Refogar", receita: "Arroz com frango" },
};

/** O limite de cada projeto: um número, para testar o + e o "Não sei". */
const LIMITE_DO_PROJETO: Record<string, string> = {
  "claro-390": "Porções por leva",
  "escuro-390": "Espaço livre na geladeira",
  "claro-1280": "Aparelhos fortes ligados juntos",
  "escuro-1280": "Horas cozinhando de uma vez",
};

async function abrir(page: Page, caminho = "/cozinha") {
  await page.goto(caminho, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { level: 1, name: "Cozinha" })).toBeVisible();
}

function doProjeto<T>(mapa: Record<string, T>, info: TestInfo): T {
  const valor = mapa[info.project.name];
  if (!valor) throw new Error(`projeto sem item: ${info.project.name}`);
  return valor;
}

/** A linha do item: o `li` que tem o grupo de rádios com o nome dele. */
const linhaDoItem = (page: Page, nome: string) =>
  page.getByRole("listitem").filter({ has: page.getByRole("group", { name: nome, exact: true }) });

test.describe("a cozinha", () => {
  test("mudar um item grava sozinho e mostra o que mudou nas receitas; não sei continua não sei", async ({ page }, info) => {
    const { nome, receita } = doProjeto(ITEM_DO_PROJETO, info);
    await abrir(page);
    const linha = linhaDoItem(page, nome);
    const grupo = linha.getByRole("group", { name: nome, exact: true });
    await expect(grupo).toBeVisible();

    // Uma resposta que ainda não está marcada: "Não sei", ou "Não tenho" se já é "Não sei".
    const naoSei = grupo.getByRole("radio", { name: "Não sei" });
    const jaEraNaoSei = await naoSei.isChecked();
    const outra = jaEraNaoSei ? /^Não (tenho|faço)$/ : "Não sei";
    await grupo.getByText(outra, { exact: typeof outra === "string" }).click();

    const nota = linha.getByText(new RegExp(receita));
    await expect(nota).toBeVisible();
    await expect(linha.getByText("Salvo")).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: `${nome}:` })).toBeAttached();

    if (jaEraNaoSei) {
      await grupo.getByText("Não sei", { exact: true }).click();
      await expect(linha.getByText("Salvo")).toBeVisible();
    }
    // Depois de recarregar, a resposta é "não sei", e não "ainda não perguntei".
    await abrir(page);
    const depois = linhaDoItem(page, nome);
    await expect(depois.getByRole("radio", { name: "Não sei" })).toBeChecked();
    await expect(depois.getByText("A senhora disse que não sabe")).toBeVisible();
    await expect(depois.getByText("Ainda não perguntei")).toHaveCount(0);
  });

  test("os limites da rotina: + grava o número, e Não sei fica marcado", async ({ page }, info) => {
    const rotulo = doProjeto(LIMITE_DO_PROJETO, info);
    await abrir(page);
    const limites = page.getByRole("region", { name: "Limites da rotina" });
    const linha = limites.getByRole("listitem").filter({ has: page.getByLabel(rotulo, { exact: true }) });
    const campo = linha.getByLabel(rotulo, { exact: true });
    await linha.getByRole("button", { name: `Mais: ${rotulo}` }).click();
    await expect(linha.getByText("Salvo")).toBeVisible();
    const numero = await campo.inputValue();
    // O tempo por cozinhada é em horas, com vírgula ("1,5").
    expect(numero).toMatch(/^\d+(,\d+)?$/);

    await abrir(page);
    await expect(page.getByLabel(rotulo, { exact: true })).toHaveValue(numero);

    const deNovo = page.getByRole("region", { name: "Limites da rotina" }).getByRole("listitem").filter({ has: page.getByLabel(rotulo, { exact: true }) });
    const naoSei = deNovo.getByRole("button", { name: "Não sei" });
    await naoSei.click();
    await expect(naoSei).toHaveAttribute("aria-pressed", "true");
    await expect(deNovo.getByText("Salvo")).toBeVisible();
    await abrir(page);
    const recarregada = page.getByRole("region", { name: "Limites da rotina" }).getByRole("listitem").filter({ has: page.getByLabel(rotulo, { exact: true }) });
    await expect(recarregada.getByRole("button", { name: "Não sei" })).toHaveAttribute("aria-pressed", "true");
    await expect(recarregada.getByText("A senhora disse que não sabe")).toBeVisible();
  });

  test("a busca e o filtro pela situação ficam na URL", async ({ page }) => {
    await abrir(page);
    await page.getByRole("searchbox", { name: "Buscar equipamento ou técnica" }).fill("forn");
    await expect(page).toHaveURL(/q=forn/);
    await expect(page.getByRole("group", { name: "Forno", exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "Forno elétrico", exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "Fogão", exact: true })).toHaveCount(0);

    await page.getByRole("group", { name: "Situação" }).getByText("Suposto").click();
    await expect(page).toHaveURL(/situacao=suposto/);
    await expect(page.getByText("Nada com esses filtros")).toBeVisible();
    await page.getByRole("searchbox", { name: "Buscar equipamento ou técnica" }).fill("");
    await expect(page.getByRole("group", { name: "Fogão", exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "Forno elétrico", exact: true })).toHaveCount(0);

    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByRole("group", { name: "Situação" }).getByRole("checkbox", { name: /Suposto/ })).toBeChecked();
    await expect(page.getByRole("group", { name: "Fogão", exact: true })).toBeVisible();
  });

  test("cada item mostra a miniatura pelo proxy, do mesmo tamanho, com o crédito; sem foto, o ícone", async ({ page }) => {
    await abrir(page);
    const fogao = linhaDoItem(page, "Fogão");
    const foto = fogao.getByRole("img", { name: "Foto ilustrativa: Fogão" });
    await expect(foto).toHaveAttribute("src", /^\/motor\/imagens\/[0-9a-f]{32}$/);
    await expect(foto).toHaveAttribute("loading", "lazy");
    await expect.poll(() => foto.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    const credito = /^Foto: .+, Wikimedia Commons$/;
    await expect(fogao.locator("[data-miniatura]")).toHaveAttribute("title", credito);
    await expect(fogao.getByText(credito)).toBeVisible();

    const reducao = linhaDoItem(page, "Redução de molho");
    await reducao.scrollIntoViewIfNeeded();
    await expect(reducao.locator("img")).toHaveCount(0);
    for (const caixa of [fogao.locator("[data-miniatura]"), reducao.locator("[data-miniatura]")]) {
      expect(await caixa.boundingBox()).toMatchObject({ width: 64, height: 64 });
    }
  });
});
