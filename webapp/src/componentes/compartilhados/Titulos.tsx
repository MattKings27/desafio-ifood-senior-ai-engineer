/**
 * Títulos de página e de seção.
 *
 * O da página é o único `<h1>`. O de seção abre espaço para o "Ver tudo", que
 * leva à lista completa: na tela inicial, toda amostra (os 5 itens parados, as
 * 4 receitas) tem o caminho para o resto.
 *
 * `resumivel`: no modo minimalista, o texto de apoio (a descrição da página, o
 * apoio da seção) some. As telas de lista usam; o detalhe, não, porque é lá
 * que ela vai ver as contas.
 */

import { CaretLeft } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

export function TituloSecao({
  titulo,
  apoio,
  acao,
  verMais,
  nivel = 2,
  id,
  resumivel = false,
  className,
}: {
  titulo: string;
  apoio?: ReactNode;
  /** No modo minimalista, o apoio some. */
  resumivel?: boolean;
  /** Qualquer ação à direita do título (um botão, um chip). */
  acao?: ReactNode;
  /** O link para a lista completa. O nome acessível inclui o título da seção. */
  verMais?: { href: string; rotulo?: string };
  nivel?: 2 | 3;
  id?: string;
  className?: string;
}) {
  const Titulo = `h${nivel}` as const;
  const rotulo = verMais?.rotulo ?? "Ver tudo";
  return (
    // Sem espaço ao lado do título, as ações descem para a linha de baixo, e
    // quebram entre si: nada empurra a página para os lados no celular.
    <div className={clsx("mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0 flex-1 basis-48">
        <Titulo
          id={id}
          className={clsx("font-bold text-tinta", nivel === 2 ? "text-lg" : "text-base")}
        >
          {titulo}
        </Titulo>
        {apoio ? <p className={clsx("mt-0.5 text-sm text-apagado", resumivel && "minimalista:hidden")}>{apoio}</p> : null}
      </div>
      {acao || verMais ? (
        <div className="flex max-w-full flex-wrap items-center gap-2">
          {acao}
          {verMais ? (
            <Link
              href={verMais.href}
              className="inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
            >
              {rotulo}
              <span className="sr-only">: {titulo}</span>
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function CabecalhoDaPagina({
  titulo,
  descricao,
  acoes,
  voltar,
  resumivel = false,
  className,
  children,
}: {
  titulo: ReactNode;
  descricao?: ReactNode;
  /** No modo minimalista, a descrição some. */
  resumivel?: boolean;
  /** Botões da página (ex.: "Adicionar ingrediente"). */
  acoes?: ReactNode;
  /** Volta para a lista, nas páginas de detalhe. */
  voltar?: { href: string; rotulo: string };
  className?: string;
  /** Algo abaixo da descrição (ex.: chips de resumo). */
  children?: ReactNode;
}) {
  return (
    <div className={clsx("mb-6", className)}>
      {voltar ? (
        <Link
          href={voltar.href}
          className="-ml-2 mb-2 inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-sm font-semibold text-apagado hover:text-tinta"
        >
          <CaretLeft size={16} weight="bold" aria-hidden="true" />
          {voltar.rotulo}
        </Link>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-titulo text-2xl font-bold leading-tight text-tinta sm:text-3xl">
            {titulo}
          </h1>
          {descricao ? (
            <p className={clsx("mt-1.5 max-w-prose text-base text-apagado", resumivel && "minimalista:hidden")}>{descricao}</p>
          ) : null}
          {children}
        </div>
        {acoes ? <div className="flex flex-wrap gap-2 sm:shrink-0">{acoes}</div> : null}
      </div>
    </div>
  );
}
