/**
 * A cozinha dela: equipamentos, técnicas e os limites da rotina.
 *
 * Três estados, sempre: tem, não tem, e desconhecido. Silêncio nunca vira "não
 * tem" (eliminaria receita viável sem ela ter dito nada) nem "tem" (deixaria
 * comprar o que ela não consegue fazer).
 */

import type { Imagem, OpcoesDoPedido } from "./base";
import { comCorpo, pedir } from "./base";

export type EstadoPosse = "tem" | "nao_tem" | "desconhecido";

/* -------------------------------------------------------------------------- */
/* Formas de hoje                                                              */
/* -------------------------------------------------------------------------- */

export type ItemPerfil = {
  id: string;
  nome: string;
  categoria: string;
  estado: EstadoPosse;
  pergunta: string;
  pressuposto?: boolean;
  pressuposta?: boolean;
  /** Está como "tem" porque qualquer cozinha tem, não porque ela disse. */
  suposto?: boolean;
  dificuldade?: number;
};

export type Perfil = {
  completude: number;
  resumo: string;
  /** O que ela mesma respondeu; o suposto de qualquer cozinha fica fora. */
  respondidos: number;
  supostos: number;
  em_aberto: number;
  fracao_respondida: number;
  equipamentos: ItemPerfil[];
  tecnicas: ItemPerfil[];
  restricoes: Record<string, { valor: number | boolean | null; pergunta: string }>;
};

/* -------------------------------------------------------------------------- */
/* Contrato v1                                                                 */
/* -------------------------------------------------------------------------- */

/** Quem mexeu por último num item: a tela ou a conversa com o agente. */
export type QuemAtualizou = "tela" | "conversa" | (string & {});

export type ItemDaCozinha = {
  id: string;
  nome: string;
  /** A do vocabulário: `cocção`, `preparo`… ou `básica`, `massas`… */
  categoria: string;
  estado: EstadoPosse;
  /** Só equipamento: qualquer cozinha tem. */
  pressuposto?: boolean;
  /** Só técnica: qualquer cozinheira faz. */
  pressuposta?: boolean;
  /** Está como "tem" porque qualquer cozinha tem, não porque ela disse. */
  suposto: boolean;
  /** Só técnica, de 1 a 5. */
  dificuldade?: number;
  pergunta: string;
  /** A miniatura do Commons pelo proxy, com o crédito; `null` sem foto livre (a tela mostra o ícone). */
  imagem: Imagem;
  /** Quantas receitas em avaliação pedem o item, e o mesmo em texto. */
  receitas_afetadas: number;
  receitas_afetadas_texto: string;
  atualizado_por: QuemAtualizou | null;
  atualizado_texto: string | null;
  /** A última resposta dela foi "não sei": nunca é "ainda não perguntei". */
  nao_sei: boolean;
};

export type Restricao = {
  /** `null` é "não sei" (com `nao_sei`) ou ainda não perguntado. Nas horas, 1.5 é uma hora e meia. */
  valor: number | boolean | null;
  /** `horas` é o tempo por cozinhada: o motor guarda minutos, a tela lê e escreve em horas. */
  tipo: "inteiro" | "horas" | "sim_nao" | (string & {});
  /** No inteiro e nas horas. */
  unidade?: string;
  min?: number;
  max?: number;
  /** Nas horas: de quanto em quanto o + e o − andam (meia hora). */
  passo?: number;
  /** Nas horas: quantas casas depois da vírgula ela pode escrever. */
  casas?: number;
  /** Nas horas: o valor dito para ela ("1,5 hora", "2 horas"), ou `null`. */
  valor_texto?: string | null;
  pergunta: string;
  atualizado_por: QuemAtualizou | null;
  atualizado_texto: string | null;
  nao_sei: boolean;
};

export type ContagensDaCozinha = {
  respondidos: number;
  supostos: number;
  em_aberto: number;
  fracao_respondida: number;
  /** "3 respondidos pela senhora · 17 supostos · 1 que a senhora não sabe · …" */
  resumo: string;
  /** "3 de 63 respondidos pela senhora": a conta de `fracao_respondida` em texto. */
  progresso_texto: string;
};

