"use client";

/**
 * As preferências dentro do React, lidas com `useSyncExternalStore`.
 *
 * No servidor (e na hidratação) vale o padrão; logo depois, a escolha
 * guardada. Nada disso aparece antes de ela abrir as Preferências, então não
 * há o que piscar: o que muda a tela inteira já foi aplicado pelo script do
 * `<head>` antes da primeira pintura.
 */

import { useSyncExternalStore } from "react";

import type { Preferencia } from "@/lib/preferencias";
import { MINIMALISTA, assinarPreferencias, lerPreferenciaDe } from "@/lib/preferencias";
import type { PreferenciaDeTema } from "@/lib/tema";
import { assinarTema, lerPreferencia } from "@/lib/tema";

export function usePreferencia<V extends string>(preferencia: Preferencia<V>): V {
  return useSyncExternalStore(
    assinarPreferencias,
    () => lerPreferenciaDe(preferencia),
    () => preferencia.padrao,
  );
}

/**
 * O modo minimalista está ligado? Para o que precisa de lógica (o interruptor
 * das Preferências). Esconder e mostrar fica com a variante `minimalista:` do
 * CSS, que vale antes da primeira pintura.
 */
export function useMinimalista(): boolean {
  return usePreferencia(MINIMALISTA) === "ligado";
}

/** O tema guardado, acompanhando as mudanças. No servidor, "automático". */
export function usePreferenciaDeTema(): PreferenciaDeTema {
  return useSyncExternalStore(assinarTema, lerPreferencia, () => "automatico");
}
