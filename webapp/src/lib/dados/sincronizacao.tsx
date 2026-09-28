"use client";

/**
 * Sincronização entre superfícies: a conversa mudou a despensa, a tela aberta
 * atrás do painel tem que acompanhar.
 *
 * Quem sabe que algo mudou (o evento `estado.alterado` do chat, o fim de uma
 * rodada de descoberta) chama `avisar(["despensa", "orcamento"])`. Os avisos
 * que chegam juntos viram um `router.refresh()` só, depois de uma espera curta
 * (250 ms), e cada componente que assinou um recurso é chamado uma vez com o
 * conjunto que mudou.
 */

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";

export type Recurso =
  | "despensa"
  | "orcamento"
  | "receitas"
  | "perfil"
  | "cardapio"
  | "atividades"
  | "conversas"
  | "visao-geral"
  | (string & {});

export type OuvinteDeRecursos = (recursos: readonly Recurso[]) => void;

type ValorDaSincronizacao = {
  avisar: (recursos: readonly Recurso[]) => void;
  /** `"*"` escuta qualquer recurso. Devolve a função que cancela a assinatura. */
  assinar: (recurso: Recurso | "*", ouvinte: OuvinteDeRecursos) => () => void;
};

const SEM_PROVEDOR: ValorDaSincronizacao = {
  avisar: () => {},
  assinar: () => () => {},
};

const Contexto = createContext<ValorDaSincronizacao>(SEM_PROVEDOR);

export function ProvedorDeSincronizacao({
  children,
  espera = 250,
}: {
  children: ReactNode;
  espera?: number;
}) {
  const router = useRouter();
  const ouvintes = useRef(new Map<string, Set<OuvinteDeRecursos>>());
  const pendentes = useRef(new Set<Recurso>());
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);

  const descarregar = useCallback(() => {
    relogio.current = null;
    const mudaram = [...pendentes.current];
    pendentes.current.clear();
    if (mudaram.length === 0) return;

    const chamados = new Set<OuvinteDeRecursos>();
    for (const chave of [...mudaram, "*"]) {
      for (const ouvinte of ouvintes.current.get(chave) ?? []) {
        if (chamados.has(ouvinte)) continue;
        chamados.add(ouvinte);
        ouvinte(mudaram);
      }
    }
    router.refresh();
  }, [router]);

  const avisar = useCallback(
    (recursos: readonly Recurso[]) => {
      if (recursos.length === 0) return;
      for (const recurso of recursos) pendentes.current.add(recurso);
      if (relogio.current) clearTimeout(relogio.current);
      relogio.current = setTimeout(descarregar, espera);
    },
    [descarregar, espera],
  );

  const assinar = useCallback((recurso: Recurso | "*", ouvinte: OuvinteDeRecursos) => {
    let conjunto = ouvintes.current.get(recurso);
    if (!conjunto) {
      conjunto = new Set();
      ouvintes.current.set(recurso, conjunto);
    }
    conjunto.add(ouvinte);
    return () => {
      conjunto.delete(ouvinte);
    };
  }, []);

  useEffect(
    () => () => {
      if (relogio.current) clearTimeout(relogio.current);
    },
    [],
  );

  const valor = useMemo(() => ({ avisar, assinar }), [avisar, assinar]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

/** `avisar` e `assinar`. Fora do provedor, os dois não fazem nada. */
export function useSincronizacao(): ValorDaSincronizacao {
  return useContext(Contexto);
}

/** Chama `ouvinte` quando algum dos recursos mudar (depois da espera). */
export function useAoMudar(recursos: Recurso | readonly Recurso[], ouvinte: OuvinteDeRecursos) {
  const { assinar } = useSincronizacao();
  const atual = useRef(ouvinte);
  useEffect(() => {
    atual.current = ouvinte;
  });
  const chave = typeof recursos === "string" ? recursos : recursos.join("|");
  useEffect(() => {
    const lista = chave.split("|");
    const chamar: OuvinteDeRecursos = (mudaram) => atual.current(mudaram);
    const cancelar = lista.map((recurso) => assinar(recurso, chamar));
    return () => {
      for (const c of cancelar) c();
    };
  }, [assinar, chave]);
}
