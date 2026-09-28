/**
 * Conferência, custo por porção e preço.
 *
 * A ordem é a do desafio e não tem atalho: primeiro a conferência (dá pra
 * fazer?), depois o custo, depois os caminhos de preço. A API recusa o preço
 * de um prato não confirmado; a tela nem pede.
 *
 * Nada aqui multiplica. O controle deslizante consulta `/preco-em` a cada
 * parada, e os limites dele vêm da API (`controle`).
 */

import type { Dinheiro, OpcoesDoPedido } from "./base";
import { comCorpo, pedir } from "./base";
import type { ConfirmarACozinha, PerguntaDaReceita, ReceitaEntrada } from "./receitas";
import type { Veredito } from "@/lib/formato";

/* -------------------------------------------------------------------------- */
/* Formas de hoje                                                              */
/* -------------------------------------------------------------------------- */

export type Avaliacao = {
  prato: string;
  /** O id da receita no catálogo (a receita que ela ditou fica guardada lá). */
  receita_id?: string;
  veredito: Veredito;
  pode_precificar: boolean;
  resumo: string;
  impedimentos: { tipo: string; id: string; motivo: string }[];
  /** As perguntas com as opções de resposta, a mesma forma das perguntas da receita. */
  perguntas: PerguntaDaReceita[];
  ingredientes_na_despensa: {
    ingrediente: string;
    quantidade: string;
    custo: Dinheiro;
    derivacao: string;
  }[];
  falta_comprar: { ingrediente: string; quanto: string; custo: Dinheiro | null }[];
  /** Presente quando a API recusou por falta de cotação do que falta comprar. */
  custo_indeterminado?: string[];
  a_gosto: string[];
  exige?: { equipamentos: string[]; tecnicas: string[] };
  /** O aceite pede também a cozinha confirmada: aqui, se ela já pode dizer "Vou cobrar". */
  pode_aceitar: boolean;
  /** O que segura o aceite, dito para ela; vazia quando pode aceitar. */
  falta_para_aceitar: string[];
  /** A pergunta de confirmar o que toda cozinha tem, quando falta; `null` no resto. */
  confirmar_a_cozinha: ConfirmarACozinha | null;
};

export type LinhaCMV = {
  ingrediente: string;
  quantidade: string;
  custo: Dinheiro;
  derivacao: string;
  /** Participação no total: a interface desenha a barra com isto. */
  fracao: number;
};

/** O custo de uma porção (o nome do tipo é técnico; a tela diz "custo da porção"). */
export type CMV = {
  prato: string;
  total: Dinheiro;
  e_faixa: boolean;
  minimo: Dinheiro;
  maximo: Dinheiro;
  incerteza: number;
  rendimento_original: number;
  itens_a_gosto: string[];
  linhas: LinhaCMV[];
  explicacao: string;
};

export type Cenario = {
  nome: string;
  descricao: string;
  preco: Dinheiro;
  taxa: Dinheiro;
  recebe: Dinheiro;
  lucro: Dinheiro;
  food_cost: number;
  margem: number;
  explicacao: string;
};

/**
 * Os limites do controle de preço, calculados na API: do mínimo sem prejuízo
 * (arredondado para cima) a seis vezes o custo, de 50 em 50 centavos. A tela
 * só passa os números para o `<input type="range">`.
 */
export type ControleDePreco = { min: Dinheiro; max: Dinheiro; passo: number };

export type TabelaPrecos = {
  prato: string;
  cmv: Dinheiro;
  preco_minimo: Dinheiro;
  explicacao_da_taxa: string;
  cenarios: Cenario[];
  sensibilidade: Record<string, Dinheiro | number | boolean>;
  /** Os limites do controle deslizante, calculados na API. */
  controle: ControleDePreco;
};

export type PontoPreco = {
  preco: Dinheiro;
  taxa: Dinheiro;
  recebe: Dinheiro;
  lucro: Dinheiro;
  food_cost: number;
  margem: number;
  da_prejuizo: boolean;
  explicacao: string;
};

export type PrecoDeMercado = {
  ingrediente: string;
  valor: Dinheiro;
  origem: "informado_por_ela" | "pesquisado_na_web" | "estimado";
  texto: string;
};

export type PrecoRegistrado = PrecoDeMercado & { orcamento_restante: Dinheiro };

/* -------------------------------------------------------------------------- */
/* Contrato v1: preço preliminar                                               */
/* -------------------------------------------------------------------------- */

/** Uma premissa da conta (`valor_hora`, `gas_por_minuto`…), com a origem e a fonte. */
export type Premissa = {
  nome: string;
  rotulo: string;
  /** `null` quando ela ainda não disse (ex.: quanto paga na embalagem). */
  valor: Dinheiro | null;
  origem: "padrao" | "dela" | "falta" | (string & {});
  fonte: string | null;
  fonte_url: string | null;
  atualizado_texto: string | null;
  editavel: boolean;
};

