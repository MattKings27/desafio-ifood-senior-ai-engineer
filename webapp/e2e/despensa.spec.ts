/**
 * A despensa no Chromium de verdade, contra o motor falso: acrescentar o que ela
 * já tinha (o orçamento fica igual), comprar com os R$ 80 (o orçamento desce, e
 * dá para devolver), tirar da despensa com "Desfazer", responder a embalagem
 * ali mesmo, e os filtros na URL.
 *
 * O motor falso tem um estado só para todos os testes, que rodam juntos nos
 * quatro projetos. Por isso cada teste mexe num item só dele (o nome leva o
 * projeto e um sufixo), e confere o orçamento pela frase da API sobre a escrita
 * dele, e não pelo saldo, que outro teste pode estar mudando na mesma hora.
 */

import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

const MOTOR = `http://127.0.0.1:${Number(process.env.PORTA_MOTOR ?? 8790)}`;
const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** Um nome só deste teste, neste projeto: "Fubá claro-390 k3x9a". */
function nomeProprio(base: string, info: TestInfo): string {
  return `${base} ${info.project.name} ${Math.random().toString(36).slice(2, 7)}`;
}

/** Acrescenta um item direto no motor falso, como se a conversa tivesse anotado. */
async function acrescentar(request: APIRequestContext, item: Record<string, unknown>): Promise<string> {
  const resposta = await request.post(`${MOTOR}/api/despensa/itens`, {
    data: { origem: "ja_tinha", id_cliente: `e2e-${Math.random().toString(36).slice(2)}`, ...item },
  });
  expect(resposta.ok()).toBe(true);
  const corpo = (await resposta.json()) as { dados: { item: { rota: string } } };
  return corpo.dados.item.rota;
}

