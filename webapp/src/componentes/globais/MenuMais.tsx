"use client";

/**
 * A folha "Mais" do celular: as seções que não cabem na barra de baixo
 * (Cozinha, Pôr preço, Histórico). A aparência e o resto das escolhas dela
 * ficam nas Preferências, na engrenagem ao lado.
 *
 * Fecha sozinha quando ela escolhe uma seção, e o foco volta ao botão Mais.
 */

import { CaretRight, DotsThreeOutline } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Folha } from "@/componentes/compartilhados/Folha";

import { DESTINOS, estaAtivo } from "./destinos";

export function MenuMais({ className }: { className?: string }) {
  const [aberto, setAberto] = useState(false);
  const caminho = usePathname();
  const extras = DESTINOS.filter((destino) => !destino.naBarra);
  const algumAtivo = extras.some(({ href }) => estaAtivo(href, caminho));

  // Mudou de página (pelo voltar do navegador, por exemplo): a folha fecha.
  useEffect(() => {
    setAberto(false);
  }, [caminho]);

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        onClick={() => setAberto(true)}
        className={clsx(
          "inline-flex h-11 items-center gap-1.5 rounded-full px-3 text-sm font-semibold transition-colors duration-rapida",
          algumAtivo ? "bg-tinta/8 text-tinta" : "text-texto hover:bg-tinta/5",
          className,
        )}
      >
        <DotsThreeOutline size={20} weight="fill" aria-hidden="true" />
        Mais
      </button>
      <Folha aberto={aberto} aoFechar={() => setAberto(false)} titulo="Mais" lado="baixo">
        <nav aria-label="Mais seções">
          <ul className="-mx-2 space-y-1">
            {extras.map(({ href, rotulo, descricao, Icone }) => {
              const ativo = estaAtivo(href, caminho);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={ativo ? "page" : undefined}
                    onClick={() => setAberto(false)}
                    className={clsx(
                      "flex min-h-16 items-center gap-3 rounded-lg px-2 py-2 transition-colors duration-rapida",
                      ativo ? "bg-tinta/8" : "hover:bg-tinta/5",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className="flex size-11 shrink-0 items-center justify-center rounded-full bg-secao text-tinta"
                    >
                      <Icone size={22} weight={ativo ? "fill" : "regular"} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-base font-semibold text-tinta">{rotulo}</span>
                      {descricao ? <span className="block text-sm text-apagado">{descricao}</span> : null}
                    </span>
                    <CaretRight size={18} aria-hidden="true" className="shrink-0 text-apagado" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </Folha>
    </>
  );
}
