"use client";

/**
 * "Perguntar": leva a pergunta do card para a conversa, já escrita.
 *
 * Vai em todo card e detalhe que tem algo a perguntar. Abre a conversa com o
 * rascunho na caixa e o contexto do que ela estava olhando; quem envia é ela.
 */

import { ChatCircleDots } from "@phosphor-icons/react/dist/ssr";

import { Botao } from "@/componentes/compartilhados/Botao";
import type { TamanhoBotao, VarianteBotao } from "@/componentes/compartilhados/estilosDoBotao";
import type { ContextoDaConversa } from "@/lib/api/conversa";

import { useConversa } from "./ProvedorDaConversa";

export function BotaoPerguntar({
  rascunho,
  contexto,
  rotulo = "Perguntar",
  variante = "secundario",
  tamanho = "sm",
  larguraTotal,
  className,
}: {
  rascunho: string;
  contexto?: ContextoDaConversa;
  /** O texto do botão. O padrão é "Perguntar"; "Responder no chat" na pendência. */
  rotulo?: string;
  variante?: VarianteBotao;
  tamanho?: TamanhoBotao;
  larguraTotal?: boolean;
  className?: string;
}) {
  const { abrir } = useConversa();
  return (
    <Botao
      variante={variante}
      tamanho={tamanho}
      larguraTotal={larguraTotal}
      className={className}
      icone={<ChatCircleDots size={18} weight="bold" />}
      onClick={(evento) => abrir({ rascunho, contexto, origem: evento.currentTarget })}
    >
      {rotulo}
    </Botao>
  );
}
