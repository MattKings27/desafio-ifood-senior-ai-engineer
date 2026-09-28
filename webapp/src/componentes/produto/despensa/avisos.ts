"use client";

/**
 * O aviso depois de uma escrita da despensa: a frase da API e, quando a
 * mudança tem evento, o "Desfazer" (`POST /api/despensa/eventos/{evento}/desfazer`).
 *
 * O "Desfazer" chama a Server Action direto, numa transição: o aviso pode ser
 * clicado depois que a tela que o abriu saiu (tirar o item leva de volta à
 * lista), e o aviso de volta ("Voltei o creme de leite…") vem da API também.
 */

import { startTransition, useCallback } from "react";

import { useToast } from "@/componentes/compartilhados/Toast";
import { desfazerMudanca } from "@/lib/acoes/despensa";
import type { Resultado } from "@/lib/acoes/base";
import { MENSAGENS } from "@/lib/api/base";
import { novoIdCliente } from "@/lib/dados/id";

/** A ação nunca lança; se lançar (servidor fora do ar), vira falha de rede. */
export async function semLancar<T>(trabalho: () => Promise<Resultado<T>>): Promise<Resultado<T>> {
  try {
    return await trabalho();
  } catch {
    return { ok: false, erro: { categoria: "rede", mensagem: MENSAGENS.rede } };
  }
}

type Avisos = ReturnType<typeof useToast>;

/** Desfaz a mudança e diz o que aconteceu, com a frase da API (ou o porquê de não ter dado). */
export async function desfazerComAviso(evento: string, toast: Avisos): Promise<void> {
  const resultado = await semLancar(() => desfazerMudanca(evento, novoIdCliente()));
  toast.mostrar(
    resultado.ok
      ? { texto: resultado.dados.texto, tom: "sucesso" }
      : { texto: resultado.erro.pergunta ?? resultado.erro.mensagem, tom: "erro" },
  );
}

export function useAvisoComDesfazer() {
  const toast = useToast();
  return useCallback(
    (texto: string, evento: string | null | undefined) => {
      toast.mostrar({
        texto,
        tom: "sucesso",
        ...(evento
          ? {
              acao: {
                rotulo: "Desfazer",
                aoClicar: () => startTransition(() => desfazerComAviso(evento, toast)),
              },
            }
          : {}),
      });
    },
    [toast],
  );
}
