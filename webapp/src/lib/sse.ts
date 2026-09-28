/**
 * Um fluxo de eventos (SSE) que se recupera sozinho: o turno da conversa e a
 * descoberta de receitas usam este mesmo embrulho do `EventSource`.
 *
 * - **Sem repetição.** Cada evento traz um `seq` (ou o `id:` do SSE). O que
 *   chega com `seq` já visto é ignorado: reconectar pede de novo a partir do
 *   último visto, e um evento que o servidor mande duas vezes aparece uma vez.
 * - **Reconexão com espera crescente** (1, 2, 5 e 10 s, e daí em diante 10 s).
 *   O `EventSource` nativo reconectaria sozinho, mas sem espera crescente e
 *   sem desistir de um servidor que responde sem fluxo (o 204 de "não há mais
 *   nada"). Aqui a conexão que cai é fechada e reaberta com `?desde=<último>`,
 *   que faz o papel do `Last-Event-ID`.
 * - **A aba voltou, a internet voltou:** reconecta na hora, sem esperar a vez.
 *   Uma conexão que parece aberta, mas está calada há muito tempo quando a aba
 *   volta (o celular congela a aba de fundo), também é reaberta.
 * - **Quem assina decide quando desistir.** Cada queda chama `aoFalhar` com
 *   quantas tentativas falharam, há quanto tempo e se a conexão nem chegou a
 *   abrir. A conversa usa isso para perguntar ao servidor se o turno já
 *   terminou (depois de 60 s, ou quando o servidor recusa o fluxo).
 */

export type EstadoDaConexao = "conectando" | "aberta" | "reconectando" | "encerrada";

export type FalhaDaConexao = {
  /** Quantas tentativas seguidas falharam. */
  tentativas: number;
  /** Há quanto tempo a conexão está caída, em milissegundos. */
  caidaHaMs: number;
  /** A conexão caiu sem ter aberto: o servidor recusou ou respondeu sem fluxo. */
  semAbrir: boolean;
};

/** A espera antes de cada nova tentativa. Depois da última, repete a última. */
export const ESPERAS_PADRAO: readonly number[] = [1_000, 2_000, 5_000, 10_000];

/** Calada por mais que isto quando a aba volta: a conexão é reaberta. */
export const SILENCIO_SUSPEITO_MS = 25_000;

export type OpcoesDaAssinatura<T> = {
  /** O endereço do fluxo a partir de um `seq` (0 = desde o começo). */
  url: (desde: number) => string;
  /** O último `seq` já visto. */
  desde?: number;
  aoEvento: (evento: T) => void;
  /** Depois deste evento, o fluxo acabou: fecha e não reconecta. */
  ehFinal?: (evento: T) => boolean;
  aoMudarEstado?: (estado: EstadoDaConexao) => void;
  aoFalhar?: (falha: FalhaDaConexao) => void;
  esperasMs?: readonly number[];
  /** Cria o `EventSource` (os testes passam um falso). */
  criar?: (url: string) => EventSource;
  agora?: () => number;
};

export type Assinatura = {
  /** Fecha de vez: nenhum evento e nenhuma tentativa depois disso. */
  fechar: () => void;
  /** Reabre já, sem esperar a vez (a aba voltou, a internet voltou). */
  reconectar: () => void;
  readonly ultimoSeq: number;
  readonly estado: EstadoDaConexao;
};

function seqDe(evento: unknown, idDoEvento: string | undefined): number | null {
  const seq = (evento as { seq?: unknown }).seq;
  if (typeof seq === "number" && Number.isFinite(seq)) return seq;
  const doId = Number(idDoEvento);
  return idDoEvento && Number.isFinite(doId) ? doId : null;
}

function criarPadrao(url: string): EventSource {
  return new EventSource(url);
}

