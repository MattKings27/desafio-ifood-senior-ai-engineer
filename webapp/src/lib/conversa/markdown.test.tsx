/**
 * O Markdown leve do agente: o subconjunto que a instrução da web permite
 * vira nós React; todo o resto cai para texto, e nada vira HTML cru.
 */

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SENTINELA } from "./mascara";
import type { PecasDoMarkdown } from "./markdown";
import { analisarEmLinha, analisarMarkdown, linkSeguro, renderizarMarkdown, textoPlano } from "./markdown";

const PECAS: PecasDoMarkdown = {
  valor: (chave) => <mark key={chave}>valor</mark>,
  retirado: (chave) => <s key={chave}>retirado</s>,
  dinheiro: (texto, chave) => (
    <data key={chave} value={texto}>
      {texto}
    </data>
  ),
};

function html(texto: string, destacarDinheiro = false, pecas: PecasDoMarkdown = PECAS): string {
  const { container } = render(<div>{renderizarMarkdown(texto, pecas, { destacarDinheiro })}</div>);
  return (container.firstElementChild as HTMLElement).innerHTML;
}

describe("linkSeguro", () => {
  it.each([
    ["https://tudogostoso.com.br/receita/1", "https://tudogostoso.com.br/receita/1"],
    ["  http://exemplo.com  ", "http://exemplo.com/"],
    ["javascript:alert(1)", null],
    ["data:text/html,oi", null],
    ["/receitas/arroz", null],
    ["https://", null],
  ])("%s", (entrada, esperado) => {
    expect(linkSeguro(entrada)).toBe(esperado);
  });
});

describe("em linha", () => {
  it("negrito, itálico e os dois juntos", () => {
    expect(html("A **porção** é *boa*")).toBe("<p>A <strong class=\"font-bold text-tinta\">porção</strong> é <em>boa</em></p>");
    expect(html("**muito *bom***")).toContain("<strong");
  });

  it("marca sem par cai para texto", () => {
    expect(html("2 ** 3 e * solto")).toBe("<p>2 ** 3 e * solto</p>");
    expect(html("**abre e não fecha")).toBe("<p>**abre e não fecha</p>");
    expect(html("** espaço **")).toBe("<p>** espaço **</p>");
    expect(html("a *b * c")).toBe("<p>a *b * c</p>");
  });

  it("links com rótulo e links soltos, só http e https, abrindo em outra aba", () => {
    const comRotulo = html("Veja [a receita](https://tudogostoso.com.br/x).");
    expect(comRotulo).toContain('href="https://tudogostoso.com.br/x"');
    expect(comRotulo).toContain('target="_blank"');
    expect(comRotulo).toContain("(abre em outra aba)");
    expect(html("Veja [isto](javascript:alert(1))")).not.toContain("<a");
    expect(html("Fonte: https://www.exemplo.com.br/receita.")).toContain('href="https://www.exemplo.com.br/receita"');
    expect(html("xhttps://nao.com")).not.toContain("<a");
  });

  it("um script no meio é só texto", () => {
    const saida = html("<script>alert(1)</script> e <b>oi</b>");
    expect(saida).toContain("&lt;script&gt;");
    expect(saida).not.toContain("<script>");
  });

  it("o sentinela vira a peça do valor em conferência, e [valor retirado] vira o chip", () => {
    expect(html(`A porção sai ${SENTINELA}.`)).toBe("<p>A porção sai <mark>valor</mark>.</p>");
    expect(html("Custa [valor retirado] hoje")).toBe("<p>Custa <s>retirado</s> hoje</p>");
    expect(html("Custa [VALOR RETIRADO] hoje")).toContain("<s>retirado</s>");
  });

  it("no texto final, o dinheiro ganha a peça própria; sem ela, fica texto", () => {
    expect(html("Sai R$ 2,47 e R$ 1.234,56.", true)).toBe(
      '<p>Sai <data value="R$ 2,47">R$ 2,47</data> e <data value="R$ 1.234,56">R$ 1.234,56</data>.</p>',
    );
    expect(html("Sai R$ 2,47.", false)).toBe("<p>Sai R$ 2,47.</p>");
    const semPeca: PecasDoMarkdown = { valor: PECAS.valor, retirado: PECAS.retirado };
    expect(html("Sai R$ 2,47.", true, semPeca)).toBe("<p>Sai R$ 2,47.</p>");
    expect(html("R$ sem número", true)).toBe("<p>R$ sem número</p>");
  });

  it("quebra de linha dentro do parágrafo", () => {
    expect(analisarEmLinha("uma\nduas")).toEqual([
      { tipo: "texto", texto: "uma" },
      { tipo: "quebra" },
      { tipo: "texto", texto: "duas" },
    ]);
    expect(html("uma\nduas")).toBe("<p>uma<br>duas</p>");
  });
});

describe("blocos", () => {
  it("parágrafos separados por linha em branco, e listas com traço, asterisco ou ponto", () => {
    const blocos = analisarMarkdown("Primeiro.\n\n- um\n* dois\n• três\n  continua\n\nFim.");
    expect(blocos.map((b) => b.tipo)).toEqual(["paragrafo", "lista", "paragrafo"]);
    const lista = blocos[1];
    expect(lista?.tipo === "lista" ? lista.itens.length : 0).toBe(3);
    expect(html("- um\n- dois")).toBe(
      '<ul class="list-disc space-y-1.5 pl-6 marker:text-apagado"><li class="pl-1">um</li><li class="pl-1">dois</li></ul>',
    );
  });

  it("título vira uma linha em negrito; régua separa; CRLF vale como quebra", () => {
    expect(html("## Custo\r\ntexto")).toBe('<p><strong class="font-bold text-tinta">Custo</strong></p><p>texto</p>');
    expect(analisarMarkdown("a\n---\nb").map((b) => b.tipo)).toEqual(["paragrafo", "paragrafo"]);
  });

  it("uma lista seguida de parágrafo sem linha em branco fecha a lista", () => {
    expect(analisarMarkdown("- item\nparágrafo").map((b) => b.tipo)).toEqual(["lista", "paragrafo"]);
  });

  it("texto vazio não gera nada", () => {
    expect(analisarMarkdown("   \n\n  ")).toEqual([]);
  });
});

describe("textoPlano", () => {
  it("sem marcas, numa linha, com os chips em palavras", () => {
    expect(
      textoPlano(`Dá pra **fazer**, veja [aqui](https://x.com).\n\n- um\n- *dois*\n\nSai R$ 2,47 e [valor retirado]. ${SENTINELA}`),
    ).toBe("Dá pra fazer, veja aqui. um; dois Sai R$ 2,47 e valor retirado. valor em conferência");
    expect(textoPlano("uma\nduas")).toBe("uma duas");
  });
});
