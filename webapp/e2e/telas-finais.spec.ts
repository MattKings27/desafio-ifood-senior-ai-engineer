/**
 * O início, o cardápio, o histórico e o pôr preço no Chromium de verdade,
 * contra o motor falso, nos quatro projetos (claro e escuro, 390 e 1280 px).
 *
 * O cardápio do motor falso é de todos os testes, que rodam em paralelo: o
 * teste que tira e desfaz acrescenta o próprio prato, com um nome que só ele
 * usa, e só mexe nele.
 */

import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const PORTA_MOTOR = Number(process.env.PORTA_MOTOR ?? 8790);
const MOTOR = `http://127.0.0.1:${PORTA_MOTOR}`;

async function abrir(page: Page, caminho: string) {
  await page.goto(caminho, { waitUntil: "networkidle" });
}

function marcador(info: TestInfo): string {
  const projeto = info.project.name.replace(/[^a-z0-9]/gi, "");
  return `${projeto}${Date.now().toString(36)}`.toLowerCase();
}

/**
 * O cartão do prato no cardápio. A lista mostra seis e guarda o resto atrás do
 * "Ver mais"; os testes, juntos, acrescentam pratos ao motor falso, e o prato
 * deste teste pode ter ficado depois do sexto.
 */
async function cartaoDoPrato(page: Page, prato: string) {
  const pratos = page.getByRole("region", { name: "Os pratos" });
  const link = pratos.getByRole("link", { name: prato, exact: true });
  const verMais = pratos.getByRole("button", { name: /^Ver mais/ });
  if ((await link.count()) === 0 && (await verMais.count()) > 0) await verMais.click();
  // O `has` procura dentro do cartão: o link vai sem a região na frente.
  return { link, cartao: pratos.getByRole("article").filter({ has: page.getByRole("link", { name: prato, exact: true }) }) };
}

/** A caixa da conversa aberta (a folha no celular, o painel no computador). */
const caixaDaConversa = (page: Page) => page.getByRole("textbox", { name: "Mensagem para o agente" });

