"use client";

/**
 * O que um card (ou um chip) pode fazer na conversa: mandar um turno
 * estruturado, ou pôr um rascunho na caixa para ela completar.
 *
 * Enquanto o agente responde, os botões que mandam ficam esperando
 * (`ocupada`): mandar no meio de um turno daria "ainda estou respondendo".
 */

import { useCallback, useMemo } from "react";

import type { ContextoDaConversa } from "@/lib/api/conversa";
import type { OpcoesDoEnvio } from "@/lib/conversa/loja";
import { MOTIVO_FORA_DO_AR } from "@/lib/conversa/loja";

import { useLojaDaConversa, useSeletor } from "./useLoja";

export type AcoesDaConversa = {
  enviar: (texto: string, opcoes?: OpcoesDoEnvio) => void;
  preencher: (rascunho: string, contexto?: ContextoDaConversa | null) => void;
  ocupada: boolean;
  /** Por que não dá para mandar agora (para o `title` e o leitor de tela). */
  motivo: string | null;
};

export const MOTIVO_RESPONDENDO = "Espere eu terminar esta resposta.";
export const MOTIVO_SEM_INTERNET = "Sem internet agora.";

export function useAcoesDaConversa(): AcoesDaConversa {
  const loja = useLojaDaConversa();
  const respondendo = useSeletor(loja, (estado) => estado.conversa.turno !== null);
  const online = useSeletor(loja, (estado) => estado.online);
  const disponivel = useSeletor(loja, (estado) => estado.disponibilidade.disponivel);
  const motivoForaDoAr = useSeletor(loja, (estado) => estado.disponibilidade.motivo);

  const enviar = useCallback(
    (texto: string, opcoes?: OpcoesDoEnvio) => {
      void loja.enviar(texto, opcoes);
    },
    [loja],
  );
  const preencher = useCallback(
    (rascunho: string, contexto?: ContextoDaConversa | null) => {
      loja.preencher({ rascunho, ...(contexto === undefined ? {} : { contexto }) });
    },
    [loja],
  );

  const motivo = respondendo
    ? MOTIVO_RESPONDENDO
    : !online
      ? MOTIVO_SEM_INTERNET
      : !disponivel
        ? (motivoForaDoAr ?? MOTIVO_FORA_DO_AR)
        : null;

  return useMemo(
    () => ({ enviar, preencher, ocupada: motivo !== null, motivo }),
    [enviar, preencher, motivo],
  );
}
