/**
 * Camada **Global** do design system: o cabeçalho.
 *
 * O cabeçalho é **branco** (a superfície), com a marca no selo: é assim no
 * portal do lojista, que é a superfície certa aqui, porque a Dona Maria vende,
 * não compra. O vermelho aparece só onde há ação: a pílula "Conversar com o
 * agente", que é a entrada da conversa e vem cedo na ordem do Tab.
 *
 * - Celular (abaixo de 1024 px): uma linha fina com o selo, o botão Mais e a
 *   engrenagem das Preferências; as seções ficam na barra de baixo.
 * - Computador: o selo, a pílula do Conversar e a engrenagem em cima; as sete
 *   seções numa linha logo abaixo.
 *
 * A engrenagem fica no canto direito em toda largura, e é uma só.
 */

import { CookingPot } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

import { AbaConversar } from "./AbaConversar";
import { MenuMais } from "./MenuMais";
import { Navegacao } from "./Navegacao";
import { Preferencias } from "./Preferencias";

function Selo() {
  return (
    <Link href="/" className="-ml-1 flex min-w-0 items-center gap-2.5 rounded-sm px-1 py-1">
      <span
        aria-hidden="true"
        className="flex size-9 shrink-0 items-center justify-center rounded-sm bg-marca-fundo text-sobre-marca"
      >
        <CookingPot size={22} weight="fill" />
      </span>
      <span className="min-w-0">
        <span className="block truncate font-titulo text-lg leading-tight font-bold text-tinta">
          Sabor da Maria
        </span>
        <span className="hidden truncate text-xs leading-tight text-apagado lg:block">
          consultoria de cardápio e preço
        </span>
      </span>
    </Link>
  );
}

export function Cabecalho() {
  return (
    <header className="sticky top-0 z-40 border-b border-borda bg-superficie">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6 lg:h-16">
        <Selo />
        <div className="flex items-center gap-1 lg:gap-2">
          <div className="lg:hidden">
            <MenuMais />
          </div>
          <div className="hidden lg:block">
            <AbaConversar />
          </div>
          <Preferencias className="-mr-1.5" />
        </div>
      </div>
      <div className="mx-auto hidden h-12 max-w-6xl items-center px-4 sm:px-6 lg:flex">
        <Navegacao className="-ml-3.5" />
      </div>
    </header>
  );
}
