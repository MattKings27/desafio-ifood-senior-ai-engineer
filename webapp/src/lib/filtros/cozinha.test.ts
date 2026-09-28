/**
 * A situação de cada item da cozinha, e os filtros e grupos sobre o perfil do
 * contrato. "Não sei" é resposta: fica "não sei", nunca "ainda não perguntei".
 */

import { describe, expect, it } from "vitest";

import type { ItemDaCozinha, PerfilDaCozinha } from "@/lib/api/perfil";
import { contrato } from "@/teste/fixturas";

import {
  FILTROS_DA_COZINHA,
  agruparPorCategoria,
  contarPorSituacao,
  passaNaCozinha,
  respostaDoItem,
  situacaoDoItem,
} from "./cozinha";
import { lerFiltros } from "./url";

const PERFIL = contrato<PerfilDaCozinha>("perfil.json");
const TODOS = [...PERFIL.equipamentos, ...PERFIL.tecnicas];
const achar = (id: string) => TODOS.find((item) => item.id === id) as ItemDaCozinha;

describe("situacaoDoItem e respostaDoItem", () => {
  it.each([
    ["fogao", "suposto", null],
    ["forno", "nao_tem", "nao_tem"],
    ["liquidificador", "tem", "tem"],
    ["batedeira", "nao_sei", "nao_sei"],
    ["air_fryer", "sem_resposta", null],
  ])("%s está em %s", (id, situacao, resposta) => {
    expect(situacaoDoItem(achar(id))).toBe(situacao);
    expect(respostaDoItem(achar(id))).toBe(resposta);
  });

  it("as contagens batem com o perfil da API", () => {
    const contagem = contarPorSituacao(TODOS);
    expect(contagem.suposto).toBe(PERFIL.supostos);
    expect(contagem.tem + contagem.nao_tem).toBe(PERFIL.respondidos);
    expect(contagem.nao_sei + contagem.sem_resposta).toBe(PERFIL.em_aberto);
    expect(contagem.nao_sei).toBe(1);
  });
});

describe("passaNaCozinha", () => {
  const filtros = (busca: string) => lerFiltros(new URLSearchParams(busca), FILTROS_DA_COZINHA);

  it("sem filtro, tudo passa", () => {
    expect(TODOS.every((item) => passaNaCozinha(item, filtros("")))).toBe(true);
  });

  it("a busca olha o nome e a categoria, sem acento", () => {
    const forno = TODOS.filter((item) => passaNaCozinha(item, filtros("q=FORN")));
    expect(forno.map((item) => item.id)).toEqual(["forno", "forno_eletrico"]);
    const coccao = TODOS.filter((item) => passaNaCozinha(item, filtros("q=coccao")));
    expect(coccao.length).toBe(PERFIL.equipamentos.filter((e) => e.categoria === "cocção").length);
  });

  it("a situação, uma ou várias", () => {
    expect(TODOS.filter((item) => passaNaCozinha(item, filtros("situacao=nao_sei"))).map((i) => i.id)).toEqual([
      "batedeira",
    ]);
    const respondidos = TODOS.filter((item) => passaNaCozinha(item, filtros("situacao=tem,nao_tem")));
    expect(respondidos.map((i) => i.id).sort()).toEqual(["bechamel", "forno", "liquidificador"]);
  });
});

describe("agruparPorCategoria", () => {
  it("na ordem da API, com o rótulo em maiúscula", () => {
    const grupos = agruparPorCategoria(PERFIL.equipamentos);
    expect(grupos.map((g) => g.rotulo)).toEqual(["Cocção", "Preparo", "Frio", "Medição", "Utensílio"]);
    expect(grupos.reduce((soma, g) => soma + g.itens.length, 0)).toBe(PERFIL.equipamentos.length);
    expect(agruparPorCategoria([])).toEqual([]);
  });
});
