/**
 * O modo de preparo com as partes da receita: o nome da parte ("Massa",
 * "Cobertura") aparece em cima do primeiro passo dela, uma vez, como a página
 * mostra; a receita sem partes fica com a lista corrida de sempre.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({ responderSobreACozinha: vi.fn() }));

import type { DetalheDaReceita, Passo } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { montar } from "@/teste/receitas";

import { PassosDaReceita, abreSecao } from "./PassosDaReceita";

const RECEITA = contrato<DetalheDaReceita>("receita.json");

const passo = (ordem: number, texto: string, secao?: string | null): Passo => ({
  ordem,
  texto,
  ...(secao === undefined ? {} : { secao }),
  requisitos: [],
  limites: [],
});

function passos(lista: readonly Passo[]) {
  return montar(<PassosDaReceita passos={lista} requisitosDaReceita={[]} jaPerguntados={new Set()} />);
}

describe("as partes da receita no modo de preparo", () => {
  it("o nome da parte fica em cima do primeiro passo dela, uma vez só", () => {
    passos([
      passo(1, "Bata a cenoura, os ovos e o óleo.", "Massa"),
      passo(2, "Asse por 40 minutos.", "Massa"),
      passo(3, "Derreta o chocolate com o leite.", "Cobertura"),
      passo(4, "Espalhe sobre o bolo.", "Cobertura"),
    ]);
    const titulos = screen.getAllByRole("heading", { level: 3 });
    expect(titulos.map((titulo) => titulo.textContent)).toEqual(["Massa", "Cobertura"]);
    const itens = screen.getAllByRole("listitem");
    expect(itens).toHaveLength(4);
    expect(within(itens[0]!).getByRole("heading", { name: "Massa" })).toBeInTheDocument();
    expect(within(itens[1]!).queryByRole("heading")).not.toBeInTheDocument();
    expect(within(itens[2]!).getByRole("heading", { name: "Cobertura" })).toBeInTheDocument();
    expect(within(itens[2]!).getByText("Derreta o chocolate com o leite.")).toBeInTheDocument();
  });

  it("o passo fora de parte com nome não ganha título, e a parte que volta ganha de novo", () => {
    passos([
      passo(1, "Bata os ovos.", "Massa do Bolo"),
      passo(2, "Asse.", null),
      passo(3, "Cozinhe o leite condensado.", "Cobertura de Brigadeiro"),
      passo(4, "Cubra o bolo.", null),
      passo(5, "Faça mais massa.", "Massa do Bolo"),
    ]);
    expect(screen.getAllByRole("heading", { level: 3 }).map((titulo) => titulo.textContent)).toEqual([
      "Massa do Bolo",
      "Cobertura de Brigadeiro",
      "Massa do Bolo",
    ]);
  });

  it("a receita sem partes fica com a lista corrida, e o passo sem o campo também", () => {
    passos(RECEITA.passos);
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Passo \d+:/)).toHaveLength(RECEITA.passos.length);
    expect(abreSecao([passo(1, "Mexa.")], 0)).toBeNull();
    expect(abreSecao([], 0)).toBeNull();
  });
});
