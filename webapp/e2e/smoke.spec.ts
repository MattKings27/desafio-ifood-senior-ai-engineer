/**
 * Fumaça da interface: toda rota, nos dois temas, a 390 e a 1280 px.
 *
 * Em cada rota: captura de página inteira (artefato do CI), nenhum erro nem
 * aviso de console, nem de hidratação, nenhum problema sério ou crítico do axe
 * (WCAG 2.2 AA), nenhuma rolagem para os lados no celular, nenhuma palavra
 * proibida na tela, o fundo do tema de fato aplicado, e a casca certa para o
 * tamanho (barra de baixo no celular; navegação e botão flutuante no computador).
 *
 * Uma tela com um problema conhecido entra em DIVIDAS_DAS_TELAS_ANTIGAS, com
 * o motivo (hoje a lista está vazia). A lista é uma catraca: se a dívida sumir
 * e continuar listada, o teste falha, para a exceção sair junto com o problema.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { PALAVRAS_PROIBIDAS } from "../src/lib/formato";

type Rota = { caminho: string; nome: string; status?: number };

const ROTAS: readonly Rota[] = [
  { caminho: "/", nome: "inicio" },
  { caminho: "/despensa", nome: "despensa" },
  { caminho: "/receitas", nome: "receitas" },
  { caminho: "/receitas?aba=falta_resposta", nome: "receitas-falta-resposta" },
  { caminho: "/receitas?aba=ranking", nome: "receitas-ranking" },
  { caminho: "/receitas/f8fc24c7f065125e", nome: "receita" },
  // Com o esqueleto de carregamento (loading.tsx), o "não encontrei" chega depois
  // de a página começar a ir: é um 404 brando, com status 200 e noindex.
  { caminho: "/receitas/uma-receita-que-nao-existe", nome: "receita-nao-encontrada" },
  { caminho: "/cozinha", nome: "cozinha" },
  { caminho: "/precificar", nome: "precificar" },
  { caminho: "/cardapio", nome: "cardapio" },
  { caminho: "/trilha", nome: "historico" },
  { caminho: "/conversa", nome: "conversa" },
  {
    caminho: `/conversa?rascunho=${encodeURIComponent("Dá pra eu fazer Bolo de cenoura?")}`,
    nome: "conversa-com-rascunho",
  },
  { caminho: "/um-endereco-que-nao-existe", nome: "nao-encontrada", status: 404 },
];

type Divida = { jargao?: string[]; axe?: string[] };

/**
 * O que alguma tela ainda tem de errado, por rota e por projeto. Todas as
 * telas foram trocadas e a lista está vazia; se uma dívida nova precisar
 * entrar, entra aqui com o motivo. É uma catraca: a lista tem que bater
 * exatamente com o que o teste encontra, então consertar a tela sem tirar a
 * entrada também reprova.
 */
const DIVIDAS_DAS_TELAS_ANTIGAS: Readonly<Record<string, (projeto: string) => Divida>> = {};

const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const FUNDO = { claro: "rgb(247, 247, 247)", escuro: "rgb(18, 18, 20)" } as const;

function temaDoProjeto(info: TestInfo): "claro" | "escuro" {
  return info.project.name.startsWith("escuro") ? "escuro" : "claro";
}

function ehCelular(info: TestInfo): boolean {
  return info.project.name.endsWith("-390");
}

/** Erros e avisos de console, e erros de página, a partir de agora. */
function vigiarErros(pagina: Page) {
  const erros: string[] = [];
  pagina.on("console", (mensagem) => {
    if (mensagem.type() === "error" || mensagem.type() === "warning") erros.push(`${mensagem.type()}: ${mensagem.text()}`);
  });
  pagina.on("pageerror", (erro) => erros.push(erro.message));
  return erros;
}

async function abrir(pagina: Page, caminho: string) {
  const resposta = await pagina.goto(caminho, { waitUntil: "networkidle" });
  await pagina.evaluate(() => document.fonts.ready);
  return resposta;
}

async function textoVisivel(pagina: Page): Promise<string> {
  return pagina.evaluate(() => document.body.innerText);
}

