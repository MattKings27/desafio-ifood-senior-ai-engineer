"use client";

/**
 * A pílula "Conversar com o agente", no cabeçalho do computador.
 *
 * É a entrada principal do agente, na cor da marca, cedo na ordem do Tab.
 * O clique abre o painel ao lado com o contexto da página; sem JavaScript, ou
 * com Ctrl, leva à página inteira da conversa.
 */

import { ChatCircleDots } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

import { ATRIBUTO_DA_ENTRADA, useEntradaDaConversa } from "@/componentes/conversa/useEntradaDaConversa";

export function AbaConversar() {
  const aoClicar = useEntradaDaConversa();
  return (
    <Link
      href="/conversa"
      onClick={aoClicar}
      {...{ [ATRIBUTO_DA_ENTRADA]: "" }}
      className="inline-flex h-11 items-center gap-2 rounded-full bg-marca-fundo px-5 text-sm font-bold text-sobre-marca transition-colors duration-rapida hover:bg-marca-fundo-escura"
    >
      <ChatCircleDots size={20} weight="fill" aria-hidden="true" />
      Conversar com o agente
    </Link>
  );
}
