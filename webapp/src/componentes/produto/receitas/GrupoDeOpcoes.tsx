"use client";

/**
 * Poucas respostas lado a lado, cada uma um botão que já responde (Tenho,
 * Não tenho, Não sei). São botões e não rádios de propósito: nas setas de um
 * grupo de rádios cada tecla escolheria uma resposta, e aqui escolher é
 * mandar. A escolhida fica marcada (`aria-pressed`) em tinta cheia; enquanto
 * a resposta vai, o grupo avisa que está ocupado e ignora outro toque, sem
 * perder o foco de quem usa teclado.
 *
 * Nenhum rótulo é cortado: com pouco espaço (menos de 18rem, que crescem junto
 * com o texto grande), as respostas ficam uma embaixo da outra, e o texto de
 * cada botão quebra linha em vez de sumir atrás de reticências.
 */

import { CircleNotch } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

export type OpcaoDoGrupo<V extends string> = { rotulo: string; valor: V };

export function GrupoDeOpcoes<V extends string>({
  rotulo,
  idDoRotulo,
  opcoes,
  escolhida,
  pendente,
  aoEscolher,
  className,
}: {
  /** O nome do grupo para o leitor de tela, quando não há um texto visível que o diga. */
  rotulo?: string;
  /** O id do texto visível que nomeia o grupo (a pergunta). */
  idDoRotulo?: string;
  opcoes: readonly OpcaoDoGrupo<V>[];
  escolhida: V | null;
  pendente: boolean;
  aoEscolher: (valor: V) => void;
  className?: string;
}) {
  return (
    <div className={clsx("@container", className)}>
      <div
        role="group"
        aria-label={idDoRotulo ? undefined : rotulo}
        aria-labelledby={idDoRotulo}
        aria-busy={pendente || undefined}
        className={clsx(
          "grid grid-cols-1 gap-1 rounded-sm border border-borda-campo/60 bg-superficie p-1",
          "@[18rem]:auto-cols-fr @[18rem]:grid-flow-col @[18rem]:grid-cols-none",
        )}
      >
        {opcoes.map((opcao) => {
          const marcada = escolhida === opcao.valor;
          return (
            <button
              key={opcao.valor}
              type="button"
              aria-pressed={marcada}
              aria-disabled={pendente || undefined}
              onClick={() => {
                if (!pendente) aoEscolher(opcao.valor);
              }}
              className={clsx(
                "flex min-h-11 min-w-0 items-center justify-center gap-1.5 rounded-[6px] px-2 py-1.5 text-center text-sm font-semibold",
                "break-words transition-colors duration-rapida aria-disabled:cursor-progress",
                marcada ? "bg-tinta text-superficie" : "text-texto hover:bg-secao hover:text-tinta",
              )}
            >
              {pendente && marcada ? (
                <CircleNotch size={16} weight="bold" className="shrink-0 animate-spin" aria-hidden="true" />
              ) : null}
              <span className="min-w-0">{opcao.rotulo}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