for (const rota of ROTAS) {
  test(`${rota.nome}: tema, acessibilidade, largura e linguagem`, async ({ page }, info) => {
    const erros = vigiarErros(page);
    const resposta = await abrir(page, rota.caminho);
    expect(resposta?.status(), "status HTTP").toBe(rota.status ?? 200);

    // A captura fica na pasta do teste, em e2e/resultados/, que o CI guarda.
    await page.screenshot({ path: info.outputPath(`${rota.nome}.png`), fullPage: true });

    // O tema do sistema foi aplicado antes da pintura, e o fundo é o do tema.
    const tema = temaDoProjeto(info);
    await expect(page.locator("html")).toHaveAttribute("data-tema", tema);
    const fundo = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(fundo, "fundo da página").toBe(FUNDO[tema]);

    // Nenhum erro nem aviso de console, de hidratação ou de página. A 404 da
    // própria página que não existe é o que se espera dela.
    const inesperados = erros.filter(
      (erro) => !(rota.status === 404 && /status of 404/.test(erro)),
    );
    expect(inesperados, "erros no console").toEqual([]);

    const divida: Divida = DIVIDAS_DAS_TELAS_ANTIGAS[rota.caminho]?.(info.project.name) ?? {};

    // Acessibilidade: nada sério nem crítico no WCAG 2.2 AA.
    const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
    const graves = analise.violations
      .filter((violacao) => violacao.impact === "serious" || violacao.impact === "critical")
      .map((violacao) => violacao.id)
      .sort();
    expect(graves, "violações sérias ou críticas do axe").toEqual([...(divida.axe ?? [])].sort());

    // Nada empurra a página para os lados no celular.
    if (ehCelular(info)) {
      const larguras = await page.evaluate(() => ({
        documento: document.documentElement.scrollWidth,
        janela: document.documentElement.clientWidth,
      }));
      expect(larguras.documento, "rolagem para os lados").toBeLessThanOrEqual(larguras.janela);
    }

    // Nenhum jargão na tela dela.
    const texto = await textoVisivel(page);
    const encontradas = PALAVRAS_PROIBIDAS.filter(({ padrao }) => padrao.test(texto)).map(({ palavra }) => palavra);
    expect(encontradas, "palavras proibidas na tela").toEqual(divida.jargao ?? []);

    // A casca certa para o tamanho de tela. O botão flutuante e o Conversar
    // da barra de baixo têm o mesmo nome; só um deles fica à vista por vez.
    const barra = page.getByRole("navigation", { name: "Seções principais" });
    const navegacao = page.getByRole("navigation", { name: "Seções", exact: true });
    const conversar = page.getByRole("link", { name: "Conversar", exact: true });
    if (ehCelular(info)) {
      await expect(barra).toBeVisible();
      await expect(barra.getByRole("link", { name: "Conversar", exact: true })).toBeVisible();
      await expect(navegacao).toBeHidden();
    } else {
      await expect(barra).toBeHidden();
      await expect(navegacao).toBeVisible();
      await expect(page.getByRole("link", { name: "Conversar com o agente" })).toBeVisible();
      if (rota.caminho.startsWith("/conversa")) await expect(conversar).toHaveCount(0);
      else await expect(conversar).toBeVisible();
    }
  });
}

test("a escolha dela vence o tema do sistema", async ({ page }, info) => {
  const contrario = temaDoProjeto(info) === "escuro" ? "claro" : "escuro";
  await page.addInitScript((tema) => window.localStorage.setItem("tema", tema), contrario);
  await abrir(page, "/");
  await expect(page.locator("html")).toHaveAttribute("data-tema", contrario);
  const fundo = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(fundo).toBe(FUNDO[contrario]);
  const cor = await page.locator('meta[name="theme-color"]').first().getAttribute("content");
  expect(cor).toBe(contrario === "escuro" ? "#1c1c1e" : "#ffffff");
});

test("trocar o tema nas Preferências vale na hora e continua depois de recarregar", async ({ page }, info) => {
  await abrir(page, "/despensa");
  const contrario = temaDoProjeto(info) === "escuro" ? "Claro" : "Escuro";
  // A engrenagem é a mesma nas duas larguras, no canto direito do cabeçalho.
  await page.getByRole("button", { name: "Preferências" }).click();
  await page
    .getByRole("dialog", { name: "Preferências" })
    .getByRole("group", { name: "Tema" })
    .getByText(contrario, { exact: true })
    .click();
  const esperado = contrario === "Escuro" ? "escuro" : "claro";
  await expect(page.locator("html")).toHaveAttribute("data-tema", esperado);
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("data-tema", esperado);
});

