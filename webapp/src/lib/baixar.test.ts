/**
 * Baixar da API: só o que chegou bem vira arquivo; a rota que não existe e a
 * rede que caiu voltam como resultado, nunca como exceção.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErroDoMotor } from "@/lib/api/base";

import { baixarDaApi, nomeDoArquivo, salvarArquivo } from "./baixar";

let rede: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  rede = vi.fn();
  vi.stubGlobal("fetch", rede);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("nomeDoArquivo", () => {
  it.each([
    [null, null],
    ["attachment", null],
    ['attachment; filename="despensa.txt"', "despensa.txt"],
    ["attachment; filename=tudo.json", "tudo.json"],
    ["attachment; filename*=UTF-8''sabor%20da%20maria.json", "sabor da maria.json"],
    ["attachment; filename*=UTF-8''%E0%A4%A; filename=\"reserva.json\"", "reserva.json"],
    ['attachment; filename="../../etc/passwd"', "passwd"],
    ['attachment; filename="<>"', null],
  ])("%s → %s", (cabecalho, esperado) => {
    expect(nomeDoArquivo(cabecalho)).toBe(esperado);
  });
});

describe("salvarArquivo", () => {
  it("clica num link de download e devolve a memória depois", () => {
    const clique = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    salvarArquivo(new Blob(["oi"]), "a.txt");
    expect(clique).toHaveBeenCalled();
    expect(document.querySelector("a[download]")).toBeNull();
    vi.advanceTimersByTime(1_000);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:x");
  });
});

describe("baixarDaApi", () => {
  it("baixa com o nome da API, ou o padrão", async () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    rede.mockResolvedValueOnce(
      new Response("DESPENSA", { status: 200, headers: { "Content-Disposition": 'attachment; filename="minha.txt"' } }),
    );
    await expect(baixarDaApi("/despensa/planilha.txt", "padrao.txt")).resolves.toEqual({ ok: true, nome: "minha.txt" });
    expect(rede.mock.calls[0]?.[0]).toBe("/motor/despensa/planilha.txt");
    rede.mockResolvedValueOnce(new Response("{}", { status: 200 }));
    await expect(baixarDaApi("/exportacao", "sabor-da-maria.json")).resolves.toEqual({ ok: true, nome: "sabor-da-maria.json" });
  });

  it("a rota que não existe volta como ausente; a rede caída, como rede", async () => {
    rede.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }));
    await expect(baixarDaApi("/exportacao", "x.json")).resolves.toMatchObject({ ok: false, categoria: "ausente" });
    rede.mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(baixarDaApi("/exportacao", "x.json")).resolves.toMatchObject({ ok: false, categoria: "rede" });
  });

  it("o que não é erro da API também volta como rede", async () => {
    rede.mockResolvedValueOnce(new Response("x", { status: 200 }));
    vi.spyOn(Response.prototype, "blob").mockRejectedValueOnce(new Error("corrompido"));
    await expect(baixarDaApi("/exportacao", "x.json")).resolves.toMatchObject({ ok: false, categoria: "rede" });
    expect(new ErroDoMotor("a", "uso")).toBeInstanceOf(Error);
  });
});
