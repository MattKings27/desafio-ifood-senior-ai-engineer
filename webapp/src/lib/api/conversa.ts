/**
 * A conversa com o agente: conversas, turnos e o fluxo de eventos.
 *
 * O turno é do backend: o navegador faz POST, recebe o `turno_id` e assina um
 * fluxo de eventos (SSE) que pode ser retomado. Fechar a aba não cancela;
 * parar é um POST explícito. Formas em `contratos/web/conversa*.json` e
 * `chat-eventos.jsonl`.
 *
 * Alguns campos vão além do contrato v1 e são opcionais aqui (o backend do
 * chat já os manda): `ref.parametros` no card, e, em cada mensagem guardada,
 * `turno_id`, `estado`, `retirados`, `erro`, `acao_resultado`, `sugestoes` e o
 * `rascunho` da parte de texto de um turno que não terminou.
 */

import type { OpcoesDoPedido } from "./base";
import type { CategoriaDeEstrela } from "./receitas";
import {
  ErroDoMotor,
  MENSAGENS,
  buscar,
  comCorpo,
  ehEnvelope,
  erroDaResposta,
  lerCorpo,
  pedir,
  urlDeEventos,
} from "./base";

export type PapelNaConversa = "senhora" | "consultora";

/** De onde ela abriu a conversa: a tela e o que estava olhando. */
export type ContextoDaConversa = {
  tela: string;
  tipo: string;
  id?: string;
  rotulo?: string;
};

/** Para onde o card aponta: a rota que deu os dados, já concreta. `null` quando os dados bastam. */
export type RefDoCartao = {
  rota: string | null;
  parametros?: Record<string, unknown>;
};

/** Um card na conversa. `dados` tem a forma da rota em `ref.rota`. */
export type CartaoDaConversa = {
  cartao_id: string;
  tipo_cartao: string;
  ref: RefDoCartao;
  gerado_texto: string;
  dados: unknown;
};

export type ParteDaMensagem =
  | { tipo: "texto"; texto: string; rascunho?: boolean }
  | { tipo: "cartao"; cartao: CartaoDaConversa };

/** Como terminou o turno que produziu a resposta guardada. */
export type DesfechoDaResposta = "concluido" | "cancelado" | "falhou" | "interrompido";

export type CategoriaDaFalha = "rede" | "tempo" | "consultora" | "regra";

export type MensagemDaConversa = {
  id: string;
  papel: PapelNaConversa;
  partes: ParteDaMensagem[];
  quando_texto: string;
  turno_id?: string | null;
  contexto?: ContextoDaConversa | null;
  estado?: DesfechoDaResposta | (string & {});
  retirados?: number;
  atividades?: { rotulo_feito: string; ok?: boolean }[];
  acao_resultado?: { ok: boolean; texto: string } | null;
  erro?: { categoria: CategoriaDaFalha | (string & {}); mensagem: string } | null;
  sugestoes?: OpcaoSugerida[];
};

export type EstadoDoTurno = {
  turno_id: string;
  estado: "em_andamento" | "concluido" | "cancelado" | "falhou" | "interrompido" | (string & {});
  ultimo_seq: number;
  iniciado_texto: string;
};

export type Conversa = {
  id: string;
  titulo: string;
  atual?: boolean;
  turno_em_andamento: EstadoDoTurno | null;
  mensagens: MensagemDaConversa[];
};

export type ResumoDaConversa = {
  id: string;
  titulo: string;
  previa: string;
  atualizado_texto: string;
  respondendo: boolean;
};

export type ListaDeConversas = { atual: string | null; conversas: ResumoDaConversa[] };

/** O que um botão de card manda: o backend executa antes de contar ao agente. */
export type AcaoDoCartao =
  | {
      tipo: "responder";
      tipo_pergunta: string;
      campo: string;
      resposta: string;
      /** A pergunta é da própria receita (o item parecido): a resposta fica gravada nela. */
      receita_id?: string;
    }
  | { tipo: "decidir"; prato: string; decisao: string; preco?: number }
  | {
      tipo: "avaliar";
      receita_id: string;
      gosta?: boolean | null;
      estrelas?: Partial<Record<CategoriaDeEstrela, number | null>>;
      notas?: string;
    };

export type PedidoDeTurno = {
  texto: string;
  contexto?: ContextoDaConversa;
  acao?: AcaoDoCartao;
  /** Gerado no navegador: repetir o envio com o mesmo id não duplica nada. */
  id_cliente: string;
};

export type OpcaoSugerida = { rotulo: string; texto: string; acao?: AcaoDoCartao };

type ComSeq = { seq: number; turno_id?: string };

