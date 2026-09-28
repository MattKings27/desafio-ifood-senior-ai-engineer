/**
 * A máquina de estados da conversa: um redutor puro (plano, 9.4).
 *
 *     ocioso ─enviar→ enviando (bolha otimista)
 *     enviando ─202→ conectando · ─erro→ bolha "Não enviou" (mesmo id_cliente)
 *     conectando ─turno.iniciado→ pensando
 *     atividade.* → trabalhando · texto.parcial/comentario → escrevendo (mascarado)
 *     cartao / acao.resultado / sugestoes → acrescenta
 *     texto.final → conferido (o verificado toma o lugar do rascunho)
 *     turno.concluido → ocioso (a resposta vai para a lista)
 *     parar → cancelando → turno.cancelado (o rascunho fica mascarado)
 *     turno.falhou{categoria} → a resposta falhou, com "Perguntar de novo"
 *
 * Os eventos chegam com `seq`: o que já foi visto é ignorado (a reconexão pede
 * de novo a partir do último, e a recarga reproduz o turno desde o começo).
 * Um evento de outro turno também é ignorado. Nada aqui busca, espera ou
 * anima: quem faz isso é a loja (`loja.ts`), que despacha as ações.
 */

import type {
  CartaoDaConversa,
  ContextoDaConversa,
  Conversa,
  DesfechoDaResposta,
  EventoDoTurno,
  MensagemDaConversa,
  OpcaoSugerida,
  PedidoDeTurno,
  RefDoCartao,
} from "@/lib/api/conversa";

import { detalheDaAtividade, normalizarFerramenta, rotuloFeitoGuardado, rotulosDaAtividade } from "./atividades";
import type { TipoDeCartao } from "./cartoes";
import { ehTipoDeCartao } from "./cartoes";
import { opcoesValidas } from "./sugestoes";

/* -------------------------------------------------------------------------- */
/* Formas                                                                      */
/* -------------------------------------------------------------------------- */

export type FaseDoTurno =
  | "enviando"
  | "conectando"
  | "pensando"
  | "trabalhando"
  | "escrevendo"
  | "conferido"
  | "cancelando";

export type ConexaoDoTurno = "conectando" | "aberta" | "reconectando";

export type ErroNaTela = { categoria: string; mensagem: string };

export type ErroDoTurno = ErroNaTela & { interrompido?: boolean };

export type AtividadeNaTela = {
  id: string;
  /** O nome normalizado, para o plano B e os testes. Nunca aparece na tela. */
  ferramenta: string;
  rotulo: string;
  rotuloFeito: string;
  estado: "fazendo" | "feito" | "falhou";
  detalhe?: string;
  resumo?: string;
};

export type CartaoNaTela = {
  id: string;
  tipo: TipoDeCartao;
  dados: unknown;
  ref: RefDoCartao;
  geradoTexto: string;
  /** Chegou neste turno, agora. Os do histórico são fotografias ("conta de hoje, 14:32"). */
  aoVivo: boolean;
};

export type ResultadoDeAcao = { ok: boolean; texto: string };

export type Turno = {
  id: string | null;
  /** O id do envio dela; `null` quando a tela se anexou a um turno que já rodava. */
  idCliente: string | null;
  pedido: PedidoDeTurno | null;
  fase: FaseDoTurno;
  /** A fase de antes de pedir para parar, para voltar se o pedido falhar. */
  faseAnterior: FaseDoTurno | null;
  conexao: ConexaoDoTurno;
  ultimoSeq: number;
  /** Algum evento se perdeu (o `seq` pulou): no fim, a loja busca a resposta gravada. */
  lacuna: boolean;
  atividades: AtividadeNaTela[];
  /** O rascunho como veio (já mascarado pelo backend); a tela mascara de novo. */
  rascunho: string;
  textoFinal: string | null;
  retirados: number;
  cartoes: CartaoNaTela[];
  resultados: ResultadoDeAcao[];
  sugestoes: OpcaoSugerida[];
  recursos: string[];
  iniciadoEm: number;
  ultimoEventoEm: number;
};

