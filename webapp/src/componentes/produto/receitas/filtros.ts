/**
 * Os filtros da grade de receitas, guardados na URL (`/receitas?aba=ranking&q=frango`).
 *
 * Arquivo puro: a página (no servidor) lê a URL com o mesmo esquema e pede a
 * lista já filtrada à API; a tela (no navegador) troca a URL com
 * `useFiltrosNaUrl` e pede de novo. Quem filtra é a API, porque as contagens
 * de cada aba também mudam com os filtros, e a busca ignora acento e caixa lá.
 */

import type { AbaDeReceitas, FiltrosDeReceitas, OrdemDeReceitas } from "@/lib/api/receitas";
import { consulta } from "@/lib/api/base";
import type { EsquemaDeFiltros, FiltrosDe } from "@/lib/filtros/url";

/** As abas da grade. "Não gosto de fazer" é uma seção fechada dentro de cada aba, não uma aba. */
export const ABAS_DA_GRADE = ["pode_fazer", "falta_resposta", "ranking"] as const;
export type AbaDaGrade = (typeof ABAS_DA_GRADE)[number];

export const ROTULO_DA_ABA: Readonly<Record<AbaDeReceitas, string>> = {
  pode_fazer: "Dá para fazer",
  falta_resposta: "Falta uma resposta sua",
  ranking: "Ranking",
  nao_quer: "Não gosto de fazer",
};

export const ORDENS = ["aproveitamento", "pontuacao", "compra", "tempo", "recentes"] as const satisfies readonly OrdemDeReceitas[];

export const ROTULO_DA_ORDEM: Readonly<Record<OrdemDeReceitas, string>> = {
  aproveitamento: "Aproveita mais a despensa",
  pontuacao: "Maior pontuação",
  compra: "Menos compra",
  tempo: "Mais rápida",
  recentes: "Mais recentes",
};

/** A ordem de cada aba quando ela não escolhe outra (a mesma da API). */
export const ORDEM_DA_ABA: Readonly<Record<AbaDeReceitas, OrdemDeReceitas>> = {
  pode_fazer: "aproveitamento",
  falta_resposta: "aproveitamento",
  ranking: "pontuacao",
  nao_quer: "recentes",
};

export const ESQUEMA_DAS_RECEITAS = {
  aba: { tipo: "opcao", opcoes: ABAS_DA_GRADE, padrao: "pode_fazer" },
  q: { tipo: "texto" },
  usa: { tipo: "texto" },
  tempo_max: { tipo: "numero" },
  so_com_o_que_tenho: { tipo: "booleano" },
  nota_min: { tipo: "numero" },
  /** Vazio: a ordem padrão da aba. */
  ordem: { tipo: "opcao", opcoes: ["", ...ORDENS] as const, padrao: "" },
} as const satisfies EsquemaDeFiltros;

export type FiltrosDaGrade = FiltrosDe<typeof ESQUEMA_DAS_RECEITAS>;

/**
 * O esquema com outra aba padrão. Sem aba na URL e nada para fazer ainda, a
 * página abre em "Falta uma resposta sua" na mesma ida ao servidor, e a tela lê
 * a URL sem `aba` do mesmo jeito que o servidor leu, sem redirecionar.
 */
export function esquemaComAba(aba: AbaDaGrade): typeof ESQUEMA_DAS_RECEITAS {
  return { ...ESQUEMA_DAS_RECEITAS, aba: { ...ESQUEMA_DAS_RECEITAS.aba, padrao: aba } } as unknown as typeof ESQUEMA_DAS_RECEITAS;
}

/** Os filtros que ficam na folha "Filtros" (a busca e a ordem ficam à vista). */
export const FILTROS_DA_FOLHA = ["tempo_max", "so_com_o_que_tenho", "nota_min", "usa"] as const;

