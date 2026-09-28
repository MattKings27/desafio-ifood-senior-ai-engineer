/**
 * O que muda a cozinha de todos, no fim: o "Tenho tudo isso" confirma de uma
 * vez o que ainda era suposto. Roda no projeto `por-ultimo`, depois dos outros
 * quatro, porque os outros testes conferem o suposto (o filtro "Suposto" da
 * cozinha, o "Confirmar a cozinha" de uma receita) no mesmo motor falso.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const TAGS_DO_AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

test("Tenho tudo isso confirma de uma vez, e o cartão da cozinha fica calmo", async ({ page }, info) => {
  await page.goto("/cozinha", { waitUntil: "networkidle" });
  const cartao = page.getByRole("region", { name: "O que toda cozinha tem" });
  await expect(cartao).toBeVisible();
  const tudo = cartao.getByRole("button", { name: "Tenho tudo isso" });
  // Numa segunda tentativa já está tudo confirmado: o cartão é o mesmo.
  if (await tudo.isVisible()) {
    await tudo.click();
    await expect(page.getByText(/^Anotei: a senhora tem fogão/)).toBeVisible();
  }
  await expect(cartao.getByText("A senhora já me disse de tudo isso.")).toBeVisible();
  await expect(cartao.getByRole("button", { name: "Tenho tudo isso" })).toHaveCount(0);
  await cartao.getByText("Ver os itens").click();
  await expect(cartao.getByRole("listitem").filter({ hasText: "Fogão" }).getByText("A senhora tem")).toBeVisible();
  await expect(cartao.getByText("Suposto: confirme")).toHaveCount(0);

  const analise = await new AxeBuilder({ page }).withTags(TAGS_DO_AXE).analyze();
  const graves = analise.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id);
  expect(graves, "violações sérias ou críticas do axe").toEqual([]);
  await page.screenshot({ path: info.outputPath("cozinha-confirmada.png"), fullPage: true });
});
