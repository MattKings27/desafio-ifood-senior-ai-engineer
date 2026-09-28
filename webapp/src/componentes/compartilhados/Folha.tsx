"use client";

/**
 * Folha: o painel que sobe de baixo no celular e entra pela direita no
 * computador (filtros, formulário de ingrediente, o menu Mais).
 *
 * É um `<dialog>` modal, como o Diálogo: foco preso, Esc fecha, o foco volta a
 * quem abriu. No celular, a folha respeita a área segura do aparelho (a barra
 * de gestos do iPhone não cobre o botão de salvar).
 */

import { X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useId } from "react";

import { BotaoIcone } from "./Botao";
import { fecharAoClicarNoFundo, useDialogoNativo } from "./Dialogo";

export type LadoDaFolha = "baixo" | "direita" | "auto";

const DE_BAIXO =
  "mt-auto mb-0 w-full max-w-none max-h-[92dvh] rounded-t-xl border-x-0 border-b-0 " +
  "translate-y-full open:translate-y-0 starting:open:translate-y-full";

const DA_DIREITA =
  "mr-0 ml-auto h-dvh max-h-dvh w-[min(100vw,28rem)] max-w-none rounded-l-xl border-y-0 border-r-0 " +
  "translate-x-full open:translate-x-0 starting:open:translate-x-full";

const AUTOMATICA =
  "mt-auto mb-0 w-full max-w-none max-h-[92dvh] rounded-t-xl border-x-0 border-b-0 " +
  "translate-y-full open:translate-y-0 starting:open:translate-y-full " +
  "lg:mt-0 lg:mr-0 lg:ml-auto lg:h-dvh lg:max-h-dvh lg:w-[28rem] lg:rounded-t-none lg:rounded-l-xl " +
  "lg:border-y-0 lg:border-r-0 lg:border-l lg:translate-y-0 lg:translate-x-full lg:open:translate-x-0 " +
  "lg:starting:open:translate-x-full lg:starting:open:translate-y-0";

const LADOS: Record<LadoDaFolha, string> = {
  baixo: DE_BAIXO,
  direita: DA_DIREITA,
  auto: AUTOMATICA,
};

export function Folha({
  aberto,
  aoFechar,
  titulo,
  descricao,
  children,
  rodape,
  lado = "auto",
  focoInicial,
  className,
}: {
  aberto: boolean;
  aoFechar: () => void;
  titulo: string;
  descricao?: ReactNode;
  children: ReactNode;
  /** Ações fixas no pé da folha (ex.: "Salvar", "Ver 12 receitas"). */
  rodape?: ReactNode;
  lado?: LadoDaFolha;
  focoInicial?: string;
  className?: string;
}) {
  const id = useId();
  const { ref, aoFecharNativo, fechar } = useDialogoNativo(aberto, aoFechar, focoInicial);

  return (
    // O Esc fecha pelo teclado (nativo); o clique no fundo é o do ponteiro.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events
    <dialog
      ref={ref}
      aria-labelledby={`${id}-titulo`}
      aria-describedby={descricao ? `${id}-descricao` : undefined}
      onClose={aoFecharNativo}
      onClick={(evento) => fecharAoClicarNoFundo(evento, fechar)}
      className={clsx(
        "overflow-hidden border border-borda bg-superficie p-0 text-texto shadow-flutuante",
        "backdrop:bg-black/50",
        "transition-[translate,display,overlay] transition-discrete duration-lenta ease-padrao",
        LADOS[lado],
        className,
      )}
    >
      <div className="flex max-h-[inherit] h-full flex-col">
        {lado !== "direita" ? (
          <div aria-hidden="true" className={clsx("flex justify-center pt-2", lado === "auto" && "lg:hidden")}>
            <span className="h-1 w-10 rounded-full bg-borda-campo/50" />
          </div>
        ) : null}
        <div className="flex items-start justify-between gap-3 px-5 pt-3 lg:pt-5">
          <div className="min-w-0 pt-1.5">
            <h2 id={`${id}-titulo`} className="font-titulo text-lg font-bold text-tinta">
              {titulo}
            </h2>
            {descricao ? (
              <div id={`${id}-descricao`} className="mt-1 text-sm text-apagado">
                {descricao}
              </div>
            ) : null}
          </div>
          <BotaoIcone rotulo="Fechar" className="-mr-2" onClick={fechar}>
            <X size={20} weight="bold" />
          </BotaoIcone>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {rodape ? (
          <div className="flex flex-col gap-2 border-t border-borda px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end">
            {rodape}
          </div>
        ) : (
          <div aria-hidden="true" className="pb-[env(safe-area-inset-bottom)]" />
        )}
      </div>
    </dialog>
  );
}
