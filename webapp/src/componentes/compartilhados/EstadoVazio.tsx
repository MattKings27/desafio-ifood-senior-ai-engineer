/**
 * O vazio explicado: o que não tem, por quê, e o que fazer.
 *
 * Uma lista vazia sem texto parece erro. Com o título dizendo o que falta e uma
 * ação para resolver ("Trazer uma receita"), vira o próximo passo dela.
 */

import { Tray } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

export function EstadoVazio({
  titulo,
  descricao,
  icone,
  acao,
  compacto = false,
  nivelTitulo,
  className,
}: {
  titulo: string;
  descricao?: ReactNode;
  /** Ícone decorativo. Sem ele, uma bandeja vazia. */
  icone?: ReactNode;
  /** Um botão ou link que resolve o vazio. */
  acao?: ReactNode;
  compacto?: boolean;
  /** Numa página que é só o vazio (ex.: "Não encontrei"), o título é o cabeçalho dela. */
  nivelTitulo?: 1 | 2 | 3;
  className?: string;
}) {
  const Titulo = nivelTitulo ? (`h${nivelTitulo}` as const) : "p";
  return (
    <div
      className={clsx(
        "flex flex-col items-center rounded-lg border border-dashed border-borda-campo/40 text-center",
        compacto ? "gap-2 p-5" : "gap-3 p-8",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={clsx(
          "flex items-center justify-center rounded-full bg-secao text-apagado",
          compacto ? "size-10" : "size-12",
        )}
      >
        {icone ?? <Tray size={compacto ? 20 : 24} weight="duotone" />}
      </span>
      <div className="max-w-prose">
        <Titulo className={clsx("font-semibold text-tinta", nivelTitulo === 1 && "font-titulo text-xl font-bold")}>
          {titulo}
        </Titulo>
        {descricao ? <p className="mt-1 text-sm text-apagado">{descricao}</p> : null}
      </div>
      {acao ? <div className="mt-1">{acao}</div> : null}
    </div>
  );
}

/** O nome de antes. Mesmas propriedades de `EstadoVazio`. */
export const Vazio = EstadoVazio;
