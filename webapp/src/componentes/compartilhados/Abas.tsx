"use client";

/**
 * Abas. Duas formas, porque são duas coisas diferentes:
 *
 * - `Abas`: troca o painel sem sair da página (o padrão ARIA de abas, com as
 *   setas do teclado e um só ponto de parada do Tab na lista).
 * - `AbasDeNavegacao`: cada aba é um endereço (`/receitas?aba=ranking`), então
 *   são links, com `aria-current` na atual. Recarregar e voltar funcionam.
 *
 * Nenhuma das duas rola de lado no celular: as abas dividem a largura e o
 * texto quebra, se precisar.
 */

import clsx from "clsx";
import Link from "next/link";
import type { KeyboardEvent, ReactNode } from "react";
import { useId, useRef, useState } from "react";

const LISTA = "grid auto-cols-fr grid-flow-col border-b border-borda";

function classeDaAba(ativa: boolean) {
  return clsx(
    "relative flex min-h-11 items-center justify-center gap-1.5 px-3 py-2 text-center text-sm font-semibold",
    "transition-colors duration-rapida focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-marca",
    "after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full",
    ativa ? "text-tinta after:bg-tinta" : "text-apagado hover:text-tinta after:bg-transparent",
  );
}

function Contagem({ valor }: { valor?: number }) {
  if (valor === undefined) return null;
  return (
    <>
      {" "}
      <span className="numero rounded-full bg-secao px-1.5 text-xs font-semibold text-texto">{valor}</span>
    </>
  );
}

export type Aba = { id: string; rotulo: string; contagem?: number; conteudo: ReactNode };

export function Abas({
  rotulo,
  abas,
  ativa,
  aoTrocar,
  inicial,
  className,
}: {
  /** O nome do conjunto de abas, para o leitor de tela. */
  rotulo: string;
  abas: readonly Aba[];
  /** Controlado: a aba atual vem de fora. */
  ativa?: string;
  aoTrocar?: (id: string) => void;
  /** Não controlado: a aba que abre primeiro. */
  inicial?: string;
  className?: string;
}) {
  const base = useId();
  const [interna, setInterna] = useState(inicial ?? abas[0]?.id);
  const atual = ativa ?? interna;
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);

  const escolher = (indice: number) => {
    const aba = abas[indice];
    if (!aba) return;
    setInterna(aba.id);
    aoTrocar?.(aba.id);
    botoes.current[indice]?.focus();
  };

  const aoTeclar = (evento: KeyboardEvent<HTMLButtonElement>) => {
    const indice = abas.findIndex((aba) => aba.id === atual);
    const destino =
      evento.key === "ArrowRight"
        ? (indice + 1) % abas.length
        : evento.key === "ArrowLeft"
          ? (indice - 1 + abas.length) % abas.length
          : evento.key === "Home"
            ? 0
            : evento.key === "End"
              ? abas.length - 1
              : null;
    if (destino === null) return;
    evento.preventDefault();
    escolher(destino);
  };

  return (
    <div className={className}>
      <div role="tablist" aria-label={rotulo} className={LISTA}>
        {abas.map((aba, indice) => {
          const selecionada = aba.id === atual;
          return (
            <button
              key={aba.id}
              ref={(no) => {
                botoes.current[indice] = no;
              }}
              type="button"
              role="tab"
              id={`${base}-aba-${aba.id}`}
              aria-selected={selecionada}
              aria-controls={`${base}-painel-${aba.id}`}
              tabIndex={selecionada ? 0 : -1}
              onClick={() => escolher(indice)}
              onKeyDown={aoTeclar}
              className={classeDaAba(selecionada)}
            >
              {aba.rotulo}
              <Contagem valor={aba.contagem} />
            </button>
          );
        })}
      </div>
      {abas.map((aba) => (
        <div
          key={aba.id}
          role="tabpanel"
          id={`${base}-painel-${aba.id}`}
          aria-labelledby={`${base}-aba-${aba.id}`}
          hidden={aba.id !== atual}
          tabIndex={0}
          className="pt-4 focus-visible:outline-2 focus-visible:outline-marca"
        >
          {aba.id === atual ? aba.conteudo : null}
        </div>
      ))}
    </div>
  );
}

export type AbaDeNavegacao = { href: string; rotulo: string; contagem?: number; ativa: boolean };

export function AbasDeNavegacao({
  rotulo,
  abas,
  className,
}: {
  rotulo: string;
  abas: readonly AbaDeNavegacao[];
  className?: string;
}) {
  return (
    <nav aria-label={rotulo} className={className}>
      <ul className={LISTA}>
        {abas.map((aba) => (
          <li key={aba.href} className="min-w-0">
            <Link
              href={aba.href}
              scroll={false}
              aria-current={aba.ativa ? "page" : undefined}
              className={classeDaAba(aba.ativa)}
            >
              {aba.rotulo}
              <Contagem valor={aba.contagem} />
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
