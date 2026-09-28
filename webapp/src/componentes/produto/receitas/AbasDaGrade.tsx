"use client";

/**
 * As abas da grade como pílulas, cada uma com a contagem. No celular elas
 * quebram linha inteiras ("Falta uma resposta sua" não vira três linhas
 * espremidas), e nada rola de lado.
 *
 * É o padrão ARIA de abas: um ponto de parada do Tab na lista, as setas (e
 * Home, End) trocam de aba, e o painel diz de qual aba é.
 */

import clsx from "clsx";
import type { KeyboardEvent, ReactNode } from "react";
import { useId, useRef } from "react";

import type { AbaDeReceitas } from "@/lib/api/receitas";

import type { AbaDaGrade } from "./filtros";
import { ABAS_DA_GRADE, ROTULO_DA_ABA } from "./filtros";

const TECLAS: Readonly<Record<string, (indice: number, total: number) => number>> = {
  ArrowRight: (indice, total) => (indice + 1) % total,
  ArrowDown: (indice, total) => (indice + 1) % total,
  ArrowLeft: (indice, total) => (indice - 1 + total) % total,
  ArrowUp: (indice, total) => (indice - 1 + total) % total,
  Home: () => 0,
  End: (_indice, total) => total - 1,
};

export function AbasDaGrade({
  ativa,
  contagens,
  aoTrocar,
  children,
}: {
  ativa: AbaDaGrade;
  contagens: Readonly<Record<AbaDeReceitas, number>>;
  aoTrocar: (aba: AbaDaGrade) => void;
  /** O painel da aba ativa. */
  children: ReactNode;
}) {
  const base = useId();
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);
  const idDaAba = (aba: AbaDaGrade) => `${base}-aba-${aba}`;
  const idDoPainel = `${base}-painel`;

  const aoTeclar = (evento: KeyboardEvent<HTMLButtonElement>, indice: number) => {
    const destino = TECLAS[evento.key]?.(indice, ABAS_DA_GRADE.length);
    if (destino === undefined) return;
    evento.preventDefault();
    // O destino vem da própria lista (resto da divisão pelo tamanho dela).
    aoTrocar(ABAS_DA_GRADE[destino] as AbaDaGrade);
    botoes.current[destino]?.focus();
  };

  return (
    <div>
      <div role="tablist" aria-label="Receitas" className="flex flex-wrap gap-1.5 sm:gap-2">
        {ABAS_DA_GRADE.map((aba, indice) => {
          const selecionada = aba === ativa;
          return (
            <button
              key={aba}
              ref={(no) => {
                botoes.current[indice] = no;
              }}
              type="button"
              role="tab"
              id={idDaAba(aba)}
              aria-selected={selecionada}
              aria-controls={idDoPainel}
              tabIndex={selecionada ? 0 : -1}
              onClick={() => aoTrocar(aba)}
              onKeyDown={(evento) => aoTeclar(evento, indice)}
              className={clsx(
                "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3 text-[0.8125rem] font-semibold sm:gap-2 sm:px-4 sm:text-sm",
                "transition-colors duration-rapida",
                selecionada
                  ? "border-tinta bg-tinta text-superficie"
                  : "border-borda-campo/60 bg-superficie text-texto hover:bg-secao hover:text-tinta",
              )}
            >
              {ROTULO_DA_ABA[aba]}
              <span
                className={clsx(
                  "numero min-w-5 rounded-full px-1.5 text-center text-xs font-bold sm:min-w-6",
                  selecionada ? "bg-superficie/20 text-superficie" : "bg-secao text-texto",
                )}
              >
                {contagens[aba]}
              </span>
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={idDoPainel}
        aria-labelledby={idDaAba(ativa)}
        tabIndex={0}
        className="rounded-sm pt-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-marca"
      >
        {children}
      </div>
    </div>
  );
}