export const OPCOES_DE_TEMPO = [
  { valor: "", rotulo: "Qualquer tempo" },
  { valor: "30", rotulo: "Até 30 min" },
  { valor: "45", rotulo: "Até 45 min" },
  { valor: "60", rotulo: "Até 1 hora" },
  { valor: "120", rotulo: "Até 2 horas" },
] as const;

export const OPCOES_DE_NOTA = [
  { valor: "", rotulo: "Qualquer pontuação" },
  { valor: "60", rotulo: "60 ou mais" },
  { valor: "70", rotulo: "70 ou mais" },
  { valor: "80", rotulo: "80 ou mais" },
  { valor: "90", rotulo: "90 ou mais" },
] as const;

/** Tempo máximo que a API aceita: inteiro de 1 a 100.000 minutos. */
function tempoValido(minutos: number | null): number | undefined {
  return minutos !== null && Number.isInteger(minutos) && minutos >= 1 && minutos <= 100_000 ? minutos : undefined;
}

/** Pontuação mínima que a API aceita: de 0 a 100. */
function notaValida(nota: number | null): number | undefined {
  return nota !== null && nota >= 0 && nota <= 100 ? nota : undefined;
}

/** O pedido à API. Filtro fora da faixa que a API aceita fica de fora, em vez de virar erro. */
export function paraPedido(filtros: FiltrosDaGrade): FiltrosDeReceitas {
  return {
    aba: filtros.aba,
    q: filtros.q.trim() || undefined,
    usa: filtros.usa.trim() || undefined,
    tempo_max: tempoValido(filtros.tempo_max),
    so_com_o_que_tenho: filtros.so_com_o_que_tenho || undefined,
    nota_min: notaValida(filtros.nota_min),
    ordem: filtros.ordem || undefined,
  };
}

/**
 * O pedido das que ela não quer, com os mesmos filtros da grade: cada uma vai
 * para a seção "Não gosto de fazer" da aba em que estaria se ela gostasse.
 */
export function pedidoDasQueNaoQuer(pedido: FiltrosDeReceitas): FiltrosDeReceitas {
  return { ...pedido, aba: "nao_quer", ordem: undefined };
}

/** A mesma lista para o mesmo pedido: a chave é a consulta, sempre na mesma ordem. */
export function chaveDoPedido(pedido: FiltrosDeReceitas): string {
  return consulta({
    aba: pedido.aba,
    q: pedido.q,
    usa: pedido.usa,
    tempo_max: pedido.tempo_max,
    so_com_o_que_tenho: pedido.so_com_o_que_tenho,
    nota_min: pedido.nota_min,
    ordem: pedido.ordem,
  });
}

/** O `searchParams` da página (objeto do Next) como parâmetros de URL. */
export function paraBusca(parametros: Record<string, string | string[] | undefined>): URLSearchParams {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) {
    if (Array.isArray(valor)) for (const item of valor) busca.append(chave, item);
    else if (valor !== undefined) busca.set(chave, valor);
  }
  return busca;
}

/** "Até 45 min", "Até 1 hora", "Até 1 h 30 min". */
export function rotuloDoTempo(minutos: number): string {
  if (minutos < 60) return `Até ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  if (resto > 0) return `Até ${horas} h ${resto} min`;
  return horas === 1 ? "Até 1 hora" : `Até ${horas} horas`;
}

/** O item da despensa do filtro `usa`, pelo id: o slug vira nome; o id gerado não diz nada. */
export function rotuloDoUsa(id: string): string {
  if (/^item-[0-9a-f]+$/i.test(id)) return "Usa um item da despensa";
  return `Usa ${id.replaceAll("-", " ")}`;
}

/** "3 encontradas", "1 encontrada", "Nenhuma encontrada". */
export function resumoDaBusca(quantas: number): string {
  if (quantas === 0) return "Nenhuma encontrada";
  return quantas === 1 ? "1 encontrada" : `${quantas} encontradas`;
}

/** "3 receitas", "1 receita". */
export function receitasTexto(quantas: number): string {
  return quantas === 1 ? "1 receita" : `${quantas} receitas`;
}
