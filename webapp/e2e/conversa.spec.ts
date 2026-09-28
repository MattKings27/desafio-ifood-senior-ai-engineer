/**
 * A conversa com o agente no Chromium de verdade, contra o motor falso.
 *
 * Cada teste usa uma sessão própria do chat no motor falso (o cookie
 * `e2e-sessao`), então os turnos de um teste nunca aparecem em outro, nem na
 * fumaça que roda ao lado. O motor falso escolhe o roteiro do turno pelo que
 * ela escreve (ver a seção da conversa em `e2e/motor-falso/servidor.mjs`).
 */

import AxeBuilder from "@axe-core/playwright";
import type { BrowserContext, Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const MOTOR = `http://127.0.0.1:${PORTA_MOTOR}`;
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

function ehCelular(info: TestInfo): boolean {
  return info.project.name.endsWith("-390");
}

async function sessaoPropria(context: BrowserContext, info: TestInfo): Promise<string> {
  const sessao = `${info.project.name}-${info.testId}-${Date.now()}`.replace(/[^\w-]/g, "");
  const base = info.project.use.baseURL ?? "http://127.0.0.1:3210";
  await context.addCookies([{ name: "e2e-sessao", value: sessao, url: base }]);
  return sessao;
}

/** Uma conversa nova e vazia, que passa a ser a atual da sessão (como "Começar outra conversa"). */
async function conversaNova(page: Page, sessao: string) {
  const resposta = await page.request.post(`${MOTOR}/api/conversas`, { headers: { Cookie: `e2e-sessao=${sessao}` }, data: {} });
  expect(resposta.status()).toBe(201);
}

async function paginaDaConversa(page: Page) {
  await page.goto("/conversa", { waitUntil: "networkidle" });
  const caixa = page.getByRole("textbox", { name: "Mensagem para o agente" });
  await expect(caixa).toBeEnabled();
  return caixa;
}

async function mandar(page: Page, texto: string) {
  const caixa = page.getByRole("textbox", { name: "Mensagem para o agente" });
  await caixa.fill(texto);
  await page.getByRole("button", { name: "Enviar" }).click();
}

const log = (page: Page) => page.getByRole("log", { name: "Mensagens da conversa" });

/** Espera as transições que terminam (o painel deslizando), para a captura sair parada. */
async function semAnimacao(page: Page) {
  await page.evaluate(async () => {
    const finitas = document.getAnimations().filter((a) => a.effect?.getComputedTiming().endTime !== Infinity);
    await Promise.all(finitas.map((a) => a.finished.catch(() => undefined)));
  });
}

test.describe("a conversa", () => {
  test("os valores ficam escondidos durante a resposta, e o texto conferido aparece no fim", async ({ page, context }, info) => {
    await conversaNova(page, await sessaoPropria(context, info));
    await paginaDaConversa(page);
    await expect(page.getByText("Olá, Dona Maria")).toBeVisible();
    await mandar(page, "Quanto sai a porção de arroz com frango?");

    // O rascunho chega com o brilho no lugar de cada valor, e nenhum dígito.
    await expect(log(page).getByText("valor em conferência").first()).toBeAttached();
    await expect(log(page).getByText("R$ ···").first()).toBeVisible();
    const rascunho = await log(page).innerText();
    expect(rascunho).not.toMatch(/2,47|2,75/);
    await expect(page.getByText("Os valores aparecem quando eu terminar de conferir a conta.")).toBeVisible();

    // A conta fecha: o texto conferido toma o lugar do rascunho.
    await expect(log(page).getByText("R$ 2,47")).toBeVisible({ timeout: 15_000 });
    await expect(log(page).getByText("R$ ···")).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Sugestões de resposta" }).getByRole("button", { name: "Quanto cobrar?" })).toBeVisible();
    await expect(page.getByText("Ver o que eu fiz (1 passo)")).toBeVisible();
  });

  test("parar a resposta no meio", async ({ page, context }, info) => {
    await conversaNova(page, await sessaoPropria(context, info));
    await paginaDaConversa(page);
    await mandar(page, "Me conta devagar tudo sobre a despensa");
    await expect(log(page).getByText("Olhando sua despensa")).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Olhando sua despensa…" })).toBeAttached();
    await page.getByRole("button", { name: "Parar", exact: true }).click();
    await expect(log(page).getByText("Parei. O que já foi anotado continua anotado.")).toBeVisible();
    await expect(log(page).getByRole("button", { name: "Perguntar de novo" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Enviar" })).toBeVisible();
  });

  test("recarregar no meio da resposta continua de onde parou", async ({ page, context }, info) => {
    await conversaNova(page, await sessaoPropria(context, info));
    await paginaDaConversa(page);
    await mandar(page, "Me conta devagar tudo sobre a despensa");
    await expect(log(page).getByText("Olhando sua despensa")).toBeVisible();
    await expect(page).toHaveURL(/\/conversa\?c=/);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(log(page).getByText("Me conta devagar tudo sobre a despensa")).toBeVisible();
    await expect(page.getByText(/Trabalhando há/)).toBeVisible();
    await expect(log(page).getByText("Olhei tudo com calma: a despensa, a planilha, as receitas e o orçamento.")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/Trabalhando há/)).toHaveCount(0);
  });

  test("o botão de um card manda a ação, e o backend diz o que anotou", async ({ page, context }, info) => {
    const sessao = await sessaoPropria(context, info);
    await conversaNova(page, sessao);
    await paginaDaConversa(page);
    await mandar(page, "Preciso de ajuda com a cozinha");
    const card = page.getByRole("article", { name: "A senhora tem forno em casa?" });
    await expect(card).toBeVisible();
    await expect(card.getByText("Vale para: Arroz com frango.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Enviar" })).toBeVisible();
    await card.getByRole("button", { name: "Tenho", exact: true }).click();
    await expect(log(page).getByText("Anotei: a senhora tem forno.")).toBeVisible();
    await expect(log(page).getByText("Anotado. Com o forno, o arroz com frango continua de pé.")).toBeVisible();
    const resposta = await page.request.get(`${MOTOR}/__conversa/ultimo-pedido`, { headers: { Cookie: `e2e-sessao=${sessao}` } });
    const { pedido } = await resposta.json();
    expect(pedido).toMatchObject({
      texto: "Tenho forno.",
      acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
    });
    expect(typeof pedido.id_cliente).toBe("string");
  });

  test("a página da conversa não tem problema sério de acessibilidade, nem rola para os lados", async ({ page, context }, info) => {
    await conversaNova(page, await sessaoPropria(context, info));
    await paginaDaConversa(page);
    await mandar(page, "Quanto sai a porção de arroz com frango?");
    await expect(log(page).getByText("R$ 2,47")).toBeVisible({ timeout: 15_000 });
    const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
    const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
    expect(graves).toEqual([]);
    const larguras = await page.evaluate(() => ({
      documento: document.documentElement.scrollWidth,
      janela: document.documentElement.clientWidth,
    }));
    expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);
    await semAnimacao(page);
    await page.screenshot({ path: info.outputPath("conversa-com-resposta.png") });
  });
});

test.describe("os cards", () => {
  test("um card de cada tipo do contrato, sem problema sério de acessibilidade", async ({ page, context }, info) => {
    await conversaNova(page, await sessaoPropria(context, info));
    await paginaDaConversa(page);
    await mandar(page, "Me mostra todos os cartões");
    await expect(log(page).getByText("Aqui está um card de cada tipo que eu mostro na conversa.")).toBeVisible();
    const cards = log(page).getByRole("article");
    await expect(cards).toHaveCount(15);
    const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
    const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
    expect(graves).toEqual([]);
    const larguras = await page.evaluate(() => ({
      documento: document.documentElement.scrollWidth,
      janela: document.documentElement.clientWidth,
    }));
    expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);
    await semAnimacao(page);
    // Para as capturas: a conversa sai da caixa com rolagem e ocupa a página
    // inteira, então cada card aparece inteiro, sem nada flutuando por cima.
    await page.evaluate(() => {
      let elemento = document.querySelector('[role="log"]')?.parentElement ?? null;
      while (elemento && elemento !== document.body) {
        elemento.style.height = "auto";
        elemento.style.maxHeight = "none";
        elemento.style.overflow = "visible";
        elemento = elemento.parentElement;
      }
    });
    await page.screenshot({ path: info.outputPath("todos-os-cards.png"), fullPage: true });
    for (let indice = 0; indice < 15; indice += 1) {
      await cards.nth(indice).screenshot({ path: info.outputPath(`card-${String(indice + 1).padStart(2, "0")}.png`) });
    }
  });
});