export type MensagemDela = {
  tipo: "senhora";
  chave: string;
  id: string | null;
  turnoId: string | null;
  texto: string;
  contexto: ContextoDaConversa | null;
  quandoTexto: string | null;
  envio: "enviada" | "enviando" | "falhou";
  idCliente: string | null;
  /** O pedido como foi, para reenviar com o mesmo `id_cliente`. */
  pedido: PedidoDeTurno | null;
  erroDoEnvio: ErroNaTela | null;
};

export type RespostaDaConsultora = {
  tipo: "consultora";
  chave: string;
  id: string | null;
  turnoId: string | null;
  estado: DesfechoDaResposta;
  /** O texto conferido, ou o rascunho mascarado (quando `rascunho`). */
  texto: string;
  rascunho: boolean;
  retirados: number;
  cartoes: CartaoNaTela[];
  atividades: { rotuloFeito: string; ok: boolean }[];
  resultados: ResultadoDeAcao[];
  erro: ErroDoTurno | null;
  sugestoes: OpcaoSugerida[];
  quandoTexto: string | null;
  /** O pedido dela que gerou esta resposta, para "Perguntar de novo". */
  pedido: PedidoDeTurno | null;
  /** Veio incompleta (eventos perdidos): a loja troca pela gravada. */
  incompleta: boolean;
};

export type ItemDaConversa = MensagemDela | RespostaDaConsultora;

export type CarregamentoDaConversa = "vazio" | "carregando" | "pronto" | "falhou" | "ausente";

export type EstadoDaConversa = {
  id: string | null;
  titulo: string;
  carregamento: CarregamentoDaConversa;
  erro: ErroNaTela | null;
  itens: ItemDaConversa[];
  turno: Turno | null;
  /** As sugestões do backend no fim do último turno que terminou bem. */
  sugestoes: OpcaoSugerida[];
};

export type AcaoDaConversa =
  | { tipo: "carregar"; id: string | null }
  | { tipo: "carregou"; conversa: Conversa; em: number }
  | { tipo: "semConversa" }
  | { tipo: "falhouAoCarregar"; erro: ErroNaTela; ausente?: boolean }
  | { tipo: "enviar"; pedido: PedidoDeTurno; em: number }
  | { tipo: "reenviar"; idCliente: string; em: number }
  | { tipo: "enviado"; idCliente: string; turnoId: string; em: number }
  | { tipo: "envioFalhou"; idCliente: string; erro: ErroNaTela }
  | { tipo: "envioRecusado"; idCliente: string }
  | { tipo: "eventos"; eventos: readonly unknown[]; em: number }
  | { tipo: "conexao"; turnoId: string; estado: ConexaoDoTurno }
  | { tipo: "parar" }
  | { tipo: "pararFalhou" }
  | { tipo: "renomeou"; id: string; titulo: string };

export const TITULO_PADRAO = "Conversa nova";

export const ESTADO_INICIAL: EstadoDaConversa = {
  id: null,
  titulo: "",
  carregamento: "vazio",
  erro: null,
  itens: [],
  turno: null,
  sugestoes: [],
};

/* -------------------------------------------------------------------------- */
/* Leitura segura do que vem de fora                                           */
/* -------------------------------------------------------------------------- */

type Solto = Record<string, unknown>;

function objeto(valor: unknown): Solto | null {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor) ? (valor as Solto) : null;
}

function texto(valor: unknown): string | null {
  return typeof valor === "string" ? valor : null;
}

function contextoValido(valor: unknown): ContextoDaConversa | null {
  const contexto = objeto(valor);
  if (!contexto || typeof contexto.tela !== "string" || typeof contexto.tipo !== "string") return null;
  return {
    tela: contexto.tela,
    tipo: contexto.tipo,
    ...(typeof contexto.id === "string" ? { id: contexto.id } : {}),
    ...(typeof contexto.rotulo === "string" ? { rotulo: contexto.rotulo } : {}),
  };
}

