/**
 * A tela inicial numa leitura só: os números, o próximo passo, o que perguntar.
 *
 * Forma em `contratos/web/visao-geral.json`. Cada bloco traz a própria `rota`,
 * para todo cartão da tela inicial ser clicável sem a tela inventar destino, e
 * todo número vem com o texto pronto: a tela não soma nem formata dinheiro.
 * `dinheiro_parado.itens` traz todos os itens com preço, do que mais custou ao
 * que menos custou: a tela mostra cinco e abre o resto.
 */

import type { Dinheiro, Imagem, OpcoesDoPedido } from "./base";
import { pedir } from "./base";
import type { PendenciaDaDespensa } from "./despensa";
import type { PratoDoCardapio } from "./cardapio";
import type { ItemDaGrade, PerguntaDaReceita } from "./receitas";

/** Um link (`rota`) ou a conversa com o pedido escrito (`rascunho`). */
export type AcaoDoProximoPasso = {
  tipo: "link" | "perguntar" | (string & {});
  rota?: string;
  rascunho?: string;
};

export type ItemParado = {
  id: string;
  nome: string;
  pago: Dinheiro;
  fracao: number;
  fracao_texto: string;
  imagem: Imagem;
  sem_receita: boolean;
  rota: string;
};

/**
 * Uma pergunta da cozinha que segura receitas, com a forma das perguntas da
 * receita (`receita.json#perguntas[]`): a tela responde ali mesmo, pelo perfil.
 * `receita` é a primeira receita que ela libera; `receitas`, todas.
 */
export type PerguntaDaCozinha = {
  id: string;
  pergunta: PerguntaDaReceita;
  receita: { slug: string; nome: string };
  receitas: { slug: string; nome: string }[];
  /** O começo da frase dela para a conversa, com a pergunta junto. */
  rascunho_chat: string;
  rota: string;
};

export type VisaoGeral = {
  kpis: {
    despensa: { total: Dinheiro; itens: number; texto: string; rota: string };
    orcamento: { restante: Dinheiro; inicial: Dinheiro; gasto: Dinheiro; texto: string; rota: string };
    receitas: { no_catalogo: number; da_pra_fazer: number; texto: string; rota: string };
    cardapio: { pratos: number; texto: string; rota: string };
    cozinha: {
      respondidos: number;
      supostos: number;
      em_aberto: number;
      fracao_respondida: number;
      texto: string;
      rota: string;
    };
  };
  proximo_passo: { texto: string; acao: AcaoDoProximoPasso };
  /** As perguntas da despensa, com a mesma forma da tela da despensa. */
  pendencias: PendenciaDaDespensa[];
  perguntas_da_cozinha: PerguntaDaCozinha[];
  dinheiro_parado: {
    total_itens: number;
    dois_maiores: { nomes: string[]; soma: Dinheiro; fracao: number; texto: string };
    itens: ItemParado[];
  };
  /** Com a forma dos cards da grade (`receitas.json#itens[]`), da aba "dá pra fazer". */
  receitas_recomendadas: ItemDaGrade[];
  cardapio_previa: PratoDoCardapio[];
};

export const visaoGeral = {
  ler: (opcoes?: OpcoesDoPedido) => pedir<VisaoGeral>("/visao-geral", opcoes),
} as const;
