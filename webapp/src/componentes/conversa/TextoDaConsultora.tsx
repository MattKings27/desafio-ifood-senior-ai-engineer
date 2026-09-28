"use client";

/**
 * O texto do agente: o rascunho mascarado enquanto ele escreve, e o texto
 * conferido quando o turno termina.
 *
 * - **Rascunho** (o turno em andamento): passa pela máscara do navegador
 *   (a segunda porta, depois da do backend), e cada valor vira o brilho
 *   "R$ ···", com a legenda de que os valores aparecem quando a conta estiver
 *   conferida.
 * - **Parado** (o turno parou ou falhou): o mesmo rascunho, mascarado para
 *   sempre, sem brilho: aqueles valores nunca foram conferidos.
 * - **Final**: o texto que passou pelo guard-rail. Os valores em reais ganham
 *   algarismos tabulares, e "[valor retirado]" vira um chip.
 *
 * Ao vivo, o texto aparece letra a letra (`useDatilografia`), com um cursor
 * no fim enquanto é escrito. Quando o conferido chega, ele entra na mesma peça,
 * no mesmo ponto do rascunho: só os valores escondidos mudam.
 */

import { Clock, EyeSlash } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useMemo } from "react";

import { trechoVisivel } from "@/lib/conversa/datilografia";
import { analisarMarkdown, renderizarBlocos } from "@/lib/conversa/markdown";
import type { PecasDoMarkdown } from "@/lib/conversa/markdown";
import { mascararRascunho, temValorEmConferencia } from "@/lib/conversa/mascara";

import { useDatilografia } from "./useDatilografia";

export type ModoDoTexto = "final" | "rascunho" | "parado";

export const LEGENDA_DOS_VALORES = "Os valores aparecem quando eu terminar de conferir a conta.";
export const LEGENDA_DOS_VALORES_PARADOS = "Parei antes de conferir estes valores, então eles ficam escondidos.";

/** Um valor em reais que ainda não foi conferido: o brilho "R$ ···". */
export function ValorEmConferencia({ parado = false }: { parado?: boolean }) {
  return (
    <span
      data-valor-em-conferencia=""
      className={clsx(
        "numero mx-0.5 inline-flex items-baseline rounded-md px-1.5 font-semibold whitespace-nowrap",
        parado ? "bg-secao text-apagado" : "esqueleto animate-brilho text-texto",
      )}
    >
      <span aria-hidden="true">R$ ···</span>
      <span className="sr-only">{parado ? "valor escondido" : "valor em conferência"}</span>
    </span>
  );
}

/** O chip no lugar de um valor que o backend tirou do texto final. */
export function ValorRetirado() {
  return (
    <span className="mx-0.5 inline-flex items-baseline rounded-full border border-atencao/25 bg-atencao/10 px-2 text-sm font-semibold whitespace-nowrap text-atencao">
      valor retirado
    </span>
  );
}

function LegendaDosValores({ parado }: { parado: boolean }) {
  return (
    <p className="flex items-start gap-2 text-sm leading-6 text-apagado">
      {parado ? (
        <EyeSlash size={18} weight="bold" aria-hidden="true" className="mt-0.5 shrink-0" />
      ) : (
        <Clock size={18} weight="bold" aria-hidden="true" className="mt-0.5 shrink-0" />
      )}
      <span>{parado ? LEGENDA_DOS_VALORES_PARADOS : LEGENDA_DOS_VALORES}</span>
    </p>
  );
}

function pecasDo(modo: ModoDoTexto, conferindoAgora: boolean): PecasDoMarkdown {
  return {
    valor: (chave) => <ValorEmConferencia key={chave} parado={modo === "parado"} />,
    retirado: (chave) => <ValorRetirado key={chave} />,
    dinheiro: (texto, chave) => (
      <span
        key={chave}
        className={clsx("numero font-semibold whitespace-nowrap text-tinta", conferindoAgora && "animate-valor-conferido")}
      >
        {texto}
      </span>
    ),
  };
}

export function TextoDaConsultora({
  texto,
  modo,
  className,
  chave = null,
  aoVivo = false,
  chegando = false,
}: {
  texto: string;
  modo: ModoDoTexto;
  className?: string;
  /** Liga a resposta em andamento à guardada (`useDatilografia`). */
  chave?: string | null;
  /** O texto está chegando agora: aparece letra a letra. */
  aoVivo?: boolean;
  /** Ainda pode vir mais texto: o cursor fica no fim, esperando. */
  chegando?: boolean;
}) {
  const visivel = modo === "final" ? texto : mascararRascunho(texto);
  const { revelados, escrevendo } = useDatilografia(visivel, { chave, aoVivo });
  const trecho = escrevendo ? trechoVisivel(visivel, revelados) : visivel;
  const blocos = useMemo(
    () => analisarMarkdown(trecho, { destacarDinheiro: modo === "final" }),
    [trecho, modo],
  );
  if (blocos.length === 0) return null;
  const emConferencia = modo !== "final" && temValorEmConferencia(trecho);
  const cursor = escrevendo || (chegando && modo === "rascunho");
  return (
    <div className={clsx("space-y-3 text-base leading-7 break-words text-texto", className)}>
      <div className={clsx("space-y-3", cursor && "cursor-de-escrita")} data-escrevendo={cursor ? "" : undefined}>
        {renderizarBlocos(blocos, pecasDo(modo, aoVivo))}
      </div>
      {emConferencia ? <LegendaDosValores parado={modo === "parado"} /> : null}
    </div>
  );
}
