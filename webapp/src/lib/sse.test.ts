/**
 * O fluxo de eventos que se recupera sozinho: sem repetição, reconexão com
 * espera crescente e retomada pelo último `seq`, a aba e a internet voltando,
 * e o fim do fluxo.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventSourceFalso, criarEventSourceFalso, instalarEventSourceFalso } from "@/teste/eventsource-falso";

import { ESPERAS_PADRAO, SILENCIO_SUSPEITO_MS, assinarFluxo } from "./sse";

type Evento = { seq?: number; tipo: string };

let agora = 0;
/** Toda assinatura aberta num teste é fechada no fim dele: senão ela escuta a aba do próximo. */
const abertas: { fechar: () => void }[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  EventSourceFalso.reiniciar();
  agora = 1_000;
});

afterEach(() => {
  for (const assinatura of abertas.splice(0)) assinatura.fechar();
  vi.useRealTimers();
});

function assinar(extras: Partial<Parameters<typeof assinarFluxo<Evento>>[0]> = {}) {
  const eventos: Evento[] = [];
  const estados: string[] = [];
  const falhas: unknown[] = [];
  const assinatura = assinarFluxo<Evento>({
    url: (desde) => `/motor/fluxo?desde=${desde}`,
    aoEvento: (evento) => eventos.push(evento),
    aoMudarEstado: (estado) => estados.push(estado),
    aoFalhar: (falha) => falhas.push(falha),
    ehFinal: (evento) => evento.tipo === "fim",
    criar: criarEventSourceFalso,
    agora: () => agora,
    ...extras,
  });
  abertas.push(assinatura);
  return { assinatura, eventos, estados, falhas };
}

