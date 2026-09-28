"use client";

/**
 * Diálogo modal sobre o `<dialog>` nativo, e a confirmação de algo que não
 * volta (tirar da despensa, tirar do cardápio).
 *
 * O `showModal()` do navegador já dá o que um diálogo precisa: o foco preso
 * dentro, o resto da página inerte, o Esc fechando. O que falta aqui é só
 * devolver o foco a quem abriu, e ligar o estado `aberto` do React ao do
 * navegador (fechar pelo Esc avisa `aoFechar`).
 *
 * A confirmação usa `role="alertdialog"` e começa com o foco no botão que não
 * estraga nada ("Cancelar"): um Enter distraído não apaga o item.
 */

import { X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { MouseEvent, ReactNode, SyntheticEvent } from "react";
import { useEffect, useId, useRef } from "react";

import { Botao, BotaoIcone } from "./Botao";

/**
 * Liga um `<dialog>` ao estado do React. Serve ao Dialogo e à Folha.
 *
 * `focoInicial` recebe um seletor dentro do diálogo; sem ele, o navegador
 * foca o primeiro controle.
 */
export function useDialogoNativo(aberto: boolean, aoFechar: () => void, focoInicial?: string) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const origem = useRef<HTMLElement | null>(null);
  // Quem fechou foi a própria tela (aberto virou false): não é "cancelar".
  const fechadoPorFora = useRef(false);
  const aoFecharAtual = useRef(aoFechar);
  useEffect(() => {
    aoFecharAtual.current = aoFechar;
  });

  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    if (aberto && !dialogo.open) {
      origem.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialogo.showModal();
      if (focoInicial) dialogo.querySelector<HTMLElement>(focoInicial)?.focus();
    } else if (!aberto && dialogo.open) {
      fechadoPorFora.current = true;
      dialogo.close();
    }
  }, [aberto, focoInicial]);

  // Saiu da tela aberto (ex.: navegou): devolve o foco mesmo assim.
  useEffect(
    () => () => {
      const quem = origem.current;
      if (quem?.isConnected) quem.focus();
    },
    [],
  );

  const aoFecharNativo = (evento?: SyntheticEvent) => {
    // No React, o `close` de um diálogo de dentro (a confirmação aberta de
    // dentro de uma folha) sobe pela árvore até o de fora. Esse fechamento não
    // é deste diálogo, e fechar a folha junto seria perder o que ela mostrava.
    if (evento && evento.target !== evento.currentTarget) return;
    const quem = origem.current;
    origem.current = null;
    if (quem?.isConnected) quem.focus();
    if (fechadoPorFora.current) {
      fechadoPorFora.current = false;
      return;
    }
    aoFecharAtual.current();
  };

  return { ref, aoFecharNativo, fechar: () => ref.current?.close() };
}

/** Clique fora do conteúdo (no fundo escurecido) fecha. */
export function fecharAoClicarNoFundo(evento: MouseEvent<HTMLDialogElement>, fechar: () => void) {
  if (evento.target === evento.currentTarget) fechar();
}

type TamanhoDoDialogo = "sm" | "md" | "lg";

const LARGURAS: Record<TamanhoDoDialogo, string> = {
  sm: "w-[min(calc(100vw-2rem),24rem)]",
  md: "w-[min(calc(100vw-2rem),32rem)]",
  lg: "w-[min(calc(100vw-2rem),44rem)]",
};

/* A entrada e a saída: 300 ms, e nada com "reduzir movimento" (globals.css). */
const MOVIMENTO =
  "opacity-0 translate-y-2 transition-[opacity,translate,display,overlay] transition-discrete duration-padrao ease-padrao " +
  "open:opacity-100 open:translate-y-0 starting:open:opacity-0 starting:open:translate-y-2";

