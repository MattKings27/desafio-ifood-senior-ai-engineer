/**
 * O tema: o script que roda antes da primeira pintura e a loja do seletor.
 *
 * O risco que estes testes cobrem é o do piscar e o do desencontro: o script
 * resolver um tema e o seletor outro, ou o automático não acompanhar o sistema.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ouvintesDe, sistemaEscuro } from "@/teste/midia";

import {
  CHAVE_DO_TEMA,
  CONSULTA_ESCURO,
  COR_DA_BARRA,
  SCRIPT_DO_TEMA,
  aplicarTema,
  assinarTema,
  definirPreferencia,
  ehPreferencia,
  lerPreferencia,
  resolverTema,
  temaAplicado,
} from "./tema";

function rodarScript() {
  new Function(SCRIPT_DO_TEMA)();
}

const temaNoHtml = () => document.documentElement.getAttribute("data-tema");
const corDaBarra = () =>
  document.head.querySelector('meta[name="theme-color"]')?.getAttribute("content");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolverTema", () => {
  it.each([
    ["claro", false, "claro"],
    ["claro", true, "claro"],
    ["escuro", false, "escuro"],
    ["automatico", true, "escuro"],
    ["automatico", false, "claro"],
  ] as const)("%s com o sistema escuro=%s dá %s", (preferencia, escuro, esperado) => {
    expect(resolverTema(preferencia, escuro)).toBe(esperado);
  });

  it("só aceita as três preferências", () => {
    expect(ehPreferencia("automatico")).toBe(true);
    expect(ehPreferencia("roxo")).toBe(false);
    expect(ehPreferencia(null)).toBe(false);
  });
});

describe("o script do <head>", () => {
  it("sem nada guardado segue o sistema claro, e pinta a barra do navegador", () => {
    rodarScript();
    expect(temaNoHtml()).toBe("claro");
    expect(corDaBarra()).toBe(COR_DA_BARRA.claro);
  });

  it("sem nada guardado segue o sistema escuro", () => {
    sistemaEscuro(true);
    rodarScript();
    expect(temaNoHtml()).toBe("escuro");
    expect(corDaBarra()).toBe(COR_DA_BARRA.escuro);
  });

  it("a escolha dela vence o sistema, nos dois sentidos", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    rodarScript();
    expect(temaNoHtml()).toBe("escuro");

    sistemaEscuro(true);
    localStorage.setItem(CHAVE_DO_TEMA, "claro");
    rodarScript();
    expect(temaNoHtml()).toBe("claro");
  });

  it("um valor estranho no armazenamento vale como automático", () => {
    sistemaEscuro(true);
    localStorage.setItem(CHAVE_DO_TEMA, "roxo");
    rodarScript();
    expect(temaNoHtml()).toBe("escuro");
  });

  it("reaproveita as metas que já existem (uma por media query) em vez de duplicar", () => {
    const metas = ["(prefers-color-scheme: light)", "(prefers-color-scheme: dark)"].map((media) => {
      const meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      meta.setAttribute("media", media);
      meta.setAttribute("content", "#000000");
      document.head.appendChild(meta);
      return meta;
    });
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    rodarScript();
    expect(document.head.querySelectorAll('meta[name="theme-color"]')).toHaveLength(2);
    expect(metas.map((m) => m.getAttribute("content"))).toEqual([COR_DA_BARRA.escuro, COR_DA_BARRA.escuro]);

    localStorage.setItem(CHAVE_DO_TEMA, "claro");
    aplicarTema();
    expect(metas.map((m) => m.getAttribute("content"))).toEqual([COR_DA_BARRA.claro, COR_DA_BARRA.claro]);
  });

  it("sem armazenamento (navegação restrita) ainda resolve o tema", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    sistemaEscuro(true);
    rodarScript();
    expect(temaNoHtml()).toBe("escuro");
  });

  it("sem matchMedia fica no claro, sem quebrar", () => {
    const original = window.matchMedia;
    Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value: undefined });
    try {
      rodarScript();
      expect(temaNoHtml()).toBe("claro");
    } finally {
      Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value: original });
    }
  });

  it("nenhuma falha escapa do script: a página carrega mesmo assim", () => {
    vi.spyOn(document.documentElement, "setAttribute").mockImplementation(() => {
      throw new Error("sem DOM");
    });
    expect(() => rodarScript()).not.toThrow();
  });
});

describe("a preferência guardada", () => {
  it("padrão é automático", () => {
    expect(lerPreferencia()).toBe("automatico");
  });

  it("lê o que ela escolheu, e ignora o que não é preferência", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    expect(lerPreferencia()).toBe("escuro");
    localStorage.setItem(CHAVE_DO_TEMA, "roxo");
    expect(lerPreferencia()).toBe("automatico");
  });

  it("armazenamento bloqueado é automático, não erro", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    expect(lerPreferencia()).toBe("automatico");
  });
});

describe("aplicarTema", () => {
  it("marca o html e cria a meta da barra quando falta", () => {
    expect(aplicarTema("escuro")).toBe("escuro");
    expect(temaNoHtml()).toBe("escuro");
    expect(corDaBarra()).toBe(COR_DA_BARRA.escuro);
    expect(temaAplicado()).toBe("escuro");
  });

  it("sem argumento, usa a preferência guardada", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "claro");
    sistemaEscuro(true);
    expect(aplicarTema()).toBe("claro");
    expect(temaAplicado()).toBe("claro");
  });

  it("matchMedia que falha conta como sistema claro", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(() => {
      throw new Error("sem mídia");
    });
    expect(aplicarTema("automatico")).toBe("claro");
  });

  it("não reescreve o atributo quando o tema já é o mesmo", () => {
    aplicarTema("claro");
    const escrever = vi.spyOn(document.documentElement, "setAttribute");
    aplicarTema("claro");
    expect(escrever).not.toHaveBeenCalled();
  });
});

describe("a loja do seletor", () => {
  it("definir grava, aplica e avisa quem assina", () => {
    const ouvinte = vi.fn();
    const sair = assinarTema(ouvinte);
    expect(definirPreferencia("escuro")).toBe("escuro");
    expect(localStorage.getItem(CHAVE_DO_TEMA)).toBe("escuro");
    expect(temaNoHtml()).toBe("escuro");
    expect(ouvinte).toHaveBeenCalledTimes(1);
    sair();
  });

  it("sem armazenamento a escolha ainda vale nesta visita", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("cheio");
    });
    expect(definirPreferencia("escuro")).toBe("escuro");
    expect(temaNoHtml()).toBe("escuro");
  });

  it("no automático, acompanha o sistema quando ele muda", () => {
    const ouvinte = vi.fn();
    const sair = assinarTema(ouvinte);
    definirPreferencia("automatico");
    ouvinte.mockClear();

    sistemaEscuro(true);
    expect(temaNoHtml()).toBe("escuro");
    expect(ouvinte).toHaveBeenCalledTimes(1);
    sair();
  });

  it("com uma escolha fixa, a mudança do sistema não mexe em nada", () => {
    const ouvinte = vi.fn();
    const sair = assinarTema(ouvinte);
    definirPreferencia("claro");
    ouvinte.mockClear();

    sistemaEscuro(true);
    expect(temaNoHtml()).toBe("claro");
    expect(ouvinte).not.toHaveBeenCalled();
    sair();
  });

  it("outra aba que troca o tema é acompanhada; outra chave, não", () => {
    const ouvinte = vi.fn();
    const sair = assinarTema(ouvinte);

    window.dispatchEvent(new StorageEvent("storage", { key: "outra-coisa" }));
    expect(ouvinte).not.toHaveBeenCalled();

    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    window.dispatchEvent(new StorageEvent("storage", { key: CHAVE_DO_TEMA }));
    expect(temaNoHtml()).toBe("escuro");
    expect(ouvinte).toHaveBeenCalledTimes(1);

    // `key: null` é o `localStorage.clear()` de outra aba.
    localStorage.clear();
    window.dispatchEvent(new StorageEvent("storage", { key: null }));
    expect(ouvinte).toHaveBeenCalledTimes(2);
    sair();
  });

  it("o último a sair desliga os ouvintes do sistema: nada vaza", () => {
    const sairA = assinarTema(() => {});
    const sairB = assinarTema(() => {});
    expect(ouvintesDe(CONSULTA_ESCURO)).toBe(1);
    sairA();
    expect(ouvintesDe(CONSULTA_ESCURO)).toBe(1);
    sairB();
    expect(ouvintesDe(CONSULTA_ESCURO)).toBe(0);
  });
});
