"use client";

/**
 * A moldura de todo card da conversa: um `<article>` com título, o que o
 * card mostra, e o rodapé com a hora da conta ("conta de hoje, 14:32") e, nos
 * cards com dinheiro do histórico, "Refazer a conta".
 *
 * Os cards vêm do backend, com os dados do motor: nada aqui é mascarado, e
 * nada aqui calcula. Cada card fica numa fronteira de erro própria: um card
 * que quebra vira uma linha dizendo isso, e a conversa continua.
 */

import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ErrorInfo } from "next/error";
import { catchError } from "next/error";
import type { ReactNode } from "react";
import { useId, useState } from "react";

import { pedir } from "@/lib/api/base";
import { CARTOES_COM_DINHEIRO, caminhoDaRota } from "@/lib/conversa/cartoes";
import type { CartaoNaTela } from "@/lib/conversa/estado";

export type PropsDoCartao = {
  cartao: CartaoNaTela;
  /** Card de uma resposta guardada: uma fotografia da conta daquela hora. */
  historico: boolean;
};

export const ROTULO_REFEITA = "conta refeita agora";

type Refazer = { aoRefazer: () => void; refazendo: boolean; erro: string | null };

/**
 * Os dados do card, com "Refazer a conta": busca de novo a rota do card (a
 * mesma que deu os dados) e troca a fotografia pela conta de agora.
 */
export function useDadosDoCartao(cartao: CartaoNaTela, historico: boolean) {
  const [refeitos, setRefeitos] = useState<{ de: unknown; dados: unknown } | null>(null);
  const [refazendo, setRefazendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // O backend mandou o card de novo com dados novos: vale o dele.
  const valeORefeito = refeitos !== null && refeitos.de === cartao.dados;
  const dados = valeORefeito ? refeitos.dados : cartao.dados;

  const caminho = caminhoDaRota(cartao.ref.rota);
  const podeRefazer = historico && CARTOES_COM_DINHEIRO.has(cartao.tipo) && caminho !== null;

  const refazer: Refazer | null = podeRefazer
    ? {
        refazendo,
        erro,
        aoRefazer: () => {
          if (refazendo) return;
          setRefazendo(true);
          setErro(null);
          pedir<unknown>(caminho, { tempoLimiteMs: 30_000 })
            .then((novos) => setRefeitos({ de: cartao.dados, dados: novos }))
            .catch(() => setErro("Não consegui refazer a conta agora. Tente de novo daqui a pouco."))
            .finally(() => setRefazendo(false));
        },
      }
    : null;

  return {
    dados,
    geradoTexto: valeORefeito ? ROTULO_REFEITA : cartao.geradoTexto,
    refazer,
  };
}

export function MolduraDoCartao({
  sobretitulo,
  icone,
  titulo,
  selo,
  midia,
  geradoTexto,
  refazer,
  rodape,
  children,
  className,
}: {
  /** O tipo do card, em palavras ("Custo de uma porção"). */
  sobretitulo: string;
  icone?: ReactNode;
  titulo: ReactNode;
  /** Um chip ao lado do título (o selo de "Dá pra fazer"). */
  selo?: ReactNode;
  /** A foto no topo, sem margem. */
  midia?: ReactNode;
  geradoTexto?: string;
  refazer?: Refazer | null;
  /** Links e botões do pé do card. */
  rodape?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const id = useId();
  const temRodape = Boolean(rodape) || Boolean(geradoTexto) || Boolean(refazer);
  return (
    <article
      aria-labelledby={`${id}-titulo`}
      className={clsx(
        "@container overflow-hidden rounded-xl border border-borda bg-superficie text-texto shadow-cartao",
        className,
      )}
    >
      {midia}
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-apagado">
              {icone ? (
                <span aria-hidden="true" className="inline-flex shrink-0">
                  {icone}
                </span>
              ) : null}
              {sobretitulo}
            </p>
            <h3 id={`${id}-titulo`} className="mt-1 font-titulo text-lg leading-snug font-bold text-tinta">
              {titulo}
            </h3>
          </div>
          {selo ? <div className="shrink-0 pt-0.5">{selo}</div> : null}
        </div>
        {children ? <div className="mt-3 space-y-3">{children}</div> : null}
        {temRodape ? (
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-borda pt-3">
            {rodape}
            {geradoTexto || refazer ? (
              <div className="ml-auto flex flex-wrap items-center gap-x-2 text-sm text-apagado">
                {geradoTexto ? <span>{geradoTexto}</span> : null}
                {refazer ? (
                  <button
                    type="button"
                    onClick={refazer.aoRefazer}
                    aria-busy={refazer.refazendo || undefined}
                    className="-mr-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 font-semibold text-marca hover:bg-marca/10"
                  >
                    <ArrowClockwise
                      size={16}
                      weight="bold"
                      aria-hidden="true"
                      className={refazer.refazendo ? "animate-spin" : undefined}
                    />
                    {refazer.refazendo ? "Refazendo a conta…" : "Refazer a conta"}
                  </button>
                ) : null}
              </div>
            ) : null}
            {refazer?.erro ? (
              <p role="alert" className="w-full text-sm text-perigo">
                {refazer.erro}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/** Uma linha "rótulo … valor" do card, como um recibo. */
export function LinhaDoCartao({
  rotulo,
  valor,
  detalhe,
  className,
}: {
  rotulo: ReactNode;
  valor: ReactNode;
  detalhe?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("py-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 text-base text-texto">{rotulo}</span>
        <span className="shrink-0 text-right">{valor}</span>
      </div>
      {detalhe ? <div className="mt-0.5">{detalhe}</div> : null}
    </div>
  );
}

function CartaoQuebrado(_props: Record<string, unknown>, { reset }: ErrorInfo) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-dashed border-borda-campo/50 bg-superficie px-4 py-3 text-sm text-apagado"
    >
      <WarningCircle size={18} weight="fill" aria-hidden="true" className="text-atencao" />
      <span className="flex-1">Não consegui mostrar este cartão.</span>
      <button
        type="button"
        onClick={reset}
        className="-mr-2 inline-flex min-h-11 items-center rounded-sm px-2 font-semibold text-marca hover:bg-marca/10"
      >
        Tentar de novo
      </button>
    </div>
  );
}

/** A fronteira de erro de cada card (a `catchError` do Next). */
export const LimiteDoCartao = catchError(CartaoQuebrado);
