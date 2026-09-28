/**
 * O custo por porção e o preço preliminar do detalhe de uma receita, no
 * Chromium de verdade, contra o motor falso: o custo recusado leva à conversa
 * com o rascunho dela, e o valor da hora se muda ali mesmo, com a estimativa
 * pedida de novo à API e o valor dito como dela.
 *
 * Cada teste traz a própria receita pelo endereço, com um marcador único no
 * nome (como em `receitas.spec.ts`). As premissas do preço, porém, são uma só
 * no motor falso: só um projeto muda o valor da hora, e devolve o do contrato
 * no fim, para nenhum outro teste ver a troca no meio.
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
  const resposta = await request.post(`${MOTOR}/api/receitas`, { data: { url: `https://www.tudogostoso.com.br/receita/${prato}-${situacao}` } });
  expect(resposta.ok()).toBe(true);
  const { dados } = (await resposta.json()) as { dados: Trazida };
  return dados;
}

async function semViolacoesGraves(page: Page) {
  const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
  const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
  expect(graves, "violações sérias ou críticas do axe").toEqual([]);
}

test.describe("o custo e o preço preliminar de uma receita", () => {
  test("o custo recusado mostra o porquê e leva à conversa com o rascunho dela", async ({ page, request }, info) => {
    const bolo = await trazer(request, `bolo-de-milho-${marcador(info)}`, "com-o-que-tem");
    await page.goto(`/receitas/${bolo.slug}`, { waitUntil: "networkidle" });
    const custo = page.getByRole("region", { name: "Custo por porção" });
    await expect(custo.getByText(/^Ainda não calculo o custo de /)).toBeVisible();
    const responder = custo.getByRole("button", { name: "Responder no chat" });
    expect((await responder.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    await responder.click();

    const caixa = page.getByRole("textbox", { name: "Mensagem para o agente" });
    await expect(caixa).toBeVisible();
    const prato = bolo.nome.charAt(0).toLocaleLowerCase("pt-BR") + bolo.nome.slice(1);
    await expect(caixa).toHaveValue(`O que falta para eu saber o custo por porção de ${prato}?`);
  });

  test("o valor da hora se muda ali mesmo, a estimativa volta da API e o valor aparece como dela", async ({ page, request }, info) => {
    test.skip(info.project.name !== "claro-390", "as premissas são uma só no motor falso: um projeto muda, os outros não");
    const bolo = await trazer(request, `bolo-de-fuba-${marcador(info)}`, "com-o-que-tem");
    try {
      await page.goto(`/receitas/${bolo.slug}`, { waitUntil: "networkidle" });
      const preco = page.getByRole("region", { name: "Preço preliminar" });
      await expect(preco.getByText("Mão de obra sugerida")).toBeVisible();
      await expect(preco.getByText("Embalagem por porção: a senhora ainda não disse")).toBeVisible();

      const mudar = preco.getByRole("button", { name: "Mudar o valor da hora" });
      expect((await mudar.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      await mudar.click();
      const campo = preco.getByRole("textbox", { name: "Valor da hora da senhora" });
      await expect(campo).toBeFocused();
      await campo.fill("20,50");
      await semViolacoesGraves(page);

      const estimativaDeNovo = page.waitForResponse((resposta) => resposta.url().endsWith(`/motor/receitas/${bolo.slug}/estimativa`));
      await campo.press("Enter");
      await estimativaDeNovo;
      await expect(page.getByText("Anotei R$ 20,50 por hora e refiz a conta.")).toBeVisible();
      await expect(preco.getByText("Valor da hora da senhora: R$ 20,50 por hora, a senhora disse")).toBeVisible();
      await expect(mudar).toBeFocused();
      await page.screenshot({ path: info.outputPath("preco-preliminar-valor-da-hora.png"), fullPage: true });

      // Voltar à página traz o mesmo: o valor ficou gravado na API, não só na tela.
      await page.reload({ waitUntil: "networkidle" });
      await expect(
        page.getByRole("region", { name: "Preço preliminar" }).getByText("Valor da hora da senhora: R$ 20,50 por hora, a senhora disse"),
      ).toBeVisible();
    } finally {
      await request.put(`${MOTOR}/api/parametros/valor_hora`, { data: { valor: 15 } });
    }
  });

  test("a API recusa um valor fora da faixa, e o porquê aparece no campo", async ({ page, request }, info) => {
    const bolo = await trazer(request, `cuscuz-${marcador(info)}`, "com-o-que-tem");
    await page.goto(`/receitas/${bolo.slug}`, { waitUntil: "networkidle" });
    const preco = page.getByRole("region", { name: "Preço preliminar" });
    await preco.getByRole("button", { name: "Mudar o valor da hora" }).click();
    const campo = preco.getByRole("textbox", { name: "Valor da hora da senhora" });
    // O motor falso recusa número negativo (422, categoria uso): nada é gravado.
    await campo.fill("-3");
    await preco.getByRole("button", { name: "Salvar" }).click();
    await expect(preco.getByRole("alert")).toHaveText("Esse valor não serve.");
    await expect(campo).toHaveAttribute("aria-invalid", "true");
    await preco.getByRole("button", { name: "Cancelar" }).click();
    await expect(preco.getByRole("button", { name: "Mudar o valor da hora" })).toBeFocused();
  });
});
