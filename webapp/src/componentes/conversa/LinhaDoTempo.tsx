"use client";

/**
 * O que o agente está fazendo, enquanto faz: a linha do tempo do turno.
 *
 * Um turno leva de 30 a 90 s (a mediana medida é de 40 s). Esperar em silêncio
 * parece travado; então a tela conta o tempo ("Trabalhando há 42 s"), diz
 * quanto costuma levar, e mostra cada passo mudando de "fazendo" para "feito"
 * ("olhando sua despensa" → "olhei sua despensa"). Depois de 90 s, avisa que
 * está demorando e oferece parar.
 *
 * Quando o turno termina, os passos viram um resumo recolhido ("Ver o que eu
 * fiz"), que também aparece nas respostas guardadas.
 */

import { CheckCircle, CircleNotch, WarningCircle, WifiSlash } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useEffect, useState } from "react";

import { Surgir } from "@/componentes/compartilhados/Movimento";
import { comMaiuscula, tempoDecorrido } from "@/lib/conversa/atividades";
import type { AtividadeNaTela, Turno } from "@/lib/conversa/estado";

/** Até aqui é normal; depois, "está demorando". */
export const TEMPO_NORMAL_MS = 90_000;

export const TEXTO_DO_TEMPO_NORMAL = "Costuma levar perto de 1 minuto.";
export const TEXTO_DA_DEMORA = "Está demorando mais que o normal, a senhora pode esperar ou parar.";

/** O relógio da tela: anda a cada segundo enquanto `ativo`. */
export function useAgora(ativo: boolean, intervaloMs = 1_000): number {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    if (!ativo) return;
    setAgora(Date.now());
    const relogio = setInterval(() => setAgora(Date.now()), intervaloMs);
    return () => clearInterval(relogio);
  }, [ativo, intervaloMs]);
  return agora;
}

function Passo({ atividade }: { atividade: AtividadeNaTela }) {
  const fazendo = atividade.estado === "fazendo";
  const falhou = atividade.estado === "falhou";
  return (
    <div className="flex items-start gap-2.5">
      <span aria-hidden="true" className="mt-0.5 inline-flex shrink-0">
        {fazendo ? (
          <CircleNotch size={20} weight="bold" className="animate-spin text-marca" />
        ) : falhou ? (
          <WarningCircle size={20} weight="fill" className="text-atencao" />
        ) : (
          <CheckCircle size={20} weight="fill" className="text-sucesso" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className={clsx("block text-base leading-6", fazendo ? "text-tinta" : "text-texto")}>
          {falhou ? `${comMaiuscula(atividade.rotulo)}: não deu certo` : comMaiuscula(fazendo ? atividade.rotulo : atividade.rotuloFeito)}
          {fazendo ? <span className="sr-only"> (em andamento)</span> : null}
        </span>
        {atividade.detalhe || atividade.resumo ? (
          <span className="mt-0.5 block text-sm leading-5 text-apagado">{atividade.resumo ?? atividade.detalhe}</span>
        ) : null}
      </span>
    </div>
  );
}

function manchete(turno: Turno, decorrido: number): string {
  if (turno.fase === "enviando") return "Mandando a sua mensagem…";
  if (turno.fase === "cancelando") return "Parando…";
  if (turno.fase === "conferido") return "Conferindo a resposta…";
  return `Trabalhando há ${tempoDecorrido(decorrido)}`;
}

/** A linha do tempo do turno em andamento. */
export function LinhaDoTempoAoVivo({
  turno,
  aoParar,
}: {
  turno: Turno;
  /** Depois de 90 s aparece "Parar" aqui também. */
  aoParar?: () => void;
}) {
  const agora = useAgora(true);
  const decorrido = Math.max(0, agora - turno.iniciadoEm);
  const demorando = decorrido > TEMPO_NORMAL_MS && turno.fase !== "cancelando";
  const reconectando = turno.conexao === "reconectando";

  return (
    <div className="rounded-lg border border-borda bg-superficie px-4 py-3.5">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 inline-flex shrink-0">
          <CircleNotch size={20} weight="bold" className="animate-spin text-apagado" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="numero text-base leading-6 font-semibold text-tinta">{manchete(turno, decorrido)}</p>
          {reconectando ? (
            <p className="mt-0.5 flex items-center gap-1.5 text-sm leading-5 text-apagado">
              <WifiSlash size={16} weight="bold" aria-hidden="true" />A conexão oscilou. Estou reconectando…
            </p>
          ) : turno.fase === "enviando" || turno.fase === "cancelando" ? null : (
            <p className="mt-0.5 text-sm leading-5 text-apagado">{demorando ? TEXTO_DA_DEMORA : TEXTO_DO_TEMPO_NORMAL}</p>
          )}
          {demorando && aoParar ? (
            <button
              type="button"
              onClick={aoParar}
              className="-ml-2 mt-1 inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
            >
              Parar a resposta
            </button>
          ) : null}
        </div>
      </div>
      {turno.atividades.length > 0 ? (
        <ol aria-label="O que eu estou fazendo" className="mt-3 space-y-2.5 border-t border-borda pt-3">
          {turno.atividades.map((atividade) => (
            <li key={atividade.id}>
              <Surgir>
                <Passo atividade={atividade} />
              </Surgir>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

/**
 * O que foi feito num turno que terminou: recolhido, para não pesar a
 * conversa, a menos que ela peça nas Preferências para ver sempre aberto.
 */
export function ResumoDasAtividades({
  atividades,
  abertoDeInicio = false,
}: {
  atividades: readonly { rotuloFeito: string; ok: boolean }[];
  /** "Mostrar o que o agente fez em cada resposta", nas Preferências. */
  abertoDeInicio?: boolean;
}) {
  if (atividades.length === 0) return null;
  return (
    <details className="group" open={abertoDeInicio}>
      <summary className="-ml-2 inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-sm px-2 text-sm font-semibold text-apagado hover:text-tinta [&::-webkit-details-marker]:hidden">
        <CheckCircle size={18} weight="fill" aria-hidden="true" className="text-sucesso" />
        {atividades.length === 1 ? "Ver o que eu fiz (1 passo)" : `Ver o que eu fiz (${atividades.length} passos)`}
      </summary>
      <ol className="mt-1 mb-2 space-y-1.5 border-l-2 border-borda pl-4">
        {atividades.map((atividade, indice) => (
          <li key={`${indice}-${atividade.rotuloFeito}`} className="flex items-start gap-2 text-sm leading-6 text-texto">
            {atividade.ok ? (
              <CheckCircle size={16} weight="fill" aria-hidden="true" className="mt-1 shrink-0 text-sucesso" />
            ) : (
              <WarningCircle size={16} weight="fill" aria-hidden="true" className="mt-1 shrink-0 text-atencao" />
            )}
            <span>
              {comMaiuscula(atividade.rotuloFeito)}
              {atividade.ok ? null : <span className="text-apagado"> (não deu certo)</span>}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}
