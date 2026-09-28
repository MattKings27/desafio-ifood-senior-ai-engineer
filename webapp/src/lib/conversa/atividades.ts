/**
 * O que o agente está fazendo, dito do jeito dela.
 *
 * O backend é o dono das frases ("olhando sua despensa" → "olhei sua
 * despensa"), e o mesmo catálogo alimenta o Histórico. A tela guarda um plano
 * B por ferramenta, para quando a frase não vier ou vier com cara de programa:
 * nome cru de ferramenta (`avaliar_receita`), jargão, texto em inglês. Nome de
 * ferramenta nunca aparece para ela.
 */

import { encontrarJargao, pareceTecnico } from "@/lib/formato";

import { comValoresEscondidos } from "./mascara";

export type RotulosDaAtividade = { rotulo: string; rotuloFeito: string };

/** `mcp_mise_avaliar_receita`, `mcp__mise__avaliar_receita` → `avaliar_receita`. */
export function normalizarFerramenta(nome: string): string {
  return nome
    .trim()
    .toLowerCase()
    .replace(/^mcp_{1,2}mise_{1,2}/, "");
}

/** Plano B por ferramenta, na tabela do plano (9.4): fazendo → feito. */
export const ROTULOS_DAS_FERRAMENTAS: Readonly<Record<string, RotulosDaAtividade>> = {
  diagnostico_despensa: { rotulo: "olhando sua despensa", rotuloFeito: "olhei sua despensa" },
  custo_unitario: { rotulo: "conferindo o custo de um ingrediente", rotuloFeito: "conferi o custo de um ingrediente" },
  web_search: { rotulo: "pesquisando receitas na internet", rotuloFeito: "pesquisei receitas na internet" },
  buscar_receita_na_web: { rotulo: "lendo a receita", rotuloFeito: "li a receita" },
  pauta_de_descoberta: {
    rotulo: "separando o que procurar com o que a senhora tem",
    rotuloFeito: "separei o que procurar com o que a senhora tem",
  },
  avaliar_receita: {
    rotulo: "conferindo se a senhora consegue fazer a receita",
    rotuloFeito: "conferi se a senhora consegue fazer a receita",
  },
  comparar_candidatas: { rotulo: "comparando as receitas", rotuloFeito: "comparei as receitas" },
  proxima_pergunta: { rotulo: "separando a próxima pergunta", rotuloFeito: "separei a próxima pergunta" },
  registrar_resposta: { rotulo: "anotando a resposta da senhora", rotuloFeito: "anotei a resposta da senhora" },
  registrar_preco_mercado: { rotulo: "anotando o preço", rotuloFeito: "anotei o preço" },
  consultar_orcamento: { rotulo: "vendo o orçamento", rotuloFeito: "vi o orçamento" },
  registrar_compra: { rotulo: "anotando a compra", rotuloFeito: "anotei a compra" },
  calcular_cmv: { rotulo: "calculando o custo por porção", rotuloFeito: "calculei o custo por porção" },
  cenarios_preco: { rotulo: "montando os caminhos de preço", rotuloFeito: "montei os caminhos de preço" },
  testar_sensibilidade: { rotulo: "fazendo a conta desse preço", rotuloFeito: "fiz a conta desse preço" },
  estimar_preco_preliminar: { rotulo: "fazendo uma estimativa do preço", rotuloFeito: "fiz uma estimativa do preço" },
  registrar_decisao: { rotulo: "guardando a decisão da senhora", rotuloFeito: "guardei a decisão da senhora" },
  registrar_avaliacao_da_receita: {
    rotulo: "anotando a avaliação da senhora",
    rotuloFeito: "anotei a avaliação da senhora",
  },
  atualizar_despensa: { rotulo: "atualizando a despensa", rotuloFeito: "atualizei a despensa" },
  registrar_gosto: { rotulo: "anotando o que a senhora acha", rotuloFeito: "anotei o que a senhora acha" },
  consultar_perfil: {
    rotulo: "olhando o que a senhora tem na cozinha",
    rotuloFeito: "olhei o que a senhora tem na cozinha",
  },
  consultar_planilha: { rotulo: "lendo a sua planilha", rotuloFeito: "li a sua planilha" },
  resumo_da_consultoria: { rotulo: "relendo o que já combinamos", rotuloFeito: "reli o que já combinamos" },
  _thinking: { rotulo: "pensando", rotuloFeito: "pensei" },
};

const CONSULTAR: RotulosDaAtividade = { rotulo: "consultando as anotações", rotuloFeito: "consultei as anotações" };

/** Quando nem a frase nem a ferramenta dizem nada útil. */
export const ROTULO_GENERICO: RotulosDaAtividade = {
  rotulo: "cuidando de um detalhe",
  rotuloFeito: "cuidei de um detalhe",
};

/** O plano B de uma ferramenta, pelo nome normalizado. */
export function rotulosDaFerramenta(ferramenta: string | null | undefined): RotulosDaAtividade {
  const nome = normalizarFerramenta(ferramenta ?? "");
  const conhecido = ROTULOS_DAS_FERRAMENTAS[nome];
  if (conhecido) return conhecido;
  if (nome.startsWith("consultar_")) return CONSULTAR;
  return ROTULO_GENERICO;
}

/** A frase serve para ela? Nada vazio, técnico ou com jargão. Dinheiro sai escondido. */
function frase(texto: unknown): string | null {
  if (typeof texto !== "string") return null;
  const limpo = texto.replace(/\s+/g, " ").trim();
  if (!limpo || limpo.length > 160) return null;
  if (pareceTecnico(limpo) || encontrarJargao(limpo).length > 0) return null;
  return comValoresEscondidos(limpo);
}

/**
 * As frases de uma atividade: as do backend quando servem, senão o plano B da
 * ferramenta. As duas vêm juntas: meia frase do backend e meia do plano B
 * ficariam desencontradas ("olhando sua despensa" → "cuidei de um detalhe").
 */
export function rotulosDaAtividade(evento: {
  ferramenta?: unknown;
  rotulo?: unknown;
  rotulo_feito?: unknown;
}): RotulosDaAtividade {
  const rotulo = frase(evento.rotulo);
  const rotuloFeito = frase(evento.rotulo_feito);
  if (rotulo && rotuloFeito) return { rotulo, rotuloFeito };
  return rotulosDaFerramenta(typeof evento.ferramenta === "string" ? evento.ferramenta : null);
}

/** O que foi feito, numa resposta guardada: a frase do backend, ou nada (não há como adivinhar). */
export function rotuloFeitoGuardado(texto: unknown): string | null {
  return frase(texto);
}

/** Um detalhe ou resumo de atividade, se servir para ela (com dinheiro escondido). */
export function detalheDaAtividade(texto: unknown): string | undefined {
  return frase(texto) ?? undefined;
}

/** A primeira letra em maiúscula, para a frase começar uma linha. */
export function comMaiuscula(texto: string): string {
  return texto ? texto.charAt(0).toLocaleUpperCase("pt-BR") + texto.slice(1) : texto;
}

/** Tempo passado, para "Trabalhando há 42 s": "5 s", "1 min", "1 min 5 s". */
export function tempoDecorrido(ms: number): string {
  const segundos = Math.max(0, Math.floor(ms / 1000));
  if (segundos < 60) return `${segundos} s`;
  const minutos = Math.floor(segundos / 60);
  const resto = segundos % 60;
  return resto === 0 ? `${minutos} min` : `${minutos} min ${resto} s`;
}