/** Um card de fora (evento ou mensagem guardada), se for de um tipo que a tela conhece. */
export function cartaoNaTela(bruto: unknown, aoVivo: boolean): CartaoNaTela | null {
  const cartao = objeto(bruto) as (Partial<CartaoDaConversa> & { tipo?: unknown }) | null;
  if (!cartao) return null;
  const tipo = cartao.tipo_cartao ?? cartao.tipo;
  if (!ehTipoDeCartao(tipo) || typeof cartao.cartao_id !== "string" || !cartao.cartao_id) return null;
  const ref = objeto(cartao.ref);
  const parametros = objeto(ref?.parametros);
  return {
    id: cartao.cartao_id,
    tipo,
    dados: cartao.dados ?? null,
    ref: {
      rota: typeof ref?.rota === "string" ? ref.rota : null,
      ...(parametros ? { parametros } : {}),
    },
    geradoTexto: texto(cartao.gerado_texto) ?? "",
    aoVivo,
  };
}

/** Troca o card de mesmo id (o backend manda de novo quando os dados mudam) ou acrescenta. */
function comCartao(cartoes: CartaoNaTela[], novo: CartaoNaTela | null): CartaoNaTela[] {
  if (!novo) return cartoes;
  const indice = cartoes.findIndex((cartao) => cartao.id === novo.id);
  if (indice === -1) return [...cartoes, novo];
  const copia = [...cartoes];
  copia[indice] = novo;
  return copia;
}

function desfechoValido(valor: unknown): DesfechoDaResposta {
  return valor === "cancelado" || valor === "falhou" || valor === "interrompido" ? valor : "concluido";
}

function erroValido(valor: unknown): ErroDoTurno | null {
  const erro = objeto(valor);
  if (!erro) return null;
  return {
    categoria: texto(erro.categoria) ?? "consultora",
    mensagem: texto(erro.mensagem) ?? "",
  };
}

/* -------------------------------------------------------------------------- */
/* As mensagens guardadas                                                      */
/* -------------------------------------------------------------------------- */

function textoDasPartes(mensagem: MensagemDaConversa): { texto: string; rascunho: boolean } {
  const partes = (Array.isArray(mensagem.partes) ? mensagem.partes : []).filter(
    (parte): parte is { tipo: "texto"; texto: string; rascunho?: boolean } =>
      objeto(parte)?.tipo === "texto" && typeof (parte as { texto?: unknown }).texto === "string",
  );
  return {
    texto: partes.map((parte) => parte.texto).join("\n\n").trim(),
    rascunho: partes.some((parte) => parte.rascunho === true),
  };
}

function daMensagemGuardada(mensagem: MensagemDaConversa): ItemDaConversa | null {
  const base = objeto(mensagem);
  if (!base || typeof mensagem.id !== "string") return null;
  const turnoId = typeof mensagem.turno_id === "string" ? mensagem.turno_id : null;
  const quandoTexto = texto(mensagem.quando_texto);
  const { texto: conteudo, rascunho } = textoDasPartes(mensagem);

  if (mensagem.papel === "senhora") {
    return {
      tipo: "senhora",
      chave: `m:${mensagem.id}`,
      id: mensagem.id,
      turnoId,
      texto: conteudo,
      contexto: contextoValido(mensagem.contexto),
      quandoTexto,
      envio: "enviada",
      idCliente: null,
      pedido: null,
      erroDoEnvio: null,
    };
  }
  if (mensagem.papel !== "consultora") return null;

  const estado = desfechoValido(mensagem.estado);
  const cartoes = (Array.isArray(mensagem.partes) ? mensagem.partes : [])
    .map((parte) => (objeto(parte)?.tipo === "cartao" ? cartaoNaTela(objeto(parte)?.cartao, false) : null))
    .reduce<CartaoNaTela[]>((lista, cartao) => comCartao(lista, cartao), []);
  const atividades = (Array.isArray(mensagem.atividades) ? mensagem.atividades : []).flatMap((atividade) => {
    const rotuloFeito = rotuloFeitoGuardado(objeto(atividade)?.rotulo_feito);
    return rotuloFeito ? [{ rotuloFeito, ok: objeto(atividade)?.ok !== false }] : [];
  });
  const resultado = objeto(mensagem.acao_resultado);
  return {
    tipo: "consultora",
    chave: `m:${mensagem.id}`,
    id: mensagem.id,
    turnoId,
    estado,
    texto: conteudo,
    // Resposta que não terminou bem só tem o rascunho, mascarado para sempre.
    rascunho: rascunho || estado !== "concluido",
    retirados: typeof mensagem.retirados === "number" && mensagem.retirados > 0 ? Math.floor(mensagem.retirados) : 0,
    cartoes,
    atividades,
    resultados:
      resultado && typeof resultado.texto === "string"
        ? [{ ok: resultado.ok !== false, texto: resultado.texto }]
        : [],
    erro: erroValido(mensagem.erro),
    sugestoes: opcoesValidas(mensagem.sugestoes),
    quandoTexto,
    pedido: null,
    incompleta: false,
  };
}

