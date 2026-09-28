/**
 * O que chega no endereço da página da conversa: a conversa (`?c=`) e, de um
 * link de card, o rascunho e o contexto (`?rascunho=&tela=&tipo=&id=&rotulo=`,
 * o formato de `enderecoDaConversa`). Sem diretiva: a página, que é server
 * component, lê isto antes de montar a tela.
 */

import type { ContextoDaConversa } from "@/lib/api/conversa";

export type ChegadaNaConversa = {
  /** A conversa do endereço (`?c=`). */
  conversa?: string;
  rascunho?: string;
  contexto?: ContextoDaConversa;
  /** `?comecar=cozinha`: o botão do Início abre uma conversa nova com o pedido dela. */
  comecar?: "cozinha";
};

export type BuscaDaPagina = Record<string, string | string[] | undefined>;

function um(valor: string | string[] | undefined): string | undefined {
  const primeiro = Array.isArray(valor) ? valor[0] : valor;
  return primeiro?.trim() ? primeiro : undefined;
}

export function chegadaDaBusca(busca: BuscaDaPagina): ChegadaNaConversa {
  const tela = um(busca.tela);
  const tipo = um(busca.tipo);
  const id = um(busca.id);
  const rotulo = um(busca.rotulo);
  const conversa = um(busca.c);
  const rascunho = um(busca.rascunho);
  const comecar = um(busca.comecar);
  return {
    ...(comecar === "cozinha" ? { comecar } : {}),
    ...(conversa ? { conversa } : {}),
    ...(rascunho ? { rascunho } : {}),
    ...(tela && tipo ? { contexto: { tela, tipo, ...(id ? { id } : {}), ...(rotulo ? { rotulo } : {}) } } : {}),
  };
}
