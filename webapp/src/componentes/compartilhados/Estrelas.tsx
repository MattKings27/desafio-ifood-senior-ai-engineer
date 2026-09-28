"use client";

/**
 * Estrelas de 1 a 5: para ela dar a nota (Sabor, Facilidade…) ou só para ver.
 *
 * A entrada é um grupo de rádios nativos: Tab entra no grupo, as setas trocam a
 * nota, e o leitor de tela diz "3 estrelas, 3 de 5". Cada estrela tem 44 px de
 * alvo. "Tirar nota" volta ao sem nota, que é diferente de uma estrela.
 */

import { Star } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useId, useState } from "react";

const NOTAS = [1, 2, 3, 4, 5] as const;

function nomeDaNota(nota: number): string {
  return nota === 1 ? "1 estrela" : `${nota} estrelas`;
}

export function Estrelas({
  legenda,
  valor,
  aoMudar,
  somenteLeitura = false,
  permiteLimpar = true,
  legendaVisivel = true,
  tamanho = "md",
  nome,
  className,
}: {
  legenda: string;
  /** De 1 a 5, ou `null` sem nota. */
  valor: number | null;
  aoMudar?: (nota: number | null) => void;
  somenteLeitura?: boolean;
  permiteLimpar?: boolean;
  legendaVisivel?: boolean;
  tamanho?: "sm" | "md";
  nome?: string;
  className?: string;
}) {
  const gerado = useId();
  const [sobre, setSobre] = useState<number | null>(null);
  const icone = tamanho === "sm" ? 18 : 28;

  if (somenteLeitura || !aoMudar) {
    const nota = valor ?? 0;
    return (
      <span
        role="img"
        aria-label={valor === null ? `${legenda}: sem nota` : `${legenda}: ${valor} de 5 estrelas`}
        className={clsx("inline-flex items-center gap-0.5", className)}
      >
        {NOTAS.map((n) => (
          <Star
            key={n}
            size={icone}
            weight={n <= nota ? "fill" : "regular"}
            aria-hidden="true"
            className={n <= nota ? "text-atencao" : "text-apagado"}
          />
        ))}
      </span>
    );
  }

  const aceso = sobre ?? valor ?? 0;
  const grupo = nome ?? `estrelas${gerado}`;

  return (
    <fieldset className={clsx("min-w-0", className)}>
      <legend className={legendaVisivel ? "mb-1 text-sm font-semibold text-tinta" : "sr-only"}>
        {legenda}
      </legend>
      <div className="flex flex-wrap items-center">
        {/* O hover só acende a prévia; o clique e o teclado passam pelo rádio. */}
        <div className="-ml-2 flex" onMouseLeave={() => setSobre(null)}>
          {NOTAS.map((n) => (
            <label key={n} className="relative cursor-pointer p-2" onMouseEnter={() => setSobre(n)}>
              <input
                type="radio"
                name={grupo}
                value={n}
                checked={valor === n}
                onChange={() => aoMudar(n)}
                className="peer sr-only"
              />
              <Star
                size={icone}
                weight={n <= aceso ? "fill" : "regular"}
                aria-hidden="true"
                className={clsx(
                  "rounded-xs transition-colors duration-rapida",
                  "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marca",
                  n <= aceso ? "text-atencao" : "text-apagado",
                )}
              />
              <span className="sr-only">{nomeDaNota(n)}</span>
            </label>
          ))}
        </div>
        {permiteLimpar && valor !== null ? (
          <button
            type="button"
            onClick={() => aoMudar(null)}
            className="ml-1 min-h-11 rounded-sm px-2 text-sm font-semibold text-apagado hover:text-tinta"
          >
            Tirar nota
          </button>
        ) : null}
      </div>
    </fieldset>
  );
}
