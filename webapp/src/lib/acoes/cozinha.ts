"use server";

/**
 * As escritas da cozinha, como Server Actions: tem, não tem ou não sei para um
 * equipamento ou uma técnica, o valor de um limite da rotina (`null` é "não
 * sei") e a confirmação do que toda cozinha tem. Cada uma devolve `Resultado`
 * e refaz a página.
 */

import { api } from "@/lib/api";
import type { PedidoDeConfirmacao, RespostaDePosse } from "@/lib/api/perfil";

import { executarAcao } from "./base";

export async function definirPosse(tipo: "equipamentos" | "tecnicas", id: string, estado: RespostaDePosse) {
  return executarAcao(() => api.perfil.definirPosse(tipo, id, estado));
}

export async function definirRestricao(campo: string, valor: number | boolean | null) {
  return executarAcao(() => api.perfil.definirRestricao(campo, valor));
}

/**
 * Ela confirma o que toda cozinha tem: `{}` é tudo o que ainda é suposto ("Tenho
 * tudo isso"), `{receita}` o que uma receita usa ("Confirmar a cozinha"), e
 * `{itens}` só os itens ditos. Cada item vira "tem", dito por ela.
 */
export async function confirmarSupostos(pedido: PedidoDeConfirmacao = {}) {
  return executarAcao(() => api.perfil.confirmarSupostos(pedido));
}