test.describe("o início", () => {
  test("os números são links para as telas, e o do orçamento abre o painel da despensa", async ({ page }) => {
    await abrir(page, "/");
    const numeros = page.getByRole("region", { name: "Os números de agora" });
    await expect(numeros.getByRole("link", { name: "Cozinha" })).toHaveAttribute("href", "/cozinha");
    await expect(numeros.getByRole("link", { name: "Receitas" })).toHaveAttribute("href", "/receitas");
    await expect(numeros.getByRole("link", { name: "Cardápio" })).toHaveAttribute("href", "/cardapio");
    await numeros.getByRole("link", { name: "Orçamento" }).click();
    await expect(page).toHaveURL(/\/despensa#orcamento$/);
    await expect(page.getByText("Contas que quase saíram erradas")).toHaveCount(0);
  });

  test("o dinheiro parado mostra cinco e o Ver mais abre o resto, cada um levando ao ingrediente", async ({ page }) => {
    await abrir(page, "/");
    const parado = page.getByRole("region", { name: "Onde o dinheiro está parado" });
    await expect(parado.getByRole("article")).toHaveCount(5);
    await parado.getByRole("button", { name: /Ver mais/ }).click();
    await expect(parado.getByRole("article")).toHaveCount(37);
    await expect(parado.getByRole("link", { name: "Alcaparras" })).toHaveAttribute("href", "/despensa/alcaparras");
  });

  test("o botão Chat da pergunta abre a conversa com a pergunta, sem mandar", async ({ page }) => {
    await abrir(page, "/");
    const perguntas = page.getByRole("region", { name: /Preciso perguntar/ });
    await perguntas.getByRole("button", { name: "Chat" }).first().click();
    const caixa = caixaDaConversa(page);
    await expect(caixa).toBeVisible();
    await expect(caixa).toHaveValue(/^Sobre a pergunta “A senhora tem forno/);
    await expect(page.getByText("Vendo:").first()).toBeVisible();
  });
});

test.describe("o cardápio", () => {
  test("tirar do cardápio pede confirmação, e o Desfazer do aviso traz o prato de volta", async ({ page, request }, info) => {
    const prato = `Escondidinho ${marcador(info)}`;
    expect((await request.post(`${MOTOR}/__cardapio/prato`, { data: { prato } })).ok()).toBe(true);
    await abrir(page, "/cardapio");
    // O nome exato: o histórico também tem "Ver a receita: <prato>".
    const { link: doPrato, cartao } = await cartaoDoPrato(page, prato);
    await expect(cartao).toBeVisible();
    await cartao.getByRole("button", { name: "Tirar do cardápio" }).click();
    const confirmacao = page.getByRole("alertdialog", { name: `Tirar ${prato} do cardápio?` });
    await confirmacao.getByRole("button", { name: "Tirar do cardápio" }).click();
    await expect(page.getByText(`A senhora tirou o ${prato.toLowerCase()} do cardápio.`).first()).toBeVisible();
    await expect(doPrato).toHaveCount(0);
    await page.getByRole("button", { name: "Desfazer", exact: true }).click();
    await expect(doPrato).toBeVisible();
  });

  test("Mudar preço abre a conversa com o pedido escrito", async ({ page }) => {
    await abrir(page, "/cardapio");
    const cartao = page.getByRole("article").filter({ has: page.getByRole("link", { name: "Frango com milho verde" }) });
    await cartao.getByRole("button", { name: "Mudar preço" }).click();
    await expect(caixaDaConversa(page)).toHaveValue("Quero mudar o preço de frango com milho verde para ");
  });
});

test.describe("o histórico", () => {
  test("os filtros vão para a URL e a lista acompanha; o Ver mais traz as anteriores", async ({ page }) => {
    await abrir(page, "/trilha");
    await expect(page.getByRole("heading", { level: 1, name: "Histórico" })).toBeVisible();
    await page.getByRole("button", { name: "Ver mais" }).click();
    await expect(page.getByText("Olhei sua despensa, mas não deu certo.")).toBeVisible();
    await page.getByRole("group", { name: "O que" }).getByText("Cardápio", { exact: true }).click();
    await expect(page).toHaveURL(/\/trilha\?categoria=cardapio$/);
    await expect(page.getByText("2 registros")).toBeVisible();
    await expect(page.getByText("Calculei o custo por porção.")).toHaveCount(0);
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByText("2 registros")).toBeVisible();
  });
});

test.describe("o pôr preço", () => {
  test("os limites do controle e o lucro vêm da API, e o tempo no fogo volta na receita", async ({ page }) => {
    await abrir(page, "/precificar");
    await page.getByRole("textbox", { name: /Nome do prato/ }).fill("Bolo de teste");
    await page.getByRole("textbox", { name: /Ingredientes, um por linha/ }).fill("2 xícaras de farinha");
    await page.getByRole("button", { name: "Conferir se dá pra fazer" }).click();
    const minutos = page.getByRole("textbox", { name: "Minutos no fogo" });
    await minutos.fill("40");
    const pedido = page.waitForRequest((req) => req.url().endsWith("/motor/avaliar") && req.method() === "POST");
    await page.getByRole("button", { name: "Responder" }).click();
    expect((await pedido).postDataJSON()).toMatchObject({ tempo_cozimento_min: 40 });
    await expect(page.getByText("Três caminhos de preço")).toBeVisible();

    // O que a API respondeu a cada parada do controle: é isso, e só isso, que a tela mostra.
    const pontos: { preco: string; lucro: string }[] = [];
    page.on("response", async (res) => {
      if (!res.url().includes("/motor/preco-em")) return;
      const { dados } = (await res.json()) as { dados: { preco: { texto: string }; lucro: { texto: string } } };
      pontos.push({ preco: dados.preco.texto, lucro: dados.lucro.texto });
    });
    const controle = page.getByRole("slider", { name: "Preço de uma porção" });
    await expect(controle).toHaveAttribute("min", "3.34");
    await expect(controle).toHaveAttribute("max", "18");
    await expect(controle).toHaveAttribute("step", "0.5");
    await controle.focus();
    for (let passo = 0; passo < 10; passo += 1) await controle.press("ArrowRight");
    // 10 passos de R$ 0,50 a partir do mínimo que a API mandou.
    await expect(controle).toHaveAttribute("aria-valuetext", "R$ 8,34");
    const ponto = [...pontos].reverse().find((p) => p.preco === "R$ 8,34");
    expect(ponto, "a tela pediu o ponto à API").toBeDefined();
    await expect(page.getByText(ponto?.lucro ?? "").first()).toBeVisible();
  });
});

