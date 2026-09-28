"use client";

/**
 * As mensagens da conversa.
 *
 * - **A dela**: uma bolha tingida, à direita, com o assunto que foi junto
 *   ("Vendo: Arroz branco tipo 1"). Se não chegou ao backend, diz "Não enviou"
 *   e oferece "Tentar de novo", com o mesmo `id_cliente` (nada sai duplicado).
 * - **A do agente**: a marca como avatar, o texto na largura toda e os
 *   cards empilhados embaixo, com "Ver o que eu fiz". O texto é o conferido;
 *   de uma resposta que parou ou falhou fica só o rascunho, com os valores
 *   escondidos para sempre, e "Perguntar de novo".
 * - **A que está sendo escrita**: os três pontinhos de "escrevendo" no
 *   instante em que ela manda, a linha do tempo quando o agente usa uma
 *   ferramenta (ou demora), o rascunho aparecendo letra a letra com cada valor
 *   em conferência ("R$ ···"), os cards conforme chegam, e o texto conferido
 *   entrando no lugar do rascunho quando a conta fecha, sem piscar.
 */

import { ArrowClockwise, CheckCircle, CookingPot, Eye, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

import type { CategoriaDaFalha } from "@/lib/api/conversa";
import { chaveDaResposta } from "@/lib/conversa/estado";
import type { MensagemDela as MensagemDelaNaTela, RespostaDaConsultora, ResultadoDeAcao, Turno } from "@/lib/conversa/estado";
import { rascunhos } from "@/lib/conversa/perguntas";
import { rotuloDoContexto } from "@/lib/conversa/sugestoes";
import { textoParaEla } from "@/lib/formato";
import { PASSOS_DA_CONSULTORA } from "@/lib/preferencias";
import { usePreferencia } from "@/lib/usePreferencias";

import { CartoesDaResposta } from "./cartoes/registro";
import { LinhaDoTempoAoVivo, ResumoDasAtividades, useAgora } from "./LinhaDoTempo";
import { TextoDaConsultora } from "./TextoDaConsultora";
import { useAcoesDaConversa } from "./useAcoesDaConversa";
import { useLojaDaConversa } from "./useLoja";

/* -------------------------------------------------------------------------- */
/* Peças                                                                       */
/* -------------------------------------------------------------------------- */

/** A marca da casa no lugar de uma foto: o agente não é uma pessoa de mentira. */
export function AvatarDaConsultora({ tamanho = "md", ativa = false }: { tamanho?: "md" | "lg"; ativa?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "relative flex shrink-0 items-center justify-center rounded-full bg-marca-fundo text-sobre-marca",
        tamanho === "lg" ? "size-14" : "size-9",
      )}
    >
      <CookingPot size={tamanho === "lg" ? 30 : 20} weight="fill" />
      {ativa ? (
        <span className="absolute -right-0.5 -bottom-0.5 size-3 rounded-full bg-sucesso ring-2 ring-superficie" />
      ) : null}
    </span>
  );
}

function BotaoDeTexto({ children, onClick, icone }: { children: ReactNode; onClick: () => void; icone?: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
    >
      {icone ? (
        <span aria-hidden="true" className="inline-flex">
          {icone}
        </span>
      ) : null}
      {children}
    </button>
  );
}

/** O que o backend fez com o botão de um card, antes de o agente falar. */
function ResultadosDasAcoes({ resultados }: { resultados: readonly ResultadoDeAcao[] }) {
  if (resultados.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {resultados.map((resultado, indice) => (
        <li
          key={`${indice}-${resultado.texto}`}
          className={clsx(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            resultado.ok ? "border-sucesso/25 bg-sucesso/10 text-sucesso" : "border-atencao/25 bg-atencao/10 text-atencao",
          )}
        >
          {resultado.ok ? (
            <CheckCircle size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0" />
          ) : (
            <WarningCircle size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0" />
          )}
          <span>{resultado.texto}</span>
        </li>
      ))}
    </ul>
  );
}

/* -------------------------------------------------------------------------- */
/* A mensagem dela                                                             */
/* -------------------------------------------------------------------------- */

