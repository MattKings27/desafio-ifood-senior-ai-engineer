/**
 * A base das Server Actions: sucesso refaz a rota, erro vira dado.
 *
 * O `refresh` do Next só existe dentro de uma Server Action de verdade; aqui
 * ele é trocado por um espião, e o que se confere é quando ele é chamado.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/cache", () => ({ refresh: () => refresh() }));

import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";

import { executarAcao, falha, paraErroDaAcao } from "./base";

afterEach(() => {
  refresh.mockClear();
  vi.restoreAllMocks();
});

describe("executarAcao", () => {
  it("sucesso devolve os dados e refaz a rota atual na mesma ida e volta", async () => {
    await expect(executarAcao(async () => ({ texto: "Anotei." }))).resolves.toEqual({
      ok: true,
      dados: { texto: "Anotei." },
    });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("com atualizar desligado, não refaz a rota (ex.: nota que salva sozinha)", async () => {
    await executarAcao(async () => 1, { atualizar: false });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("recusa da API vira Resultado com categoria, mensagem e pergunta; nada é lançado", async () => {
    const resultado = await executarAcao(async () => {
      throw new ErroDoMotor("Falta o peso.", "dado", "Quanto vem na embalagem?");
    });
    expect(resultado).toEqual({
      ok: false,
      erro: { categoria: "dado", mensagem: "Falta o peso.", pergunta: "Quanto vem na embalagem?" },
    });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("falha que não veio da API vai para o log e chega a ela como falha de caminho", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const resultado = await executarAcao(async () => {
      throw new Error("bug nosso: undefined is not a function");
    });
    expect(resultado).toEqual({ ok: false, erro: { categoria: "rede", mensagem: MENSAGENS.rede } });
    expect(log).toHaveBeenCalledOnce();
  });
});

describe("paraErroDaAcao e falha", () => {
  it("sem pergunta, o erro não carrega a chave", () => {
    expect(paraErroDaAcao(new ErroDoMotor("Não encontrei.", "ausente"))).toEqual({
      categoria: "ausente",
      mensagem: "Não encontrei.",
    });
  });

  it("falha monta o mesmo formato, para validar antes de chamar a API", () => {
    expect(falha("uso", "Escreva o nome.")).toEqual({
      ok: false,
      erro: { categoria: "uso", mensagem: "Escreva o nome." },
    });
    expect(falha("dado", "Falta.", "Quanto?")).toEqual({
      ok: false,
      erro: { categoria: "dado", mensagem: "Falta.", pergunta: "Quanto?" },
    });
  });
});