/* -------------------------------------------------------------------------- */
/* O turno                                                                     */
/* -------------------------------------------------------------------------- */

function novoTurno(dados: {
  id: string | null;
  idCliente: string | null;
  pedido: PedidoDeTurno | null;
  fase: FaseDoTurno;
  em: number;
}): Turno {
  return {
    id: dados.id,
    idCliente: dados.idCliente,
    pedido: dados.pedido,
    fase: dados.fase,
    faseAnterior: null,
    conexao: "conectando",
    ultimoSeq: 0,
    lacuna: false,
    atividades: [],
    rascunho: "",
    textoFinal: null,
    retirados: 0,
    cartoes: [],
    resultados: [],
    sugestoes: [],
    recursos: [],
    iniciadoEm: dados.em,
    ultimoEventoEm: dados.em,
  };
}

/** A fase que o evento pede, respeitando o pedido de parar e o texto já conferido. */
function fase(turno: Turno, desejada: FaseDoTurno): FaseDoTurno {
  if (turno.fase === "cancelando" || turno.fase === "conferido") return turno.fase;
  return desejada;
}

function comBolha(
  itens: ItemDaConversa[],
  idCliente: string | null,
  mudar: (bolha: MensagemDela) => MensagemDela,
): ItemDaConversa[] {
  if (!idCliente) return itens;
  return itens.map((item) => (item.tipo === "senhora" && item.idCliente === idCliente ? mudar(item) : item));
}

/** A chave da resposta que o turno vira: a mesma enquanto ele anda e depois de guardado. */
export function chaveDaResposta(turno: Pick<Turno, "id" | "idCliente" | "iniciadoEm">): string {
  return `t:${turno.id ?? turno.idCliente ?? turno.iniciadoEm}`;
}

function encerrar(
  estado: EstadoDaConversa,
  turno: Turno,
  desfecho: DesfechoDaResposta,
  erro: ErroDoTurno | null,
): EstadoDaConversa {
  const concluiu = desfecho === "concluido";
  const resposta: RespostaDaConsultora = {
    tipo: "consultora",
    chave: chaveDaResposta(turno),
    id: null,
    turnoId: turno.id,
    estado: desfecho,
    texto: turno.textoFinal ?? turno.rascunho,
    rascunho: turno.textoFinal === null,
    retirados: turno.retirados,
    cartoes: turno.cartoes,
    atividades: turno.atividades.map((atividade) => ({
      rotuloFeito: atividade.rotuloFeito,
      ok: atividade.estado === "feito",
    })),
    resultados: turno.resultados,
    erro,
    sugestoes: concluiu ? turno.sugestoes : [],
    quandoTexto: null,
    pedido: turno.pedido,
    incompleta: turno.lacuna || (concluiu && turno.textoFinal === null),
  };
  const itens = comBolha(estado.itens, turno.idCliente, (bolha) => ({
    ...bolha,
    envio: "enviada",
    turnoId: bolha.turnoId ?? turno.id,
  }));
  return { ...estado, itens: [...itens, resposta], turno: null, sugestoes: resposta.sugestoes };
}

