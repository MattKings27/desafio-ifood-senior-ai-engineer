"use client";

/**
 * Uma media query acompanhada no React. No servidor (e antes de montar) é
 * `false`: o painel da conversa começa fechado, então não há o que piscar.
 */

import { useSyncExternalStore } from "react";

/** A partir daqui o painel fica preso ao lado (não modal); abaixo, é uma folha. */
export const TELA_LARGA = "(min-width: 1024px)";

/** Toque é o jeito principal de apontar (celular, tablet): Enter quebra linha. */
export const TOQUE = "(pointer: coarse)";

export function consultarMidia(consulta: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(consulta).matches
    : false;
}

export function useMidia(consulta: string): boolean {
  return useSyncExternalStore(
    (avisar) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
      const lista = window.matchMedia(consulta);
      lista.addEventListener("change", avisar);
      return () => lista.removeEventListener("change", avisar);
    },
    () => consultarMidia(consulta),
    () => false,
  );
}
