/**
 * O histórico: o que o agente e a senhora fizeram, em frases dela.
 *
 * A tela de Histórico lê só `/atividades`: as decisões, as mudanças da
 * despensa e da cozinha, o que ela disse das receitas e o que o agente
 * consultou, em frases, agrupado por dia. Nome de ferramenta, identidade e
 * milissegundos são informação de quem mantém o sistema: nunca chegam aqui.
 */

import type { OpcoesDoPedido } from "./base";
import { consulta, pedir } from "./base";

/* -------------------------------------------------------------------------- */
/* Contrato v1                                                                 */
/* -------------------------------------------------------------------------- */

/** Quem fez: ela, o agente, ou a própria plataforma (a grade que se enche sozinha). */
export type QuemFez = "senhora" | "consultora" | "tela";

export type CategoriaDaAtividade = "despensa" | "receitas" | "cozinha" | "preco" | "cardapio";

export type Atividade = {
  id: string;
  quem: QuemFez | (string & {});
  /** "A senhora", "O agente" ou "A tela", pronto para a tela. */
  quem_rotulo: string;
  categoria: CategoriaDaAtividade | (string & {});
  categoria_rotulo: string;
  /** A frase, já dita para ela: nunca o nome de uma ferramenta. */
  texto: string;
  /** "hoje, 10:02", "24 de setembro". */
  quando_texto: string;
  /** "10:02": o horário, para a lista que já está agrupada por dia. */
  hora_texto: string;
  /** O dia no horário dela (`2026-09-26`), o mesmo do filtro. */
  dia: string;
  /** "pela tela" ou "pela conversa"; `null` quando não se aplica. */
  canal_texto: string | null;
  resultado: "ok" | "negado" | "erro" | (string & {});
  /** A tela da coisa de que a frase fala. */
  link: string | null;
};

export type GrupoDeAtividades = { dia: string; rotulo: string; itens: Atividade[] };

export type OpcaoDoHistorico = { id: string; rotulo: string };

export type PaginaDeAtividades = {
  /** A página, agrupada por dia, do mais novo para o mais antigo. */
  grupos: GrupoDeAtividades[];
  /** Quantas atividades batem com os filtros, em todas as páginas. */
  total: number;
  texto: string;
  /** O id da última atividade da página; `null` quando não há mais o que carregar. */
  proximo_cursor: string | null;
  categorias: OpcaoDoHistorico[];
  quem: OpcaoDoHistorico[];
  /** Os dias que têm atividade (com os outros filtros), para o filtro de dia. */
  dias: OpcaoDoHistorico[];
};

export type FiltrosDeAtividades = {
  cursor?: string;
  limite?: number;
  quem?: string;
  categoria?: string;
  dia?: string;
  q?: string;
};

export const atividades = {
  listar: (filtros: FiltrosDeAtividades = {}, opcoes?: OpcoesDoPedido) =>
    pedir<PaginaDeAtividades>(`/atividades${consulta(filtros)}`, opcoes),
} as const;