function aplicarEvento(estado: EstadoDaConversa, bruto: unknown, em: number): EstadoDaConversa {
  const turno = estado.turno;
  const evento = objeto(bruto) as (EventoDoTurno & Solto) | null;
  if (!turno || !turno.id || !evento || typeof evento.tipo !== "string") return estado;
  if (typeof evento.turno_id === "string" && evento.turno_id !== turno.id) return estado;
  const seq = typeof evento.seq === "number" && Number.isFinite(evento.seq) ? evento.seq : null;
  if (seq !== null && seq <= turno.ultimoSeq) return estado;

  const t: Turno = {
    ...turno,
    ultimoSeq: seq ?? turno.ultimoSeq,
    lacuna: turno.lacuna || (seq !== null && seq > turno.ultimoSeq + 1),
    ultimoEventoEm: em,
  };
  const com = (mudancas: Partial<Turno>): EstadoDaConversa => ({ ...estado, turno: { ...t, ...mudancas } });

  switch (evento.tipo) {
    case "turno.iniciado":
      return com({ fase: t.fase === "enviando" || t.fase === "conectando" ? "pensando" : t.fase });

    case "atividade.iniciada": {
      const id = texto(evento.atividade_id) ?? `at-${seq ?? t.atividades.length + 1}`;
      const rotulos = rotulosDaAtividade(evento);
      const nova: AtividadeNaTela = {
        id,
        ferramenta: normalizarFerramenta(texto(evento.ferramenta) ?? ""),
        ...rotulos,
        estado: "fazendo",
        ...(detalheDaAtividade(evento.detalhe) ? { detalhe: detalheDaAtividade(evento.detalhe) } : {}),
      };
      const existe = t.atividades.some((atividade) => atividade.id === id);
      const atividades = existe
        ? t.atividades.map((atividade) => (atividade.id === id ? nova : atividade))
        : [...t.atividades, nova];
      // O que o agente escreveu antes de uma ferramenta é bastidor ("agora vou conferir a
      // cozinha"): a resposta é o texto que vem depois da última, e o rascunho recomeça.
      // Parando, fica o que ela viu: é o que a resposta cancelada guarda.
      const recomeca = !existe && t.fase !== "cancelando";
      return com({ atividades, fase: fase(t, "trabalhando"), ...(recomeca ? { rascunho: "" } : {}) });
    }

    case "atividade.concluida": {
      const id = texto(evento.atividade_id);
      const resumo = detalheDaAtividade(evento.resumo);
      const atividades = t.atividades.map((atividade): AtividadeNaTela =>
        atividade.id === id
          ? { ...atividade, estado: evento.ok === false ? "falhou" : "feito", ...(resumo ? { resumo } : {}) }
          : atividade,
      );
      const algumaFazendo = atividades.some((atividade) => atividade.estado === "fazendo");
      const desejada: FaseDoTurno = algumaFazendo ? "trabalhando" : t.rascunho ? "escrevendo" : "pensando";
      return com({ atividades, fase: fase(t, desejada) });
    }

    case "cartao":
      return com({ cartoes: comCartao(t.cartoes, cartaoNaTela(evento, true)) });

    case "acao.resultado": {
      const resultado = texto(evento.texto);
      return com({
        resultados: resultado ? [...t.resultados, { ok: evento.ok !== false, texto: resultado }] : t.resultados,
        cartoes: comCartao(t.cartoes, cartaoNaTela(evento.cartao, true)),
      });
    }

    case "texto.parcial": {
      const delta = texto(evento.delta);
      if (!delta) return com({});
      return com({ rascunho: t.rascunho + delta, fase: fase(t, "escrevendo") });
    }

    case "texto.comentario": {
      const comentario = texto(evento.texto)?.trim();
      if (!comentario) return com({});
      return com({
        rascunho: t.rascunho ? `${t.rascunho.trimEnd()}\n\n${comentario}` : comentario,
        fase: fase(t, "escrevendo"),
      });
    }

    case "texto.final": {
      const final = texto(evento.texto);
      if (final === null) return com({});
      const retirados =
        typeof evento.retirados === "number" && evento.retirados > 0 ? Math.floor(evento.retirados) : 0;
      return com({ textoFinal: final, retirados, fase: t.fase === "cancelando" ? "cancelando" : "conferido" });
    }

    case "estado.alterado": {
      const recursos = Array.isArray(evento.recursos)
        ? evento.recursos.filter((recurso): recurso is string => typeof recurso === "string")
        : [];
      return com({ recursos: [...new Set([...t.recursos, ...recursos])] });
    }

    case "sugestoes":
      return com({ sugestoes: opcoesValidas(evento.opcoes) });

    case "turno.concluido":
      return encerrar(estado, t, "concluido", null);

    case "turno.cancelado":
      return encerrar(estado, t, "cancelado", null);

    case "turno.falhou": {
      const interrompido = evento.interrompido === true;
      return encerrar(estado, t, interrompido ? "interrompido" : "falhou", {
        categoria: texto(evento.categoria) ?? "consultora",
        mensagem: texto(evento.mensagem) ?? "",
        ...(interrompido ? { interrompido } : {}),
      });
    }

    default:
      // Tipo que a tela ainda não conhece: o `seq` anda, e nada mais muda.
      return com({});
  }
}

