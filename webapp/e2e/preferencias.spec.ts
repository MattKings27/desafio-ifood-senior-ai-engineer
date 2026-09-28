/**
 * Preferências no Chromium de verdade: a engrenagem em toda rota, a 390 e a
 * 1280 px; o tema Claro, Escuro e Automático (seguindo o sistema emulado),
 * com a cor dos tokens de fato trocada; a escolha que sobrevive a recarregar,
 * aplicada antes da primeira pintura; o texto grande; o movimento reduzido;
 * e a folha sem problema sério de acessibilidade nem rolagem para os lados.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const ROTAS = ["/", "/despensa", "/receitas", "/cozinha", "/precificar", "/cardapio", "/trilha", "/conversa"];
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** O fundo da página e a superfície de cada tema (os tokens de `globals.css`). */
const CORES = {
  claro: { fundo: "rgb(247, 247, 247)", superficie: "rgb(255, 255, 255)" },
  escuro: { fundo: "rgb(18, 18, 20)", superficie: "rgb(28, 28, 30)" },
} as const;

/** Espera as transições que terminam (a folha deslizando), para a captura sair parada. */
async function semAnimacao(page: Page) {
  await page.evaluate(async () => {
    const finitas = document.getAnimations().filter((a) => a.effect?.getComputedTiming().endTime !== Infinity);
    await Promise.all(finitas.map((a) => a.finished.catch(() => undefined)));
  });
}

async function abrirPreferencias(page: Page) {
  const engrenagem = page.getByRole("button", { name: "Preferências" });
  await engrenagem.click();
  const folha = page.getByRole("dialog", { name: "Preferências" });
  await expect(folha).toBeVisible();
  return { engrenagem, folha };
}

async function escolher(page: Page, grupo: string, opcao: string) {
  await page.getByRole("dialog", { name: "Preferências" }).getByRole("group", { name: grupo }).getByText(opcao, { exact: true }).click();
}

/** O tema marcado, o fundo da página e a cor que o token da superfície pinta de fato. */
async function coresDaTela(page: Page) {
  return page.evaluate(() => {
    const sonda = document.createElement("div");
    sonda.style.background = "var(--color-superficie)";
    document.body.appendChild(sonda);
    const superficie = getComputedStyle(sonda).backgroundColor;
    sonda.remove();
    return {
      tema: document.documentElement.getAttribute("data-tema"),
      fundo: getComputedStyle(document.body).backgroundColor,
      superficie,
    };
  });
}

test("a engrenagem está no canto direito de toda rota", async ({ page }) => {
  for (const rota of ROTAS) {
    await page.goto(rota, { waitUntil: "domcontentloaded" });
    const engrenagem = page.getByRole("button", { name: "Preferências" });
    await expect(engrenagem, rota).toBeVisible();
    const caixa = await engrenagem.boundingBox();
    expect(caixa?.height ?? 0, rota).toBeGreaterThanOrEqual(44);
    // No canto direito: nada clicável da linha de cima do cabeçalho fica depois dela.
    const direitas = await page.evaluate(() => {
      const linha = document.querySelector("header > div");
      const visiveis = [...(linha?.querySelectorAll<HTMLElement>("a, button") ?? [])].filter((e) => e.getClientRects().length > 0);
      return visiveis.map((e) => ({ nome: e.getAttribute("aria-label") ?? e.textContent?.trim() ?? "", direita: e.getBoundingClientRect().right }));
    });
    const maisADireita = direitas.reduce((a, b) => (b.direita > a.direita ? b : a));
    expect(maisADireita.nome, rota).toBe("Preferências");
  }
});

test("Claro e Escuro trocam o tema e as cores na hora", async ({ page }) => {
  await page.goto("/despensa", { waitUntil: "networkidle" });
  await abrirPreferencias(page);
  await escolher(page, "Tema", "Escuro");
  await expect(page.locator("html")).toHaveAttribute("data-tema", "escuro");
  expect(await coresDaTela(page)).toEqual({ tema: "escuro", ...CORES.escuro });
  await escolher(page, "Tema", "Claro");
  await expect(page.locator("html")).toHaveAttribute("data-tema", "claro");
  expect(await coresDaTela(page)).toEqual({ tema: "claro", ...CORES.claro });
  const cor = await page.locator('meta[name="theme-color"]').first().getAttribute("content");
  expect(cor).toBe("#ffffff");
});

test("Automático segue o sistema, e acompanha quando ele muda", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/", { waitUntil: "networkidle" });
  await abrirPreferencias(page);
  await escolher(page, "Tema", "Escuro");
  await escolher(page, "Tema", "Automático");
  await expect(page.locator("html")).toHaveAttribute("data-tema", "claro");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-tema", "escuro");
  expect((await coresDaTela(page)).fundo).toBe(CORES.escuro.fundo);
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-tema", "claro");
});

