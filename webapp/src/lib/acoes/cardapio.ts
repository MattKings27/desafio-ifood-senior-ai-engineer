"use server";

/**
 * As escritas da tela do cardápio, como Server Actions: tirar um prato do
 * cardápio e desfazer a última decisão de um prato.
 *
 * Tirar grava uma decisão nova ("recusado"), e desfazer grava outra que volta
 * ao estado de antes: a tela nunca apaga nada, e a API diz a frase do que
 * mudou. As duas refazem a rota na mesma ida e volta, e devolvem só a frase
 * para o aviso.
 *
 * Mudar o preço não mora aqui: é pela conversa, porque a decisão do preço é
 * dela com a conta do agente ao lado.
 */

import { api } from "@/lib/api";

import type { Resultado } from "./base";
import { executarAcao, falha } from "./base";

/** O que a tela mostra depois de uma mudança: a frase da API. */
export type FraseDaMudanca = { texto: string };

export async function tirarDoCardapio(prato: string, idCliente?: string): Promise<Resultado<FraseDaMudanca>> {
  if (!prato.trim()) return falha("uso", "Diga qual prato sai do cardápio.");
  return executarAcao(async () => {
    const { texto } = await api.cardapio.decidir({ prato, decisao: "recusado", id_cliente: idCliente });
    return { texto };
  });
}

export async function desfazerNoCardapio(prato: string, idCliente?: string): Promise<Resultado<FraseDaMudanca>> {
  if (!prato.trim()) return falha("uso", "Diga qual prato volta ao que era.");
  return executarAcao(async () => {
    const { texto } = await api.cardapio.desfazer(prato, idCliente);
    return { texto };
  });
}
