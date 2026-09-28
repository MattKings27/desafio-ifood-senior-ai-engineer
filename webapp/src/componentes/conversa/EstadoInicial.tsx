"use client";

/**
 * A conversa ainda vazia: quem é o agente, o que ele faz, e perguntas
 * prontas para começar, escolhidas pela página em que a senhora está (na
 * Despensa, "Onde está o meu dinheiro parado?"; nas Receitas, "O que dá pra
 * fazer hoje?"). Tocar numa delas já manda a pergunta.
 */

import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

import { sugestoesDaTela } from "@/lib/conversa/sugestoes";

import { AvatarDaConsultora } from "./Mensagem";
import { useAcoesDaConversa } from "./useAcoesDaConversa";
import { useLojaDaConversa } from "./useLoja";

export const APRESENTACAO =
  "Eu olho a sua despensa, a sua cozinha e as receitas, e faço as contas com a sua planilha. Pode perguntar do seu jeito.";

export function EstadoInicial({
  caminho,
  nivelTitulo = 2,
}: {
  caminho: string | null | undefined;
  nivelTitulo?: 2 | 3;
}) {
  const loja = useLojaDaConversa();
  const { ocupada, motivo } = useAcoesDaConversa();
  const Titulo = `h${nivelTitulo}` as const;
  const sugestoes = sugestoesDaTela(caminho);

  return (
    <div className="flex flex-col items-center py-4 text-center">
      <AvatarDaConsultora tamanho="lg" />
      <Titulo className="mt-3 font-titulo text-xl font-bold text-tinta">Olá, Dona Maria</Titulo>
      <p className="mt-1 max-w-sm text-base text-texto">{APRESENTACAO}</p>
      <div className="mt-6 w-full max-w-sm">
        <p className="text-left text-sm font-semibold text-apagado">Para começar</p>
        <ul className="mt-2 space-y-2">
          {sugestoes.map((sugestao) => (
            <li key={sugestao.texto}>
              <button
                type="button"
                aria-disabled={ocupada || undefined}
                title={motivo ?? undefined}
                onClick={() => {
                  if (!ocupada) void loja.enviarSugestao(sugestao);
                }}
                className={clsx(
                  "flex min-h-12 w-full items-center justify-between gap-3 rounded-lg border border-borda-campo/60 bg-superficie px-4 py-2.5",
                  "text-left text-base font-semibold text-tinta transition-colors duration-rapida",
                  ocupada ? "cursor-not-allowed opacity-60" : "hover:border-tinta hover:bg-secao",
                )}
              >
                <span>{sugestao.texto}</span>
                <ArrowRight size={18} weight="bold" aria-hidden="true" className="shrink-0 text-marca" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
