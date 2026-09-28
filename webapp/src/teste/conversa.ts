/**
 * Dublês da conversa para os testes: um transporte falso (a API do chat sem
 * rede), com o fluxo do turno nas mãos do teste, e uma loja pronta em cima
 * dele, com o quadro de animação controlado pelo teste.
 *
 *     const { loja, emitir, descarregar } = lojaDeTeste();
 *     await loja.enviar("Oi");
 *     emitir({ seq: 1, tipo: "turno.iniciado" });
 *     descarregar();
 */

import { vi } from "vitest";

import type {
  Conversa,
  EstadoDoChat,
  EstadoDoTurno,
  EventoDoTurno,
  ListaDeConversas,
  MensagemDaConversa,
  ResumoDaConversa,
} from "@/lib/api/conversa";
import type { DependenciasDaLoja, Loja } from "@/lib/conversa/loja";
import { criarLoja } from "@/lib/conversa/loja";
import type { OuvintesDoTurno, Transporte } from "@/lib/conversa/transporte";
import type { EstadoDaConexao } from "@/lib/sse";

export type AssinaturaFalsa = {
  conversaId: string;
  turnoId: string;
  desde: number;
  ouvintes: OuvintesDoTurno;
  fechada: boolean;
};

export function conversaVazia(id = "cv-1", titulo = "Conversa nova"): Conversa {
  return { id, titulo, turno_em_andamento: null, mensagens: [] };
}

export function resumo(id: string, extras: Partial<ResumoDaConversa> = {}): ResumoDaConversa {
  return { id, titulo: `Conversa ${id}`, previa: "", atualizado_texto: "hoje", respondendo: false, ...extras };
}

export function mensagem(
  id: string,
  papel: MensagemDaConversa["papel"],
  texto: string,
  extras: Partial<MensagemDaConversa> = {},
): MensagemDaConversa {
  return { id, papel, partes: [{ tipo: "texto", texto }], quando_texto: "hoje, 14:58", ...extras };
}

export type TransporteFalso = {
  transporte: Transporte & { [K in keyof Transporte]: ReturnType<typeof vi.fn> & Transporte[K] };
  assinaturas: AssinaturaFalsa[];
  /** Um evento no fluxo aberto mais recente. */
  emitir: (evento: { tipo: string; seq?: number; turno_id?: string; [campo: string]: unknown }) => void;
  /** Muda o estado da conexão do fluxo mais recente. */
  conexao: (estado: EstadoDaConexao) => void;
  /** Uma queda do fluxo mais recente. */
  cair: (falha?: { tentativas?: number; caidaHaMs?: number; semAbrir?: boolean }) => void;
};

export function transporteFalso(sobrescrever: Partial<Transporte> = {}): TransporteFalso {
  const assinaturas: AssinaturaFalsa[] = [];
  const padrao: Transporte = {
    listar: async (): Promise<ListaDeConversas> => ({ atual: null, conversas: [] }),
    ler: async (id) => conversaVazia(id),
    criar: async () => conversaVazia("cv-nova"),
    renomear: async (id, titulo) => ({ id, titulo }),
    apagar: async (id) => ({ apagada: id, atual: null }),
    marcarAtual: async (id) => ({ id }),
    enviar: async () => ({ turno_id: "t-1", anexado: false }),
    parar: async () => ({}),
    estadoDoTurno: async (_conversa, turno): Promise<EstadoDoTurno> => ({
      turno_id: turno,
      estado: "em_andamento",
      ultimo_seq: 0,
      iniciado_texto: "hoje",
    }),
    estadoDoChat: async (): Promise<EstadoDoChat> => ({ disponivel: true, modelo: "claude-fable-5-1" }),
    assinar: (conversaId, turnoId, desde, ouvintes) => {
      const assinatura: AssinaturaFalsa = { conversaId, turnoId, desde, ouvintes, fechada: false };
      assinaturas.push(assinatura);
      return {
        fechar: () => {
          assinatura.fechada = true;
        },
        reconectar: () => {},
        get ultimoSeq() {
          return desde;
        },
        get estado() {
          return "aberta" as const;
        },
      };
    },
  };
  const juntos = { ...padrao, ...sobrescrever };
  const transporte = Object.fromEntries(
    Object.entries(juntos).map(([nome, funcao]) => [nome, vi.fn(funcao as (...args: unknown[]) => unknown)]),
  ) as unknown as TransporteFalso["transporte"];

  const aberta = () => {
    const ultima = assinaturas.filter((a) => !a.fechada).at(-1);
    if (!ultima) throw new Error("nenhum fluxo aberto");
    return ultima;
  };

  return {
    transporte,
    assinaturas,
    emitir: (evento) => aberta().ouvintes.aoEvento(evento as unknown as EventoDoTurno),
    conexao: (estado) => aberta().ouvintes.aoMudarEstado?.(estado),
    cair: (falha = {}) =>
      aberta().ouvintes.aoFalhar?.({ tentativas: 1, caidaHaMs: 0, semAbrir: false, ...falha }),
  };
}

export type LojaDeTeste = TransporteFalso & {
  loja: Loja;
  /** Roda o quadro de animação: os eventos na fila chegam ao estado. */
  descarregar: () => void;
  avisar: ReturnType<typeof vi.fn>;
  relogio: { agora: number };
};

export function lojaDeTeste(
  sobrescrever: Partial<Transporte> = {},
  dependencias: Partial<DependenciasDaLoja> = {},
): LojaDeTeste {
  const falso = transporteFalso(sobrescrever);
  const tarefas: (() => void)[] = [];
  const relogio = { agora: 1_000_000 };
  const avisar = vi.fn();
  let proximoId = 0;
  const loja = criarLoja({
    transporte: falso.transporte,
    agora: () => relogio.agora,
    agendar: (tarefa) => {
      tarefas.push(tarefa);
      return () => {
        const indice = tarefas.indexOf(tarefa);
        if (indice >= 0) tarefas.splice(indice, 1);
      };
    },
    avisar,
    novoIdCliente: () => {
      proximoId += 1;
      return `u-${proximoId}`;
    },
    ...dependencias,
  });
  return {
    ...falso,
    loja,
    avisar,
    relogio,
    descarregar: () => {
      for (const tarefa of tarefas.splice(0)) tarefa();
    },
  };
}

/** Espera as promessas pendentes (o `await` de dentro da loja). */
export async function esperarPromessas(vezes = 5): Promise<void> {
  for (let i = 0; i < vezes; i += 1) await Promise.resolve();
}
