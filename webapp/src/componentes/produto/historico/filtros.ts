/**
 * Os filtros do histórico, guardados na URL (`/trilha?categoria=cardapio&quem=senhora`).
 *
 * Arquivo puro: a página (no servidor) lê a URL com o mesmo esquema e pede a
 * primeira página já filtrada; a tela (no navegador) troca a URL com
 * `useFiltrosNaUrl` e pede de novo. Quem filtra é a API: a busca ignora acento
 * e caixa lá, e os dias do filtro dependem dos outros filtros.
 */

import type { FiltrosDeAtividades } from "@/lib/api/atividades";
import { consulta } from "@/lib/api/base";
import type { EsquemaDeFiltros, FiltrosDe } from "@/lib/filtros/url";

export const CATEGORIAS = ["despensa", "receitas", "cozinha", "preco", "cardapio"] as const;
export const QUEM = ["senhora", "consultora", "tela"] as const;

export const ESQUEMA_DO_HISTORICO = {
  q: { tipo: "texto" },
  categoria: { tipo: "opcao", opcoes: ["", ...CATEGORIAS] as const, padrao: "" },
  quem: { tipo: "opcao", opcoes: ["", ...QUEM] as const, padrao: "" },
  /** O dia no horário dela (`2026-09-26`); vazio é todos os dias. */
  dia: { tipo: "texto" },
} as const satisfies EsquemaDeFiltros;

export type FiltrosDoHistorico = FiltrosDe<typeof ESQUEMA_DO_HISTORICO>;

const DIA = /^\d{4}-\d{2}-\d{2}$/;

/** O pedido à API: só o que ela escolheu; dia mal escrito na URL é ignorado. */
export function paraPedido(filtros: FiltrosDoHistorico): FiltrosDeAtividades {
  const q = filtros.q.trim();
  return {
    ...(q ? { q } : {}),
    ...(filtros.categoria ? { categoria: filtros.categoria } : {}),
    ...(filtros.quem ? { quem: filtros.quem } : {}),
    ...(DIA.test(filtros.dia) ? { dia: filtros.dia } : {}),
  };
}

/** O que identifica um pedido: a mesma consulta é a mesma lista. */
export function chaveDoPedido(pedido: FiltrosDeAtividades): string {
  return consulta(pedido);
}

/** Os parâmetros da página (`searchParams`) como a leitura dos filtros espera. */
export function paraBusca(parametros: Record<string, string | string[] | undefined>): URLSearchParams {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) {
    if (Array.isArray(valor)) for (const item of valor) busca.append(chave, item);
    else if (valor !== undefined) busca.set(chave, valor);
  }
  return busca;
}
