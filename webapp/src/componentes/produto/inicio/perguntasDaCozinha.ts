/**
 * As perguntas que ela responde no início: só as da cozinha (equipamento,
 * técnica, rotina). Peso, medida e preço nunca são pergunta. Módulo puro: a
 * tela inicial, que é do servidor, e a seção das perguntas, que é do
 * navegador, usam o mesmo filtro.
 */

import { daCozinha } from "@/componentes/produto/receitas/perguntas";
import type { PerguntaDaCozinha } from "@/lib/api/visao-geral";

export function perguntasDaCozinha(perguntas: readonly PerguntaDaCozinha[]): PerguntaDaCozinha[] {
  return perguntas.filter((pergunta) => daCozinha(pergunta.pergunta));
}
