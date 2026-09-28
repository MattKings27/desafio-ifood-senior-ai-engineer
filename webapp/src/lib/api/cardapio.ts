/**
 * O cardápio: os pratos que ela aceitou, os que não quer, e as decisões.
 *
 * A decisão é dela, sempre. Desfazer grava uma decisão nova que volta ao estado
 * de antes, passando de novo pela conferência; o histórico diz que ela voltou
 * atrás. O preço de cada prato é o dela; o custo e o lucro são os de agora.
 */

import type { Dinheiro, Imagem, OpcoesDoPedido } from "./base";
import { comCorpo, pedir } from "./base";
import type { Pontuacao } from "./receitas";

/* -------------------------------------------------------------------------- */
/* Formas de hoje                                                              */
/* -------------------------------------------------------------------------- */

export type OpiniaoSobrePrato = {
  prato: string;
  gosto: "gosta" | "nao_gosta" | "desconhecido";
  impedimento: string;
  texto: string;
};

export type GostoRegistrado = OpiniaoSobrePrato & { bloqueia: boolean };

/* -------------------------------------------------------------------------- */
/* Contrato v1                                                                 */
/* -------------------------------------------------------------------------- */

export type PratoDoCardapio = {
  slug: string;
  prato: string;
  imagem: Imagem;
  /** O preço que ela escolheu ao aceitar; `null` só em registro antigo, sem o preço gravado. */
  preco: Dinheiro | null;
  /** O que chega para ela depois da taxa de 10%. */
  recebe: Dinheiro | null;
  /** O custo da porção com a despensa de agora (ou o do dia do aceite, ver `aviso`). */
  custo_porcao: Dinheiro | null;
  lucro_porcao: Dinheiro | null;
  /** A conta do preço ao lucro, escrita. */
  derivacao: string;
  da_prejuizo: boolean;
  /** O que ela precisa saber da conta: mudou, dá prejuízo ou não fechou hoje. */
  aviso: string | null;
  nota: Pontuacao | null;
  decidido_texto: string;
  notas: string | null;
  rota: string;
};

export type ResumoDoCardapio = {
  pratos: number;
  preco_medio: Dinheiro | null;
  margem_media_texto: string;
  orcamento_usado: Dinheiro;
  /** A linha dos R$ 80,00, pronta ("Nada gasto dos R$ 80,00 dos complementos ainda."). */
  orcamento_texto: string;
  orcamento_rota: string;
  texto: string;
};

export type PratoRecusado = { prato: string; motivo_texto: string; decidido_texto: string; rota: string };

export type TipoDeDecisao = "aceito" | "recusado" | "adiado";

/** O que um passo do histórico é, lido contra o anterior do mesmo prato. */
export type TipoDoPasso = "aceito" | "preco" | "retirado" | "recusado" | "adiado" | "desfeito";

export type DecisaoNoHistorico = {
  id: number;
  prato: string;
  tipo: TipoDoPasso | (string & {});
  /** "Aceitou", "Tirou do cardápio", "Voltou atrás"…, pronto para a tela. */
  tipo_rotulo: string;
  texto_humano: string;
  quando_texto: string;
  canal: "tela" | "conversa" | (string & {});
  pode_desfazer: boolean;
  rota: string;
};

export type CardapioCompleto = {
  pratos: PratoDoCardapio[];
  resumo: ResumoDoCardapio;
  nao_quer: PratoRecusado[];
  historico: DecisaoNoHistorico[];
};

/** A resposta de desfazer e das notas: o cardápio como ficou, e a frase do que mudou. */
export type CardapioDepoisDaMudanca = CardapioCompleto & { texto: string };

export type PedidoDeDecisao = {
  prato: string;
  decisao: TipoDeDecisao;
  preco?: number;
  motivo?: string;
  id_cliente?: string;
};

export type DecisaoRegistrada = {
  prato: string;
  decisao: string;
  /** A decisão dita para ela ("A senhora tirou o arroz com frango do cardápio."). */
  texto: string;
  cardapio: string[];
  /** No aceite abaixo do mínimo: quanto ela perde por porção, e o mínimo. A decisão continua dela. */
  da_prejuizo?: boolean;
  aviso?: string;
};

const doPrato = (prato: string) => `/cardapio/${encodeURIComponent(prato)}`;

export const cardapio = {
  ler: (opcoes?: OpcoesDoPedido) => pedir<CardapioCompleto>("/cardapio", opcoes),

  decidir: ({ motivo = "", ...pedido }: PedidoDeDecisao) =>
    pedir<DecisaoRegistrada>("/decisao", comCorpo("POST", { ...pedido, motivo })),

  /** Volta o prato ao que era antes da última decisão; o registro continua inteiro. */
  desfazer: (prato: string, idCliente?: string) =>
    pedir<CardapioDepoisDaMudanca>(`${doPrato(prato)}/desfazer`, {
      ...comCorpo("POST"),
      ...(idCliente ? { headers: { "Idempotency-Key": idCliente } } : {}),
    }),

  salvarNotas: (prato: string, texto: string) =>
    pedir<CardapioDepoisDaMudanca>(`${doPrato(prato)}/notas`, comCorpo("PUT", { texto })),
} as const;

/* -------------------------------------------------------------------------- */
/* Rotas de hoje                                                               */
/* -------------------------------------------------------------------------- */

export const cardapioDeHoje = {
  /** Se ela gosta de fazer o prato. "Não gosto" tira o prato da lista dela. */
  registrarGosto: (prato: string, gosta: boolean, impedimento = "") =>
    pedir<GostoRegistrado>("/gosto", {
      method: "POST",
      body: JSON.stringify({ prato, gosta, impedimento }),
    }),
} as const;
