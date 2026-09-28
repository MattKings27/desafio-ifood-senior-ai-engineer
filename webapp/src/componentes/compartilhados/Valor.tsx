/**
 * Dinheiro na tela, e a conta que o produziu.
 *
 * `Valor` renderiza **sempre** `dinheiro.texto`, que veio formatado da API.
 * O campo `valor` existe para ordenar e comparar, nunca para exibição:
 * formatar moeda em dois lugares é exatamente como pt-BR e en-US acabam na
 * mesma tela. Sem texto, aparece "—": um valor ausente nunca vira R$ 0,00.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

import type { Dinheiro } from "@/lib/api/base";

export type TamanhoDoValor = "sm" | "md" | "lg" | "xl" | "destaque";
export type TomDoValor = "normal" | "positivo" | "negativo" | "marca" | "apagado";

const TAMANHOS: Record<TamanhoDoValor, string> = {
  sm: "text-sm font-semibold",
  md: "text-base font-semibold",
  lg: "text-xl font-bold",
  // Números grandes e isolados vão em Sora, como título.
  xl: "font-titulo text-3xl font-bold tracking-tight",
  destaque: "font-titulo text-4xl font-bold tracking-tight",
};

const TONS: Record<TomDoValor, string> = {
  normal: "text-tinta",
  positivo: "text-sucesso",
  negativo: "text-perigo",
  marca: "text-marca",
  apagado: "text-apagado",
};

export function Valor({
  dinheiro,
  tamanho = "md",
  tom,
  className,
  semValor = "—",
}: {
  dinheiro?: Pick<Dinheiro, "texto"> & Partial<Pick<Dinheiro, "valor">> | null;
  tamanho?: TamanhoDoValor;
  tom?: TomDoValor;
  className?: string;
  /** O que aparece quando o valor ainda não é conhecido. */
  semValor?: string;
}) {
  const texto = dinheiro?.texto?.trim();
  if (!texto) {
    return (
      <span className={clsx("numero", TAMANHOS[tamanho], TONS.apagado, className)}>
        <span aria-hidden="true">{semValor}</span>
        <span className="sr-only">valor ainda desconhecido</span>
      </span>
    );
  }
  // Comparar com zero só escolhe a cor; o número mostrado é o texto da API.
  const negativo = typeof dinheiro?.valor === "number" && dinheiro.valor < 0;
  const escolhido = tom ?? (negativo ? "negativo" : "normal");
  return <span className={clsx("numero", TAMANHOS[tamanho], TONS[escolhido], className)}>{texto}</span>;
}

/**
 * A conta que produziu um número, como uma linha de recibo.
 *
 * Nunca fica atrás de dica ou de clique. Se o número aparece, a conta aparece:
 * é ela que permite à Dona Maria discordar, e discordar é como um erro nosso
 * é descoberto. Em Inter com algarismos tabulares, não em fonte de código.
 */
export function Derivacao({
  children,
  className,
  como = "p",
}: {
  children: ReactNode;
  className?: string;
  como?: "p" | "span" | "div";
}) {
  const Elemento = como;
  return (
    <Elemento className={clsx("numero mt-1 block text-xs leading-relaxed text-apagado", className)}>
      {children}
    </Elemento>
  );
}
