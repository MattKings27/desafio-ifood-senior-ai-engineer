"use client";

/**
 * O relógio da datilografia (`lib/conversa/datilografia`): quantos caracteres
 * do texto já apareceram, avançando a cada quadro da tela.
 *
 * - `chave` liga a resposta em andamento à resposta guardada que a substitui
 *   quando o turno termina: a guardada continua de onde a outra parou.
 * - `aoVivo`: o texto está chegando agora e começa do zero. Sem isso (uma
 *   resposta do histórico), o texto aparece inteiro, a menos que a `chave`
 *   diga que ele ainda estava sendo escrito.
 * - Menos movimento (no aparelho ou nas Preferências): o texto aparece do
 *   jeito que chega, sem relógio nenhum.
 */

import { useEffect, useRef, useState } from "react";

import {
  caracteresNoQuadro,
  configuracaoDaDatilografia,
  esquecerProgresso,
  gravarProgresso,
  lerProgresso,
  pontoQueCasa,
  reposicionar,
} from "@/lib/conversa/datilografia";
import { MOVIMENTO } from "@/lib/preferencias";
import { usePreferencia } from "@/lib/usePreferencias";

import { useMidia } from "./useMidia";

export const MENOS_MOVIMENTO = "(prefers-reduced-motion: reduce)";

export type Datilografia = {
  /** Quantos caracteres do texto já apareceram. */
  revelados: number;
  /** Ainda falta texto para aparecer. */
  escrevendo: boolean;
};

type Estado = { texto: string; revelados: number; resto: number };

function inicial(texto: string, chave: string | null, aoVivo: boolean): Estado {
  const guardado = chave ? lerProgresso(chave) : undefined;
  if (!guardado) return { texto, revelados: aoVivo ? 0 : texto.length, resto: 0 };
  if (!aoVivo) return { texto, revelados: reposicionar(guardado.texto, guardado.revelados, texto), resto: 0 };
  // Ao vivo, só continua o que é o mesmo texto: um rascunho que recomeçou
  // depois de uma ferramenta é outro texto, e começa do zero.
  const ponto = pontoQueCasa(guardado.texto.slice(0, guardado.revelados), texto);
  return { texto, revelados: Math.min(ponto ?? 0, texto.length), resto: 0 };
}

export function useDatilografia(texto: string, { chave = null, aoVivo = false }: { chave?: string | null; aoVivo?: boolean } = {}): Datilografia {
  const menosMovimentoNoAparelho = useMidia(MENOS_MOVIMENTO);
  const menosMovimentoNaTela = usePreferencia(MOVIMENTO) === "reduzir";
  const reduzir = menosMovimentoNoAparelho || menosMovimentoNaTela || configuracaoDaDatilografia.instantanea;
  const estado = useRef<Estado | null>(null);
  if (estado.current === null) estado.current = inicial(texto, chave, aoVivo);
  const atual = estado.current;
  // O texto mudou: o mesmo crescendo mantém a posição; outro (o conferido no
  // lugar do rascunho) recebe a posição equivalente. Idempotente, então pode
  // rodar duas vezes no modo estrito.
  if (atual.texto !== texto) {
    atual.revelados = reposicionar(atual.texto, atual.revelados, texto);
    atual.texto = texto;
  }
  if (reduzir) atual.revelados = texto.length;
  const [, redesenhar] = useState(0);

  useEffect(() => {
    if (chave) {
      if (atual.revelados >= atual.texto.length && !aoVivo) esquecerProgresso(chave);
      else gravarProgresso(chave, { texto: atual.texto, revelados: atual.revelados });
    }
    if (reduzir || atual.revelados >= texto.length) return;
    let quadro = 0;
    let antes: number | null = null;
    const passo = (agora: number) => {
      const dt = antes === null ? 16 : agora - antes;
      antes = agora;
      const avanco = caracteresNoQuadro(atual.texto.length - atual.revelados, dt) + atual.resto;
      const inteiros = Math.floor(avanco);
      atual.resto = avanco - inteiros;
      if (inteiros > 0) {
        atual.revelados = Math.min(atual.texto.length, atual.revelados + inteiros);
        if (chave) gravarProgresso(chave, { texto: atual.texto, revelados: atual.revelados });
        redesenhar((n) => n + 1);
      }
      if (atual.revelados < atual.texto.length) quadro = requestAnimationFrame(passo);
      else if (chave && !aoVivo) esquecerProgresso(chave);
    };
    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, [texto, reduzir, chave, aoVivo, atual]);

  return { revelados: atual.revelados, escrevendo: atual.revelados < texto.length };
}
