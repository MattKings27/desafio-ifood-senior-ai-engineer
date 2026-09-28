/**
 * Despensa e orçamento dos complementos.
 *
 * As formas de `contratos/web/despensa*.json` (a tela da despensa e o detalhe
 * de um item) e as de hoje (`Orcamento`, a compra de um complemento). Todo
 * valor em reais chega pronto, com o texto; a tela nunca faz conta com ele.
 */

import type { Dinheiro, Imagem, OpcoesDoPedido } from "./base";
import { comCorpo, consulta, pedir, pedirTexto } from "./base";
import type { Veredito } from "@/lib/formato";

/* -------------------------------------------------------------------------- */
/* Formas de hoje                                                              */
/* -------------------------------------------------------------------------- */

export type Pendencia = {
  ingrediente: string;
  motivo?: string;
  pergunta: string;
  impacto: Dinheiro;
};

export type Orcamento = {
  inicial: Dinheiro;
  gasto: Dinheiro;
  restante: Dinheiro;
  fracao_usada: number;
  compras: { descricao: string; valor: Dinheiro; quando: string }[];
};

/* -------------------------------------------------------------------------- */
/* Contrato v1                                                                 */
/* -------------------------------------------------------------------------- */

export type Confianca = "alta" | "media" | "desconhecida";

/** De onde o item veio. Só `orcamento` mexe nos R$ 80 dos complementos. */
export type OrigemDoItem = "planilha" | "ja_tinha" | "orcamento";

export type ItemDaDespensa = {
  id: string;
  nome: string;
  categoria: string;
  categoria_rotulo: string;
  /** Na unidade-base (`kg`, `L` ou `un`). */
  estoque: number;
  unidade: string;
  estoque_texto: string;
  /** `null` quando ela não disse quanto pagou. */
  pago: Dinheiro | null;
  /** `null` quando não dá para saber (falta o preço, ou o peso da embalagem). */
  custo_unitario: Dinheiro | null;
  derivacao: string;
  confianca: Confianca;
  confianca_rotulo: string;
  fracao_do_total: number;
  fracao_texto: string;
  origem: OrigemDoItem;
  origem_rotulo: string;
  imagem: Imagem;
  receitas_que_usam: number;
  receitas_que_usam_texto: string;
  pendente: boolean;
  rota: string;
};

/** O que falta saber: quanto vem na embalagem, ou quanto ela pagou. */
export type TipoDePendencia = "conteudo_embalagem" | "preco_pago";

/** Os campos da resposta de preço, na ordem em que a pergunta os pede. */
export type CampoDaResposta = "preco_pago" | "quantidade_comprada";

/** A resposta que dá para dar ali mesmo, sem ir à conversa. */
export type RespostaInline = {
  tipo: TipoDePendencia;
  rotulo: string;
  /** As unidades da embalagem (`g`, `kg`, `ml`, `L`); vazio na de preço. */
  unidades: string[];
  /** Só na de preço: o que ela responde. */
  campos?: CampoDaResposta[];
};

export type PendenciaDaDespensa = {
  /** O `id` do item. */
  id: string;
  ingrediente: string;
  tipo: TipoDePendencia;
  pergunta: string;
  impacto: Dinheiro;
  impacto_texto: string;
  resposta_inline: RespostaInline | null;
  /** O começo da frase dela, em primeira pessoa, para a caixa da conversa. */
  rascunho_chat: string;
  rota: string;
};

export type CompraDoOrcamento = {
  id: number;
  descricao: string;
  ingrediente: string | null;
  item_id: string | null;
  valor: Dinheiro;
  quando_texto: string;
  canal: string;
  /** A compra já voltou para os complementos. */
  estornada: boolean;
  /** A linha é a própria devolução. */
  estorno: boolean;
  pode_estornar: boolean;
  rota_estorno: string | null;
};

