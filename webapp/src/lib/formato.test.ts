/**
 * O que a tela ainda faz com números e palavras: rótulos de controle, o que ela
 * digita com vírgula, ordenação sem conta, e a porta contra o jargão.
 */

import { describe, expect, it } from "vitest";

import {
  PALAVRAS_PROIBIDAS,
  ROTULO_DO_VEREDITO,
  casaComBusca,
  compararDinheiro,
  corDoVeredito,
  encontrarJargao,
  formatarNumero,
  lerNumeroBR,
  pareceTecnico,
  porcentagem,
  reais,
  semAcento,
  textoParaEla,
} from "./formato";

describe("rótulos de controle", () => {
  it.each([
    [15, "R$ 15,00"],
    [8.5, "R$ 8,50"],
    [1234.5, "R$ 1.234,50"],
  ])("reais(%s) = %s, como se escreve no Brasil", (valor, esperado) => {
    expect(reais(valor)).toBe(esperado);
  });

  it.each([
    [0.42, 0, "42%"],
    [0.4237, 1, "42,4%"],
    [1, 0, "100%"],
  ])("porcentagem(%s, %s) = %s", (fracao, casas, esperado) => {
    expect(porcentagem(fracao, casas)).toBe(esperado);
  });

  it("número com vírgula e ponto de milhar", () => {
    expect(formatarNumero(1234.5)).toBe("1.234,5");
    expect(formatarNumero(2.456, 1)).toBe("2,5");
    expect(formatarNumero(4, 0)).toBe("4");
  });
});

describe("lerNumeroBR: o que ela digita", () => {
  it.each([
    ["1,5", 1.5],
    ["1.234,56", 1234.56],
    ["1.500", 1500],
    ["1.234.567", 1234567],
    ["1.5", 1.5],
    ["12.50", 12.5],
    ["R$ 12,90", 12.9],
    [" 7 ", 7],
    ["-2", -2],
    [",5", 0.5],
    ["0", 0],
  ])("%j é %s", (texto, esperado) => {
    expect(lerNumeroBR(texto)).toBe(esperado);
  });

  it.each(["", "   ", "abc", "1,2,3", "1e5", "--1", "R$"])(
    "%j não é número: null, nunca zero",
    (texto) => {
      expect(lerNumeroBR(texto)).toBeNull();
    },
  );
});

describe("compararDinheiro: ordenar sem fazer conta", () => {
  const r = (valor: number) => ({ valor, texto: `R$ ${valor}` });

  it("ordena pelo valor já recebido", () => {
    const lista = [r(3), r(1), r(2)].sort(compararDinheiro);
    expect(lista.map((d) => d.texto)).toEqual(["R$ 1", "R$ 2", "R$ 3"]);
  });

  it("o que não tem valor vai para o fim", () => {
    const lista = [null, r(2), undefined, r(1)].sort(compararDinheiro);
    expect(lista.slice(0, 2).map((d) => d?.texto)).toEqual(["R$ 1", "R$ 2"]);
    expect(lista.slice(2)).toEqual([null, undefined]);
  });

  it("iguais empatam", () => {
    expect(compararDinheiro(r(1), r(1))).toBe(0);
    expect(compararDinheiro(null, null)).toBe(0);
  });
});

describe("veredito", () => {
  it.each([
    ["APTO", "text-sucesso", "Dá pra fazer"],
    ["APTO COM COMPRA", "text-info", "Dá, comprando"],
    ["FALTA INFO", "text-atencao", "Falta saber"],
    ["BLOQUEADO", "text-perigo", "Não dá"],
  ] as const)("%s usa %s e diz %s", (veredito, classe, rotulo) => {
    expect(corDoVeredito(veredito).texto).toBe(classe);
    expect(corDoVeredito(veredito).rotulo).toBe(rotulo);
    expect(ROTULO_DO_VEREDITO[veredito]).toBe(rotulo);
  });

  it("nenhum veredito usa o vermelho da marca", () => {
    for (const v of ["APTO", "APTO COM COMPRA", "FALTA INFO", "BLOQUEADO"] as const) {
      expect(corDoVeredito(v).texto).not.toBe("text-marca");
    }
  });

  it("nenhum rótulo mostrado a ela é jargão", () => {
    for (const rotulo of Object.values(ROTULO_DO_VEREDITO)) {
      expect(encontrarJargao(rotulo)).toEqual([]);
    }
  });
});