test("a escolha continua depois de recarregar, aplicada antes da primeira pintura", async ({ page }) => {
  await page.goto("/cardapio", { waitUntil: "networkidle" });
  await abrirPreferencias(page);
  await escolher(page, "Tema", "Escuro");
  await escolher(page, "Tamanho do texto", "Grande");
  await escolher(page, "Movimento", "Reduzir");
  await page.reload({ waitUntil: "commit" });
  // Antes de o React carregar, o script do <head> já marcou o <html>.
  await page.waitForSelector("body");
  const marcas = await page.evaluate(() => ({
    tema: document.documentElement.getAttribute("data-tema"),
    texto: document.documentElement.getAttribute("data-texto"),
    movimento: document.documentElement.getAttribute("data-movimento"),
  }));
  expect(marcas).toEqual({ tema: "escuro", texto: "grande", movimento: "reduzir" });
  await page.waitForLoadState("networkidle");
  expect((await coresDaTela(page)).fundo).toBe(CORES.escuro.fundo);
  // Sem erro de hidratação por causa das marcas.
  const { folha } = await abrirPreferencias(page);
  await expect(folha.getByRole("radio", { name: "Escuro" })).toBeChecked();
  await expect(folha.getByRole("radio", { name: "Grande" })).toBeChecked();
});

test("texto grande aumenta a tela inteira, sem empurrar para os lados", async ({ page }) => {
  await page.goto("/despensa", { waitUntil: "networkidle" });
  const antes = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  await abrirPreferencias(page);
  await escolher(page, "Tamanho do texto", "Grande");
  await expect(page.locator("html")).toHaveAttribute("data-texto", "grande");
  const depois = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  expect(antes).toBe(16);
  expect(depois).toBe(18);
  await page.keyboard.press("Escape");
  const larguras = await page.evaluate(() => ({
    documento: document.documentElement.scrollWidth,
    janela: document.documentElement.clientWidth,
  }));
  expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);
});

test("reduzir movimento corta as transições", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await abrirPreferencias(page);
  await escolher(page, "Movimento", "Reduzir");
  await expect(page.locator("html")).toHaveAttribute("data-movimento", "reduzir");
  const duracao = await page.evaluate(() => getComputedStyle(document.querySelector("dialog[open]") as Element).transitionDuration);
  expect(duracao.split(",").every((d) => parseFloat(d) <= 0.001)).toBe(true);
});

test("a folha aberta não tem problema sério de acessibilidade, nem rola para os lados; Esc devolve o foco", async ({ page }, info) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const { engrenagem, folha } = await abrirPreferencias(page);
  for (const secao of ["Aparência", "Conversa", "Seus dados", "Sobre o agente"]) {
    await expect(folha.getByRole("heading", { name: secao })).toBeVisible();
  }
  await expect(folha.getByText(/Quem conversa com a senhora é o Claude Fable 5\.1/)).toBeVisible();
  await semAnimacao(page);
  await page.screenshot({ path: info.outputPath("preferencias.png") });
  await folha.getByRole("heading", { name: "Sobre o agente" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("preferencias-fim.png") });
  const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
  const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
  expect(graves).toEqual([]);
  const larguras = await page.evaluate(() => ({
    documento: document.documentElement.scrollWidth,
    janela: document.documentElement.clientWidth,
  }));
  expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);
  await page.keyboard.press("Escape");
  await expect(folha).toBeHidden();
  await expect(engrenagem).toBeFocused();
});

test("Seus dados: baixar a despensa em texto e a cópia de tudo", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const { folha } = await abrirPreferencias(page);
  const despensa = page.waitForEvent("download");
  await folha.getByRole("button", { name: "Baixar a despensa em texto" }).click();
  expect((await despensa).suggestedFilename()).toBe("despensa-da-dona-maria.txt");
  await expect(folha.getByText("Pronto: despensa-da-dona-maria.txt foi para os arquivos baixados.")).toBeVisible();
  const tudo = page.waitForEvent("download");
  await folha.getByRole("button", { name: "Baixar tudo" }).click();
  expect((await tudo).suggestedFilename()).toBe("sabor-da-maria-dados.json");
});

test("Seus dados: restaurar os dados da planilha pede confirmação, avisa e refaz a tela", async ({ page }) => {
  await page.goto("/despensa", { waitUntil: "networkidle" });
  const { folha } = await abrirPreferencias(page);
  await folha.getByRole("button", { name: "Restaurar os dados da planilha" }).click();
  const confirmacao = page.getByRole("alertdialog", { name: "Restaurar os dados da planilha?" });
  await expect(confirmacao).toBeVisible();
  await expect(confirmacao.getByText(/As receitas que eu já li continuam na grade/)).toBeVisible();

  // Cancelar não pede nada à API.
  await confirmacao.getByRole("button", { name: "Cancelar" }).click();
  await expect(confirmacao).toBeHidden();

  await folha.getByRole("button", { name: "Restaurar os dados da planilha" }).click();
  const pedido = page.waitForRequest((req) => req.url().endsWith("/motor/dados/restaurar") && req.method() === "POST");
  // Depois de restaurar, a tela de trás se refaz com o que a API diz agora.
  const refeita = page.waitForRequest((req) => req.method() === "GET" && req.headers()["rsc"] === "1");
  await page.getByRole("alertdialog", { name: "Restaurar os dados da planilha?" }).getByRole("button", { name: "Restaurar" }).click();
  expect((await pedido).postDataJSON()).toMatchObject({ confirmar: true });
  await expect(page.getByText(/Pronto, tudo voltou a ser como na planilha: 37 ingredientes, R\$ 663,39 pagos/)).toBeVisible();
  await refeita;
  await expect(page.getByRole("alertdialog")).toBeHidden();
});