export function MensagemDela({ mensagem }: { mensagem: MensagemDelaNaTela }) {
  const loja = useLojaDaConversa();
  const falhou = mensagem.envio === "falhou";
  return (
    <div className="flex flex-col items-end gap-1 pl-8 sm:pl-12">
      <p className="sr-only">A senhora escreveu:</p>
      <div
        className={clsx(
          "max-w-full rounded-2xl rounded-br-md bg-tinta-clara px-4 py-2.5 text-base leading-7 break-words whitespace-pre-wrap text-texto",
          falhou && "ring-1 ring-perigo/40",
          mensagem.envio === "enviando" && "opacity-80",
        )}
      >
        {mensagem.texto}
      </div>
      {mensagem.contexto ? (
        <p className="flex items-center gap-1 text-sm text-apagado">
          <Eye size={14} weight="bold" aria-hidden="true" />
          Vendo: {rotuloDoContexto(mensagem.contexto)}
        </p>
      ) : null}
      {falhou ? (
        <div role="alert" className="flex flex-wrap items-center justify-end gap-x-2 text-sm text-perigo">
          <span className="flex items-center gap-1.5 font-semibold">
            <WarningCircle size={16} weight="fill" aria-hidden="true" />
            Não enviou.
          </span>
          {mensagem.erroDoEnvio ? (
            <span className="text-apagado">
              {textoParaEla(mensagem.erroDoEnvio.mensagem, "Não consegui falar com o sistema agora.")}
            </span>
          ) : null}
          {mensagem.idCliente ? (
            <BotaoDeTexto
              icone={<ArrowClockwise size={16} weight="bold" />}
              onClick={() => void loja.reenviar(mensagem.idCliente as string)}
            >
              Tentar de novo
            </BotaoDeTexto>
          ) : null}
        </div>
      ) : null}
      {mensagem.envio === "enviada" && mensagem.quandoTexto ? (
        <p className="text-xs text-apagado">{mensagem.quandoTexto}</p>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* A resposta do agente                                                    */
/* -------------------------------------------------------------------------- */

/** O título de uma resposta que falhou, pela categoria (nunca a mensagem técnica). */
export const TITULO_DA_FALHA: Readonly<Record<CategoriaDaFalha, string>> = {
  rede: "Não consegui falar com o agente",
  tempo: "A resposta demorou demais",
  consultora: "O agente não conseguiu responder",
  regra: "Não deu para fazer isso agora",
};

export const TEXTO_DA_FALHA: Readonly<Record<CategoriaDaFalha, string>> = {
  rede: "A conexão caiu no meio da resposta. Pode perguntar de novo.",
  tempo: "Pode perguntar de novo; às vezes a segunda vez é mais rápida.",
  consultora: "Aconteceu um problema do lado dele. Pode perguntar de novo daqui a pouco.",
  regra: "Ainda falta confirmar alguma coisa antes deste passo.",
};

export const TEXTO_DO_CANCELADO = "Parei. O que já foi anotado continua anotado.";
export const TEXTO_DO_INTERROMPIDO =
  "A resposta foi interrompida no meio. O que já foi anotado continua anotado.";

function categoria(valor: string | undefined): CategoriaDaFalha {
  return valor === "rede" || valor === "tempo" || valor === "regra" ? valor : "consultora";
}

function Desfecho({ resposta }: { resposta: RespostaDaConsultora }) {
  const loja = useLojaDaConversa();
  if (resposta.estado === "concluido") return null;
  const perguntarDeNovo = (
    <BotaoDeTexto icone={<ArrowClockwise size={16} weight="bold" />} onClick={() => void loja.perguntarDeNovo(resposta.chave)}>
      Perguntar de novo
    </BotaoDeTexto>
  );
  if (resposta.estado === "cancelado") {
    return (
      <div className="flex flex-wrap items-center gap-x-3 text-sm text-apagado">
        <span>{TEXTO_DO_CANCELADO}</span>
        {perguntarDeNovo}
      </div>
    );
  }
  if (resposta.estado === "interrompido") {
    return (
      <div className="rounded-lg border border-borda bg-secao px-3 py-2.5 text-sm text-texto">
        <p>{TEXTO_DO_INTERROMPIDO}</p>
        {perguntarDeNovo}
      </div>
    );
  }
  const tipo = categoria(resposta.erro?.categoria);
  return (
    <div className="rounded-lg border border-atencao/25 bg-atencao/10 px-3 py-2.5 text-sm">
      <p className="flex items-center gap-1.5 font-semibold text-tinta">
        <WarningCircle size={18} weight="fill" aria-hidden="true" className="text-atencao" />
        {TITULO_DA_FALHA[tipo]}
      </p>
      <p className="mt-0.5 text-texto">{textoParaEla(resposta.erro?.mensagem, TEXTO_DA_FALHA[tipo])}</p>
      {perguntarDeNovo}
    </div>
  );
}

function AvisoDosRetirados({ retirados }: { retirados: number }) {
  const acoes = useAcoesDaConversa();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-atencao/25 bg-atencao/10 px-3 py-2 text-sm text-texto">
      <span className="flex items-center gap-1.5">
        <WarningCircle size={16} weight="fill" aria-hidden="true" className="text-atencao" />
        {retirados === 1
          ? "Tirei desta resposta um valor que eu não consegui conferir com a conta."
          : `Tirei desta resposta ${retirados} valores que eu não consegui conferir com a conta.`}
      </span>
      <BotaoDeTexto onClick={() => acoes.preencher(rascunhos.trazerConta())}>Trazer a conta</BotaoDeTexto>
    </div>
  );
}

export function RespostaDaConsultoraNaTela({ resposta }: { resposta: RespostaDaConsultora }) {
  const passos = usePreferencia(PASSOS_DA_CONSULTORA);
  const modo = resposta.rascunho ? "parado" : "final";
  return (
    <div className="flex gap-3">
      <AvatarDaConsultora />
      <div className="min-w-0 flex-1 space-y-3 pt-1">
        <p className="sr-only">O agente respondeu:</p>
        <ResultadosDasAcoes resultados={resposta.resultados} />
        {resposta.texto ? <TextoDaConsultora texto={resposta.texto} modo={modo} chave={resposta.chave} /> : null}
        {resposta.retirados > 0 && modo === "final" ? <AvisoDosRetirados retirados={resposta.retirados} /> : null}
        <Desfecho resposta={resposta} />
        <CartoesDaResposta cartoes={resposta.cartoes} />
        <ResumoDasAtividades atividades={resposta.atividades} abertoDeInicio={passos === "abertos"} />
        {resposta.quandoTexto ? <p className="text-xs text-apagado">{resposta.quandoTexto}</p> : null}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* A resposta em andamento                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Sem ferramenta e sem texto, os pontinhos bastam até aqui; depois, a linha do
 * tempo aparece para contar quanto tempo está levando.
 */
export const ESPERA_ANTES_DA_LINHA_DO_TEMPO_MS = 6_000;

/** "Escrevendo": três pontos na altura de uma linha de texto, no lugar onde o texto vai entrar. */
export function IndicadorDeEscrita() {
  return (
    <div data-indicador-de-escrita="" aria-hidden="true" className="flex h-7 items-center gap-1.5">
      <span className="size-2 animate-escrevendo rounded-full bg-apagado" />
      <span className="size-2 animate-escrevendo rounded-full bg-apagado [animation-delay:160ms]" />
      <span className="size-2 animate-escrevendo rounded-full bg-apagado [animation-delay:320ms]" />
    </div>
  );
}

export function RespostaEmAndamento({ turno }: { turno: Turno }) {
  const loja = useLojaDaConversa();
  const agora = useAgora(true);
  const final = turno.textoFinal;
  const texto = final ?? turno.rascunho;
  const semTexto = !texto;
  const mostrarLinhaDoTempo =
    turno.atividades.length > 0 ||
    turno.fase === "cancelando" ||
    turno.conexao === "reconectando" ||
    (semTexto && agora - turno.iniciadoEm > ESPERA_ANTES_DA_LINHA_DO_TEMPO_MS);
  return (
    <div className="flex gap-3" aria-busy="true">
      <AvatarDaConsultora ativa />
      <div className="min-w-0 flex-1 space-y-3 pt-1">
        <p className="sr-only">O agente está respondendo.</p>
        {mostrarLinhaDoTempo ? <LinhaDoTempoAoVivo turno={turno} aoParar={() => void loja.parar()} /> : null}
        <ResultadosDasAcoes resultados={turno.resultados} />
        {texto ? (
          <TextoDaConsultora
            texto={texto}
            modo={final !== null ? "final" : "rascunho"}
            chave={chaveDaResposta(turno)}
            aoVivo
            chegando={final === null}
          />
        ) : turno.fase !== "cancelando" ? (
          <IndicadorDeEscrita />
        ) : null}
        <CartoesDaResposta cartoes={turno.cartoes} />
      </div>
    </div>
  );
}
