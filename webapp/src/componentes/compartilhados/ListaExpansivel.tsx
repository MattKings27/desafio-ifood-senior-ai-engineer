"use client";

/**
 * Lista que mostra os primeiros e guarda o resto atrás de "Ver mais".
 *
 * Toda amostra tem o caminho para o todo: a tela inicial mostra os 5 itens em
 * que mais dinheiro está parado, e a seta abre os 37. O botão diz quantos
 * faltam, e `aria-expanded`/`aria-controls` contam ao leitor de tela o que ele
 * abre. Os itens revelados entram com um fade curto (300 ms).
 */

import { CaretDown } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useId, useState } from "react";

import { Surgir } from "./Movimento";

export function ListaExpansivel<T>({
  itens,
  visiveis = 5,
  renderizar,
  chave,
  como = "ul",
  className,
  classeDoItem,
  rotuloVerMais = "Ver mais",
  rotuloVerMenos = "Ver menos",
  descricaoDoResto = "itens",
  vazio,
  id,
}: {
  itens: readonly T[];
  /** Quantos aparecem antes de abrir. */
  visiveis?: number;
  renderizar: (item: T, indice: number) => ReactNode;
  chave: (item: T, indice: number) => string;
  como?: "ul" | "ol";
  className?: string;
  classeDoItem?: string;
  rotuloVerMais?: string;
  rotuloVerMenos?: string;
  /** Como chamar o que está escondido, para o leitor de tela ("ingredientes"). */
  descricaoDoResto?: string;
  /** O que mostrar quando não há itens. */
  vazio?: ReactNode;
  id?: string;
}) {
  const gerado = useId();
  const idDaLista = id ?? `lista${gerado}`;
  const [aberta, setAberta] = useState(false);

  if (itens.length === 0) return vazio ? <>{vazio}</> : null;

  const escondidos = Math.max(0, itens.length - visiveis);
  const mostrados = aberta ? itens : itens.slice(0, visiveis);
  const Lista = como;

  return (
    <div>
      <Lista id={idDaLista} className={className}>
        {mostrados.map((item, indice) => (
          <li key={chave(item, indice)} className={classeDoItem}>
            {indice >= visiveis ? <Surgir>{renderizar(item, indice)}</Surgir> : renderizar(item, indice)}
          </li>
        ))}
      </Lista>
      {escondidos > 0 ? (
        <button
          type="button"
          aria-expanded={aberta}
          aria-controls={idDaLista}
          onClick={() => setAberta((antes) => !antes)}
          className={clsx(
            "mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 -ml-2",
            "text-sm font-semibold text-marca transition-colors duration-rapida hover:bg-marca/10",
          )}
        >
          {aberta ? (
            rotuloVerMenos
          ) : (
            <>
              {rotuloVerMais}{" "}
              <span className="numero rounded-full bg-marca/10 px-1.5 text-xs text-marca-escura">
                {escondidos}
              </span>{" "}
              <span className="sr-only">{descricaoDoResto}</span>
            </>
          )}
          <CaretDown
            size={16}
            weight="bold"
            aria-hidden="true"
            className={clsx("transition-transform duration-padrao ease-padrao", aberta && "rotate-180")}
          />
        </button>
      ) : null}
    </div>
  );
}