export function Dialogo({
  aberto,
  aoFechar,
  titulo,
  descricao,
  children,
  acoes,
  alerta = false,
  tamanho = "md",
  fecharAoClicarFora,
  focoInicial,
  className,
}: {
  aberto: boolean;
  aoFechar: () => void;
  titulo: string;
  descricao?: ReactNode;
  children?: ReactNode;
  /** Os botões do pé. No celular, empilhados, com o principal por baixo do polegar. */
  acoes?: ReactNode;
  /** Confirmação de algo que não volta: `alertdialog`, sem fechar clicando fora. */
  alerta?: boolean;
  tamanho?: TamanhoDoDialogo;
  fecharAoClicarFora?: boolean;
  /** Seletor do que recebe o foco ao abrir (ex.: `[data-foco-inicial]`). */
  focoInicial?: string;
  className?: string;
}) {
  const id = useId();
  const { ref, aoFecharNativo, fechar } = useDialogoNativo(aberto, aoFechar, focoInicial);
  const fechaFora = fecharAoClicarFora ?? !alerta;

  return (
    // O teclado já fecha pelo Esc (nativo do <dialog>); o clique no fundo é o
    // equivalente para o ponteiro.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events
    <dialog
      ref={ref}
      role={alerta ? "alertdialog" : undefined}
      aria-labelledby={`${id}-titulo`}
      aria-describedby={descricao ? `${id}-descricao` : undefined}
      onClose={aoFecharNativo}
      onClick={fechaFora ? (evento) => fecharAoClicarNoFundo(evento, fechar) : undefined}
      className={clsx(
        "m-auto max-h-[min(90dvh,48rem)] max-w-none overflow-hidden rounded-lg border border-borda bg-superficie p-0 text-texto shadow-flutuante",
        "backdrop:bg-black/50",
        LARGURAS[tamanho],
        MOVIMENTO,
        className,
      )}
    >
      <div className="flex max-h-[inherit] flex-col">
        <div className="flex items-start justify-between gap-3 px-5 pt-5">
          <h2 id={`${id}-titulo`} className="pt-1.5 font-titulo text-lg font-bold text-tinta">
            {titulo}
          </h2>
          {alerta ? null : (
            <BotaoIcone rotulo="Fechar" className="-mr-2 -mt-1" onClick={fechar}>
              <X size={20} weight="bold" />
            </BotaoIcone>
          )}
        </div>
        {descricao ? (
          <div id={`${id}-descricao`} className="px-5 pt-2 text-base text-texto">
            {descricao}
          </div>
        ) : null}
        {children ? <div className="overflow-y-auto px-5 py-4">{children}</div> : <div className="pb-4" />}
        {acoes ? (
          <div className="flex flex-col-reverse gap-2 border-t border-borda px-5 py-4 sm:flex-row sm:justify-end">
            {acoes}
          </div>
        ) : null}
      </div>
    </dialog>
  );
}

/**
 * "Tem certeza?" para o que não volta. `aoConfirmar` pode ser assíncrono: o
 * botão fica carregando e o diálogo só fecha quando quem chamou mandar.
 */
export function DialogoDeConfirmacao({
  aberto,
  titulo,
  descricao,
  rotuloConfirmar,
  rotuloCancelar = "Cancelar",
  perigoso = false,
  carregando = false,
  aoConfirmar,
  aoCancelar,
}: {
  aberto: boolean;
  titulo: string;
  descricao: ReactNode;
  rotuloConfirmar: string;
  rotuloCancelar?: string;
  /** A ação apaga ou tira algo: o botão vai na cor de perigo. */
  perigoso?: boolean;
  carregando?: boolean;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}) {
  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoCancelar}
      titulo={titulo}
      descricao={descricao}
      alerta
      tamanho="sm"
      focoInicial="[data-foco-inicial]"
      acoes={
        <>
          <Botao variante="terciario" data-foco-inicial="" onClick={aoCancelar}>
            {rotuloCancelar}
          </Botao>
          <Botao variante={perigoso ? "perigo" : "primario"} carregando={carregando} onClick={aoConfirmar}>
            {rotuloConfirmar}
          </Botao>
        </>
      }
    />
  );
}