test("o link de pular leva direto ao conteúdo", async ({ page }) => {
  await abrir(page, "/");
  await page.keyboard.press("Tab");
  const pular = page.getByRole("link", { name: "Pular para o conteúdo" });
  await expect(pular).toBeFocused();
  await expect(pular).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#conteudo")).toBeFocused();
});

test.describe("no celular", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) > 400, "só a 390 px");

  test("a folha Mais leva às outras seções, e o Esc devolve o foco", async ({ page }) => {
    await abrir(page, "/");
    const mais = page.getByRole("button", { name: "Mais", exact: true });
    await mais.click();
    const folha = page.getByRole("dialog", { name: "Mais" });
    await expect(folha).toBeVisible();
    await expect(folha.getByRole("link")).toHaveText([/Cozinha/, /Pôr preço/, /Histórico/]);
    await page.keyboard.press("Escape");
    await expect(folha).toBeHidden();
    await expect(mais).toBeFocused();

    await mais.click();
    await folha.getByRole("link", { name: /Cozinha/ }).click();
    await expect(page).toHaveURL(/\/cozinha$/);
    await expect(folha).toBeHidden();
  });

  test("a barra de baixo marca onde ela está, e o Conversar abre a conversa por cima", async ({ page }) => {
    await abrir(page, "/receitas");
    const barra = page.getByRole("navigation", { name: "Seções principais" });
    await expect(barra.getByRole("link", { name: "Receitas" })).toHaveAttribute("aria-current", "page");
    const conversar = barra.getByRole("link", { name: "Conversar" });
    await conversar.click();
    const folha = page.getByRole("dialog", { name: "Conversa com o agente" });
    await expect(folha).toBeVisible();
    await expect(folha.getByText("Vendo:")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(folha).toBeHidden();
    await expect(conversar).toBeFocused();
    await abrir(page, "/conversa");
    await expect(barra.getByRole("link", { name: "Conversar" })).toHaveAttribute("aria-current", "page");
  });
});

test.describe("no computador", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 1000, "só a 1280 px");

  test("a navegação cabe numa linha a 1024 px, sem rolar para os lados", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 800 });
    await abrir(page, "/");
    const navegacao = page.getByRole("navigation", { name: "Seções", exact: true });
    await expect(navegacao).toBeVisible();
    const topos = await navegacao
      .getByRole("link")
      .evaluateAll((links) => links.map((link) => Math.round(link.getBoundingClientRect().top)));
    expect(topos).toHaveLength(7);
    expect(new Set(topos).size, "todas as seções na mesma linha").toBe(1);
    const larguras = await page.evaluate(() => ({
      documento: document.documentElement.scrollWidth,
      janela: document.documentElement.clientWidth,
    }));
    expect(larguras.documento).toBeLessThanOrEqual(larguras.janela);
  });

  test("o botão flutuante e a pílula do cabeçalho abrem o painel ao lado, sem sair da página", async ({ page }) => {
    await abrir(page, "/despensa");
    const flutuante = page.getByRole("link", { name: "Conversar", exact: true });
    await flutuante.click();
    const painel = page.getByRole("complementary", { name: "Conversa com o agente" });
    await expect(painel).toBeVisible();
    await expect(page).toHaveURL(/\/despensa\?conversa=1$/);
    await expect(flutuante).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(painel).toBeHidden();
    await expect(flutuante).toBeFocused();

    await page.getByRole("link", { name: "Conversar com o agente" }).click();
    await expect(painel).toBeVisible();
    await painel.getByRole("link", { name: "Abrir em tela cheia" }).click();
    await expect(page).toHaveURL(/\/conversa/);
    await expect(page.getByRole("link", { name: "Conversar", exact: true })).toHaveCount(0);
  });

  test("as Preferências fecham com Esc e devolvem o foco à engrenagem", async ({ page }) => {
    await abrir(page, "/");
    const engrenagem = page.getByRole("button", { name: "Preferências" });
    await engrenagem.click();
    await expect(page.getByRole("group", { name: "Tema" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("group", { name: "Tema" })).toBeHidden();
    await expect(engrenagem).toBeFocused();
  });
});
