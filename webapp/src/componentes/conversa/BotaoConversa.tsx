"use client";

/**
 * O botão flutuante da conversa, no computador (no celular, quem cumpre o papel
 * é o Conversar da barra de baixo). Abre o painel ao lado, sem sair da tela,
 * com o contexto da página; some na página da conversa e enquanto o painel
 * está aberto.
 *
 * É um link para /conversa: sem JavaScript (ou com Ctrl, ou o botão do meio)
 * leva à página inteira. O ponto aceso diz que o agente está respondendo;
 * o número, quantas respostas chegaram com a conversa fechada.
 *
 * Com o painel aberto ele fica escondido, e não desmontado: quando o painel
 * fecha, o foco volta para este mesmo botão.
 */

import { ChatCircleDots } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ehPaginaDaConversa, useConversa } from "./ProvedorDaConversa";
import { ATRIBUTO_DA_ENTRADA, useEntradaDaConversa } from "./useEntradaDaConversa";

/** O que o leitor de tela ouve depois de "Conversar". */
export function avisoDoSelo(respondendo: boolean, naoLidas: number): string | null {
  if (respondendo) return "o agente está respondendo";
  if (naoLidas === 1) return "1 resposta nova";
  if (naoLidas > 1) return `${naoLidas} respostas novas`;
  return null;
}

export function BotaoConversa({ className }: { className?: string }) {
  const caminho = usePathname();
  const { aberta, respondendo, naoLidas = 0 } = useConversa();
  const aoClicar = useEntradaDaConversa();
  if (ehPaginaDaConversa(caminho)) return null;
  const aviso = avisoDoSelo(respondendo, naoLidas);

  return (
    <Link
      href="/conversa"
      hidden={aberta}
      aria-expanded={aberta}
      {...{ [ATRIBUTO_DA_ENTRADA]: "" }}
      onClick={aoClicar}
      className={clsx(
        "fixed right-6 bottom-6 z-40 hidden h-14 items-center gap-2.5 rounded-full bg-marca-fundo pr-6 pl-5",
        "text-base font-bold text-sobre-marca shadow-flutuante transition-colors duration-rapida",
        "hover:bg-marca-fundo-escura focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-marca",
        !aberta && "lg:inline-flex",
        className,
      )}
    >
      <span aria-hidden="true" className="relative inline-flex">
        <ChatCircleDots size={24} weight="fill" />
        {respondendo ? (
          <span className="absolute -top-0.5 -right-0.5 flex size-2.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-sobre-marca opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-sobre-marca ring-2 ring-marca-fundo" />
          </span>
        ) : null}
      </span>
      Conversar
      {respondendo ? (
        <span aria-hidden="true" className="rounded-full bg-marca-fundo-escura px-2 py-0.5 text-xs font-semibold">
          respondendo…
        </span>
      ) : naoLidas > 0 ? (
        <span
          aria-hidden="true"
          className="numero flex h-6 min-w-6 items-center justify-center rounded-full bg-sobre-marca px-1.5 text-xs font-bold text-marca-fundo"
        >
          {naoLidas}
        </span>
      ) : null}
      {aviso ? <span className="sr-only">: {aviso}</span> : null}
    </Link>
  );
}
