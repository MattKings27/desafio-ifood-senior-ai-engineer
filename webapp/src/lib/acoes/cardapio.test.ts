/**
 * As Server Actions do cardápio: tirar um prato e desfazer. O pedido que
 * chega à API, a frase que volta para o aviso, a rota refeita, e o erro que
 * vira `Resultado` em vez de exceção.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/cache", () => ({ refresh: () => refresh() }));

import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";
import type { CardapioCompleto } from "@/lib/api/cardapio";
import { contrato } from "@/teste/fixturas";

import { desfazerNoCardapio, tirarDoCardapio } from "./cardapio";

const CARDAPIO = contrato<CardapioCompleto>("cardapio.json");

afterEach(() => {
  vi.restoreAllMocks();
  refresh.mockClear();
});

describe("tirar do cardápio", () => {
  it("grava a recusa com a chave do clique e devolve só a frase", async () => {
    const decidir = vi
      .spyOn(api.cardapio, "decidir")
      .mockResolvedValue({ prato: "Arroz com frango", decisao: "recusado", texto: "A senhora tirou o arroz com frango do cardápio.", cardapio: [] });
    await expect(tirarDoCardapio("Arroz com frango", "c-1")).resolves.toEqual({
      ok: true,
      dados: { texto: "A senhora tirou o arroz com frango do cardápio." },
    });
    expect(decidir).toHaveBeenCalledWith({ prato: "Arroz com frango", decisao: "recusado", id_cliente: "c-1" });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("sem prato não vai à API, e a recusa da API vira resultado", async () => {
    const decidir = vi.spyOn(api.cardapio, "decidir");
    await expect(tirarDoCardapio("  ")).resolves.toMatchObject({ ok: false, erro: { categoria: "uso" } });
    expect(decidir).not.toHaveBeenCalled();
    decidir.mockRejectedValue(new ErroDoMotor("não deu", "regra"));
    await expect(tirarDoCardapio("Arroz")).resolves.toEqual({ ok: false, erro: { categoria: "regra", mensagem: "não deu" } });
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("desfazer", () => {
  it("volta o prato pela rota do desfazer e devolve a frase", async () => {
    const desfazer = vi
      .spyOn(api.cardapio, "desfazer")
      .mockResolvedValue({ ...CARDAPIO, texto: "A senhora voltou atrás: o arroz com frango está de novo no cardápio, a R$ 18,00." });
    await expect(desfazerNoCardapio("Arroz com frango", "c-2")).resolves.toEqual({
      ok: true,
      dados: { texto: "A senhora voltou atrás: o arroz com frango está de novo no cardápio, a R$ 18,00." },
    });
    expect(desfazer).toHaveBeenCalledWith("Arroz com frango", "c-2");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("sem prato não vai à API", async () => {
    const desfazer = vi.spyOn(api.cardapio, "desfazer");
    await expect(desfazerNoCardapio("")).resolves.toMatchObject({ ok: false, erro: { categoria: "uso" } });
    expect(desfazer).not.toHaveBeenCalled();
  });
});
