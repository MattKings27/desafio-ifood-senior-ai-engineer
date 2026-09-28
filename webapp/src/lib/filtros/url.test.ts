/**
 * Filtros na URL: ler, escrever e contar, sem perder o que não é filtro.
 *
 * A URL limpa é a lista inteira: valor padrão nunca vai para o endereço, para
 * o link que ela manda para alguém ser curto e o "voltar" fazer sentido.
 */

import { describe, expect, it } from "vitest";

import { contarAtivos, escreverFiltros, lerFiltros } from "./url";

const ESQUEMA = {
  q: { tipo: "texto" },
  veredito: { tipo: "lista" },
  tempo_max: { tipo: "numero" },
  so_com_o_que_tenho: { tipo: "booleano" },
  ordem: { tipo: "opcao", opcoes: ["nota", "custo", "tempo"], padrao: "nota" },
} as const;

const ler = (busca: string) => lerFiltros(new URLSearchParams(busca), ESQUEMA);

describe("lerFiltros", () => {
  it("URL vazia é tudo no padrão", () => {
    expect(ler("")).toEqual({ q: "", veredito: [], tempo_max: null, so_com_o_que_tenho: false, ordem: "nota" });
  });

  it("lê cada tipo de campo", () => {
    expect(
      ler("q=frango&veredito=APTO&veredito=FALTA+INFO&tempo_max=40&so_com_o_que_tenho=true&ordem=custo"),
    ).toEqual({
      q: "frango",
      veredito: ["APTO", "FALTA INFO"],
      tempo_max: 40,
      so_com_o_que_tenho: true,
      ordem: "custo",
    });
  });

  it("lista aceita vírgula também, e ignora pedaço vazio", () => {
    expect(ler("veredito=APTO,,BLOQUEADO").veredito).toEqual(["APTO", "BLOQUEADO"]);
  });

  it("valor inválido cai no padrão, em vez de filtrar por lixo", () => {
    expect(ler("tempo_max=muito&ordem=aleatoria&so_com_o_que_tenho=talvez")).toMatchObject({
      tempo_max: null,
      ordem: "nota",
      so_com_o_que_tenho: false,
    });
    expect(ler("tempo_max=").tempo_max).toBeNull();
  });

  it("booleano aceita 1 e 0", () => {
    expect(ler("so_com_o_que_tenho=1").so_com_o_que_tenho).toBe(true);
    expect(ler("so_com_o_que_tenho=0").so_com_o_que_tenho).toBe(false);
  });

  it("padrões declarados no esquema valem quando a URL não diz", () => {
    const esquema = {
      q: { tipo: "texto", padrao: "arroz" },
      n: { tipo: "numero", padrao: 3 },
      b: { tipo: "booleano", padrao: true },
    } as const;
    expect(lerFiltros(new URLSearchParams(""), esquema)).toEqual({ q: "arroz", n: 3, b: true });
    expect(lerFiltros(new URLSearchParams("b=false"), esquema).b).toBe(false);
  });
});

describe("escreverFiltros", () => {
  it("escreve só o que foge do padrão, e preserva o que não é filtro", () => {
    const base = new URLSearchParams("aba=ranking&q=velho");
    const saida = escreverFiltros(
      { q: "  frango  ", veredito: ["APTO", "BLOQUEADO"], tempo_max: 30, so_com_o_que_tenho: false, ordem: "nota" },
      ESQUEMA,
      base,
    );
    expect(saida.toString()).toBe("aba=ranking&q=frango&veredito=APTO&veredito=BLOQUEADO&tempo_max=30");
    // A base não é alterada.
    expect(base.toString()).toBe("aba=ranking&q=velho");
  });

  it("voltar ao padrão tira o parâmetro da URL", () => {
    const saida = escreverFiltros(
      { q: "", veredito: [], tempo_max: null, so_com_o_que_tenho: false, ordem: "nota" },
      ESQUEMA,
      new URLSearchParams("q=a&veredito=APTO&tempo_max=10&so_com_o_que_tenho=true&ordem=custo"),
    );
    expect(saida.toString()).toBe("");
  });

  it("ignora chave que não está no esquema, e escreve booleano ligado", () => {
    const saida = escreverFiltros(
      { so_com_o_que_tenho: true, ...({ intruso: "x" } as object) },
      ESQUEMA,
    );
    expect(saida.toString()).toBe("so_com_o_que_tenho=true");
  });

  it("ida e volta: escrever e ler dá o mesmo filtro", () => {
    const filtros = {
      q: "bolo",
      veredito: ["APTO COM COMPRA"],
      tempo_max: 45,
      so_com_o_que_tenho: true,
      ordem: "tempo" as const,
    };
    expect(lerFiltros(escreverFiltros(filtros, ESQUEMA), ESQUEMA)).toEqual(filtros);
  });
});

describe("contarAtivos", () => {
  it("conta o que foge do padrão, para o 'Filtros (n)'", () => {
    expect(contarAtivos(ler(""), ESQUEMA)).toBe(0);
    expect(contarAtivos(ler("q=a&veredito=APTO&tempo_max=10"), ESQUEMA)).toBe(3);
  });

  it("pode ignorar campos que ficam fora da folha (a busca, a ordem)", () => {
    expect(contarAtivos(ler("q=a&ordem=custo&tempo_max=10"), ESQUEMA, ["q", "ordem"])).toBe(1);
  });

  it("busca só com espaços não conta", () => {
    expect(contarAtivos({ ...ler(""), q: "   " }, ESQUEMA)).toBe(0);
  });
});
