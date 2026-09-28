/**
 * Link com cara de botão ("Ver receita", "Adicionar ingrediente" que abre uma
 * página). Sem diretiva: serve tanto a server components quanto a clientes.
 */

import Link from "next/link";
import type { ComponentProps, ComponentPropsWithoutRef, ReactNode } from "react";

import { unirClasses } from "./classes";
import type { Aparencia } from "./estilosDoBotao";
import { Conteudo, classesDoBotao } from "./estilosDoBotao";

export type PropsDoBotaoLink = Omit<ComponentProps<typeof Link>, "children"> &
  Aparencia & {
    children: ReactNode;
    /** Endereço de fora: abre em outra aba e avisa isso a quem usa leitor de tela. */
    externo?: boolean;
  };

export function BotaoLink({
  variante,
  tamanho,
  larguraTotal,
  icone,
  iconeDepois,
  className,
  children,
  externo = false,
  href,
  ...resto
}: PropsDoBotaoLink) {
  const classes = unirClasses(classesDoBotao({ variante, tamanho, larguraTotal }), className);
  if (externo) {
    return (
      <a
        href={String(href)}
        target="_blank"
        rel="noopener noreferrer"
        className={classes}
        {...(resto as ComponentPropsWithoutRef<"a">)}
      >
        <Conteudo icone={icone} iconeDepois={iconeDepois}>
          {children}{" "}
          <span className="sr-only">(abre em outra aba)</span>
        </Conteudo>
      </a>
    );
  }
  return (
    <Link href={href} className={classes} {...resto}>
      <Conteudo icone={icone} iconeDepois={iconeDepois}>
        {children}
      </Conteudo>
    </Link>
  );
}

