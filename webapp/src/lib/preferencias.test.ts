/**
 * As preferências dela: o script que aplica tema, tamanho do texto e movimento
 * antes da primeira pintura, a leitura e a gravação no aparelho, e a troca
 * feita em outra aba.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { sistemaEscuro } from "@/teste/midia";

import {
  MINIMALISTA,
  MOVIMENTO,
  PASSOS_DA_CONSULTORA,
  SCRIPT_DA_APARENCIA,
  TAMANHO_DO_TEXTO,
  aplicarAparencia,
  assinarPreferencias,
  definirPreferenciaDe,
  lerPreferenciaDe,
} from "./preferencias";
import { CHAVE_DO_TEMA, SCRIPT_DO_TEMA } from "./tema";
import { useMinimalista, usePreferencia, usePreferenciaDeTema } from "./usePreferencias";

const html = () => document.documentElement;

afterEach(() => {
  vi.restoreAllMocks();
  html().removeAttribute("data-texto");
  html().removeAttribute("data-movimento");
  html().removeAttribute("data-minimalista");
});

function rodarScript() {
  new Function(SCRIPT_DA_APARENCIA)();
}

describe("o script do <head>", () => {
  it("começa pelo do tema e marca o tamanho do texto e o movimento", () => {
    expect(SCRIPT_DA_APARENCIA.startsWith(SCRIPT_DO_TEMA)).toBe(true);
    rodarScript();
    expect(html().getAttribute("data-tema")).toBe("claro");
    expect(html().getAttribute("data-texto")).toBe("normal");
    expect(html().getAttribute("data-movimento")).toBe("sistema");
    expect(html().getAttribute("data-minimalista")).toBe("desligado");
  });

  it("aplica o que ela escolheu, e ignora valor estranho", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    localStorage.setItem("texto", "grande");
    localStorage.setItem("movimento", "reduzir");
    rodarScript();
    expect([html().getAttribute("data-tema"), html().getAttribute("data-texto"), html().getAttribute("data-movimento")]).toEqual([
      "escuro",
      "grande",
      "reduzir",
    ]);
    localStorage.setItem("texto", "gigante");
    rodarScript();
    expect(html().getAttribute("data-texto")).toBe("normal");
  });

  it("o modo minimalista ligado vale antes da primeira pintura; valor estranho fica desligado", () => {
    localStorage.setItem("minimalista", "ligado");
    rodarScript();
    expect(html().getAttribute("data-minimalista")).toBe("ligado");
    localStorage.setItem("minimalista", "sim");
    rodarScript();
    expect(html().getAttribute("data-minimalista")).toBe("desligado");
  });

  it("sem armazenamento, fica o padrão, sem quebrar a página", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    sistemaEscuro(true);
    expect(() => rodarScript()).not.toThrow();
    expect(html().getAttribute("data-tema")).toBe("escuro");
    expect(html().getAttribute("data-texto")).toBe("normal");
  });

  it("nenhuma falha escapa", () => {
    vi.spyOn(html(), "setAttribute").mockImplementation(() => {
      throw new Error("sem DOM");
    });
    expect(() => rodarScript()).not.toThrow();
  });
});

describe("ler, gravar e aplicar", () => {
  it("lê o guardado, com o padrão para o que falta ou não vale", () => {
    expect(lerPreferenciaDe(TAMANHO_DO_TEXTO)).toBe("normal");
    localStorage.setItem("texto", "grande");
    expect(lerPreferenciaDe(TAMANHO_DO_TEXTO)).toBe("grande");
    localStorage.setItem("movimento", "rapido");
    expect(lerPreferenciaDe(MOVIMENTO)).toBe("sistema");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    expect(lerPreferenciaDe(PASSOS_DA_CONSULTORA)).toBe("recolhidos");
  });

  it("gravar aplica no <html> (o que é da tela inteira) e avisa quem assina", () => {
    const ouvinte = vi.fn();
    const sair = assinarPreferencias(ouvinte);
    definirPreferenciaDe(TAMANHO_DO_TEXTO, "grande");
    expect(localStorage.getItem("texto")).toBe("grande");
    expect(html().getAttribute("data-texto")).toBe("grande");
    definirPreferenciaDe(PASSOS_DA_CONSULTORA, "abertos");
    expect(localStorage.getItem("passos-da-consultora")).toBe("abertos");
    expect(ouvinte).toHaveBeenCalledTimes(2);
    sair();
    definirPreferenciaDe(MOVIMENTO, "reduzir");
    expect(ouvinte).toHaveBeenCalledTimes(2);
  });

  it("sem armazenamento, a escolha vale nesta visita", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("cheio");
    });
    definirPreferenciaDe(MOVIMENTO, "reduzir");
    expect(html().getAttribute("data-movimento")).toBe("reduzir");
  });

  it("aplicarAparencia marca o guardado, e não reescreve o que já está igual", () => {
    localStorage.setItem("movimento", "reduzir");
    aplicarAparencia();
    expect(html().getAttribute("data-movimento")).toBe("reduzir");
    const escrever = vi.spyOn(html(), "setAttribute");
    aplicarAparencia();
    expect(escrever).not.toHaveBeenCalled();
  });

  it("outra aba mudou: esta acompanha; chave de fora não conta", () => {
    const ouvinte = vi.fn();
    const sair = assinarPreferencias(ouvinte);
    const outro = assinarPreferencias(() => {});
    localStorage.setItem("texto", "grande");
    window.dispatchEvent(new StorageEvent("storage", { key: "texto" }));
    expect(html().getAttribute("data-texto")).toBe("grande");
    window.dispatchEvent(new StorageEvent("storage", { key: "outra-coisa" }));
    window.dispatchEvent(new StorageEvent("storage", { key: null }));
    expect(ouvinte).toHaveBeenCalledTimes(2);
    sair();
    outro();
    window.dispatchEvent(new StorageEvent("storage", { key: "texto" }));
    expect(ouvinte).toHaveBeenCalledTimes(2);
  });
});

describe("os ganchos do React", () => {
  it("usePreferencia acompanha a escolha", () => {
    const { result } = renderHook(() => usePreferencia(TAMANHO_DO_TEXTO));
    expect(result.current).toBe("normal");
    act(() => definirPreferenciaDe(TAMANHO_DO_TEXTO, "grande"));
    expect(result.current).toBe("grande");
  });

  it("useMinimalista diz se o modo está ligado, e acompanha a troca", () => {
    const { result } = renderHook(() => useMinimalista());
    expect(result.current).toBe(false);
    act(() => definirPreferenciaDe(MINIMALISTA, "ligado"));
    expect(result.current).toBe(true);
    expect(html().getAttribute("data-minimalista")).toBe("ligado");
    act(() => definirPreferenciaDe(MINIMALISTA, "desligado"));
    expect(result.current).toBe(false);
  });

  it("outra aba ligou o modo minimalista: esta acompanha", () => {
    const { result } = renderHook(() => useMinimalista());
    localStorage.setItem("minimalista", "ligado");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "minimalista" }));
    });
    expect(result.current).toBe(true);
    expect(html().getAttribute("data-minimalista")).toBe("ligado");
  });

  it("usePreferenciaDeTema lê o tema guardado", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    const { result } = renderHook(() => usePreferenciaDeTema());
    expect(result.current).toBe("escuro");
  });
});
