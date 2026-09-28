/**
 * A tela de receitas no Chromium de verdade, contra o motor falso, nos quatro
 * projetos (claro e escuro, 390 e 1280 px).
 *
 * Os testes rodam em paralelo contra o mesmo motor falso, então cada um traz
 * as próprias receitas pelo endereço (o motor falso monta a receita pelo
 * último pedaço do caminho: `...-com-o-que-tem`, `...-falta-tempo`) com um
 * marcador único no nome, e filtra a grade por ele. Assim a contagem de um
 * teste nunca conta a receita de outro, e mudar uma receita não mexe na de
 * ninguém.
 */

import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const MOTOR = `http://127.0.0.1:${PORTA_MOTOR}`;
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

type Trazida = { slug: string; nome: string };

/** Um marcador que só este teste, neste projeto, usa: vira uma palavra do nome das receitas. */
function marcador(info: TestInfo): string {
  const projeto = info.project.name.replace(/[^a-z0-9]/gi, "");
  return `m${projeto}${info.testId.replace(/[^a-z0-9]/gi, "").slice(-6)}${Date.now().toString(36)}`.toLowerCase();
}

/** Traz uma receita pelo endereço, direto no motor falso (como a tela faria). */
async function trazer(request: APIRequestContext, prato: string, situacao: string): Promise<Trazida> {
  const url = `https://www.tudogostoso.com.br/receita/${prato}-${situacao}`;
  const resposta = await request.post(`${MOTOR}/api/receitas`, { data: { url } });
  expect(resposta.ok()).toBe(true);
  const { dados } = (await resposta.json()) as { dados: Trazida };
  return dados;
}

async function abrir(page: Page, caminho: string) {
  await page.goto(caminho, { waitUntil: "networkidle" });
}

const abas = (page: Page) => page.getByRole("tablist", { name: "Receitas" });
const aba = (page: Page, nome: string) => abas(page).getByRole("tab", { name: new RegExp(`^${nome}`) });

async function semViolacoesGraves(page: Page) {
  // O axe mede a tela parada: um toast ainda entrando, no meio da opacidade, não é o
  // contraste que ela vê.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))));
  const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
  // Cada violação com os elementos que a causam, para a falha dizer onde olhar.
  const graves = analise.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
  expect(graves, "violações sérias ou críticas do axe").toEqual([]);
}

