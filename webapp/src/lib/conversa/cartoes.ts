/**
 * Os tipos de card da conversa (contratos/web/LEIA.md, "Cards").
 *
 * O card vem do backend, com os dados do motor, nunca do texto do modelo. A
 * tela conhece estes 15 tipos (um exemplo de cada em `contratos/web/cartoes/`);
 * um tipo que ela não conhece é ignorado (um card novo do backend não quebra a
 * conversa, só não aparece até a tela aprender).
 */

export const TIPOS_DE_CARTAO = [
  "despensa_resumo",
  "ingrediente",
  "receita",
  "viabilidade",
  "comparacao",
  "pergunta",
  "cozinha_atualizada",
  "orcamento",
  "custo_porcao",
  "cenarios",
  "ponto_de_preco",
  "preco_preliminar",
  "decisao",
  "avaliacao_da_receita",
  "fontes",
] as const;

export type TipoDeCartao = (typeof TIPOS_DE_CARTAO)[number];

const CONHECIDOS: ReadonlySet<string> = new Set(TIPOS_DE_CARTAO);

export function ehTipoDeCartao(tipo: unknown): tipo is TipoDeCartao {
  return typeof tipo === "string" && CONHECIDOS.has(tipo);
}

/**
 * Cards com dinheiro: no histórico são fotografias da conta daquela hora
 * ("conta de hoje, 14:32"), e ganham "Refazer a conta".
 */
export const CARTOES_COM_DINHEIRO: ReadonlySet<TipoDeCartao> = new Set<TipoDeCartao>([
  "despensa_resumo",
  "ingrediente",
  "viabilidade",
  "comparacao",
  "orcamento",
  "custo_porcao",
  "cenarios",
  "ponto_de_preco",
  "preco_preliminar",
  "decisao",
]);

/**
 * A rota do card como caminho da API para o navegador
 * (`/api/receitas/arroz-com-frango/custo` → `/receitas/arroz-com-frango/custo`,
 * que o `pedir` manda por `/motor`). Só caminho relativo da
 * API, sem subir de pasta nem trocar de endereço: qualquer outra coisa é
 * `null`, e o card não oferece "Refazer a conta".
 */
export function caminhoDaRota(rota: unknown): string | null {
  if (typeof rota !== "string") return null;
  if (!/^\/api\/[A-Za-z0-9\-._~%/?=&+]+$/.test(rota)) return null;
  if (rota.includes("..") || rota.includes("//")) return null;
  return rota.slice("/api".length);
}

/** Como cada tipo de card se chama, no plural, quando vários vêm juntos ("7 receitas conferidas"). */
export const PLURAL_DO_CARTAO: Readonly<Record<TipoDeCartao, string>> = {
  despensa_resumo: "resumos da despensa",
  ingrediente: "ingredientes",
  receita: "receitas trazidas",
  viabilidade: "receitas conferidas",
  comparacao: "comparações",
  pergunta: "perguntas",
  cozinha_atualizada: "mudanças na cozinha",
  orcamento: "contas do orçamento",
  custo_porcao: "custos por porção",
  cenarios: "cenários de preço",
  ponto_de_preco: "preços",
  preco_preliminar: "preços preliminares",
  decisao: "decisões",
  avaliacao_da_receita: "avaliações",
  fontes: "fontes",
};

/** A partir de quantos cards do mesmo tipo a resposta os junta num grupo. */
export const CARTOES_PARA_AGRUPAR = 3;
/** Quantos cards do grupo aparecem antes do "Ver mais". */
export const CARTOES_VISIVEIS_NO_GRUPO = 2;

type CartaoComRota = { id: string; tipo: TipoDeCartao; ref: { rota: string | null } };

/**
 * Os cards de uma resposta sem repetição: o mesmo tipo com a mesma `ref.rota`
 * (a mesma receita conferida duas vezes no turno) fica só no último, que tem os
 * dados de depois. Card sem rota (a pergunta, as fontes) não se compara.
 */
export function semCartoesRepetidos<C extends CartaoComRota>(cartoes: readonly C[]): C[] {
  const ultimo = new Map<string, number>();
  cartoes.forEach((cartao, indice) => {
    if (cartao.ref.rota) ultimo.set(`${cartao.tipo} ${cartao.ref.rota}`, indice);
  });
  return cartoes.filter((cartao, indice) => !cartao.ref.rota || ultimo.get(`${cartao.tipo} ${cartao.ref.rota}`) === indice);
}

export type BlocoDeCartoes<C> = { tipo: "um"; cartao: C } | { tipo: "grupo"; tipoDeCartao: TipoDeCartao; cartoes: C[] };

/**
 * Os cards em blocos: 3 ou mais do mesmo tipo viram um grupo, no lugar do
 * primeiro deles, com os outros tipos na ordem em que chegaram.
 */
export function agruparCartoes<C extends CartaoComRota>(cartoes: readonly C[]): BlocoDeCartoes<C>[] {
  const porTipo = new Map<TipoDeCartao, C[]>();
  for (const cartao of cartoes) porTipo.set(cartao.tipo, [...(porTipo.get(cartao.tipo) ?? []), cartao]);
  const blocos: BlocoDeCartoes<C>[] = [];
  const agrupados = new Set<TipoDeCartao>();
  for (const cartao of cartoes) {
    const doTipo = porTipo.get(cartao.tipo) ?? [];
    if (doTipo.length < CARTOES_PARA_AGRUPAR) {
      blocos.push({ tipo: "um", cartao });
    } else if (!agrupados.has(cartao.tipo)) {
      agrupados.add(cartao.tipo);
      blocos.push({ tipo: "grupo", tipoDeCartao: cartao.tipo, cartoes: doTipo });
    }
  }
  return blocos;
}
