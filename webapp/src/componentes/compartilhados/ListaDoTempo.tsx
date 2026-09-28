/**
 * Uma linha do tempo: o histórico de um item, as decisões do cardápio, o que o
 * agente e a senhora fizeram.
 *
 * As datas vêm prontas da API (`quando_texto`: "hoje, 10:02"): a tela não
 * formata data, e não há diferença de fuso entre o servidor e o navegador.
 */

import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

import type { TomDoChip } from "./Chip";

export type ItemDoTempo = {
  id: string;
  texto: ReactNode;
  quandoTexto: string;
  /** Ícone do tipo de evento, dentro do marcador. */
  icone?: ReactNode;
  tom?: TomDoChip;
  link?: { href: string; rotulo: string };
  /** Uma ação do próprio evento (ex.: "Desfazer"). */
  acao?: ReactNode;
  detalhe?: ReactNode;
};

export type GrupoDoTempo = { id: string; titulo: string; itens: readonly ItemDoTempo[] };

const COR_DO_MARCADOR: Record<TomDoChip, string> = {
  neutro: "bg-secao text-apagado",
  marca: "bg-marca/10 text-marca",
  sucesso: "bg-sucesso/10 text-sucesso",
  atencao: "bg-atencao/10 text-atencao",
  perigo: "bg-perigo/10 text-perigo",
  info: "bg-info/10 text-info",
};

function Itens({ itens }: { itens: readonly ItemDoTempo[] }) {
  return (
    <ol className="relative">
      {itens.map((item, indice) => (
        <li key={item.id} className="relative flex gap-3 pb-5 last:pb-0">
          {indice < itens.length - 1 ? (
            <span aria-hidden="true" className="absolute top-9 bottom-1 left-[17px] w-px bg-borda" />
          ) : null}
          <span
            aria-hidden="true"
            className={clsx(
              "relative flex size-9 shrink-0 items-center justify-center rounded-full",
              COR_DO_MARCADOR[item.tom ?? "neutro"],
            )}
          >
            {item.icone ?? <span className="size-2 rounded-full bg-current" />}
          </span>
          <div className="min-w-0 flex-1 pt-1.5">
            <div className="text-base text-texto">{item.texto}</div>
            {item.detalhe ? <div className="mt-1 text-sm text-apagado">{item.detalhe}</div> : null}
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="text-apagado">{item.quandoTexto}</span>
              {item.link ? (
                <Link href={item.link.href} className="font-semibold text-marca hover:underline">
                  {item.link.rotulo}
                </Link>
              ) : null}
              {item.acao}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ListaDoTempo({
  itens,
  grupos,
  vazio,
  className,
}: {
  itens?: readonly ItemDoTempo[];
  /** Agrupado por dia (ou por prato): cada grupo com o seu título. */
  grupos?: readonly GrupoDoTempo[];
  vazio?: ReactNode;
  className?: string;
}) {
  const semNada = (grupos ?? []).every((grupo) => grupo.itens.length === 0) && (itens ?? []).length === 0;
  if (semNada) return vazio ? <>{vazio}</> : null;

  return (
    <div className={clsx("space-y-6", className)}>
      {itens && itens.length > 0 ? <Itens itens={itens} /> : null}
      {grupos
        ?.filter((grupo) => grupo.itens.length > 0)
        .map((grupo) => (
          <section key={grupo.id} aria-labelledby={`grupo-${grupo.id}`}>
            <h3 id={`grupo-${grupo.id}`} className="mb-3 text-sm font-bold text-tinta">
              {grupo.titulo}
            </h3>
            <Itens itens={grupo.itens} />
          </section>
        ))}
    </div>
  );
}
