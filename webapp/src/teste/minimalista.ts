/**
 * O modo minimalista nos testes de interface.
 *
 * O jsdom não roda o Tailwind. Esta folha repete o que ele gera para o
 * `hidden`, o `invisible` e a variante `minimalista:` das classes de
 * exibição, na mesma ordem do CSS de verdade (a variante depois), para o
 * `toBeVisible` dizer o que ela vê em cada modo. O CSS de verdade é conferido
 * no Chromium, nos testes de ponta a ponta.
 */

const EXIBICOES: Readonly<Record<string, string>> = {
  hidden: "none",
  block: "block",
  flex: "flex",
  "inline-flex": "inline-flex",
};

const FOLHA = [
  ".hidden{display:none}",
  ".invisible{visibility:hidden}",
  ...Object.entries(EXIBICOES).map(
    ([classe, valor]) => `[data-minimalista="ligado"] .minimalista\\:${classe}{display:${valor}}`,
  ),
].join("\n");

/** Liga ou desliga o modo, como o script do `<head>` marca o `<html>`. */
export function modoMinimalista(ligado: boolean): void {
  if (!document.getElementById("folha-do-minimalista")) {
    const estilo = document.createElement("style");
    estilo.id = "folha-do-minimalista";
    estilo.textContent = FOLHA;
    document.head.appendChild(estilo);
  }
  document.documentElement.setAttribute("data-minimalista", ligado ? "ligado" : "desligado");
}