test.describe("a grade de receitas", () => {
  test("as abas mostram as contagens da API, e o que a cozinha não permite não aparece", async ({ page, request }, info) => {
    const m = marcador(info);
    const bolo = await trazer(request, `bolo-de-fuba-${m}`, "com-o-que-tem");
    const torta = await trazer(request, `torta-de-frango-${m}`, "comprando");
    const pudim = await trazer(request, `pudim-${m}`, "falta-tempo");
    const lasanha = await trazer(request, `lasanha-${m}`, "nao-da");

    await abrir(page, `/receitas?q=${m}`);
    await expect(aba(page, "Dá para fazer")).toHaveAttribute("aria-selected", "true");
    await expect(aba(page, "Dá para fazer")).toContainText("2");
    await expect(aba(page, "Falta uma resposta sua")).toContainText("1");
    await expect(aba(page, "Ranking")).toContainText("0");

    // Receita nova ainda não disse o gosto: fica em "Ainda não me disse se gosta", com a pergunta.
    const grade = page.getByRole("list", { name: "Ainda não me disse se gosta" });
    await expect(grade.getByRole("link", { name: bolo.nome })).toBeVisible();
    await expect(grade.getByRole("link", { name: torta.nome })).toBeVisible();
    await expect(grade.getByText("Com o que a senhora tem")).toBeVisible();
    await expect(grade.getByText(/Comprando R\$\s6,00, cabe nos R\$\s80,00/)).toBeVisible();
    await expect(grade.getByRole("group", { name: `A senhora gosta de fazer ${bolo.nome}?` })).toBeVisible();
    await expect(page.getByText(lasanha.nome)).toHaveCount(0);
    await semViolacoesGraves(page);

    await aba(page, "Falta uma resposta sua").click();
    await expect(page).toHaveURL(/aba=falta_resposta/);
    const pendentes = page.getByRole("list", { name: "Ainda não me disse se gosta" });
    await expect(pendentes.getByRole("link", { name: pudim.nome })).toBeVisible();
    // O tempo no fogo não é pergunta: o card pergunta o gosto, e só.
    await expect(pendentes.getByRole("group", { name: `A senhora gosta de fazer ${pudim.nome}?` })).toBeVisible();
    await expect(page.getByText(/Mais ou menos quantos minutos\?/)).toHaveCount(0);
    await expect(page.getByText(lasanha.nome)).toHaveCount(0);
    await semViolacoesGraves(page);

    await aba(page, "Ranking").click();
    await expect(page.getByText("Nenhuma receita com esses filtros")).toBeVisible();
    await page.screenshot({ path: info.outputPath("receitas-abas.png"), fullPage: true });
  });

  test("a busca e os filtros ficam na URL e voltam depois de recarregar", async ({ page, request }, info) => {
    const m = marcador(info);
    await trazer(request, `arroz-${m}`, "com-o-que-tem");
    const feijoada = await trazer(request, `feijoada-${m}`, "comprando");

    await abrir(page, "/receitas");
    await page.getByRole("searchbox", { name: "Buscar receitas" }).fill(m.toUpperCase());
    await expect(page).toHaveURL(new RegExp(`q=${m.toUpperCase()}`));
    await expect(page.getByText("2 encontradas")).toBeVisible();
    await expect(page.getByRole("button", { name: `Busca: ${m.toUpperCase()}: tirar este filtro` })).toBeVisible();

    await page.getByRole("button", { name: /^Filtros/ }).click();
    const folha = page.getByRole("dialog", { name: "Filtros" });
    await folha.getByText("Só com o que a senhora tem").click();
    await expect(page).toHaveURL(/so_com_o_que_tenho=true/);
    await expect(folha.getByRole("button", { name: "Ver 1 receita" })).toBeVisible();
    await folha.getByRole("button", { name: "Ver 1 receita" }).click();
    await expect(folha).toBeHidden();
    await expect(page.getByText("1 encontrada")).toBeVisible();
    await expect(page.getByRole("link", { name: feijoada.nome })).toHaveCount(0);

    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByRole("searchbox", { name: "Buscar receitas" })).toHaveValue(m.toUpperCase());
    await expect(page.getByText("1 encontrada")).toBeVisible();
    await page.getByRole("button", { name: "Só com o que tenho: tirar este filtro" }).click();
    await expect(page).not.toHaveURL(/so_com_o_que_tenho/);
    await expect(page.getByText("2 encontradas")).toBeVisible();
    await expect(page.getByRole("link", { name: feijoada.nome })).toBeVisible();
  });

  test("trazer uma receita pelo endereço: nova, já conhecida, e a página sem receita", async ({ page }, info) => {
    const m = marcador(info);
    const url = `https://www.panelinha.com.br/receita/escondidinho-${m}-comprando`;
    await abrir(page, "/receitas");
    await page.getByRole("button", { name: "Trazer uma receita" }).click();
    const folha = page.getByRole("dialog", { name: "Trazer uma receita" });
    const campo = folha.getByRole("textbox", { name: "Endereço da receita" });
    await expect(campo).toBeFocused();

    await campo.fill("receita de bolo");
    await folha.getByRole("button", { name: "Trazer" }).click();
    await expect(folha.getByText(/não parece de uma página/)).toBeVisible();

    await campo.fill(url);
    await folha.getByRole("button", { name: "Trazer" }).click();
    await expect(folha.getByText(`Trouxe Escondidinho ${m}.`)).toBeVisible();
    await expect(folha.getByText("Ela está em Dá para fazer.")).toBeVisible();
    await expect(folha.getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", /\/receitas\/[0-9a-f]{16}$/);

    await folha.getByRole("button", { name: "Trazer outra" }).click();
    await campo.fill(url);
    await folha.getByRole("button", { name: "Trazer" }).click();
    await expect(folha.getByText(`Escondidinho ${m} já estava aqui.`)).toBeVisible();

    await folha.getByRole("button", { name: "Trazer outra" }).click();
    await campo.fill(`https://www.panelinha.com.br/receita/${m}-sem-receita`);
    await folha.getByRole("button", { name: "Trazer" }).click();
    await expect(folha.getByText("Esse site não publica a receita de um jeito que eu leia. Tenta outro?")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(folha).toBeHidden();
    await expect(page.getByRole("list", { name: "Ainda não me disse se gosta" }).getByRole("link", { name: `Escondidinho ${m}` })).toBeVisible();
  });

  test("o gosto ali mesmo: a receita muda de seção, com Desfazer, e Não gosto de fazer guarda a que ela não quer", async ({
    page,
    request,
  }, info) => {
    const m = marcador(info);
    const pudim = await trazer(request, `pudim-de-leite-${m}`, "com-o-que-tem");
    await abrir(page, `/receitas?q=${m}`);
    const aindaNao = page.getByRole("list", { name: "Ainda não me disse se gosta" });
    const pergunta = aindaNao.getByRole("group", { name: `A senhora gosta de fazer ${pudim.nome}?` });
    await expect(pergunta).toBeVisible();
    await semViolacoesGraves(page);

    await pergunta.getByRole("button", { name: "Gosto de fazer" }).click();
    const gosto = page.getByRole("list", { name: "Gosto de fazer" });
    await expect(gosto.getByRole("link", { name: pudim.nome })).toBeVisible();
    await expect(page.getByText(/Anotei que a senhora gosta de fazer pudim de leite .*\. Ela foi para Gosto de fazer\./)).toBeVisible();
    await page.getByRole("button", { name: "Desfazer" }).click();
    await expect(aindaNao.getByRole("link", { name: pudim.nome })).toBeVisible();

    await aindaNao.getByRole("group", { name: `A senhora gosta de fazer ${pudim.nome}?` }).getByRole("button", { name: "Não gosto" }).click();
    const naoGosto = page.getByRole("button", { name: /^Não gosto de fazer/ });
    await expect(naoGosto).toContainText("1");
    await expect(naoGosto).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("link", { name: pudim.nome })).toHaveCount(0);
    await naoGosto.click();
    const recusadas = page.getByRole("list", { name: "Não gosto de fazer" });
    await expect(recusadas.getByRole("link", { name: pudim.nome })).toBeVisible();
    await semViolacoesGraves(page);
    await page.screenshot({ path: info.outputPath("receitas-secoes-do-gosto.png"), fullPage: true });

    await recusadas.getByRole("button", { name: `Mudei de ideia: gosto de fazer ${pudim.nome}` }).click();
    await expect(page.getByRole("list", { name: "Gosto de fazer" }).getByRole("link", { name: pudim.nome })).toBeVisible();
  });

  test("com nada para fazer, a página abre em Falta uma resposta sua: primeiro o gosto, depois a pergunta da cozinha", async ({
    page,
    request,
  }, info) => {
    const m = marcador(info);
    const bolo = await trazer(request, `bolo-de-forno-${m}`, "falta-forno");
    await abrir(page, `/receitas?q=${m}`);
    // Na mesma ida ao servidor, sem redirecionar: a URL fica como veio.
    await expect(aba(page, "Falta uma resposta sua")).toHaveAttribute("aria-selected", "true");
    await expect(page).not.toHaveURL(/aba=/);

    // O gosto vem antes da cozinha: nada de forno, nem no card nem no painel, enquanto ela não disser.
    const painel = page.getByRole("region", { name: "Responda e eu libero mais receitas" });
    await expect(painel).toHaveCount(0);
    const card = page.getByRole("list", { name: "Ainda não me disse se gosta" }).getByRole("article").filter({ hasText: bolo.nome });
    await expect(card.getByRole("radio", { name: "Não tenho" })).toHaveCount(0);
    await card.getByRole("button", { name: "Gosto de fazer" }).click();

    // Com o gosto dito, a pergunta do forno no card (a cozinha do motor falso é de todos: ninguém responde aqui).
    const gosto = page.getByRole("list", { name: "Gosto de fazer" }).getByRole("article").filter({ hasText: bolo.nome });
    await expect(gosto.getByRole("radio", { name: "Não tenho" })).toHaveCount(1);
    await expect(painel).toBeVisible();
    await expect(painel.getByText(bolo.nome, { exact: true })).toBeVisible();
    await semViolacoesGraves(page);
  });

  test("Falta uma resposta sua diz quantas usam só o que ela tem, sem cortar nome, pergunta nem resposta", async ({
    page,
    request,
  }, info) => {
    const m = marcador(info);
    const bolo = await trazer(request, `bolo-de-fuba-cremoso-com-goiabada-e-queijo-da-vovo-${m}`, "falta-forno");
    await trazer(request, `estrogonofe-de-frango-${m}`, "falta-preco");
    await abrir(page, `/receitas?aba=falta_resposta&q=${m}`);
    await expect(aba(page, "Falta uma resposta sua")).toContainText("2");
    const resumo = "1 receita usa só o que a senhora tem; falta só a senhora me dizer se tem forno. 1 receita pede alguma compra.";
    await expect(page.getByText(resumo)).toBeVisible();

    const aindaNao = page.getByRole("list", { name: "Ainda não me disse se gosta" });
    await expect(aindaNao.getByRole("link", { name: bolo.nome })).toBeVisible();
    await aindaNao.getByRole("article").filter({ hasText: bolo.nome }).getByRole("button", { name: "Gosto de fazer" }).click();
    const pendentes = page.getByRole("tabpanel");
    const card = page.getByRole("list", { name: "Gosto de fazer" }).getByRole("article").filter({ hasText: bolo.nome });
    await expect(card.getByRole("radio", { name: "Não tenho" })).toHaveCount(1);
    await expect(card.getByText("Não tenho", { exact: true })).toBeVisible();
    // Nada cortado: nem reticências, nem linhas escondidas, nem texto maior que a caixa.
    const cortados = await pendentes.evaluate((lista) =>
      [...lista.querySelectorAll<HTMLElement>("*")]
        // O texto só para leitor de tela (sr-only) é recortado de propósito, e não conta.
        .filter((el) => el.closest(".sr-only") === null)
        .filter((el) => {
          const estilo = getComputedStyle(el);
          const reticencias = estilo.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth + 1;
          const linhas = estilo.webkitLineClamp !== "none" && estilo.webkitLineClamp !== "";
          const vaza = el.matches("button, h3, p, span, a") && el.scrollWidth > el.clientWidth + 1;
          return reticencias || linhas || vaza;
        })
        .map((el) => `${el.tagName.toLowerCase()}: ${el.textContent?.slice(0, 40)}`),
    );
    expect(cortados, "texto cortado nos cards de Falta uma resposta sua").toEqual([]);
    await page.screenshot({ path: info.outputPath("falta-uma-resposta.png"), fullPage: true });
    // O vazio de "Dá para fazer" sem filtro ("Nenhuma receita confirmada ainda", com a mesma
    // frase) fica nos testes da tela: aqui a busca pelo marcador é um filtro, e o vazio é o dele.
  });

  test("procurar mais receitas mostra a procura e o que ela achou", async ({ page }) => {
    await abrir(page, "/receitas");
    await page.getByRole("button", { name: "Procurar mais receitas" }).click();
    await expect(page.getByText("Encontrei 1 receita nova.")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Procurar mais receitas" })).toBeEnabled();
  });
});

test.describe("o detalhe de uma receita", () => {
  test("mostra o que ela tem e o que falta comprar, com a conta de cada compra", async ({ page, request }, info) => {
    const m = marcador(info);
    const torta = await trazer(request, `torta-${m}`, "comprando");
    await abrir(page, `/receitas/${torta.slug}`);
    await expect(page.getByRole("heading", { level: 1, name: torta.nome })).toBeVisible();
    await expect(page.getByText("Dá, comprando o que falta")).toBeVisible();

    const tem = page.getByRole("heading", { name: "A senhora tem" }).locator("..");
    await expect(tem.getByText("Carne moída (patinho)")).toBeVisible();
    await expect(tem.getByText("1,5 kg")).toBeVisible();
    await expect(tem.getByText("Sobra").first()).toBeVisible();

    const falta = page.getByRole("heading", { name: "Falta comprar" }).locator("..");
    await expect(falta.getByText("milho verde", { exact: true })).toBeVisible();
    await expect(falta.getByText(/Compra: 1 lata, R\$ 6,00/)).toBeVisible();
    await expect(falta.getByText("Cabe no orçamento")).toBeVisible();
    await expect(falta.getByText(/1 lata × R\$ 6,00/)).toBeVisible();

    await expect(page.getByRole("heading", { name: "Modo de preparo" })).toBeVisible();
    await expect(page.getByText("mais uma boca do fogão ao mesmo tempo")).toBeVisible();
    await semViolacoesGraves(page);
    await page.screenshot({ path: info.outputPath("receita-detalhe.png"), fullPage: true });
  });

  test("peso, preço e a linha que a leitura não entendeu nunca viram pergunta no detalhe", async ({ page, request }, info) => {
    const m = marcador(info);
    const frango = await trazer(request, `frango-com-alcaparras-${m}`, "falta-medida");
    await abrir(page, `/receitas/${frango.slug}`);
    await expect(page.getByRole("heading", { level: 1, name: frango.nome })).toBeVisible();
    const checklist = page.getByRole("region", { name: "Checklist de produção" });
    const ingredientes = page.getByRole("region", { name: "Ingredientes" });
    for (const regiao of [checklist, ingredientes]) {
      for (const texto of [/quanto pesa/i, /Quanto custa/, /É o seu/, /Não entendi quanto vai/]) {
        await expect(regiao.getByText(texto)).toHaveCount(0);
      }
    }
    await expect(page.getByRole("textbox", { name: "Quanto pesa" })).toHaveCount(0);
    // O pré-determinado aparece como estimado, com a fonte, e o corrigir discreto.
    await expect(checklist.getByText("Estimado").first()).toBeVisible();
    await semViolacoesGraves(page);
    await page.screenshot({ path: info.outputPath("receita-sem-pergunta-de-numero.png"), fullPage: true });
  });

  test("as estrelas e as notas ficam depois de recarregar", async ({ page, request }, info) => {
    const m = marcador(info);
    const bolo = await trazer(request, `bolo-${m}`, "com-o-que-tem");
    await abrir(page, `/receitas/${bolo.slug}`);
    const avaliacao = page.getByRole("region", { name: "Avaliação da senhora" });

    await avaliacao.getByRole("group", { name: "Gosta de fazer?" }).getByRole("button", { name: "Sim" }).click();
    await expect(avaliacao.getByRole("button", { name: "Sim" })).toHaveAttribute("aria-pressed", "true");
    // A quarta estrela de Sabor (o rádio é o rótulo inteiro, com a estrela desenhada).
    await avaliacao.getByRole("group", { name: "Sabor" }).locator("label").nth(3).click();
    await expect(avaliacao.getByText(/está em .* lugar no ranking da senhora/)).toBeVisible();
    await expect(avaliacao.getByText("Pontuação", { exact: true })).toBeVisible();

    const notas = avaliacao.getByRole("textbox", { name: "Notas da senhora" });
    await notas.fill("Servir com farofa de alho.");
    await expect(avaliacao.getByText(/^Salvo/)).toBeVisible();

    await page.reload({ waitUntil: "networkidle" });
    const depois = page.getByRole("region", { name: "Avaliação da senhora" });
    await expect(depois.getByRole("button", { name: "Sim" })).toHaveAttribute("aria-pressed", "true");
    await expect(depois.getByRole("group", { name: "Sabor" }).getByRole("radio", { name: "4 estrelas" })).toBeChecked();
    await expect(depois.getByRole("textbox", { name: "Notas da senhora" })).toHaveValue("Servir com farofa de alho.");
    await depois.getByText("Como calculamos").click();
    await expect(depois.getByText(/pontuação = 100 ×/)).toBeVisible();
  });

  test("Pôr preço fica desabilitado com o que falta, e libera com a cozinha e o gosto", async ({ page, request }, info) => {
    await abrir(page, "/receitas/f8fc24c7f065125e");
    const porPreco = page.getByRole("button", { name: "Pôr preço" });
    await expect(porPreco).toHaveAttribute("aria-disabled", "true");
    await expect(porPreco).toHaveAccessibleDescription(/^Antes de aceitar, faltam 2 coisas\. Confirmar que a senhora tem fogão/);

    const m = marcador(info);
    const arroz = await trazer(request, `arroz-carreteiro-${m}`, "com-o-que-tem");
    await abrir(page, `/receitas/${arroz.slug}`);
    await expect(porPreco).toHaveAttribute("aria-disabled", "true");
    await expect(porPreco).toHaveAccessibleDescription(/Dizer se a senhora gosta de fazer arroz carreteiro/);

    await page.getByRole("group", { name: "Gosta de fazer?" }).getByRole("button", { name: "Sim" }).click();
    await expect(porPreco).not.toHaveAttribute("aria-disabled", "true");
    await porPreco.click();
    const caixa = page.getByRole("textbox", { name: "Mensagem para o agente" });
    await expect(caixa).toBeVisible();
    await expect(caixa).toHaveValue(`Quero pôr preço na ${arroz.nome}`);
  });

  test("a receita que não existe mostra que não encontrou", async ({ page }) => {
    await abrir(page, "/receitas/uma-receita-que-nao-existe");
    await expect(page.getByRole("heading", { name: "Não encontrei esta receita" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Ver as receitas" })).toHaveAttribute("href", "/receitas");
  });
});