export type OrcamentoDaDespensa = {
  inicial: Dinheiro;
  restante: Dinheiro;
  gasto: Dinheiro;
  fracao_gasta: number;
  texto: string;
  compras: CompraDoOrcamento[];
};

export type CategoriaDaDespensa = { id: string; rotulo: string; quantidade: number };

export type CategoriaParaEscolher = { id: string; rotulo: string };

export type ListaDaDespensa = {
  itens: ItemDaDespensa[];
  total_investido: Dinheiro;
  /** A despensa inteira, com ou sem filtro. */
  total_itens: number;
  /** O que o filtro deixou. */
  encontrados: number;
  /** As que têm item, com a contagem da despensa inteira. */
  categorias: CategoriaDaDespensa[];
  /** Todas, com "Outros": a lista do formulário de um item novo. */
  categorias_para_escolher: CategoriaParaEscolher[];
  pendencias: PendenciaDaDespensa[];
  orcamento: OrcamentoDaDespensa;
};

export type ReceitaQueUsa = {
  slug: string;
  nome: string;
  veredito: Veredito;
  veredito_rotulo: string;
  imagem: Imagem;
  usa_texto: string;
  rota: string;
};

export type EventoDaDespensa = {
  /** `planilha` na linha da planilha, depois `ev-NNNN`. */
  id: string;
  tipo: "planilha" | "adicionar" | "corrigir" | "remover" | "restaurar" | (string & {});
  /** O que ela fez: `acabou`, `informar_embalagem`, `estorno`, `desfazer`… */
  acao: string;
  texto: string;
  quando_texto: string;
  canal: "planilha" | "tela" | "conversa" | (string & {});
  /** Só a última mudança de cada item. */
  pode_desfazer: boolean;
  /** O evento que este desfez. */
  desfaz: string | null;
  item_id: string;
  item_nome: string;
  motivo: string | null;
  rota: string;
};

export type PaginaDeEventos = {
  eventos: EventoDaDespensa[];
  /** O `id` do último da página; `null` na última. */
  proximo_cursor: string | null;
  total: number;
  versao: number;
};

export type DetalheDoItem = ItemDaDespensa & {
  comprado_texto: string;
  /** A unidade em que ela comprou, como a API guarda (`kg`, `un 200g`). */
  unidade_compra_rotulo: string;
  pendencia: PendenciaDaDespensa | null;
  receitas: ReceitaQueUsa[];
  historico: EventoDaDespensa[];
  compras: CompraDoOrcamento[];
  rascunho_chat: string;
};

export type NovoItem = {
  nome: string;
  /** Na `unidade` (em `un 200g`, o número de embalagens). */
  estoque: number;
  /** `kg`, `g`, `L`, `ml`, `un`, ou a embalagem com o peso (`un 200g`). */
  unidade: string;
  quantidade_comprada?: number | null;
  preco_pago?: number | null;
  /** "Já tinha" não mexe nos R$ 80; "Comprei com os R$ 80" desconta na hora. */
  origem: "ja_tinha" | "orcamento";
  /** Sem ela, a API escolhe pelo nome. */
  categoria?: string | null;
  /** Para qual prato comprou, quando comprou com os R$ 80. */
  receita?: string;
  id_cliente: string;
};

/** Só o que mudou. Trocar a `unidade` pede o estoque e a quantidade comprada nela. */
export type CorrecaoDoItem = Partial<{
  estoque: number;
  unidade: string;
  quantidade_comprada: number;
  preco_pago: number;
  categoria: string;
  conteudo_da_embalagem: string;
  motivo: string;
  id_cliente: string;
}>;

export type MudancaNaReceita = { receita: string; antes: string; depois: string };

export type ReceitasAfetadas = {
  liberadas: string[];
  bloqueadas: string[];
  mudaram: MudancaNaReceita[];
  texto: string;
};

