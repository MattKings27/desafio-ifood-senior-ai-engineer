/**
 * Preparo comum a todo teste de interface.
 *
 * O jsdom 30 não tem `<dialog>` modal, `matchMedia`, `IntersectionObserver`,
 * `ResizeObserver` nem `scrollIntoView`. Os dublês abaixo fazem só o que os
 * componentes usam, e o bastante para o comportamento ser testado: o diálogo
 * abre e fecha, dispara `close` e `cancel`; as mídias mudam quando o teste
 * manda.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, expect } from "vitest";
import * as matchers from "vitest-axe/matchers";

import { configuracaoDaDatilografia } from "@/lib/conversa/datilografia";

import { instalarMatchMedia, reiniciarMidia } from "./midia";

expect.extend(matchers);

instalarMatchMedia();

// A resposta aparece de uma vez nos testes de interface, como para quem pediu
// menos movimento; os testes da datilografia ligam o ritmo de propósito.
configuracaoDaDatilografia.instantanea = true;

/* --- <dialog> ----------------------------------------------------------- */

const prototipo = HTMLDialogElement.prototype as HTMLDialogElement & {
  showModal?: () => void;
  show?: () => void;
  close?: (valor?: string) => void;
};

if (typeof prototipo.showModal !== "function") {
  prototipo.show = function show(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  prototipo.showModal = function showModal(this: HTMLDialogElement) {
    if (this.hasAttribute("open")) {
      throw new DOMException("O diálogo já está aberto", "InvalidStateError");
    }
    this.setAttribute("open", "");
    this.setAttribute("data-modal", "");
  };
  prototipo.close = function close(this: HTMLDialogElement, valor?: string) {
    if (!this.hasAttribute("open")) return;
    if (valor !== undefined) this.returnValue = valor;
    this.removeAttribute("open");
    this.removeAttribute("data-modal");
    this.dispatchEvent(new Event("close"));
  };
  Object.defineProperty(prototipo, "open", {
    configurable: true,
    get(this: HTMLDialogElement) {
      return this.hasAttribute("open");
    },
    set(this: HTMLDialogElement, valor: boolean) {
      if (valor) this.setAttribute("open", "");
      else this.removeAttribute("open");
    },
  });
}

/* --- observadores e rolagem ------------------------------------------------ */

class ObservadorQuieto {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

for (const nome of ["IntersectionObserver", "ResizeObserver"] as const) {
  if (!(nome in window)) {
    Object.defineProperty(window, nome, { configurable: true, writable: true, value: ObservadorQuieto });
    Object.defineProperty(globalThis, nome, { configurable: true, writable: true, value: ObservadorQuieto });
  }
}

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

// Sem isto um teste enxerga o DOM (e o tema, e o armazenamento) que o anterior
// deixou, e a falha aparece no teste errado.
afterEach(() => {
  cleanup();
  reiniciarMidia();
  try {
    window.localStorage.clear();
    window.sessionStorage.clear();
  } catch {
    // jsdom sem armazenamento: nada a limpar.
  }
  document.documentElement.removeAttribute("data-tema");
  document.documentElement.removeAttribute("data-minimalista");
  for (const meta of document.head.querySelectorAll('meta[name="theme-color"]')) meta.remove();
});
