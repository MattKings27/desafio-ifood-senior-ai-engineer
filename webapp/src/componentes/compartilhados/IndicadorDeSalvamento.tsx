"use client";

/**
 * O estado do salvamento automático (as notas dela, a nota de uma receita).
 *
 * Anuncia só o que importa: o "Salvo" final e o erro. O "Salvando…" aparece na
 * tela mas não é anunciado a cada tecla, que seria ruído no leitor de tela.
 * As duas regiões vivas ficam no DOM o tempo todo, vazias quando não há nada.
 */

import { CheckCircle, CircleNotch, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

export type EstadoDoSalvamento = "ocioso" | "salvando" | "salvo" | "erro";

export function IndicadorDeSalvamento({
  estado,
  quandoTexto,
  aoTentarDeNovo,
  className,
}: {
  estado: EstadoDoSalvamento;
  /** Da API, já pronto: "hoje, 14:31". */
  quandoTexto?: string | null;
  aoTentarDeNovo?: () => void;
  className?: string;
}) {
  return (
    <div className={clsx("flex min-h-6 flex-wrap items-center gap-x-2 gap-y-1 text-sm", className)}>
      {estado === "salvando" ? (
        <span className="inline-flex items-center gap-1.5 text-apagado">
          <CircleNotch size={16} weight="bold" className="animate-spin" aria-hidden="true" />
          Salvando…
        </span>
      ) : null}
      <span role="status" className="inline-flex items-center gap-1.5 text-apagado">
        {estado === "salvo" ? (
          <>
            <CheckCircle size={16} weight="fill" className="text-sucesso" aria-hidden="true" />
            {quandoTexto ? `Salvo ${quandoTexto}` : "Salvo"}
          </>
        ) : null}
      </span>
      <span role="alert" className="inline-flex items-center gap-1.5 font-medium text-perigo">
        {estado === "erro" ? (
          <>
            <WarningCircle size={16} weight="fill" aria-hidden="true" />
            Não salvou.
          </>
        ) : null}
      </span>
      {estado === "erro" && aoTentarDeNovo ? (
        <button
          type="button"
          onClick={aoTentarDeNovo}
          className="min-h-11 rounded-sm px-2 font-semibold text-marca hover:bg-marca/10"
        >
          Tentar de novo
        </button>
      ) : null}
    </div>
  );
}
