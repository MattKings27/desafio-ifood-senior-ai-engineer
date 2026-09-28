"use server";

/**
 * As escritas da despensa, como Server Actions: acrescentar, corrigir, tirar,
 * desfazer e devolver uma compra aos R$ 80.
 *
 * Cada uma devolve `Resultado` (nunca lança) e, dando certo, refaz a rota atual
 * na mesma ida e volta. Tirar o item pela página dele pede `atualizar: false`:
 * a página do item que saiu não existe mais, e quem chamou leva a senhora de
 * volta à lista.
 */

import { api } from "@/lib/api";
import type { CorrecaoDoItem, NovoItem } from "@/lib/api/despensa";

import type { OpcoesDaExecucao } from "./base";
import { executarAcao } from "./base";

export async function adicionarItem(novo: NovoItem) {
  return executarAcao(() => api.despensa.adicionar(novo));
}

export async function corrigirItem(id: string, correcao: CorrecaoDoItem) {
  return executarAcao(() => api.despensa.corrigir(id, correcao));
}

export async function removerItem(id: string, idCliente?: string, opcoes: OpcoesDaExecucao = {}) {
  return executarAcao(() => api.despensa.remover(id, idCliente), opcoes);
}

export async function desfazerMudanca(evento: string, idCliente?: string) {
  return executarAcao(() => api.despensa.desfazerEvento(evento, idCliente));
}

export async function devolverCompra(compra: number, idCliente?: string) {
  return executarAcao(() => api.despensa.estornarCompra(compra, idCliente));
}
