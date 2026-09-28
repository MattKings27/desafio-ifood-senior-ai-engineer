/**
 * O transporte real: cada função chega à rota certa da API do chat, e a
 * assinatura do turno usa o fluxo de eventos com retomada.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventSourceFalso, criarEventSourceFalso } from "@/teste/eventsource-falso";

import { ehFimDoTurno, transporteReal } from "./transporte";

const envelope = (dados: unknown) => ({ ok: true, dados, erro: null, categoria: null, pergunta: null });

let rede: ReturnType<typeof vi.fn>;

beforeEach(() => {
  rede = vi.fn(async () => new Response(JSON.stringify(envelope({ turno_id: "t-1" })), { status: 202 }));
  vi.stubGlobal("fetch", rede);
  EventSourceFalso.reiniciar();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function chamada(indice = -1): { url: string; metodo: string; corpo: unknown } {
  const [url, init] = rede.mock.calls.at(indice) as [string, RequestInit];
  return { url, metodo: init.method ?? "GET", corpo: init.body === undefined ? undefined : JSON.parse(String(init.body)) };
}

describe("transporteReal", () => {
  it("cada função vai à sua rota", async () => {
    const t = transporteReal(criarEventSourceFalso);
    await t.listar();
    expect(chamada()).toMatchObject({ url: "/motor/conversas", metodo: "GET" });
    await t.ler("cv-1");
    expect(chamada().url).toBe("/motor/conversas/cv-1");
    await t.criar();
    expect(chamada()).toMatchObject({ url: "/motor/conversas", metodo: "POST", corpo: {} });
    await t.renomear("cv-1", "Bolo");
    expect(chamada()).toMatchObject({ metodo: "PATCH", corpo: { titulo: "Bolo" } });
    await t.marcarAtual("cv-1");
    expect(chamada()).toMatchObject({ url: "/motor/conversas/cv-1", metodo: "PATCH", corpo: { atual: true } });
    await t.apagar("cv-1");
    expect(chamada()).toMatchObject({ metodo: "DELETE" });
    await expect(t.enviar("cv-1", { texto: "Oi", id_cliente: "u-1" })).resolves.toEqual({ turno_id: "t-1", anexado: false });
    expect(chamada()).toMatchObject({ url: "/motor/conversas/cv-1/turnos", metodo: "POST", corpo: { texto: "Oi", id_cliente: "u-1" } });
    await t.parar("cv-1", "t-1");
    expect(chamada()).toMatchObject({ url: "/motor/conversas/cv-1/turnos/t-1/parar", metodo: "POST" });
    await t.estadoDoTurno("cv-1", "t-1");
    expect(chamada().url).toBe("/motor/conversas/cv-1/turnos/t-1");
    await t.estadoDoChat();
    expect(chamada().url).toBe("/motor/chat/estado");
  });

  it("assina o fluxo do turno a partir do último visto, e fecha no fim do turno", () => {
    const t = transporteReal(criarEventSourceFalso);
    const eventos: unknown[] = [];
    const estados: string[] = [];
    const assinatura = t.assinar("cv-1", "t-1", 4, {
      aoEvento: (evento) => eventos.push(evento),
      aoMudarEstado: (estado) => estados.push(estado),
    });
    const fonte = EventSourceFalso.ultima();
    expect(fonte.url).toBe("/motor/conversas/cv-1/turnos/t-1/eventos?desde=4");
    fonte.abrir();
    fonte.emitir({ seq: 5, tipo: "turno.concluido" });
    expect(eventos).toHaveLength(1);
    expect(assinatura.estado).toBe("encerrada");
    expect(estados).toEqual(["aberta", "encerrada"]);
  });

  it("sem fabricante, usa o do navegador", () => {
    const antes = (globalThis as { EventSource?: unknown }).EventSource;
    (globalThis as { EventSource?: unknown }).EventSource = EventSourceFalso;
    try {
      transporteReal().assinar("cv-1", "t-1", 0, { aoEvento: () => {} }).fechar();
      expect(EventSourceFalso.ultima().url).toBe("/motor/conversas/cv-1/turnos/t-1/eventos?desde=0");
    } finally {
      (globalThis as { EventSource?: unknown }).EventSource = antes;
    }
  });
});

describe("ehFimDoTurno", () => {
  it.each([
    ["turno.concluido", true],
    ["turno.cancelado", true],
    ["turno.falhou", true],
    ["texto.final", false],
    [undefined, false],
  ])("%s → %s", (tipo, esperado) => {
    expect(ehFimDoTurno({ tipo })).toBe(esperado);
  });
});