async function abrir(page: Page, caminho: string) {
  await page.goto(caminho, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

const aviso = (page: Page, texto: string | RegExp) => page.locator("[role=status], [role=alert]").getByText(texto);

test.describe("a despensa", () => {
  test("acrescentar o que ela já tinha não mexe no orçamento", async ({ page }, info) => {
    const nome = nomeProprio("Farinha de rosca", info);
    await abrir(page, "/despensa");
    await page.getByRole("button", { name: "Adicionar ingrediente" }).first().click();
    const folha = page.getByRole("dialog", { name: "Adicionar ingrediente" });
    await expect(folha).toBeVisible();
    await folha.getByLabel("Nome do ingrediente").fill(nome);
    await folha.getByLabel("Quanto tem agora").fill("0,5");
    await expect(folha.getByRole("radio", { name: "Já tinha" })).toBeChecked();
    await folha.getByRole("button", { name: "Anotar na despensa" }).click();

    await expect(aviso(page, /Como a senhora já tinha, não mexi nos complementos\./)).toBeVisible();
    await expect(folha).toBeHidden();
    // Não entrou nas compras dos R$ 80.
    await expect(page.locator("#orcamento")).not.toContainText(nome);

    // Aparece na grade, com a pergunta do preço e a origem.
    await page.getByRole("searchbox", { name: "Buscar ingrediente" }).fill(nome);
    const cartao = page.locator("[data-cartao-link]").filter({ has: page.getByRole("link", { name: nome }) });
    await expect(cartao).toBeVisible();
    await expect(cartao.getByText("A senhora já tinha")).toBeVisible();
    await expect(cartao.getByText("Falta uma resposta")).toBeVisible();
    await expect(page.getByText("1 encontrado", { exact: true })).toBeVisible();
  });

  test("comprar com os R$ 80 desconta do orçamento, e devolver põe de volta", async ({ page }, info) => {
    const nome = nomeProprio("Milho verde", info);
    await abrir(page, "/despensa");
    const orcamento = page.locator("#orcamento");
    await orcamento.getByRole("button", { name: "Registrar compra" }).click();
    const folha = page.getByRole("dialog", { name: "Registrar compra" });
    await expect(folha).toBeVisible();
    await expect(folha.getByRole("radio", { name: /Comprei com os R\$ 80,00/ })).toBeChecked();
    await folha.getByLabel("Nome do ingrediente").fill(nome);
    await folha.getByLabel("Como a senhora mede").selectOption("embalagem");
    await folha.getByLabel("Quanto vem em cada embalagem").fill("200");
    await folha.getByLabel("Unidade do que vem na embalagem").selectOption("g");
    await folha.getByLabel("Quantas embalagens tem agora").fill("2");
    await folha.getByLabel(/Quanto pagou/).fill("9,00");
    await folha.getByLabel(/Para qual prato comprou/).fill("Arroz com frango");
    await folha.getByRole("button", { name: "Anotar na despensa" }).click();

    await expect(aviso(page, /Saíram R\$ 9,00 dos complementos; restam R\$ \d/)).toBeVisible();
    const compra = orcamento.getByRole("listitem").filter({ hasText: nome });
    await expect(compra).toContainText("R$ 9,00");
    await expect(compra).toContainText("para Arroz com frango");

    await compra.getByRole("button", { name: "Devolver ao orçamento" }).click();
    const confirmar = page.getByRole("alertdialog", { name: "Devolver ao orçamento?" });
    await expect(confirmar).toContainText(nome);
    await confirmar.getByRole("button", { name: "Devolver", exact: true }).click();
    await expect(aviso(page, new RegExp(`Devolvi R\\$ 9,00 aos complementos; restam R\\$ \\d.*${nome} saiu da despensa\\.`))).toBeVisible();
    await expect(orcamento.getByRole("listitem").filter({ hasText: nome })).toHaveCount(0);
  });

  test("tirar da despensa e desfazer pelo aviso", async ({ page, request }, info) => {
    const nome = nomeProprio("Fubá", info);
    const rota = await acrescentar(request, { nome, estoque: 1, unidade: "kg", preco_pago: 5 });
    await abrir(page, rota);
    await expect(page.getByRole("heading", { level: 1, name: nome })).toBeVisible();
    await expect(page.getByText("R$ 5,00 ÷ 1 kg = R$ 5,00/kg")).toBeVisible();

    await page.getByRole("button", { name: "Tirar da despensa" }).click();
    const confirmar = page.getByRole("alertdialog");
    await expect(confirmar).toContainText("Dá para desfazer logo depois");
    await confirmar.getByRole("button", { name: "Tirar da despensa" }).click();

    await expect(page).toHaveURL(/\/despensa$/);
    await expect(aviso(page, /Tirei .* da despensa\. Não mexi nos complementos\./)).toBeVisible();
    await page.getByRole("button", { name: "Desfazer" }).click();
    await expect(aviso(page, /Voltei .* para a despensa\./)).toBeVisible();
    await page.getByRole("searchbox", { name: "Buscar ingrediente" }).fill(nome);
    await expect(page.getByRole("link", { name: nome })).toBeVisible();
  });

  test("o peso da embalagem não é pergunta: nem na lista, nem no item", async ({ page, request }, info) => {
    const nome = nomeProprio("Leite condensado", info);
    const rota = await acrescentar(request, { nome, estoque: 2, unidade: "un", quantidade_comprada: 2, preco_pago: 7.5 });
    await abrir(page, "/despensa");
    await expect(page.getByRole("region", { name: "Preciso saber" })).toHaveCount(0);
    await expect(page.getByLabel("Quanto vem na embalagem?")).toHaveCount(0);
    await abrir(page, rota);
    await expect(page.getByRole("heading", { level: 1, name: nome })).toBeVisible();
    await expect(page.getByLabel("Quanto vem na embalagem?")).toHaveCount(0);
    // O caminho de corrigir continua: o Editar do item.
    await expect(page.getByRole("button", { name: "Editar" })).toBeVisible();
  });

  test("busca, categoria, ordem e a folha de filtros ficam na URL", async ({ page }) => {
    await abrir(page, "/despensa");
    const busca = page.getByRole("searchbox", { name: "Buscar ingrediente" });
    await busca.fill("FEIJAO");
    await expect(page).toHaveURL(/q=FEIJAO/);
    await expect(page.getByText("2 encontrados", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Feijão carioquinha" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Feijão preto" })).toBeVisible();

    await page.getByRole("group", { name: "Categorias" }).getByText("Hortifrúti").click();
    await expect(page).toHaveURL(/categoria=hortifruti/);
    await expect(page.getByText("Nenhum ingrediente com esses filtros")).toBeVisible();
    await page.getByRole("button", { name: "Limpar filtros" }).last().click();
    await expect(page).toHaveURL(/\/despensa$/);
    await expect(page.getByText(/^\d+ ingredientes$/)).toBeVisible();

    await page.getByLabel("Ordenar por").selectOption("nome");
    await expect(page).toHaveURL(/ordem=nome/);
    await expect(page.locator("[data-cartao-link] h3").first()).toHaveText("Açafrão em pó (cúrcuma)");

    await page.getByRole("button", { name: /^Filtros/ }).click();
    const folha = page.getByRole("dialog", { name: "Filtros" });
    await folha.getByText("Com pergunta em aberto").click();
    await folha.getByRole("button", { name: /^Ver / }).click();
    await expect(folha).toBeHidden();
    await expect(page).toHaveURL(/pendentes=true/);
    const grade = page.getByRole("region", { name: "Ingredientes" });
    await expect(grade.getByRole("link", { name: "Cobertura de chocolate" })).toBeVisible();
    await expect(grade.getByRole("link", { name: "Alcaparras" })).toHaveCount(0);

    // A URL é a fonte: recarregar mostra a mesma lista, com o filtro à vista.
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByRole("list", { name: "Filtros ativos" }).getByRole("button", { name: /Com pergunta em aberto/ })).toBeVisible();
    await expect(grade.getByRole("link", { name: "Alcaparras" })).toHaveCount(0);
  });

  test("a página de um item: a conta, o histórico e nada sério no axe", async ({ page, request }, info) => {
    const nome = nomeProprio("Canela", info);
    const rota = await acrescentar(request, { nome, estoque: 100, unidade: "g", preco_pago: 4 });
    await abrir(page, rota);
    const conta = page.getByRole("region", { name: "A conta" });
    await expect(conta).toContainText("Custo por quilo");
    await expect(conta).toContainText("R$ 40,00/kg");
    await expect(conta).toContainText("R$ 4,00 ÷ 0,1 kg = R$ 40,00/kg");
    await expect(page.getByRole("region", { name: "Histórico" })).toContainText("A senhora acrescentou o que já tinha");
    await expect(page.getByText("Nenhuma receita usa isso ainda")).toBeVisible();

    const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
    const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
    expect(graves).toEqual([]);

    // "Acabou" zera o estoque, e o aviso traz o "Desfazer".
    await page.getByRole("button", { name: "Acabou" }).click();
    await expect(aviso(page, /acabou\./)).toBeVisible();
    await expect(conta).toContainText("acabou");
    await page.screenshot({ path: info.outputPath("ingrediente.png"), fullPage: true });
  });
});
