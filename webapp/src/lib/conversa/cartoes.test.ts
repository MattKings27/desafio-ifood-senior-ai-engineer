/** Os cards de uma resposta: sem repetição, e os muitos do mesmo tipo num grupo só. */

import { describe, expect, it } from "vitest";

import type { TipoDeCartao } from "./cartoes";
import { agruparCartoes, semCartoesRepetidos } from "./cartoes";

const card = (id: string, tipo: TipoDeCartao, rota: string | null) => ({ id, tipo, ref: { rota } });

describe("sem repetição", () => {
  it("mesmo tipo e mesma rota: fica o último, no lugar dele", () => {
    const cartoes = [
      card("a", "viabilidade", "/api/receitas/x"),
      card("b", "orcamento", "/api/orcamento"),
      card("c", "viabilidade", "/api/receitas/x"),
      card("d", "viabilidade", "/api/receitas/y"),
    ];
    expect(semCartoesRepetidos(cartoes).map((c) => c.id)).toEqual(["b", "c", "d"]);
  });

  it("card sem rota nunca se compara, e outro tipo na mesma rota fica", () => {
    const cartoes = [
      card("a", "pergunta", null),
      card("b", "pergunta", null),
      card("c", "receita", "/api/receitas/x"),
      card("d", "viabilidade", "/api/receitas/x"),
    ];
    expect(semCartoesRepetidos(cartoes).map((c) => c.id)).toEqual(["a", "b", "c", "d"]);
  });
});

describe("em grupo", () => {
  it("três ou mais do mesmo tipo viram um grupo no lugar do primeiro", () => {
    const cartoes = [
      card("r1", "receita", "/api/receitas/1"),
      card("o", "orcamento", "/api/orcamento"),
      card("r2", "receita", "/api/receitas/2"),
      card("v1", "viabilidade", "/api/receitas/1"),
      card("r3", "receita", "/api/receitas/3"),
      card("v2", "viabilidade", "/api/receitas/2"),
    ];
    const blocos = agruparCartoes(cartoes);
    expect(blocos.map((b) => (b.tipo === "um" ? b.cartao.id : `${b.tipoDeCartao}:${b.cartoes.map((c) => c.id).join(",")}`))).toEqual([
      "receita:r1,r2,r3",
      "o",
      "v1",
      "v2",
    ]);
  });

  it("sem card, sem bloco", () => {
    expect(agruparCartoes([])).toEqual([]);
  });
});
