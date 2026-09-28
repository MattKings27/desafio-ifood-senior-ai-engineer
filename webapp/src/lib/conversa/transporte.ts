/**
 * O caminho até o backend do chat, numa interface só: a loja fala com isto, e
 * os testes trocam por um transporte falso.
 *
 * O real usa `api.conversa` (envelope, categorias de erro, 409 que anexa) e o
 * `assinarFluxo` de `@/lib/sse` (sem repetição, espera crescente, retomada).
 */

import type {
  Conversa,
  EstadoDoChat,
  EstadoDoTurno,
  EventoDoTurno,
  ListaDeConversas,
  PedidoDeTurno,
  ResumoDaConversa,
  TurnoEnviado,
} from "@/lib/api/conversa";
import { conversa as apiDaConversa } from "@/lib/api/conversa";
import type { Assinatura, EstadoDaConexao, FalhaDaConexao } from "@/lib/sse";
import { assinarFluxo } from "@/lib/sse";

export type OuvintesDoTurno = {
  aoEvento: (evento: EventoDoTurno) => void;
  aoMudarEstado?: (estado: EstadoDaConexao) => void;
  aoFalhar?: (falha: FalhaDaConexao) => void;
};

export type Transporte = {
  listar: () => Promise<ListaDeConversas>;
  ler: (id: string) => Promise<Conversa>;
  criar: () => Promise<Conversa>;
  renomear: (id: string, titulo: string) => Promise<Pick<ResumoDaConversa, "id" | "titulo">>;
  apagar: (id: string) => Promise<{ apagada: string; atual?: string | null }>;
  marcarAtual: (id: string) => Promise<unknown>;
  enviar: (conversaId: string, pedido: PedidoDeTurno) => Promise<TurnoEnviado>;
  parar: (conversaId: string, turnoId: string) => Promise<unknown>;
  estadoDoTurno: (conversaId: string, turnoId: string) => Promise<EstadoDoTurno>;
  estadoDoChat: () => Promise<EstadoDoChat>;
  assinar: (conversaId: string, turnoId: string, desde: number, ouvintes: OuvintesDoTurno) => Assinatura;
};

/** O turno acabou: depois destes, o fluxo não manda mais nada. */
export function ehFimDoTurno(evento: { tipo?: unknown }): boolean {
  return evento.tipo === "turno.concluido" || evento.tipo === "turno.cancelado" || evento.tipo === "turno.falhou";
}

export function transporteReal(criar?: (url: string) => EventSource): Transporte {
  return {
    listar: () => apiDaConversa.listar(),
    ler: (id) => apiDaConversa.ler(id),
    criar: () => apiDaConversa.criar(),
    renomear: (id, titulo) => apiDaConversa.renomear(id, titulo),
    apagar: (id) => apiDaConversa.apagar(id),
    marcarAtual: (id) => apiDaConversa.marcarAtual(id),
    enviar: (conversaId, pedido) => apiDaConversa.enviarTurno(conversaId, pedido),
    parar: (conversaId, turnoId) => apiDaConversa.parar(conversaId, turnoId),
    estadoDoTurno: (conversaId, turnoId) => apiDaConversa.estadoDoTurno(conversaId, turnoId),
    estadoDoChat: () => apiDaConversa.estadoDoChat({ tempoLimiteMs: 8_000 }),
    assinar: (conversaId, turnoId, desde, ouvintes) =>
      assinarFluxo<EventoDoTurno>({
        url: (seq) => apiDaConversa.urlDosEventos(conversaId, turnoId, seq),
        desde,
        aoEvento: ouvintes.aoEvento,
        aoMudarEstado: ouvintes.aoMudarEstado,
        aoFalhar: ouvintes.aoFalhar,
        ehFinal: ehFimDoTurno,
        ...(criar ? { criar } : {}),
      }),
  };
}