export type LinhaDaEstimativa = {
  id: "ingredientes" | "mao_de_obra" | "gas" | "energia" | "embalagem" | (string & {});
  rotulo: string;
  /** `null` quando falta a premissa: a linha fica de fora da conta, sinalizada. */
  valor: Dinheiro | null;
  derivacao: string;
  /** Os `nome`s das premissas que a linha usa. */
  premissas: string[];
};

export type DinheiroComConta = Dinheiro & { derivacao: string };

export type PontoDaEstimativa = {
  nome: string;
  descricao: string;
  preco: Dinheiro;
  taxa: Dinheiro;
  recebe: Dinheiro;
  /** O lucro do desafio: 0,90 × preço − ingrediente. */
  lucro: Dinheiro;
  /** O que sobra depois também da mão de obra, do gás e da embalagem. */
  sobra_real: Dinheiro;
  derivacao: string;
};

/** Preço de mercado conferido na página. Nesta versão a lista vem sempre vazia. */
export type ReferenciaDeMercado = {
  preco: Dinheiro;
  descricao: string;
  fonte: string;
  url: string;
  verificada_texto: string;
};

export type Estimativa = {
  slug: string;
  prato: string;
  preliminar: true;
  rotulo: string;
  linhas: LinhaDaEstimativa[];
  premissas: Premissa[];
  custo_producao: DinheiroComConta | null;
  /** Custo de produção ÷ 0,90, arredondado para cima. */
  piso: DinheiroComConta | null;
  minimo_so_ingrediente: DinheiroComConta | null;
  pontos: PontoDaEstimativa[];
  referencias_de_mercado: ReferenciaDeMercado[];
  referencias_texto: string;
  sinais: {
    mercado_abaixo_do_piso: boolean;
    faltam_parametros: string[];
    falta_confirmar: string[];
  };
  texto: string;
};

export const preco = {
  /** O preço preliminar de uma receita, com as premissas e as fontes (a rota do card). */
  estimativa: (slug: string, opcoes?: OpcoesDoPedido) =>
    pedir<Estimativa>(`/receitas/${encodeURIComponent(slug)}/estimativa`, {
      ...opcoes,
      tempoLimiteMs: opcoes?.tempoLimiteMs ?? 30_000,
    }),

  parametro: (nome: string, opcoes?: OpcoesDoPedido) =>
    pedir<Premissa>(`/parametros/${encodeURIComponent(nome)}`, opcoes),

  definirParametro: (nome: string, valor: number | null) =>
    pedir<Premissa>(`/parametros/${encodeURIComponent(nome)}`, comCorpo("PUT", { valor })),
} as const;

/* -------------------------------------------------------------------------- */
/* Rotas de hoje                                                               */
/* -------------------------------------------------------------------------- */

export const precoDeHoje = {
  avaliar: (receita: ReceitaEntrada) =>
    pedir<Avaliacao>("/avaliar", { method: "POST", body: JSON.stringify(receita) }),

  cmv: (receita: ReceitaEntrada) =>
    pedir<CMV>("/cmv", { method: "POST", body: JSON.stringify(receita) }),

  /**
   * Os cenários de um prato já aprovado. A API recalcula o custo; `cmv`, se
   * vier, só é conferido contra o calculado. A tela não inventa a base do preço.
   */
  precos: (prato: string, cmv?: number) =>
    pedir<TabelaPrecos>(
      `/precos?prato=${encodeURIComponent(prato)}` +
        (cmv === undefined ? "" : `&cmv=${encodeURIComponent(cmv)}`),
    ),

  /** Um ponto arbitrário do controle. A API calcula; a interface só desenha. */
  precoEm: (prato: string, valor: number) =>
    pedir<PontoPreco>(
      `/preco-em?prato=${encodeURIComponent(prato)}&preco=${encodeURIComponent(valor)}`,
    ),

  precosDeMercado: () => pedir<{ precos: PrecoDeMercado[] }>("/precos-mercado"),

  /** O preço de um item que falta comprar. Sem ele o orçamento não é avaliável. */
  registrarPreco: (
    ingrediente: string,
    valor: number,
    {
      quantidade,
      unidade = "",
      origem = "informado_por_ela",
    }: { quantidade?: number; unidade?: string; origem?: string } = {},
  ) =>
    pedir<PrecoRegistrado>("/preco-mercado", {
      method: "POST",
      body: JSON.stringify({ ingrediente, valor, quantidade, unidade, origem }),
    }),
} as const;
