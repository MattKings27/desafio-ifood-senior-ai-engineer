/**
 * Os filtros da despensa sobre a lista do contrato: cada filtro sozinho, os
 * juntos, e as três ordens, com o que não tem valor sempre no fim.
 */

import { describe, expect, it } from "vitest";

import type { ItemDaDespensa, ListaDaDespensa } from "@/lib/api/despensa";
import { contrato } from "@/teste/fixturas";

import type { FiltrosDaDespensaNaUrl } from "./despensa";
import { FILTROS_DA_DESPENSA, contar, itensVisiveis, ordenarDespensa, passaNosFiltros } from "./despensa";
import { lerFiltros } from "./url";

const LISTA = contrato<ListaDaDespensa>("despensa.json");
const SEM_FILTRO = lerFiltros(new URLSearchParams(), FILTROS_DA_DESPENSA);

function com(parcial: Partial<FiltrosDaDespensaNaUrl>): FiltrosDaDespensaNaUrl {
  return { ...SEM_FILTRO, ...parcial };
}

const nomes = (itens: readonly ItemDaDespensa[]) => itens.map((item) => item.nome);

describe("passaNosFiltros", () => {
  it("sem filtro, tudo passa; a ordem padrão é a do dinheiro parado", () => {
    expect(SEM_FILTRO.ordem).toBe("valor");
    expect(LISTA.itens.every((item) => passaNosFiltros(item, SEM_FILTRO))).toBe(true);
  });

  it("a busca ignora acento e caixa", () => {
    expect(nomes(itensVisiveis(LISTA.itens, com({ q: "FEIJAO" })))).toEqual(["Feijão carioquinha", "Feijão preto"]);
    expect(nomes(itensVisiveis(LISTA.itens, com({ q: "  acafrao " })))).toEqual(["Açafrão em pó (cúrcuma)"]);
  });

  it("categoria, confiança, origem, sem receita e com pergunta", () => {
    const graos = itensVisiveis(LISTA.itens, com({ categoria: ["graos"] }));
    expect(graos.length).toBe(8);
    expect(graos.every((item) => item.categoria === "graos")).toBe(true);

    expect(nomes(itensVisiveis(LISTA.itens, com({ confianca: ["desconhecida"] })))).toEqual([
      "Cobertura de chocolate",
      "Farinha de rosca",
    ]);
    expect(nomes(itensVisiveis(LISTA.itens, com({ origem: ["ja_tinha", "orcamento"] })))).toEqual([
      "Creme de leite",
      "Farinha de rosca",
    ]);
    expect(itensVisiveis(LISTA.itens, com({ sem_receita: true })).every((item) => item.receitas_que_usam === 0)).toBe(true);
    expect(nomes(itensVisiveis(LISTA.itens, com({ pendentes: true })))).toEqual(["Cobertura de chocolate", "Farinha de rosca"]);
  });

  it("os filtros se somam", () => {
    expect(itensVisiveis(LISTA.itens, com({ q: "feijao", categoria: ["hortifruti"] }))).toEqual([]);
    expect(nomes(itensVisiveis(LISTA.itens, com({ pendentes: true, origem: ["planilha"] })))).toEqual([
      "Cobertura de chocolate",
    ]);
  });
});

describe("ordenarDespensa", () => {
  const item = (nome: string, pago: number | null, custo: number | null): ItemDaDespensa => ({
    ...(LISTA.itens[0] as ItemDaDespensa),
    id: nome,
    nome,
    pago: pago === null ? null : { valor: pago, texto: `R$ ${pago}` },
    custo_unitario: custo === null ? null : { valor: custo, texto: `R$ ${custo}/kg` },
  });
  const itens = [item("Bacon", 10, 20), item("açúcar", null, null), item("Alho", 10, 5), item("Couve", 30, null)];

  it("mais dinheiro parado primeiro; empate pelo nome; sem preço no fim", () => {
    expect(nomes(ordenarDespensa(itens, "valor"))).toEqual(["Couve", "Alho", "Bacon", "açúcar"]);
  });

  it("pelo nome, sem ligar para acento e caixa", () => {
    expect(nomes(ordenarDespensa(itens, "nome"))).toEqual(["açúcar", "Alho", "Bacon", "Couve"]);
  });

  it("pelo custo por unidade, do maior; sem custo no fim, pelo nome", () => {
    expect(nomes(ordenarDespensa(itens, "custo"))).toEqual(["Bacon", "Alho", "açúcar", "Couve"]);
  });

  it("não mexe na lista que recebeu", () => {
    const antes = nomes(itens);
    ordenarDespensa(itens, "nome");
    expect(nomes(itens)).toEqual(antes);
  });
});

describe("contar", () => {
  it("só o um vai no singular", () => {
    expect(contar(0, "ingrediente", "ingredientes")).toBe("0 ingredientes");
    expect(contar(1, "ingrediente", "ingredientes")).toBe("1 ingrediente");
    expect(contar(37, "encontrado", "encontrados")).toBe("37 encontrados");
  });
});
