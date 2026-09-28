/**
 * Os filtros da despensa: o que fica na URL (`/despensa?q=feijao&categoria=graos`)
 * e como a lista que já veio da API é filtrada e ordenada no navegador.
 *
 * Nada aqui faz conta com dinheiro: ordenar compara `.valor` (o que a API
 * mandou), e o que não tem valor vai para o fim.
 */

import type { Confianca, ItemDaDespensa, OrigemDoItem } from "@/lib/api/despensa";
import { casaComBusca, compararDinheiro } from "@/lib/formato";

import type { EsquemaDeFiltros, FiltrosDe } from "./url";

export const ORDENS_DA_DESPENSA = ["valor", "nome", "custo"] as const;
export type OrdemDaDespensa = (typeof ORDENS_DA_DESPENSA)[number];

export const FILTROS_DA_DESPENSA = {
  q: { tipo: "texto" },
  categoria: { tipo: "lista" },
  ordem: { tipo: "opcao", opcoes: ORDENS_DA_DESPENSA, padrao: "valor" },
  confianca: { tipo: "lista" },
  origem: { tipo: "lista" },
  sem_receita: { tipo: "booleano" },
  pendentes: { tipo: "booleano" },
} as const satisfies EsquemaDeFiltros;

export type FiltrosDaDespensaNaUrl = FiltrosDe<typeof FILTROS_DA_DESPENSA>;

/** Os filtros que moram na folha "Filtros": o número do botão conta só estes. */
export const FILTROS_DA_FOLHA = ["confianca", "origem", "sem_receita", "pendentes"] as const;

/** O que não é filtro da folha: a busca, as categorias e a ordem ficam à vista. */
export const FORA_DA_FOLHA = ["q", "categoria", "ordem"] as const;

export const ROTULO_DA_ORDEM: Readonly<Record<OrdemDaDespensa, string>> = {
  valor: "Mais dinheiro parado",
  nome: "Nome",
  custo: "Custo por unidade",
};

export const ROTULO_DA_CONFIANCA: Readonly<Record<Confianca, string>> = {
  alta: "Conta direta",
  media: "Com conversão de embalagem",
  desconhecida: "Falta um dado",
};

export const ROTULO_DA_ORIGEM: Readonly<Record<OrigemDoItem, string>> = {
  planilha: "Da planilha",
  ja_tinha: "Já tinha",
  orcamento: "Comprado com os complementos",
};

/** O item passa por todos os filtros ativos (cada filtro vazio deixa tudo passar). */
export function passaNosFiltros(item: ItemDaDespensa, filtros: FiltrosDaDespensaNaUrl): boolean {
  if (filtros.q.trim() && !casaComBusca(item.nome, filtros.q)) return false;
  if (filtros.categoria.length > 0 && !filtros.categoria.includes(item.categoria)) return false;
  if (filtros.confianca.length > 0 && !filtros.confianca.includes(item.confianca)) return false;
  if (filtros.origem.length > 0 && !filtros.origem.includes(item.origem)) return false;
  if (filtros.sem_receita && item.receitas_que_usam > 0) return false;
  if (filtros.pendentes && !item.pendente) return false;
  return true;
}

function porNome(a: ItemDaDespensa, b: ItemDaDespensa): number {
  return a.nome.localeCompare(b.nome, "pt-BR", { sensitivity: "base" });
}

/** Do maior para o menor, com o desconhecido por último; empate, pelo nome. */
function doMaior(a: ItemDaDespensa["pago"], b: ItemDaDespensa["pago"]): number {
  if (!a || !b) return compararDinheiro(a, b);
  return compararDinheiro(b, a);
}

export function ordenarDespensa(itens: readonly ItemDaDespensa[], ordem: OrdemDaDespensa): ItemDaDespensa[] {
  const copia = [...itens];
  if (ordem === "nome") return copia.sort(porNome);
  if (ordem === "custo") return copia.sort((a, b) => doMaior(a.custo_unitario, b.custo_unitario) || porNome(a, b));
  return copia.sort((a, b) => doMaior(a.pago, b.pago) || porNome(a, b));
}

/** A lista que a tela mostra: filtrada e na ordem escolhida. */
export function itensVisiveis(itens: readonly ItemDaDespensa[], filtros: FiltrosDaDespensaNaUrl): ItemDaDespensa[] {
  return ordenarDespensa(
    itens.filter((item) => passaNosFiltros(item, filtros)),
    filtros.ordem,
  );
}

/** "1 ingrediente", "37 ingredientes": o plural de uma contagem da tela. */
export function contar(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}
