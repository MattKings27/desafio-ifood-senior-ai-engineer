/**
 * Cartão, e cartão clicável inteiro.
 *
 * O cartão clicável usa o "link esticado": o link fica no título (é o nome que
 * o leitor de tela anuncia), e um pseudo-elemento dele cobre o cartão todo.
 * Botões de dentro (ex.: "Perguntar") ficam por cima com `AcimaDoLink`, e
 * continuam clicáveis por conta própria. O anel de foco é desenhado no cartão,
 * não no título, para ficar claro o que o Enter vai abrir.
 *
 * No hover o cartão só firma a borda: nada de levantar todo cartão da tela.
 */

import clsx from "clsx";
import Link from "next/link";
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

import { unirClasses } from "./classes";

export type ElementoDoCard = "section" | "article" | "div" | "li" | "aside";
export type TomDoCard = "padrao" | "creme" | "secao" | "alerta" | "plano";
export type DensidadeDoCard = "normal" | "compacta" | "nenhuma";

const TONS: Record<TomDoCard, string> = {
  padrao: "border border-borda bg-superficie shadow-cartao",
  plano: "border border-borda bg-superficie",
  creme: "border border-transparent bg-creme",
  secao: "border border-transparent bg-secao",
  alerta: "border border-perigo/20 bg-tinta-clara",
};

const DENSIDADES: Record<DensidadeDoCard, string> = {
  normal: "p-4 sm:p-5",
  compacta: "p-3",
  nenhuma: "p-0",
};

type PropsDoCard = Omit<ComponentPropsWithoutRef<"section">, "title"> & {
  como?: ElementoDoCard;
  tom?: TomDoCard;
  densidade?: DensidadeDoCard;
};

export function Card({
  como = "section",
  tom = "padrao",
  densidade = "normal",
  className,
  children,
  ...resto
}: PropsDoCard) {
  const Elemento = como as ElementType;
  return (
    <Elemento
      className={unirClasses(clsx("rounded-lg", TONS[tom], DENSIDADES[densidade]), className)}
      {...resto}
    >
      {children}
    </Elemento>
  );
}

/**
 * O link que cobre o cartão inteiro. Vai dentro do título do cartão; o cartão
 * (ou quem o contém) precisa de `relative`, que o CardLink já põe.
 */
export function LinkEsticado({
  href,
  children,
  className,
  externo = false,
}: {
  href: string;
  children: ReactNode;
  className?: string;
  externo?: boolean;
}) {
  const classes = clsx(
    "after:absolute after:inset-0 after:rounded-[inherit] after:content-['']",
    "hover:underline hover:underline-offset-4",
    className,
  );
  if (externo) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" data-link-esticado="" className={classes}>
        {children}{" "}
        <span className="sr-only">(abre em outra aba)</span>
      </a>
    );
  }
  return (
    <Link href={href} data-link-esticado="" className={classes}>
      {children}
    </Link>
  );
}

/** O que precisa continuar clicável por cima do link esticado. */
export function AcimaDoLink({
  children,
  className,
  como = "div",
}: {
  children: ReactNode;
  className?: string;
  como?: "div" | "span" | "p";
}) {
  const Elemento = como;
  return <Elemento className={clsx("relative z-10", className)}>{children}</Elemento>;
}

type NivelDoTitulo = 2 | 3 | 4;

export function CardLink({
  href,
  titulo,
  nivelTitulo = 3,
  classeDoTitulo,
  midia,
  externo,
  como = "article",
  tom,
  densidade,
  className,
  children,
}: {
  href: string;
  /** O nome do cartão, que vira o texto do link. */
  titulo: ReactNode;
  nivelTitulo?: NivelDoTitulo;
  classeDoTitulo?: string;
  /** Foto ou ilustração antes do título (fica dentro da área clicável). */
  midia?: ReactNode;
  externo?: boolean;
  como?: ElementoDoCard;
  tom?: TomDoCard;
  densidade?: DensidadeDoCard;
  className?: string;
  children?: ReactNode;
}) {
  const Titulo = `h${nivelTitulo}` as const;
  return (
    <Card
      como={como}
      tom={tom}
      densidade={densidade}
      data-cartao-link=""
      className={clsx(
        "relative transition-colors duration-rapida hover:border-borda-campo/50",
        className,
      )}
    >
      {midia}
      <Titulo className={clsx("text-base font-bold leading-snug text-tinta", classeDoTitulo)}>
        <LinkEsticado href={href} externo={externo}>
          {titulo}
        </LinkEsticado>
      </Titulo>
      {children}
    </Card>
  );
}