/* -------------------------------------------------------------------------- */
/* O redutor                                                                   */
/* -------------------------------------------------------------------------- */

function carregou(estado: EstadoDaConversa, conversa: Conversa, em: number): EstadoDaConversa {
  const mesma = estado.id === conversa.id;
  const itens = (Array.isArray(conversa.mensagens) ? conversa.mensagens : [])
    .map(daMensagemGuardada)
    .filter((item): item is ItemDaConversa => item !== null);

  const andamento = objeto(conversa.turno_em_andamento);
  const turnoId = texto(andamento?.turno_id);
  const rodando = Boolean(turnoId) && (andamento?.estado === undefined || andamento.estado === "em_andamento");

  let turno: Turno | null = null;
  if (rodando && turnoId) {
    // O turno que já está sendo acompanhado continua; outro é assinado desde o começo.
    turno =
      mesma && estado.turno?.id === turnoId
        ? estado.turno
        : novoTurno({ id: turnoId, idCliente: null, pedido: null, fase: "conectando", em });
  } else if ((mesma || (estado.id === null && itens.length === 0)) && estado.turno?.fase === "enviando") {
    // O envio dela ainda está a caminho: a bolha otimista fica. Vale também
    // para a primeira mensagem, mandada antes de a conversa existir.
    turno = estado.turno;
    const bolha = estado.itens.find(
      (item) => item.tipo === "senhora" && item.idCliente === estado.turno?.idCliente,
    );
    if (bolha) itens.push(bolha);
  }

  const ultimo = itens.at(-1);
  return {
    id: conversa.id,
    titulo: conversa.titulo?.trim() || TITULO_PADRAO,
    carregamento: "pronto",
    erro: null,
    itens,
    turno,
    sugestoes: !turno && ultimo?.tipo === "consultora" && ultimo.estado === "concluido" ? ultimo.sugestoes : [],
  };
}