export function assinarFluxo<T>(opcoes: OpcoesDaAssinatura<T>): Assinatura {
  const esperas = opcoes.esperasMs && opcoes.esperasMs.length > 0 ? opcoes.esperasMs : ESPERAS_PADRAO;
  const criar = opcoes.criar ?? criarPadrao;
  const agora = opcoes.agora ?? Date.now;

  let fonte: EventSource | null = null;
  let ultimoSeq = opcoes.desde ?? 0;
  let estado: EstadoDaConexao = "conectando";
  let tentativas = 0;
  let caidaDesde: number | null = null;
  let ultimoSinal = agora();
  let relogio: ReturnType<typeof setTimeout> | null = null;

  const mudar = (novo: EstadoDaConexao) => {
    if (estado === novo) return;
    estado = novo;
    opcoes.aoMudarEstado?.(novo);
  };

  const limparRelogio = () => {
    if (relogio !== null) clearTimeout(relogio);
    relogio = null;
  };

  const soltarFonte = () => {
    if (!fonte) return;
    fonte.onopen = null;
    fonte.onmessage = null;
    fonte.onerror = null;
    fonte.close();
    fonte = null;
  };

  const encerrar = () => {
    if (estado === "encerrada") return;
    limparRelogio();
    soltarFonte();
    mudar("encerrada");
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", aoVoltarAAba);
    if (typeof window !== "undefined") window.removeEventListener("online", aoVoltarAInternet);
  };

  const receber = (bruto: unknown, idDoEvento: string | undefined) => {
    if (typeof bruto !== "string") return;
    let evento: unknown;
    try {
      evento = JSON.parse(bruto);
    } catch {
      return;
    }
    if (typeof evento !== "object" || evento === null) return;
    const seq = seqDe(evento, idDoEvento);
    if (seq !== null) {
      if (seq <= ultimoSeq) return;
      ultimoSeq = seq;
    }
    opcoes.aoEvento(evento as T);
    if (estado !== "encerrada" && opcoes.ehFinal?.(evento as T)) encerrar();
  };

  const falhou = (semAbrir: boolean) => {
    const momento = agora();
    caidaDesde ??= momento;
    tentativas += 1;
    mudar("reconectando");
    opcoes.aoFalhar?.({ tentativas, caidaHaMs: momento - caidaDesde, semAbrir });
    if (estado === "encerrada") return;
    const espera = esperas[Math.min(tentativas - 1, esperas.length - 1)] ?? 10_000;
    limparRelogio();
    relogio = setTimeout(abrir, espera);
  };

  function abrir() {
    if (estado === "encerrada") return;
    limparRelogio();
    soltarFonte();
    let abriu = false;
    const es = criar(opcoes.url(ultimoSeq));
    fonte = es;
    es.onopen = () => {
      abriu = true;
      tentativas = 0;
      caidaDesde = null;
      ultimoSinal = agora();
      mudar("aberta");
    };
    es.onmessage = (mensagem: MessageEvent) => {
      ultimoSinal = agora();
      receber(mensagem.data, mensagem.lastEventId || undefined);
    };
    es.onerror = () => {
      soltarFonte();
      falhou(!abriu);
    };
  }

  const reconectar = () => {
    if (estado === "encerrada") return;
    tentativas = 0;
    abrir();
  };

  function aoVoltarAAba() {
    if (document.visibilityState !== "visible" || estado === "encerrada") return;
    if (estado !== "aberta" || agora() - ultimoSinal > SILENCIO_SUSPEITO_MS) reconectar();
  }

  function aoVoltarAInternet() {
    if (estado !== "aberta") reconectar();
  }

  if (typeof document !== "undefined") document.addEventListener("visibilitychange", aoVoltarAAba);
  if (typeof window !== "undefined") window.addEventListener("online", aoVoltarAInternet);
  abrir();

  return {
    fechar: encerrar,
    reconectar,
    get ultimoSeq() {
      return ultimoSeq;
    },
    get estado() {
      return estado;
    },
  };
}