describe("assinarFluxo", () => {
  it("abre do último visto, entrega cada evento uma vez e fecha no fim", () => {
    const { assinatura, eventos, estados } = assinar({ desde: 3 });
    const fonte = EventSourceFalso.ultima();
    expect(fonte.url).toBe("/motor/fluxo?desde=3");
    expect(assinatura.estado).toBe("conectando");
    fonte.abrir();
    fonte.emitir({ seq: 2, tipo: "velho" });
    fonte.emitir({ seq: 4, tipo: "a" });
    fonte.emitir({ seq: 4, tipo: "a" });
    fonte.emitir({ tipo: "b" }, 5);
    fonte.emitir({ tipo: "sem-seq" });
    fonte.emitir("não é json");
    fonte.emitir(JSON.stringify(7));
    fonte.onmessage?.(new MessageEvent("message", { data: 3 }));
    expect(eventos.map((e) => e.tipo)).toEqual(["a", "b", "sem-seq"]);
    expect(assinatura.ultimoSeq).toBe(5);
    fonte.emitir({ seq: 6, tipo: "fim" });
    expect(assinatura.estado).toBe("encerrada");
    expect(fonte.fechada).toBe(true);
    expect(estados).toEqual(["aberta", "encerrada"]);
    // Fechar de novo, reconectar ou a aba voltar não fazem nada depois do fim.
    assinatura.fechar();
    assinatura.reconectar();
    expect(EventSourceFalso.instancias).toHaveLength(1);
  });

  it("caiu: reabre com espera crescente a partir do último visto, e avisa quem assina", () => {
    const { eventos, falhas, estados } = assinar();
    const primeira = EventSourceFalso.ultima();
    primeira.abrir();
    primeira.emitir({ seq: 1, tipo: "a" });
    agora += 500;
    primeira.cair();
    expect(falhas).toEqual([{ tentativas: 1, caidaHaMs: 0, semAbrir: false }]);
    expect(estados.at(-1)).toBe("reconectando");
    vi.advanceTimersByTime(ESPERAS_PADRAO[0]! - 1);
    expect(EventSourceFalso.instancias).toHaveLength(1);
    vi.advanceTimersByTime(1);
    const segunda = EventSourceFalso.ultima();
    expect(segunda.url).toBe("/motor/fluxo?desde=1");

    agora += 2_000;
    segunda.cair();
    expect(falhas.at(-1)).toEqual({ tentativas: 2, caidaHaMs: 2_000, semAbrir: true });
    vi.advanceTimersByTime(ESPERAS_PADRAO[1]!);
    const terceira = EventSourceFalso.ultima();
    terceira.abrir();
    terceira.emitir({ seq: 1, tipo: "a" });
    terceira.emitir({ seq: 2, tipo: "b" });
    expect(eventos.map((e) => e.tipo)).toEqual(["a", "b"]);
  });

  it("depois da última espera, repete a última; esperas próprias valem", () => {
    assinar({ esperasMs: [10, 20] });
    for (let i = 0; i < 3; i += 1) {
      EventSourceFalso.ultima().cair();
      vi.advanceTimersByTime(i === 0 ? 10 : 20);
    }
    expect(EventSourceFalso.instancias).toHaveLength(4);
    assinar({ esperasMs: [] });
    EventSourceFalso.ultima().cair();
    vi.advanceTimersByTime(ESPERAS_PADRAO[0]!);
    expect(EventSourceFalso.instancias).toHaveLength(6);
  });

  it("quem assina pode desistir no aviso de falha", () => {
    let assinatura: ReturnType<typeof assinarFluxo> | null = null;
    assinatura = assinarFluxo<Evento>({
      url: () => "/f",
      aoEvento: () => {},
      aoFalhar: () => assinatura?.fechar(),
      criar: criarEventSourceFalso,
    });
    abertas.push(assinatura);
    EventSourceFalso.ultima().cair();
    vi.advanceTimersByTime(20_000);
    expect(EventSourceFalso.instancias).toHaveLength(1);
    expect(assinatura.estado).toBe("encerrada");
  });

  it("a aba voltou: reconecta se estava caída, ou calada demais", () => {
    const { assinatura } = assinar();
    const fonte = EventSourceFalso.ultima();
    fonte.abrir();
    const visibilidade = vi.spyOn(document, "visibilityState", "get");
    visibilidade.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(EventSourceFalso.instancias).toHaveLength(1);

    visibilidade.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(EventSourceFalso.instancias).toHaveLength(1);

    agora += SILENCIO_SUSPEITO_MS + 1;
    document.dispatchEvent(new Event("visibilitychange"));
    expect(EventSourceFalso.instancias).toHaveLength(2);
    expect(fonte.fechada).toBe(true);

    assinatura.fechar();
    document.dispatchEvent(new Event("visibilitychange"));
    expect(EventSourceFalso.instancias).toHaveLength(2);
    visibilidade.mockRestore();
  });

  it("a internet voltou: reconecta se não estava aberta", () => {
    const { assinatura } = assinar();
    const fonte = EventSourceFalso.ultima();
    fonte.abrir();
    window.dispatchEvent(new Event("online"));
    expect(EventSourceFalso.instancias).toHaveLength(1);
    fonte.cair();
    window.dispatchEvent(new Event("online"));
    expect(EventSourceFalso.instancias).toHaveLength(2);
    assinatura.fechar();
    window.dispatchEvent(new Event("online"));
    expect(EventSourceFalso.instancias).toHaveLength(2);
  });

  it("sem fabricante, usa o EventSource do navegador", () => {
    const desfazer = instalarEventSourceFalso();
    const assinatura = assinarFluxo<Evento>({ url: () => "/nativo", aoEvento: () => {} });
    expect(EventSourceFalso.ultima().url).toBe("/nativo");
    const fonte = EventSourceFalso.ultima();
    const ouvinte = vi.fn();
    fonte.addEventListener("message", ouvinte);
    fonte.emitir({ seq: 1, tipo: "a" });
    fonte.removeEventListener("message", ouvinte);
    fonte.emitir({ seq: 2, tipo: "b" });
    expect(ouvinte).toHaveBeenCalledTimes(1);
    assinatura.fechar();
    fonte.abrir();
    fonte.emitir({ seq: 3, tipo: "c" });
    fonte.cair();
    expect(EventSourceFalso.abertas()).toHaveLength(0);
    desfazer();
    expect(() => EventSourceFalso.ultima()).toThrow("nenhum EventSource");
  });
});
