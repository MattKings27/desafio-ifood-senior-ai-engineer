/**
 * As seções do produto, num lugar só: a navegação do computador, a barra de
 * baixo do celular e a folha "Mais" leem esta lista.
 *
 * No celular, a barra de baixo tem Início · Despensa · Conversar · Receitas ·
 * Cardápio; o resto vai para "Mais". No computador, todas ficam no cabeçalho.
 */

import type { Icon } from "@phosphor-icons/react";
import {
  Basket,
  BookOpenText,
  ClockCounterClockwise,
  CookingPot,
  House,
  ListChecks,
  Tag,
} from "@phosphor-icons/react/dist/ssr";

export type Destino = {
  href: string;
  rotulo: string;
  Icone: Icon;
  /** Aparece na barra de baixo do celular. */
  naBarra: boolean;
  /** No celular, fica na folha "Mais", com esta explicação. */
  descricao?: string;
};

export const DESTINOS: readonly Destino[] = [
  { href: "/", rotulo: "Início", Icone: House, naBarra: true },
  { href: "/despensa", rotulo: "Despensa", Icone: Basket, naBarra: true },
  { href: "/receitas", rotulo: "Receitas", Icone: BookOpenText, naBarra: true },
  {
    href: "/cozinha",
    rotulo: "Cozinha",
    Icone: CookingPot,
    naBarra: false,
    descricao: "O que a senhora tem e sabe fazer",
  },
  {
    href: "/precificar",
    rotulo: "Pôr preço",
    Icone: Tag,
    naBarra: false,
    descricao: "Confira se dá pra fazer e ponha o preço",
  },
  { href: "/cardapio", rotulo: "Cardápio", Icone: ListChecks, naBarra: true },
  {
    href: "/trilha",
    rotulo: "Histórico",
    Icone: ClockCounterClockwise,
    naBarra: false,
    descricao: "Tudo o que foi feito, e por quem",
  },
];

/** A seção está aberta? A raiz só na própria raiz; as outras, também nas sub-rotas. */
export function estaAtivo(href: string, caminho: string): boolean {
  if (href === "/") return caminho === "/";
  return caminho === href || caminho.startsWith(`${href}/`);
}
