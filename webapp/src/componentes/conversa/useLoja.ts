"use client";

/**
 * A loja da conversa dentro do React: o contexto que a entrega, e o seletor
 * que redesenha só quando o pedaço olhado muda (`useSyncExternalStore`).
 */

import { createContext, useContext, useSyncExternalStore } from "react";

import type { EstadoDaLoja, Loja } from "@/lib/conversa/loja";

export const ContextoDaLoja = createContext<Loja | null>(null);

/** A loja do provedor. Fora do `ProvedorDaConversa`, não há conversa para mostrar. */
export function useLojaDaConversa(): Loja {
  const loja = useContext(ContextoDaLoja);
  if (!loja) throw new Error("useLojaDaConversa precisa do ProvedorDaConversa em volta");
  return loja;
}

/** A loja, se houver provedor; `null` fora dele (peças que podem aparecer soltas). */
export function useLojaOpcional(): Loja | null {
  return useContext(ContextoDaLoja);
}

/**
 * Um pedaço do estado da loja. O seletor tem que devolver algo que já está no
 * estado (ou um valor simples): um objeto novo a cada leitura redesenharia sem
 * fim.
 */
export function useSeletor<T>(loja: Loja, seletor: (estado: EstadoDaLoja) => T): T {
  const ler = () => seletor(loja.ler());
  return useSyncExternalStore(loja.assinar, ler, ler);
}