/** Um item de "O que toda cozinha tem", com o estado dito para ela. */
export type ItemDeTodaCozinha = {
  tipo: "equipamento" | "tecnica";
  id: string;
  nome: string;
  imagem: Imagem;
  estado: EstadoPosse;
  /** `suposto` espera a confirmação dela; os outros já são a resposta dela. */
  status: "confirmado" | "suposto" | "falta_saber" | "nao_da";
  /** "suposto: confirme", "a senhora tem", "a senhora não faz", "a senhora não sabe". */
  status_texto: string;
};

/**
 * "O que toda cozinha tem": o que é suposto de qualquer cozinha, com o estado
 * de cada um. `a_confirmar` conta os que ainda esperam o "Tenho tudo isso".
 */
export type TodaCozinha = {
  titulo: string;
  texto: string;
  a_confirmar: number;
  a_confirmar_texto: string;
  tudo_confirmado: boolean;
  itens: ItemDeTodaCozinha[];
};

export type PerfilDaCozinha = ContagensDaCozinha & {
  /** Conta também o suposto: não vai para a tela. */
  completude: number;
  equipamentos: ItemDaCozinha[];
  tecnicas: ItemDaCozinha[];
  restricoes: Record<string, Restricao>;
  toda_cozinha: TodaCozinha;
};

/** O que ela responde na tela. "Não sei" volta o item para o desconhecido, com `nao_sei`. */
export type RespostaDePosse = "tem" | "nao_tem" | "nao_sei";

export type ImpactoDaMudanca = {
  liberadas: string[];
  bloqueadas: string[];
  /** As que continuam dependendo de uma resposta dela. */
  pendentes: string[];
  texto: string;
};

export type RestricaoGravada = Restricao & { id: string };

/**
 * O que ela confirma de uma vez: `{}` é tudo o que ainda é suposto ("Tenho tudo
 * isso"); `receita` (o slug) é o que aquela receita usa; `itens`, só eles.
 */
export type PedidoDeConfirmacao =
  | Record<string, never>
  | { receita: string }
  | { itens: { tipo: "equipamento" | "tecnica"; id: string }[] };

/** A resposta da confirmação (`perfil-supostos.json#resposta`). */
export type ConfirmacaoDaCozinha = {
  confirmados: { tipo: "equipamento" | "tecnica"; id: string; nome: string }[];
  /** "Anotei: a senhora tem fogão e sabe refogar." */
  texto: string;
  perfil: ContagensDaCozinha;
  toda_cozinha: TodaCozinha;
};

export type RespostaDaCozinha = {
  /** O item como ficou, na forma do GET (a restrição com o `id`). */
  item: ItemDaCozinha | RestricaoGravada;
  impacto: ImpactoDaMudanca;
  perfil: ContagensDaCozinha;
};

export const perfil = {
  ler: (opcoes?: OpcoesDoPedido) => pedir<PerfilDaCozinha>("/perfil", opcoes),

  definirPosse: (tipo: "equipamentos" | "tecnicas", id: string, estado: RespostaDePosse) =>
    pedir<RespostaDaCozinha>(`/perfil/${tipo}/${encodeURIComponent(id)}`, comCorpo("PUT", { estado })),

  /** Um limite da rotina (bocas do fogão, reserva de gás…). `null` é "não sei". */
  definirRestricao: (campo: string, valor: number | boolean | null) =>
    pedir<RespostaDaCozinha>(
      `/perfil/restricoes/${encodeURIComponent(campo)}`,
      comCorpo("PUT", { valor }),
    ),

  /** Ela confirma o que toda cozinha tem: tudo, o que uma receita usa, ou os itens ditos. */
  confirmarSupostos: (pedido: PedidoDeConfirmacao = {}) =>
    pedir<ConfirmacaoDaCozinha>("/perfil/supostos/confirmar", comCorpo("POST", pedido)),
} as const;

/* -------------------------------------------------------------------------- */
/* Rotas de hoje                                                               */
/* -------------------------------------------------------------------------- */

export const perfilDeHoje = {
  perfil: () => pedir<Perfil>("/perfil"),

  /** A resposta dela a uma pergunta da conferência: equipamento, técnica ou rotina. */
  responder: (tipo: string, campo: string, resposta: string) =>
    pedir<{ registrado: boolean | string }>("/resposta", {
      method: "POST",
      body: JSON.stringify({ tipo, campo, resposta }),
    }),
} as const;
