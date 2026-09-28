"use client";

/**
 * Escolha única entre poucas opções, lado a lado (Tenho / Não tenho / Não sei;
 * Claro / Escuro / Automático).
 *
 * São rádios nativos num `fieldset` com `legend`: as setas do teclado trocam a
 * opção, o leitor de tela anuncia "1 de 3", e nada disso precisou ser reescrito
 * em JavaScript. A opção escolhida fica em tinta cheia, não em vermelho: o
 * vermelho da marca é para agir.
 *
 * `adaptavel` põe as opções lado a lado quando o espaço dá (18rem, que crescem
 * com o texto grande) e uma por linha quando não dá, com o rótulo quebrando
 * linha em vez de sumir atrás de reticências: é o jeito dos cards estreitos.
 */

import clsx from "clsx";
import type { ReactNode } from "react";
import { useId } from "react";

export type OpcaoDoSegmentado<V extends string> = {
  valor: V;
  rotulo: string;
  icone?: ReactNode;
};

export function Segmentado<V extends string>({
  legenda,
  opcoes,
  valor,
  aoMudar,
  nome,
  legendaVisivel = true,
  desabilitado = false,
  larguraTotal = true,
  orientacao = "horizontal",
  className,
}: {
  legenda: string;
  opcoes: readonly OpcaoDoSegmentado<V>[];
  /** `null` quando nada foi escolhido ainda (ex.: "ainda não perguntei"). */
  valor: V | null;
  aoMudar: (valor: V) => void;
  nome?: string;
  legendaVisivel?: boolean;
  desabilitado?: boolean;
  larguraTotal?: boolean;
  /**
   * `vertical`: uma opção por linha, para rótulos que não cabem lado a lado.
   * `adaptavel`: lado a lado com espaço, uma por linha sem ele, sem cortar texto.
   */
  orientacao?: "horizontal" | "vertical" | "adaptavel";
  className?: string;
}) {
  const gerado = useId();
  const grupo = nome ?? `segmentado${gerado}`;
  return (
    <fieldset className={clsx("min-w-0", className)} disabled={desabilitado}>
      <legend className={legendaVisivel ? "mb-2 text-sm font-semibold text-tinta" : "sr-only"}>
        {legenda}
      </legend>
      <div className={orientacao === "adaptavel" ? "@container" : undefined}>
        <div
          className={clsx(
            "gap-1 rounded-sm border border-borda-campo/60 bg-superficie p-1",
            orientacao === "vertical"
              ? "grid grid-cols-1"
              : orientacao === "adaptavel"
                ? "grid grid-cols-1 @[18rem]:auto-cols-fr @[18rem]:grid-flow-col @[18rem]:grid-cols-none"
                : larguraTotal
                  ? "grid auto-cols-fr grid-flow-col"
                  : "inline-grid auto-cols-auto grid-flow-col",
          )}
        >
          {opcoes.map((opcao) => (
            <label key={opcao.valor} className="relative min-w-0">
              <input
                type="radio"
                name={grupo}
                value={opcao.valor}
                checked={valor === opcao.valor}
                onChange={() => aoMudar(opcao.valor)}
                className="peer sr-only"
              />
              <span
                className={clsx(
                  "flex min-h-11 cursor-pointer items-center gap-1.5 rounded-[6px] px-3",
                  orientacao === "vertical" ? "justify-start text-left" : "justify-center text-center",
                  "text-sm font-semibold text-apagado transition-colors duration-rapida",
                  "hover:bg-secao hover:text-tinta",
                  "peer-checked:bg-tinta peer-checked:text-superficie",
                  "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marca",
                  "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
                )}
              >
                {opcao.icone ? (
                  <span aria-hidden="true" className="inline-flex shrink-0">
                    {opcao.icone}
                  </span>
                ) : null}
                <span className={orientacao === "horizontal" ? "truncate" : "min-w-0 break-words"}>{opcao.rotulo}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
    </fieldset>
  );
}