export function reduzirConversa(estado: EstadoDaConversa, acao: AcaoDaConversa): EstadoDaConversa {
  switch (acao.tipo) {
    case "carregar":
      if (estado.id === acao.id && acao.id !== null) return { ...estado, carregamento: "carregando", erro: null };
      return { ...ESTADO_INICIAL, id: acao.id, carregamento: "carregando" };

    case "carregou":
      return carregou(estado, acao.conversa, acao.em);

    case "semConversa":
      return { ...ESTADO_INICIAL, carregamento: "pronto" };

    case "falhouAoCarregar":
      return { ...estado, carregamento: acao.ausente ? "ausente" : "falhou", erro: acao.erro, turno: null };

    case "enviar": {
      if (estado.turno) return estado;
      const { pedido } = acao;
      const bolha: MensagemDela = {
        tipo: "senhora",
        chave: `c:${pedido.id_cliente}`,
        id: null,
        turnoId: null,
        texto: pedido.texto,
        contexto: pedido.contexto ?? null,
        quandoTexto: null,
        envio: "enviando",
        idCliente: pedido.id_cliente,
        pedido,
        erroDoEnvio: null,
      };
      return {
        ...estado,
        itens: [...estado.itens, bolha],
        turno: novoTurno({ id: null, idCliente: pedido.id_cliente, pedido, fase: "enviando", em: acao.em }),
        sugestoes: [],
      };
    }

    case "reenviar": {
      if (estado.turno) return estado;
      const bolha = estado.itens.find(
        (item): item is MensagemDela => item.tipo === "senhora" && item.idCliente === acao.idCliente,
      );
      if (!bolha?.pedido) return estado;
      return {
        ...estado,
        itens: comBolha(estado.itens, acao.idCliente, (atual) => ({
          ...atual,
          envio: atual.envio === "falhou" ? "enviando" : atual.envio,
          erroDoEnvio: null,
        })),
        turno: novoTurno({ id: null, idCliente: acao.idCliente, pedido: bolha.pedido, fase: "enviando", em: acao.em }),
        sugestoes: [],
      };
    }

    case "enviado": {
      const turno = estado.turno;
      if (!turno || turno.idCliente !== acao.idCliente || turno.fase !== "enviando") return estado;
      return {
        ...estado,
        itens: comBolha(estado.itens, acao.idCliente, (bolha) => ({ ...bolha, envio: "enviada", turnoId: acao.turnoId })),
        turno: { ...turno, id: acao.turnoId, fase: "conectando", iniciadoEm: acao.em, ultimoEventoEm: acao.em },
      };
    }

    case "envioFalhou": {
      if (estado.turno?.idCliente !== acao.idCliente) return estado;
      return {
        ...estado,
        itens: comBolha(estado.itens, acao.idCliente, (bolha) => ({ ...bolha, envio: "falhou", erroDoEnvio: acao.erro })),
        turno: null,
      };
    }

    case "envioRecusado": {
      if (estado.turno?.idCliente !== acao.idCliente) return estado;
      return {
        ...estado,
        itens: estado.itens.filter(
          (item) => !(item.tipo === "senhora" && item.idCliente === acao.idCliente && item.id === null),
        ),
        turno: null,
      };
    }

    case "eventos": {
      let atual = estado;
      for (const evento of acao.eventos) atual = aplicarEvento(atual, evento, acao.em);
      return atual;
    }

    case "conexao": {
      const turno = estado.turno;
      if (!turno || turno.id !== acao.turnoId || turno.conexao === acao.estado) return estado;
      return { ...estado, turno: { ...turno, conexao: acao.estado } };
    }

    case "parar": {
      const turno = estado.turno;
      if (!turno?.id || turno.fase === "cancelando") return estado;
      return { ...estado, turno: { ...turno, fase: "cancelando", faseAnterior: turno.fase } };
    }

    case "pararFalhou": {
      const turno = estado.turno;
      if (!turno || turno.fase !== "cancelando") return estado;
      return { ...estado, turno: { ...turno, fase: turno.faseAnterior ?? "pensando", faseAnterior: null } };
    }

    case "renomeou":
      return estado.id === acao.id ? { ...estado, titulo: acao.titulo.trim() || TITULO_PADRAO } : estado;
  }
}

/* -------------------------------------------------------------------------- */
/* Perguntas sobre o estado                                                    */
/* -------------------------------------------------------------------------- */

/** O agente está trabalhando num turno (o envio conta: já é a vez dele). */
export function estaRespondendo(estado: EstadoDaConversa): boolean {
  return estado.turno !== null;
}

/** A última resposta do agente, se a conversa termina nela. */
export function ultimaResposta(estado: EstadoDaConversa): RespostaDaConsultora | null {
  const ultimo = estado.itens.at(-1);
  return ultimo?.tipo === "consultora" ? ultimo : null;
}

/** A mensagem dela logo antes de uma resposta (para "Perguntar de novo" no histórico). */
export function perguntaAntes(estado: EstadoDaConversa, chave: string): MensagemDela | null {
  const indice = estado.itens.findIndex((item) => item.chave === chave);
  for (let i = indice - 1; i >= 0; i -= 1) {
    const item = estado.itens[i];
    if (item?.tipo === "senhora") return item;
  }
  return null;
}
