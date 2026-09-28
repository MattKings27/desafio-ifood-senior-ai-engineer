import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { configuracaoDaDatilografia, esquecerTodosOsProgressos } from "@/lib/conversa/datilografia";
import { SENTINELA } from "@/lib/conversa/mascara";
import { MOVIMENTO, definirPreferenciaDe } from "@/lib/preferencias";
import { definirMidia } from "@/teste/midia";

import { TextoDaConsultora } from "./TextoDaConsultora";
import { MENOS_MOVIMENTO } from "./useDatilografia";

const RESPOSTA =
  "Olá, Dona Maria! Com o que a senhora tem dá para fazer escondidinho de carne moída, frango acebolado e arroz de forno.";

/** O texto revelado: o que está dentro da peça dos parágrafos (sem a legenda dos valores). */
function texto(container: HTMLElement): string {
  return container.firstElementChild?.firstElementChild?.textContent ?? "";
}

function passar(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

beforeEach(() => {
  configuracaoDaDatilografia.instantanea = false;
  esquecerTodosOsProgressos();
  vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance", "Date", "setTimeout", "setInterval", "clearTimeout", "clearInterval"] });
});

afterEach(() => {
  vi.useRealTimers();
  configuracaoDaDatilografia.instantanea = true;
});

describe("a resposta aparecendo letra a letra", () => {
  it("começa vazia, cresce aos poucos com o cursor, e termina inteira sem cursor", () => {
    const { container } = render(<TextoDaConsultora texto={RESPOSTA} modo="rascunho" chave="t:1" aoVivo />);
    expect(texto(container).length).toBeLessThan(3);
    passar(100);
    const depoisDe100ms = texto(container).length;
    expect(depoisDe100ms).toBeGreaterThan(3);
    expect(depoisDe100ms).toBeLessThan(RESPOSTA.length);
    expect(RESPOSTA.startsWith(texto(container))).toBe(true);
    expect(container.querySelector("[data-escrevendo]")).not.toBeNull();
    passar(2_500);
    expect(texto(container)).toBe(RESPOSTA);
    expect(container.querySelector("[data-escrevendo]")).toBeNull();
  });

  it("acompanha o texto que chega: um bloco grande acelera, e a tela não fica segundos atrás", () => {
    const inicio = RESPOSTA.slice(0, 20);
    const { container, rerender } = render(<TextoDaConsultora texto={inicio} modo="rascunho" chave="t:2" aoVivo chegando />);
    passar(1_000);
    expect(texto(container)).toBe(inicio);
    // Caught up, e ainda pode vir mais: o cursor espera no fim.
    expect(container.querySelector("[data-escrevendo]")).not.toBeNull();
    const longo = `${RESPOSTA} ${RESPOSTA} ${RESPOSTA} ${RESPOSTA}`;
    rerender(<TextoDaConsultora texto={longo} modo="rascunho" chave="t:2" aoVivo chegando />);
    passar(250);
    const rapido = texto(container).length - inicio.length;
    // Em 250 ms, bem mais do que a base de 35 por segundo.
    expect(rapido).toBeGreaterThan(80);
    passar(2_500);
    expect(texto(container)).toBe(longo);
  });

  it("o texto conferido entra no lugar do rascunho sem trocar a peça e sem voltar atrás", () => {
    const rascunho = `A porção sai ${SENTINELA} e o prato inteiro sai ${SENTINELA}, com lucro bom.`;
    const final = "A porção sai R$ 2,47 e o prato inteiro sai R$ 18,90, com lucro bom.";
    const { container, rerender } = render(<TextoDaConsultora texto={rascunho} modo="rascunho" chave="t:3" aoVivo chegando />);
    passar(400);
    const peca = container.firstElementChild;
    const antes = texto(container);
    expect(antes).toContain("R$ ···");
    rerender(<TextoDaConsultora texto={final} modo="final" chave="t:3" aoVivo />);
    expect(container.firstElementChild).toBe(peca);
    const depois = texto(container);
    // O mesmo ponto: o que ela já leu continua lá, só os valores mudaram.
    const esperado = antes
      .replace("R$ ···valor em conferência", "R$ 2,47")
      .replace("R$ ···valor em conferência", "R$ 18,90");
    expect(depois).toBe(esperado);
    expect(depois).toContain("R$ 2,47");
    passar(2_000);
    expect(texto(container)).toBe(final);
  });

  it("quando o turno termina, a resposta guardada continua de onde a outra parou", () => {
    const { container, unmount } = render(<TextoDaConsultora texto={RESPOSTA} modo="final" chave="t:4" aoVivo />);
    passar(300);
    const parou = texto(container).length;
    expect(parou).toBeGreaterThan(0);
    expect(parou).toBeLessThan(RESPOSTA.length);
    unmount();
    const guardada = render(<TextoDaConsultora texto={RESPOSTA} modo="final" chave="t:4" />);
    expect(texto(guardada.container).length).toBe(parou);
    passar(2_500);
    expect(texto(guardada.container)).toBe(RESPOSTA);
    // Do histórico (sem progresso guardado), aparece inteira.
    const historico = render(<TextoDaConsultora texto={RESPOSTA} modo="final" chave="t:velha" />);
    expect(texto(historico.container)).toBe(RESPOSTA);
  });

  it("menos movimento no aparelho: o texto aparece do jeito que chega", () => {
    definirMidia(MENOS_MOVIMENTO, true);
    const { container } = render(<TextoDaConsultora texto={RESPOSTA} modo="rascunho" chave="t:5" aoVivo />);
    expect(texto(container)).toBe(RESPOSTA);
  });

  it("'Reduzir' nas Preferências: o texto aparece do jeito que chega", () => {
    definirPreferenciaDe(MOVIMENTO, "reduzir");
    const { container } = render(<TextoDaConsultora texto={RESPOSTA} modo="rascunho" chave="t:6" aoVivo />);
    expect(texto(container)).toBe(RESPOSTA);
  });
});