export type EventoDoTurno = ComSeq &
  (
    | { tipo: "turno.iniciado"; conversa_id: string; mensagem_id?: string; id_cliente?: string }
    | { tipo: "acao.resultado"; ok: boolean; texto: string; cartao?: CartaoDaConversa }
    | {
        tipo: "atividade.iniciada";
        atividade_id: string;
        ferramenta: string;
        rotulo: string;
        rotulo_feito: string;
        detalhe?: string;
      }
    | { tipo: "atividade.concluida"; atividade_id: string; ok: boolean; resumo?: string }
    | ({ tipo: "cartao" } & CartaoDaConversa)
    | { tipo: "texto.parcial"; delta: string }
    | { tipo: "texto.comentario"; texto: string }
    | { tipo: "texto.final"; texto: string; retirados: number }
    | { tipo: "estado.alterado"; recursos: string[] }
    | { tipo: "sugestoes"; opcoes: OpcaoSugerida[] }
    | { tipo: "turno.concluido" }
    | { tipo: "turno.cancelado" }
    | {
        tipo: "turno.falhou";
        categoria: CategoriaDaFalha | (string & {});
        mensagem: string;
        interrompido?: boolean;
      }
  );

export type TurnoEnviado = {
  turno_id: string;
  /** `true` quando já havia um turno rodando (409) e o navegador se anexou a ele. */
  anexado: boolean;
};

/** O agente atende agora? Fora do ar é dado (`disponivel: false`), não erro. */
export type EstadoDoChat = {
  disponivel: boolean;
  motivo?: string | null;
  aviso?: string | null;
  /** O modelo que responde (`claude-fable-5-1`), quando o backend sabe dizer. */
  modelo?: string | null;
};

const daConversa = (id: string) => `/conversas/${encodeURIComponent(id)}`;
const doTurno = (conversa: string, turno: string) =>
  `${daConversa(conversa)}/turnos/${encodeURIComponent(turno)}`;

function dadosDe(corpo: unknown): unknown {
  return ehEnvelope(corpo) ? corpo.dados : corpo;
}

function turnoIdDe(corpo: unknown): string | null {
  const dentro = dadosDe(corpo);
  if (typeof dentro !== "object" || dentro === null) return null;
  const id = (dentro as { turno_id?: unknown }).turno_id;
  return typeof id === "string" && id !== "" ? id : null;
}

export const conversa = {
  listar: (opcoes?: OpcoesDoPedido) => pedir<ListaDeConversas>("/conversas", opcoes),

  criar: (titulo?: string) =>
    pedir<Conversa>("/conversas", comCorpo("POST", titulo ? { titulo } : {})),

  ler: (id: string, opcoes?: OpcoesDoPedido) => pedir<Conversa>(daConversa(id), opcoes),

  renomear: (id: string, titulo: string) =>
    pedir<Pick<ResumoDaConversa, "id" | "titulo">>(daConversa(id), comCorpo("PATCH", { titulo })),

  /** Marca a conversa como a atual (a que abre quando ela volta). */
  marcarAtual: (id: string) =>
    pedir<Pick<ResumoDaConversa, "id" | "titulo">>(daConversa(id), comCorpo("PATCH", { atual: true })),

  apagar: (id: string) =>
    pedir<{ apagada: string; atual?: string | null }>(daConversa(id), comCorpo("DELETE")),

  /**
   * Manda a mensagem dela. 202 começa um turno; 409 diz que já havia um
   * rodando, e o navegador se anexa a ele em vez de mostrar erro.
   */
  async enviarTurno(conversaId: string, pedido: PedidoDeTurno): Promise<TurnoEnviado> {
    const resposta = await buscar(`${daConversa(conversaId)}/turnos`, comCorpo("POST", pedido));
    if (resposta.status === 409) {
      const turno = turnoIdDe(await lerCorpo(resposta.clone()));
      if (turno) return { turno_id: turno, anexado: true };
    }
    if (!resposta.ok) throw await erroDaResposta(resposta);
    const turno = turnoIdDe(await lerCorpo(resposta));
    if (!turno) {
      throw new ErroDoMotor(MENSAGENS.rede, "rede", undefined, "resposta sem turno_id", resposta.status);
    }
    return { turno_id: turno, anexado: false };
  },

  estadoDoTurno: (conversaId: string, turnoId: string, opcoes?: OpcoesDoPedido) =>
    pedir<EstadoDoTurno>(doTurno(conversaId, turnoId), opcoes),

  parar: (conversaId: string, turnoId: string) =>
    pedir<Partial<EstadoDoTurno>>(`${doTurno(conversaId, turnoId)}/parar`, comCorpo("POST")),

  /** O agente atende agora? */
  estadoDoChat: (opcoes?: OpcoesDoPedido) => pedir<EstadoDoChat>("/chat/estado", opcoes),

  /** O fluxo de eventos do turno (SSE). `desde` retoma de onde parou. */
  urlDosEventos: (conversaId: string, turnoId: string, desde?: number) =>
    urlDeEventos(`${doTurno(conversaId, turnoId)}/eventos`, desde),
} as const;
