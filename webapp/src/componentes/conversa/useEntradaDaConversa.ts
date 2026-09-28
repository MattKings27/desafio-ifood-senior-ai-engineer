"use client";

/**
 * O clique das entradas da conversa (a pílula do cabeçalho, o botão flutuante
 * e o Conversar da barra de baixo).
 *
 * As três são links para /conversa: sem JavaScript, com Ctrl ou com o botão do
 * meio, levam à página inteira. O clique simples abre o painel (ou a folha)
 * ali mesmo, com o contexto da página em que ela está.
 */

import type { MouseEvent } from "react";
import { useCallback } from "react";

import { useConversa } from "./ProvedorDaConversa";

/** O atributo das entradas: é para uma delas que o foco volta, se quem abriu sumiu. */
export const ATRIBUTO_DA_ENTRADA = "data-abre-conversa";

export function cliqueSimples(evento: MouseEvent<HTMLAnchorElement>): boolean {
  return evento.button === 0 && !evento.metaKey && !evento.ctrlKey && !evento.shiftKey && !evento.altKey;
}

export function useEntradaDaConversa(): (evento: MouseEvent<HTMLAnchorElement>) => void {
  const { abrirDaPagina } = useConversa();
  return useCallback(
    (evento: MouseEvent<HTMLAnchorElement>) => {
      if (!cliqueSimples(evento)) return;
      evento.preventDefault();
      abrirDaPagina(evento.currentTarget);
    },
    [abrirDaPagina],
  );
}