describe("jargão", () => {
  it.each([
    ["O motor respondeu 503", ["motor"]],
    ["passou pelo portão", ["portão"]],
    ["APTO COM COMPRA", ["APTO"]],
    ["FALTA INFO", ["FALTA INFO"]],
    ["está BLOQUEADO", ["BLOQUEADO"]],
    ["o Veredito saiu", ["veredito"]],
    ["o CMV do prato", ["CMV"]],
    ["food cost de 30%", ["food cost"]],
    ["log append-only", ["append-only"]],
    ["rode make api", ["make api"]],
  ])("%j tem %j", (texto, esperado) => {
    expect(encontrarJargao(texto)).toEqual(esperado);
  });

  it.each([
    "A senhora já pode vender",
    "motorista de entrega",
    "apto para vender",
    "bloqueado pela chuva",
    "o apartamento",
  ])("%j não é jargão (palavra inteira, caixa certa)", (texto) => {
    expect(encontrarJargao(texto)).toEqual([]);
  });

  it("a lista tem as palavras que o plano proíbe", () => {
    expect(PALAVRAS_PROIBIDAS.map((p) => p.palavra)).toEqual([
      "motor",
      "portão",
      "APTO",
      "FALTA INFO",
      "BLOQUEADO",
      "veredito",
      "CMV",
      "food cost",
      "append-only",
      "make api",
    ]);
  });
});

describe("texto técnico", () => {
  it.each([
    "motor respondeu 503",
    "HTTP 500",
    "status 404",
    "[Errno 2] No such file",
    "Traceback (most recent call last)",
    "TypeError: fetch failed",
    "connect ECONNREFUSED 127.0.0.1:8777",
    "http://localhost:8777/api",
    "trilha indisponível: .estado/auditoria.jsonl",
    "/srv/dados/arquivo",
    "chame avaliar_receita antes",
    "valor `null`",
    "{\"detail\": \"x\"}",
    "Not Found",
  ])("%j tem cara de programa", (texto) => {
    expect(pareceTecnico(texto)).toBe(true);
  });

  it.each([
    "Falta o peso da embalagem da cobertura.",
    "Use 1/2 xícara de óleo.",
    "Custa R$ 41,00/kg, conta de 500 g.",
    "Sem forno, o frango assado não dá.",
    "Não encontrei esse ingrediente na despensa.",
  ])("%j é texto de gente", (texto) => {
    expect(pareceTecnico(texto)).toBe(false);
  });

  it("textoParaEla deixa passar o limpo e troca o resto pela alternativa", () => {
    expect(textoParaEla("Falta o peso.", "outro")).toBe("Falta o peso.");
    expect(textoParaEla("  Falta o peso.  ", "outro")).toBe("Falta o peso.");
    expect(textoParaEla("motor respondeu 503", "Tente de novo.")).toBe("Tente de novo.");
    expect(textoParaEla("o CMV não fechou", "Tente de novo.")).toBe("Tente de novo.");
    expect(textoParaEla("", "vazio")).toBe("vazio");
    expect(textoParaEla(null, "vazio")).toBe("vazio");
    expect(textoParaEla(undefined, "vazio")).toBe("vazio");
  });
});

describe("busca sem acento", () => {
  it("minúsculas e sem acento", () => {
    expect(semAcento("  Açafrão DA Terra ")).toBe("acafrao da terra");
  });

  it("cada palavra do termo aparece, em qualquer ordem", () => {
    expect(casaComBusca("Cobertura de chocolate", "choco")).toBe(true);
    expect(casaComBusca("Cobertura de chocolate", "chocolate cobertura")).toBe(true);
    expect(casaComBusca("Pão francês", "pao frances")).toBe(true);
    expect(casaComBusca("Alcaparras", "azeitona")).toBe(false);
    expect(casaComBusca("Alcaparras", "   ")).toBe(true);
  });
});
