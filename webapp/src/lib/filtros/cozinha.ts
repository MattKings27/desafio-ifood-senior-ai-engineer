/**
 * Os filtros da cozinha: a busca e a situação de cada item, na URL
 * (`/cozinha?estado=nao_sei`), e os grupos por categoria.
 *
 * A situação separa o que ela respondeu do que é suposição: "não sei" é
 * resposta dela e aparece como "não sei", nunca como "ainda não perguntei".
 */

import type { ItemDaCozinha, RespostaDePosse } from "@/lib/api/perfil";
import { casaComBusca } from "@/lib/formato";

import type { EsquemaDeFiltros, FiltrosDe } from "./url";

export const SITUACOES_DA_COZINHA = ["tem", "nao_tem", "nao_sei", "suposto", "sem_resposta"] as const;
export type SituacaoNaCozinha = (typeof SITUACOES_DA_COZINHA)[number];

export const FILTROS_DA_COZINHA = {
  q: { tipo: "texto" },
  situacao: { tipo: "lista" },
} as const satisfies EsquemaDeFiltros;

export type FiltrosDaCozinhaNaUrl = FiltrosDe<typeof FILTROS_DA_COZINHA>;

export const ROTULO_DA_SITUACAO: Readonly<Record<SituacaoNaCozinha, string>> = {
  tem: "Tenho ou faço",
  nao_tem: "Não tenho ou não faço",
  nao_sei: "Não sei",
  suposto: "Suposto",
  sem_resposta: "Ainda não perguntei",
};

/** Onde o item está agora, do ponto de vista do que ela disse. */
export function situacaoDoItem(item: Pick<ItemDaCozinha, "estado" | "suposto" | "nao_sei">): SituacaoNaCozinha {
  if (item.suposto) return "suposto";
  if (item.estado === "tem") return "tem";
  if (item.estado === "nao_tem") return "nao_tem";
  return item.nao_sei ? "nao_sei" : "sem_resposta";
}

/** A resposta que o seletor mostra marcada; `null` quando ela ainda não respondeu (suposto também). */
export function respostaDoItem(item: Pick<ItemDaCozinha, "estado" | "suposto" | "nao_sei">): RespostaDePosse | null {
  const situacao = situacaoDoItem(item);
  if (situacao === "suposto" || situacao === "sem_resposta") return null;
  return situacao;
}

export function passaNaCozinha(item: ItemDaCozinha, filtros: FiltrosDaCozinhaNaUrl): boolean {
  if (filtros.q.trim() && !casaComBusca(`${item.nome} ${item.categoria}`, filtros.q)) return false;
  if (filtros.situacao.length > 0 && !filtros.situacao.includes(situacaoDoItem(item))) return false;
  return true;
}

export function contarPorSituacao(itens: readonly ItemDaCozinha[]): Record<SituacaoNaCozinha, number> {
  const contagem = Object.fromEntries(SITUACOES_DA_COZINHA.map((s) => [s, 0])) as Record<SituacaoNaCozinha, number>;
  for (const item of itens) contagem[situacaoDoItem(item)] += 1;
  return contagem;
}

export type GrupoDaCozinha = { categoria: string; rotulo: string; itens: ItemDaCozinha[] };

/** Os itens por categoria, na ordem em que a API manda ("cocção" vira "Cocção"). */
export function agruparPorCategoria(itens: readonly ItemDaCozinha[]): GrupoDaCozinha[] {
  const grupos = new Map<string, GrupoDaCozinha>();
  for (const item of itens) {
    let grupo = grupos.get(item.categoria);
    if (!grupo) {
      grupo = {
        categoria: item.categoria,
        rotulo: item.categoria.charAt(0).toLocaleUpperCase("pt-BR") + item.categoria.slice(1),
        itens: [],
      };
      grupos.set(item.categoria, grupo);
    }
    grupo.itens.push(item);
  }
  return [...grupos.values()];
}
