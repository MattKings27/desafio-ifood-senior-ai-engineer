"use client";

/**
 * As faixas no topo da conversa quando não dá para mandar mensagem: sem
 * internet, ou com o agente fora do ar. Dizem o que houve, que o resto do
 * sistema continua funcionando, e (fora do ar) deixam tentar de novo na hora.
 * A loja também tenta sozinha a cada meio minuto, e a faixa some quando ela
 * voltar.
 */

import { ArrowClockwise, CloudSlash, WifiSlash } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";
import { useState } from "react";

import { MOTIVO_FORA_DO_AR } from "@/lib/conversa/loja";

import { useLojaDaConversa, useSeletor } from "./useLoja";

export const TEXTO_SEM_INTERNET =
  "A senhora pode ler a conversa. Para mandar uma mensagem, espere a conexão voltar.";

function Faixa({ icone, titulo, texto, acao }: { icone: ReactNode; titulo: string; texto: string; acao?: ReactNode }) {
  return (
    <div role="status" className="flex items-start gap-3 border-b border-atencao/25 bg-atencao/10 px-4 py-3">
      <span aria-hidden="true" className="mt-0.5 shrink-0 text-atencao">
        {icone}
      </span>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-tinta">{titulo}</p>
        <p className="text-texto">{texto}</p>
        {acao}
      </div>
    </div>
  );
}

export function FaixasDaConversa() {
  const loja = useLojaDaConversa();
  const online = useSeletor(loja, (estado) => estado.online);
  const disponibilidade = useSeletor(loja, (estado) => estado.disponibilidade);
  const [tentando, setTentando] = useState(false);

  if (!online) {
    return <Faixa icone={<WifiSlash size={20} weight="bold" />} titulo="Sem internet agora" texto={TEXTO_SEM_INTERNET} />;
  }
  if (!disponibilidade.disponivel) {
    const motivo = disponibilidade.motivo && disponibilidade.motivo !== MOTIVO_FORA_DO_AR ? disponibilidade.motivo : null;
    return (
      <Faixa
        icone={<CloudSlash size={20} weight="bold" />}
        titulo="O agente está fora do ar agora"
        texto={motivo ?? "As outras telas continuam funcionando normalmente. Eu aviso aqui quando ele voltar."}
        acao={
          <button
            type="button"
            aria-busy={tentando || undefined}
            onClick={() => {
              setTentando(true);
              void loja.verificarDisponibilidade().finally(() => setTentando(false));
            }}
            className="-ml-2 mt-1 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 font-semibold text-marca hover:bg-marca/10"
          >
            <ArrowClockwise size={16} weight="bold" aria-hidden="true" className={tentando ? "animate-spin" : undefined} />
            {tentando ? "Tentando…" : "Tentar agora"}
          </button>
        }
      />
    );
  }
  return null;
}