export type RespostaDaEscrita = {
  /** O item como ficou; `null` quando ele saiu da despensa. */
  item: ItemDaDespensa | null;
  id: string;
  ingrediente: string;
  repetida: boolean;
  /** O evento gravado, para o "Desfazer". */
  evento: string | null;
  removido: string | null;
  estorno: Dinheiro | null;
  compra: Dinheiro | null;
  pendencias_resolvidas: string[];
  pendencia: PendenciaDaDespensa | null;
  receitas_afetadas: ReceitasAfetadas;
  orcamento: OrcamentoDaDespensa;
  /** A frase do aviso, já do jeito dela. */
  texto: string;
};

export type RespostaDoEstorno = {
  compra_id: number;
  estorno_id: number;
  estorno: Dinheiro;
  removido: string | null;
  receitas_afetadas: ReceitasAfetadas;
  orcamento: OrcamentoDaDespensa;
  texto: string;
};

export type FiltrosDaDespensa = {
  q?: string;
  categoria?: string;
  ordem?: "valor" | "nome" | "custo" | "categoria";
};

const item = (id: string) => `/despensa/itens/${encodeURIComponent(id)}`;
const comChave = (idCliente?: string) => (idCliente ? { id_cliente: idCliente } : undefined);

export const despensa = {
  /** A lista inteira, com categorias, pendências e o orçamento. */
  listar: (filtros: FiltrosDaDespensa = {}, opcoes?: OpcoesDoPedido) =>
    pedir<ListaDaDespensa>(`/despensa${consulta(filtros)}`, opcoes),

  /** O detalhe: custo com a conta, receitas que usam, histórico e compras. */
  item: (id: string, opcoes?: OpcoesDoPedido) => pedir<DetalheDoItem>(item(id), opcoes),

  adicionar: (novo: NovoItem) => pedir<RespostaDaEscrita>("/despensa/itens", comCorpo("POST", novo)),

  corrigir: (id: string, correcao: CorrecaoDoItem) =>
    pedir<RespostaDaEscrita>(item(id), comCorpo("PATCH", correcao)),

  /** Tirar da despensa. Se veio dos R$ 80, a resposta traz o estorno. */
  remover: (id: string, idCliente?: string) =>
    pedir<RespostaDaEscrita>(`${item(id)}${consulta({ id_cliente: idCliente })}`, comCorpo("DELETE")),

  eventos: (filtros: { limite?: number; cursor?: string } = {}, opcoes?: OpcoesDoPedido) =>
    pedir<PaginaDeEventos>(`/despensa/eventos${consulta(filtros)}`, opcoes),

  /** Desfaz a última mudança de um item (`ev-0012`). */
  desfazerEvento: (id: string, idCliente?: string) =>
    pedir<RespostaDaEscrita>(
      `/despensa/eventos/${encodeURIComponent(id)}/desfazer`,
      comCorpo("POST", comChave(idCliente)),
    ),

  /** A planilha transcrita em texto UTF-8, como o agente lê. */
  planilhaTxt: (opcoes?: OpcoesDoPedido) => pedirTexto("/despensa/planilha.txt", opcoes),

  /** Devolve uma compra aos R$ 80; o item que ela acrescentou sai junto. */
  estornarCompra: (id: number, idCliente?: string) =>
    pedir<RespostaDoEstorno>(
      `/compras/${encodeURIComponent(String(id))}/estorno`,
      comCorpo("POST", comChave(idCliente)),
    ),
} as const;

/* -------------------------------------------------------------------------- */
/* Rotas de hoje                                                               */
/* -------------------------------------------------------------------------- */

export const despensaDeHoje = {
  orcamento: () => pedir<Orcamento>("/orcamento"),

  /** Uma compra de complemento, para um prato já confirmado. */
  registrarCompra: (compra: {
    prato: string;
    ingrediente: string;
    quantidade: number;
    unidade?: string;
    valor: number;
  }) =>
    pedir<{ texto: string; orcamento: Orcamento }>(
      "/compra",
      comCorpo("POST", { unidade: "", ...compra }),
    ),
} as const;
