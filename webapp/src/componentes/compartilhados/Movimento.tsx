"use client";

/**
 * Movimento: pouco, e com propósito.
 *
 * Permitido: a folha e o painel entrando e saindo (400 ms), o valor conferido
 * aparecendo no lugar do rascunho (300 ms), cards descobertos chegando
 * (300 ms, sem cascata longa), listas abrindo e fechando (300 ms), avisos.
 * Proibido: contagem animada de dinheiro (mostraria números intermediários que
 * ninguém conferiu), levantar todo cartão no hover, seção entrando ao carregar.
 *
 * `LazyMotion` carrega só o pacote de animações de DOM, e `strict` faz o uso
 * de `motion.div` (o pacote inteiro) quebrar: aqui se usa `m.div`. Quem pediu
 * menos movimento no sistema, ou escolheu "Reduzir" nas Preferências, não vê
 * deslocamento nenhum.
 */

import type { ReactNode } from "react";
import { AnimatePresence, LazyMotion, MotionConfig, domAnimation, m } from "motion/react";

import { MOVIMENTO } from "@/lib/preferencias";
import { usePreferencia } from "@/lib/usePreferencias";

export { AnimatePresence, m };

/** Em segundos, como o motion espera. Os mesmos 150/300/400 ms do DESIGN.md. */
export const DURACAO = { rapida: 0.15, padrao: 0.3, lenta: 0.4 } as const;

/** O `cubic-bezier(0.4, 0, 0.2, 1)` de `--ease-padrao`. */
export const EASE_PADRAO = [0.4, 0, 0.2, 1] as const;

/**
 * `reducedMotion`: "user" segue o aparelho; quando ela escolhe "Reduzir" nas
 * Preferências, fica "always", e o CSS (`data-movimento`) corta o resto.
 */
export function ProvedorDeMovimento({ children }: { children: ReactNode }) {
  const movimento = usePreferencia(MOVIMENTO);
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig
        reducedMotion={movimento === "reduzir" ? "always" : "user"}
        transition={{ duration: DURACAO.padrao, ease: EASE_PADRAO }}
      >
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}

/**
 * Carrega as animações onde a peça é usada. Dentro do ProvedorDeMovimento é
 * redundante (e barato); fora dele (um teste, uma página de erro), sem isto o
 * `m.div` ficaria parado no estado inicial, com opacidade zero.
 */
export function ComMovimento({ children }: { children: ReactNode }) {
  return <LazyMotion features={domAnimation}>{children}</LazyMotion>;
}

/** Um card que acabou de chegar (descoberta, resultado de busca). */
export function Surgir({
  children,
  atraso = 0,
  className,
}: {
  children: ReactNode;
  /** Em segundos. Para uma fila curta, no máximo alguns décimos. */
  atraso?: number;
  className?: string;
}) {
  return (
    <ComMovimento>
      <m.div
        className={className}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DURACAO.padrao, delay: atraso, ease: EASE_PADRAO }}
      >
        {children}
      </m.div>
    </ComMovimento>
  );
}

/**
 * Troca um conteúdo por outro com um cruzamento suave: o rascunho mascarado
 * dando lugar ao valor conferido. Mudou a `chave`, o conteúdo novo entra.
 */
export function Revelar({
  chave,
  children,
  className,
}: {
  chave: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <ComMovimento>
      <AnimatePresence mode="wait" initial={false}>
        <m.span
          key={chave}
          className={className}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: DURACAO.padrao / 2, ease: EASE_PADRAO }}
        >
          {children}
        </m.span>
      </AnimatePresence>
    </ComMovimento>
  );
}
