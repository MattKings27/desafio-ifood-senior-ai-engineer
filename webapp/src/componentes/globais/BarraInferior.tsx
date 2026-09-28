"use client";

/**
 * A barra de baixo do celular (abaixo de 1024 px): Início · Despensa ·
 * CONVERSAR · Receitas · Cardápio.
 *
 * O Conversar fica no meio, elevado, na cor da marca: é a entrada do
 * agente, e tem que ser a coisa mais fácil de achar na tela. O toque abre
 * a conversa numa folha por cima da página, com o contexto dela ("Vendo:
 * Despensa"); na página da conversa, leva à caixa de texto. Os rótulos ficam
 * sempre visíveis (ícone sozinho é adivinhação), e a barra respeita a área
 * segura do aparelho.
 */

import { ChatCircleDots } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useConversa } from "@/componentes/conversa";
import { ATRIBUTO_DA_ENTRADA, useEntradaDaConversa } from "@/componentes/conversa/useEntradaDaConversa";

import type { Destino } from "./destinos";
import { DESTINOS, estaAtivo } from "./destinos";

function Item({ destino, caminho }: { destino: Destino; caminho: string }) {
  const ativo = estaAtivo(destino.href, caminho);
  const { Icone } = destino;
  return (
    <li className="min-w-0">
      <Link
        href={destino.href}
        aria-current={ativo ? "page" : undefined}
        className={clsx(
          "flex h-full min-h-14 flex-col items-center justify-center gap-0.5 px-1 pt-1.5 pb-1",
          "text-xs font-semibold transition-colors duration-rapida",
          ativo ? "text-tinta" : "text-apagado hover:text-tinta",
        )}
      >
        <Icone size={24} weight={ativo ? "fill" : "regular"} aria-hidden="true" />
        <span className="max-w-full truncate">{destino.rotulo}</span>
      </Link>
    </li>
  );
}

export function BarraInferior() {
  const caminho = usePathname();
  const { respondendo } = useConversa();
  const aoClicarNoConversar = useEntradaDaConversa();
  const naBarra = DESTINOS.filter((destino) => destino.naBarra);
  const antes = naBarra.slice(0, 2);
  const depois = naBarra.slice(2);
  const conversando = estaAtivo("/conversa", caminho);

  return (
    <nav
      aria-label="Seções principais"
      className={clsx(
        "fixed inset-x-0 bottom-0 z-40 border-t border-borda bg-superficie",
        "pb-[env(safe-area-inset-bottom)] lg:hidden",
      )}
    >
      <ul className="mx-auto grid h-[var(--altura-barra-inferior)] max-w-lg grid-cols-5 items-stretch">
        {antes.map((destino) => (
          <Item key={destino.href} destino={destino} caminho={caminho} />
        ))}
        <li className="min-w-0">
          <Link
            href="/conversa"
            aria-current={conversando ? "page" : undefined}
            onClick={aoClicarNoConversar}
            {...{ [ATRIBUTO_DA_ENTRADA]: "" }}
            className="group flex h-full flex-col items-center justify-end gap-0.5 pb-1 text-xs font-bold text-marca"
          >
            <span
              aria-hidden="true"
              className={clsx(
                "relative -mt-6 mb-0.5 flex size-14 items-center justify-center rounded-full",
                "bg-marca-fundo text-sobre-marca shadow-flutuante ring-4 ring-superficie",
                "transition-transform duration-rapida group-active:scale-95",
              )}
            >
              <ChatCircleDots size={28} weight="fill" />
              {respondendo ? (
                <span className="absolute top-2 right-2 size-2.5 rounded-full bg-sobre-marca ring-2 ring-marca-fundo" />
              ) : null}
            </span>
            Conversar
            {respondendo ? <span className="sr-only">: o agente está respondendo</span> : null}
          </Link>
        </li>
        {depois.map((destino) => (
          <Item key={destino.href} destino={destino} caminho={caminho} />
        ))}
      </ul>
    </nav>
  );
}
