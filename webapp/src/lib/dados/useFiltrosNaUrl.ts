"use client";

/**
 * Os filtros da página atual, lidos e escritos na URL (ver `@/lib/filtros/url`).
 *
 * Trocar um filtro usa `history.replaceState`: o Next acompanha e o
 * `useSearchParams` atualiza, sem ida ao servidor e sem entrar no histórico do
 * "voltar". Quem usa fica dentro de um `<Suspense>` (exigência do
 * `useSearchParams`).
 */

import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import type { EsquemaDeFiltros, FiltrosDe } from "@/lib/filtros/url";
import { contarAtivos, escreverFiltros, lerFiltros } from "@/lib/filtros/url";

/**
 * As marcas que o Next põe no estado do histórico. Um `replaceState` que chega
 * com elas é tratado como do próprio Next e não avisa o roteador: a URL mudava
 * e o `useSearchParams` ficava com a antiga. Sem elas, o Next acompanha a troca
 * e copia as dele de volta; o resto do estado (a marca do painel da conversa)
 * continua.
 */
const MARCAS_DO_NEXT = new Set(["__NA", "_N", "__PRIVATE_NEXTJS_INTERNALS_TREE"]);

export function estadoSemAsMarcasDoNext(estado: unknown): Record<string, unknown> | null {
  if (estado === null || typeof estado !== "object") return null;
  return Object.fromEntries(Object.entries(estado).filter(([chave]) => !MARCAS_DO_NEXT.has(chave)));
}

export function useFiltrosNaUrl<E extends EsquemaDeFiltros>(esquema: E) {
  const parametros = useSearchParams();
  const filtros = useMemo(() => lerFiltros(parametros, esquema), [parametros, esquema]);

  const trocarUrl = useCallback((novos: URLSearchParams) => {
    const url = new URL(window.location.href);
    url.search = novos.toString();
    window.history.replaceState(estadoSemAsMarcasDoNext(window.history.state), "", url);
  }, []);

  const definir = useCallback(
    (parcial: Partial<FiltrosDe<E>>) => {
      trocarUrl(escreverFiltros(parcial, esquema, new URLSearchParams(window.location.search)));
    },
    [esquema, trocarUrl],
  );

  const limpar = useCallback(
    (chaves: readonly (keyof E)[] = Object.keys(esquema)) => {
      const atuais = new URLSearchParams(window.location.search);
      for (const chave of chaves) atuais.delete(String(chave));
      trocarUrl(atuais);
    },
    [esquema, trocarUrl],
  );

  const ativos = useMemo(() => contarAtivos(filtros, esquema), [filtros, esquema]);
  return { filtros, definir, limpar, ativos };
}
