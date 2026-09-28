/**
 * Contraste AA de cada par de texto e fundo que a interface usa, nos dois temas.
 *
 * Lê o `globals.css` de verdade. A regra de contraste do axe não é confiável
 * no jsdom (ele não pinta), então a garantia de tokens vem daqui, e a da tela
 * montada vem do axe do Playwright no Chromium.
 *
 * A tabela do DESIGN.md é gerada por esta mesma conta. Para regenerar depois
 * de mudar um token: `ATUALIZAR_CONTRASTE=1 npx vitest run src/lib/contraste.test.ts`.
 */

import { readFileSync, writeFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { doRepositorio, doWebapp } from "@/teste/fixturas";

import {
  PARES,
  compor,
  contraste,
  formatarRazao,
  hexParaRgb,
  lerTokens,
  luminancia,
  razaoDoPar,
  resolverFundo,
  tabelaDeContraste,
} from "./contraste";

const CSS = readFileSync(doWebapp("src", "app", "globals.css"), "utf-8");
const TEMAS = lerTokens(CSS);

describe("a conta do WCAG", () => {
  it.each([
    ["#ffffff", "#000000", 21],
    ["#EB0033", "#ffffff", 4.58],
    ["#333333", "#ffffff", 12.63],
    ["#fff", "#fff", 1],
  ])("%s contra %s dá %s:1", (a, b, esperado) => {
    expect(contraste(a, b)).toBeCloseTo(esperado, 2);
  });

  it("a ordem das cores não muda a razão", () => {
    expect(contraste("#eb0033", "#fff")).toBe(contraste("#fff", "#eb0033"));
  });

  it("luminância vai de 0 (preto) a 1 (branco)", () => {
    expect(luminancia([0, 0, 0])).toBe(0);
    expect(luminancia([255, 255, 255])).toBeCloseTo(1, 10);
  });

  it("aceita o hexadecimal curto e recusa o que não é cor", () => {
    expect(hexParaRgb("#abc")).toEqual([0xaa, 0xbb, 0xcc]);
    expect(() => hexParaRgb("#abcd")).toThrow("cor inválida");
    expect(() => hexParaRgb("vermelho")).toThrow("cor inválida");
  });

  it("compor uma tinta a 10% é a média ponderada, canal a canal", () => {
    expect(compor("#000000", "#ffffff", 0.1)).toEqual([229.5, 229.5, 229.5]);
    expect(compor([10, 20, 30], [10, 20, 30], 0.5)).toEqual([10, 20, 30]);
  });

  it("formata como o DESIGN.md, truncando para nunca arredondar a favor", () => {
    expect(formatarRazao(4.5799)).toBe("4,57:1");
    expect(formatarRazao(21)).toBe("21,00:1");
  });
});

describe("leitura do globals.css", () => {
  it("encontra os tokens do claro e do escuro", () => {
    expect(TEMAS.claro["marca-fundo"]).toBe("#eb0033");
    expect(TEMAS.escuro["marca-fundo"]).toBe("#eb0033");
    expect(TEMAS.escuro.superficie).toBe("#1c1c1e");
  });

  it("todo token de cor do claro é redeclarado no escuro: nenhuma cor fica para trás", () => {
    // O modo escuro antigo trocava só os neutros; creme, seção e a marca
    // escura continuavam claros e apareciam como remendos na tela escura.
    const faltando = Object.keys(TEMAS.claro).filter((nome) => !(nome in TEMAS.redeclaradosNoEscuro));
    expect(faltando).toEqual([]);
  });

  it("o plano B sem JavaScript tem exatamente os valores do escuro", () => {
    expect(TEMAS.escuroSemScript).toEqual(TEMAS.redeclaradosNoEscuro);
  });

  it("a marca como texto no escuro não é o vermelho cheio, que reprova (3,7:1)", () => {
    expect(TEMAS.escuro.marca).not.toBe("#eb0033");
    expect(contraste("#eb0033", TEMAS.escuro.superficie!)).toBeLessThan(4.5);
  });

  it("o perigo no escuro é um coral, longe do rosa da marca", () => {
    // Bloqueio e prejuízo não podem ser lidos como botão.
    expect(TEMAS.escuro.perigo).not.toBe(TEMAS.escuro.marca);
    expect(contraste(TEMAS.escuro.perigo!, TEMAS.escuro.marca!)).toBeGreaterThan(1.1);
  });

  it("um bloco que não existe é um erro claro, não um tema vazio", () => {
    expect(() => lerTokens("@theme { --color-a: #fff; }")).toThrow("bloco não encontrado");
    expect(() => lerTokens("@theme { --color-a: #fff;")).toThrow("bloco sem fim");
  });

  it("um par com token que não existe é um erro, não um contraste inventado", () => {
    expect(() => resolverFundo(TEMAS.claro, "nao-existe")).toThrow("token sem valor");
  });
});

describe.each(["claro", "escuro"] as const)("tema %s", (tema) => {
  it.each(PARES.map((par) => [par.uso, par] as const))("%s passa", (_uso, par) => {
    const razao = razaoDoPar(TEMAS[tema], par);
    expect(
      razao,
      `${par.frente} sobre ${JSON.stringify(par.fundo)} deu ${formatarRazao(razao)}`,
    ).toBeGreaterThanOrEqual(par.minimo);
  });
});

describe("a tabela do DESIGN.md", () => {
  const caminho = doRepositorio("DESIGN.md");
  const INICIO = "<!-- contraste:inicio -->";
  const FIM = "<!-- contraste:fim -->";

  it("é a mesma que a conta gera agora", () => {
    const tabela = tabelaDeContraste(TEMAS);
    const lido = readFileSync(caminho, "utf-8");
    const marcadores = (texto: string) => [texto.indexOf(INICIO), texto.indexOf(FIM)] as const;
    const [antes, depois] = marcadores(lido);
    expect(antes, "marcadores da tabela no DESIGN.md").toBeGreaterThan(-1);
    expect(depois).toBeGreaterThan(antes);

    let design = lido;
    if (process.env.ATUALIZAR_CONTRASTE === "1") {
      design = `${lido.slice(0, antes + INICIO.length)}\n${tabela}\n${lido.slice(depois)}`;
      writeFileSync(caminho, design);
    }
    const [inicio, fim] = marcadores(design);
    expect(design.slice(inicio + INICIO.length, fim).trim()).toBe(tabela);
  });
});