test.describe("do pôr preço ao cardápio", () => {
  test("o Vou cobrar grava o prato, e o cardápio mostra os mesmos números que o pôr preço mostrou", async ({ page, request }, info) => {
    const prato = `Galinhada ${marcador(info)}`;
    await abrir(page, "/precificar");
    await page.getByRole("textbox", { name: /Nome do prato/ }).fill(prato);
    await page.getByRole("textbox", { name: /Ingredientes, um por linha/ }).fill("500 g de frango\n2 xícaras de arroz");
    await page.getByRole("textbox", { name: /Quanto tempo fica no fogo/ }).fill("40");
    await page.getByRole("button", { name: "Conferir se dá pra fazer" }).click();
    await expect(page.getByText("Três caminhos de preço")).toBeVisible();

    // O ponto que a API mandou para o preço do controle: é o que o cardápio tem de mostrar.
    const pontos = new Map<string, { recebe: string; lucro: string; explicacao: string }>();
    page.on("response", async (res) => {
      if (!res.url().includes("/motor/preco-em")) return;
      const { dados } = (await res.json()) as {
        dados: { preco: { texto: string }; recebe: { texto: string }; lucro: { texto: string }; explicacao: string };
      };
      pontos.set(dados.preco.texto, { recebe: dados.recebe.texto, lucro: dados.lucro.texto, explicacao: dados.explicacao });
    });
    const controle = page.getByRole("slider", { name: "Preço de uma porção" });
    await controle.focus();
    for (let passo = 0; passo < 6; passo += 1) await controle.press("ArrowRight");
    await expect(controle).toHaveAttribute("aria-valuetext", "R$ 6,34");
    const cobrar = page.getByRole("button", { name: "Vou cobrar R$ 6,34" });
    await expect(cobrar).toBeVisible();
    const decisao = page.waitForRequest((req) => req.url().endsWith("/motor/decisao") && req.method() === "POST");
    await cobrar.click();
    expect((await decisao).postDataJSON()).toMatchObject({ prato, decisao: "aceito", preco: 6.34 });
    await expect(page.getByRole("heading", { name: "Anotado" })).toBeVisible();

    await page.getByRole("link", { name: "Ver o cardápio" }).click();
    await expect(page).toHaveURL(/\/cardapio$/);
    await expect(page.getByRole("heading", { level: 1, name: "O cardápio" })).toBeVisible();
    const { cartao } = await cartaoDoPrato(page, prato);
    await expect(cartao).toBeVisible();
    const conta = pontos.get("R$ 6,34");
    expect(conta, "a tela pediu o ponto de R$ 6,34 à API").toBeDefined();
    await expect(cartao.getByText("R$ 6,34", { exact: true })).toBeVisible();
    await expect(cartao.getByText(conta?.recebe ?? "", { exact: true })).toBeVisible();
    await expect(cartao.getByText("R$ 3,00", { exact: true })).toBeVisible();
    await expect(cartao.getByText(conta?.lucro ?? "", { exact: true })).toBeVisible();
    await expect(cartao.getByText(conta?.explicacao ?? "")).toBeVisible();

    // O prato deste teste sai do cardápio do motor falso, que é de todos os testes.
    expect((await request.post(`${MOTOR}/api/decisao`, { data: { prato, decisao: "recusado" } })).ok()).toBe(true);
  });
});
