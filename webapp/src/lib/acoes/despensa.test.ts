/**
 * As Server Actions da despensa e da cozinha: cada uma chama a rota certa,
 * devolve `Resultado` sem lançar, e refaz a página quando dá certo (menos
 * tirar o item pela página dele, que volta para a lista).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const { refresh, despensa, perfil } = vi.hoisted(() => ({
  refresh: vi.fn(),
  despensa: {
    adicionar: vi.fn(),
    corrigir: vi.fn(),
    remover: vi.fn(),
    desfazerEvento: vi.fn(),
    estornarCompra: vi.fn(),
  },
  perfil: { definirPosse: vi.fn(), definirRestricao: vi.fn() },
}));
vi.mock("next/cache", () => ({ refresh: () => refresh() }));
vi.mock("@/lib/api", () => ({ api: { despensa, perfil } }));

import { ErroDoMotor } from "@/lib/api/base";

import { definirPosse, definirRestricao } from "./cozinha";
import { adicionarItem, corrigirItem, desfazerMudanca, devolverCompra, removerItem } from "./despensa";

afterEach(() => {
  vi.clearAllMocks();
});

const NOVO = { nome: "Creme de leite", estoque: 2, unidade: "un 200g", origem: "orcamento" as const, id_cliente: "k" };

describe("as ações da despensa", () => {
  it("acrescentar, corrigir, desfazer e devolver chamam a API e refazem a página", async () => {
    despensa.adicionar.mockResolvedValue({ texto: "Anotei." });
    despensa.corrigir.mockResolvedValue({ texto: "Corrigi." });
    despensa.desfazerEvento.mockResolvedValue({ texto: "Voltei." });
    despensa.estornarCompra.mockResolvedValue({ texto: "Devolvi." });

    await expect(adicionarItem(NOVO)).resolves.toEqual({ ok: true, dados: { texto: "Anotei." } });
    expect(despensa.adicionar).toHaveBeenCalledWith(NOVO);
    await expect(corrigirItem("bacon", { estoque: 0 })).resolves.toMatchObject({ ok: true });
    expect(despensa.corrigir).toHaveBeenCalledWith("bacon", { estoque: 0 });
    await expect(desfazerMudanca("ev-0007", "k2")).resolves.toMatchObject({ ok: true });
    expect(despensa.desfazerEvento).toHaveBeenCalledWith("ev-0007", "k2");
    await expect(devolverCompra(3, "k3")).resolves.toMatchObject({ ok: true });
    expect(despensa.estornarCompra).toHaveBeenCalledWith(3, "k3");
    expect(refresh).toHaveBeenCalledTimes(4);
  });

  it("tirar pela página do item não refaz a página (ela não existe mais)", async () => {
    despensa.remover.mockResolvedValue({ texto: "Tirei." });
    await removerItem("bacon", "k4", { atualizar: false });
    expect(despensa.remover).toHaveBeenCalledWith("bacon", "k4");
    expect(refresh).not.toHaveBeenCalled();
    await removerItem("bacon");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("a recusa da API volta como dado, com a frase dela", async () => {
    despensa.adicionar.mockRejectedValue(new ErroDoMotor("a compra exige R$ 90,00 e restam R$ 80,00 do orçamento", "regra"));
    await expect(adicionarItem(NOVO)).resolves.toEqual({
      ok: false,
      erro: { categoria: "regra", mensagem: "a compra exige R$ 90,00 e restam R$ 80,00 do orçamento" },
    });
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("as ações da cozinha", () => {
  it("a posse de um item e o valor de um limite", async () => {
    perfil.definirPosse.mockResolvedValue({ impacto: { texto: "Anotado." } });
    perfil.definirRestricao.mockResolvedValue({ impacto: { texto: "Anotado." } });
    await expect(definirPosse("equipamentos", "forno", "nao_sei")).resolves.toMatchObject({ ok: true });
    expect(perfil.definirPosse).toHaveBeenCalledWith("equipamentos", "forno", "nao_sei");
    await expect(definirRestricao("bocas_fogao", null)).resolves.toMatchObject({ ok: true });
    expect(perfil.definirRestricao).toHaveBeenCalledWith("bocas_fogao", null);
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
