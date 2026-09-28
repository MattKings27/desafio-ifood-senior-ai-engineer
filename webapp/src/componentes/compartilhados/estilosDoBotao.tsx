/**
 * As classes do botão, num módulo sem diretiva: servem ao Botao (cliente), ao
 * BotaoLink (servidor ou cliente) e a quem precisar pintar um link como botão.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

export type VarianteBotao = "primario" | "secundario" | "terciario" | "texto" | "perigo";
export type TamanhoBotao = "sm" | "md" | "lg";

export const BASE_DO_BOTAO =
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-sm font-semibold select-none " +
  "whitespace-nowrap transition-[background-color,border-color,color,transform] duration-rapida ease-padrao " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-marca " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed";

export const VARIANTES_DO_BOTAO: Record<VarianteBotao, string> = {
  primario: "bg-marca-fundo text-sobre-marca hover:bg-marca-fundo-escura active:scale-[0.98]",
  secundario: "border border-marca bg-superficie text-marca hover:bg-marca/10",
  terciario: "border border-borda-campo/60 bg-superficie text-tinta hover:bg-secao",
  texto: "bg-transparent text-marca hover:bg-marca/10",
  perigo: "bg-perigo text-superficie hover:opacity-90 active:scale-[0.98]",
};

const TAMANHOS: Record<TamanhoBotao, string> = {
  sm: "h-11 px-3 text-sm",
  md: "h-12 px-4 text-base",
  lg: "h-14 px-6 text-base",
};

export type Aparencia = {
  variante?: VarianteBotao;
  tamanho?: TamanhoBotao;
  /** Ocupa a largura toda (ex.: a ação principal de uma folha no celular). */
  larguraTotal?: boolean;
  /** Ícone antes do texto. Decorativo: o texto é o nome do botão. */
  icone?: ReactNode;
  /** Ícone depois do texto. */
  iconeDepois?: ReactNode;
};

export function classesDoBotao({
  variante = "primario",
  tamanho = "md",
  larguraTotal = false,
}: Aparencia = {}): string {
  return clsx(BASE_DO_BOTAO, VARIANTES_DO_BOTAO[variante], TAMANHOS[tamanho], larguraTotal && "w-full");
}

/** Ícone antes, texto, ícone depois: o miolo de todo botão. */
export function Conteudo({
  icone,
  iconeDepois,
  children,
}: {
  icone?: ReactNode;
  iconeDepois?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <>
      {icone ? (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {icone}
        </span>
      ) : null}
      {children}
      {iconeDepois ? (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {iconeDepois}
        </span>
      ) : null}
    </>
  );
}