test.describe("o painel em qualquer página", () => {
  test("abre com o contexto da página, que dá para tirar, e o Esc devolve o foco", async ({ page, context }, info) => {
    await sessaoPropria(context, info);
    await page.goto("/despensa", { waitUntil: "networkidle" });
    const entrada = ehCelular(info)
      ? page.getByRole("navigation", { name: "Seções principais" }).getByRole("link", { name: "Conversar", exact: true })
      : page.getByRole("link", { name: "Conversar", exact: true });
    await entrada.click();

    const painel = ehCelular(info)
      ? page.getByRole("dialog", { name: "Conversa com o agente" })
      : page.getByRole("complementary", { name: "Conversa com o agente" });
    await expect(painel).toBeVisible();
    await expect(page).toHaveURL(/\/despensa\?conversa=1$/);
    await expect(painel.getByText("Vendo:")).toBeVisible();
    await expect(painel.getByText(/Despensa/).first()).toBeVisible();
    await semAnimacao(page);
    await page.screenshot({ path: info.outputPath("painel-aberto.png") });

    await painel.getByRole("button", { name: "Tirar da mensagem: Despensa" }).click();
    await expect(painel.getByText("Vendo:")).toHaveCount(0);

    await painel.getByRole("textbox", { name: "Mensagem para o agente" }).focus();
    await page.keyboard.press("Escape");
    await expect(painel).toBeHidden();
    await expect(page).toHaveURL(/\/despensa$/);
    await expect(entrada).toBeFocused();
  });

  test("no computador, a página anda para o lado e continua usável; tela cheia leva à página da conversa", async ({ page, context }, info) => {
    test.skip(ehCelular(info), "só no computador");
    await sessaoPropria(context, info);
    await page.goto("/receitas", { waitUntil: "networkidle" });
    await page.getByRole("link", { name: "Conversar com o agente" }).click();
    const painel = page.getByRole("complementary", { name: "Conversa com o agente" });
    await expect(painel).toBeVisible();
    const deslocamento = await page.evaluate(() => getComputedStyle(document.body).paddingRight);
    expect(deslocamento).toBe("420px");
    await expect(page.getByRole("navigation", { name: "Seções", exact: true })).toBeVisible();
    const larguras = await page.evaluate(() => ({
      documento: document.documentElement.scrollWidth,
      janela: document.documentElement.clientWidth,
    }));
    expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);

    await painel.getByRole("link", { name: "Abrir em tela cheia" }).click();
    await expect(page).toHaveURL(/\/conversa/);
    await expect(page.getByRole("complementary", { name: "Conversa com o agente" })).toHaveCount(0);
  });

  test("o Perguntar de um card abre com o rascunho e não envia sozinho", async ({ page, context }, info) => {
    const sessao = await sessaoPropria(context, info);
    await page.goto("/conversa?rascunho=A%20embalagem%20da%20cobertura%20de%20chocolate%20tem%20&tela=despensa&tipo=pendencia&id=cobertura-de-chocolate&rotulo=Cobertura%20de%20chocolate", {
      waitUntil: "networkidle",
    });
    const caixa = page.getByRole("textbox", { name: "Mensagem para o agente" });
    await expect(caixa).toHaveValue("A embalagem da cobertura de chocolate tem ");
    await expect(page.getByText("Vendo:")).toBeVisible();
    await expect(page).toHaveURL(/\/conversa\?c=/);
    const pedido = await (await page.request.get(`${MOTOR}/__conversa/ultimo-pedido`, { headers: { Cookie: `e2e-sessao=${sessao}` } })).json();
    expect(pedido.pedido).toBeNull();
  });
});
