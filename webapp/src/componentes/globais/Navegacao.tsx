"use client";

/**
 * A navegação do computador (a partir de 1024 px), no cabeçalho.
 *
 * A seção atual fica em tinta, sobre um fundo leve, com `aria-current`. Não é
 * o vermelho da marca: vermelho aqui é para agir (o Conversar, o botão
 * principal), não para dizer onde ela está. Nada rola de lado: as sete seções
 * cabem numa linha a partir de 1024 px.
 */

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { DESTINOS, estaAtivo } from "./destinos";

export function Navegacao({ className }: { className?: string }) {
  const caminho = usePathname();
  return (
    <nav aria-label="Seções" className={className}>
      <ul className="flex items-center gap-1">
        {DESTINOS.map(({ href, rotulo, Icone }) => {
          const ativo = estaAtivo(href, caminho);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={ativo ? "page" : undefined}
                className={clsx(
                  "inline-flex h-10 items-center gap-2 rounded-full px-3.5 text-sm font-semibold whitespace-nowrap",
                  "transition-colors duration-rapida",
                  ativo ? "bg-tinta/8 text-tinta" : "text-apagado hover:bg-tinta/5 hover:text-tinta",
                )}
              >
                <Icone size={18} weight={ativo ? "fill" : "regular"} aria-hidden="true" />
                {rotulo}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
