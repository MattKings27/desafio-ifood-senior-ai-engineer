"use client";

/**
 * A caixa de texto da conversa.
 *
 * - Cresce de 1 a 5 linhas; depois disso, rola por dentro.
 * - No computador, Enter envia e Shift com Enter pula uma linha. No toque,
 *   Enter pula uma linha (o teclado do celular não tem Shift à mão), e quem
 *   envia é o botão.
 * - Enquanto o agente responde, "Parar" toma o lugar de "Enviar". Ela pode
 *   continuar escrevendo a próxima mensagem, que sai quando a resposta acabar.
 * - Até 2.000 caracteres; perto do limite, um contador aparece.
 * - Sem internet, ou com o agente fora do ar, a caixa fica desabilitada, e
 *   a faixa de cima diz por quê.
 *
 * O chip "Vendo: Arroz branco tipo 1" diz o que vai junto com a mensagem (o
 * que ela estava olhando quando abriu a conversa), e sai com o ✕.
 */

import { Eye, PaperPlaneRight, Stop, X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { KeyboardEvent } from "react";
import { useCallback, useEffect, useId, useLayoutEffect, useRef } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import type { ContextoDaConversa } from "@/lib/api/conversa";
import { LIMITE_DE_CARACTERES } from "@/lib/conversa/loja";
import { rotuloDoContexto } from "@/lib/conversa/sugestoes";
import { formatarNumero } from "@/lib/formato";

import { useLojaDaConversa, useSeletor } from "./useLoja";
import { TOQUE, useMidia } from "./useMidia";

/** A partir daqui, o contador de caracteres aparece. */
export const CONTADOR_A_PARTIR_DE = 1_500;

export const MAXIMO_DE_LINHAS = 5;

export const DICA_DO_TECLADO = "Enter envia. Shift e Enter pulam uma linha.";

export function ChipDeContexto({ contexto, aoTirar }: { contexto: ContextoDaConversa; aoTirar: () => void }) {
  const rotulo = rotuloDoContexto(contexto);
  return (
    <div className="inline-flex h-9 max-w-full items-center gap-1.5 rounded-full border border-info/25 bg-info/10 pl-3 text-sm text-info">
      <Eye size={16} weight="bold" aria-hidden="true" className="shrink-0" />
      <span className="min-w-0 truncate">
        <span className="font-semibold">Vendo:</span> {rotulo}
        <span className="sr-only">. O agente vai saber o que a senhora está vendo.</span>
      </span>
      <button
        type="button"
        onClick={aoTirar}
        aria-label={`Tirar da mensagem: ${rotulo}`}
        title="Tirar da mensagem"
        className="-my-1 inline-flex size-11 shrink-0 items-center justify-center rounded-full hover:bg-info/10"
      >
        <X size={16} weight="bold" aria-hidden="true" />
      </button>
    </div>
  );
}

function Contador({ id, tamanho }: { id: string; tamanho: number }) {
  if (tamanho < CONTADOR_A_PARTIR_DE) return null;
  const cheio = tamanho >= LIMITE_DE_CARACTERES;
  return (
    <span id={id} className={clsx("numero shrink-0", cheio ? "font-semibold text-atencao" : "text-apagado")}>
      {cheio
        ? `Chegou ao limite de ${formatarNumero(LIMITE_DE_CARACTERES)} caracteres.`
        : `${formatarNumero(tamanho)} de ${formatarNumero(LIMITE_DE_CARACTERES)} caracteres`}
    </span>
  );
}

export function Composer({ className }: { className?: string }) {
  const loja = useLojaDaConversa();
  const caixa = useSeletor(loja, (estado) => estado.caixa);
  const fase = useSeletor(loja, (estado) => estado.conversa.turno?.fase ?? null);
  const temTurno = useSeletor(loja, (estado) => Boolean(estado.conversa.turno?.id));
  const online = useSeletor(loja, (estado) => estado.online);
  const disponivel = useSeletor(loja, (estado) => estado.disponibilidade.disponivel);
  const carregando = useSeletor(loja, (estado) => estado.conversa.carregamento === "carregando");
  const toque = useMidia(TOQUE);
  const area = useRef<HTMLTextAreaElement | null>(null);
  const id = useId();

  const respondendo = fase !== null;
  const bloqueada = !online || !disponivel;
  const vazio = caixa.texto.trim() === "";
  const naoEnvia = vazio || bloqueada || carregando;

  const ajustar = useCallback(() => {
    const elemento = area.current;
    if (!elemento) return;
    const estilo = window.getComputedStyle(elemento);
    const linha = Number.parseFloat(estilo.lineHeight) || 24;
    const bordas = (Number.parseFloat(estilo.paddingTop) || 0) + (Number.parseFloat(estilo.paddingBottom) || 0);
    const maximo = linha * MAXIMO_DE_LINHAS + bordas;
    elemento.style.height = "auto";
    elemento.style.height = `${Math.min(elemento.scrollHeight, maximo)}px`;
    elemento.style.overflowY = elemento.scrollHeight > maximo ? "auto" : "hidden";
  }, []);

  useLayoutEffect(ajustar, [ajustar, caixa.texto]);

  // Alguém pediu a caixa (abriu o painel, tocou em "Perguntar"): o foco vem
  // para cá, com o cursor no fim. No toque, só quando há rascunho: abrir o
  // teclado sem ela pedir cobriria a conversa.
  useEffect(() => {
    if (caixa.foco === 0) return;
    const elemento = area.current;
    if (!elemento || elemento.disabled) return;
    if (toque && elemento.value.trim() === "") return;
    elemento.focus({ preventScroll: true });
    const fim = elemento.value.length;
    elemento.setSelectionRange(fim, fim);
    // Só o pedido de foco manda aqui; o resto é lido do próprio elemento.
  }, [caixa.foco, toque]);

  const enviar = () => {
    if (naoEnvia || respondendo) return;
    void loja.enviarDaCaixa();
    // Quem mandou pelo botão, com o teclado, continua na caixa: o botão vira
    // "Parar" e um segundo Enter ali pararia a resposta.
    if (!toque) area.current?.focus({ preventScroll: true });
  };

  const aoTeclar = (evento: KeyboardEvent<HTMLTextAreaElement>) => {
    if (evento.key !== "Enter" || evento.shiftKey || evento.nativeEvent.isComposing || toque) return;
    evento.preventDefault();
    enviar();
  };

  const idDaDica = `${id}-dica`;
  const idDoContador = `${id}-contador`;
  const descritoPor = [!toque ? idDaDica : null, caixa.texto.length >= CONTADOR_A_PARTIR_DE ? idDoContador : null]
    .filter(Boolean)
    .join(" ");

  return (
    <form
      aria-label="Mandar mensagem para o agente"
      className={clsx("space-y-2", className)}
      onSubmit={(evento) => {
        evento.preventDefault();
        enviar();
      }}
    >
      {caixa.contexto ? (
        <ChipDeContexto contexto={caixa.contexto} aoTirar={() => loja.definirContexto(null)} />
      ) : null}
      <div
        className={clsx(
          "flex items-end gap-2 rounded-xl border p-1.5 pl-3 transition-colors duration-rapida",
          bloqueada
            ? "border-borda bg-secao"
            : "border-borda-campo bg-superficie focus-within:border-tinta focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-marca",
        )}
      >
        <label htmlFor={id} className="sr-only">
          Mensagem para o agente
        </label>
        <textarea
          ref={area}
          id={id}
          rows={1}
          value={caixa.texto}
          maxLength={LIMITE_DE_CARACTERES}
          disabled={bloqueada}
          placeholder={bloqueada ? "A conversa volta quando o agente estiver de novo no ar" : "Escreva sua pergunta…"}
          enterKeyHint={toque ? "enter" : "send"}
          aria-describedby={descritoPor || undefined}
          onChange={(evento) => loja.definirTexto(evento.target.value)}
          onKeyDown={aoTeclar}
          className={clsx(
            "block min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent py-2.5 text-base leading-6 text-tinta",
            "placeholder:text-apagado focus-visible:outline-none disabled:cursor-not-allowed disabled:text-apagado",
          )}
        />
        {respondendo ? (
          <Botao
            key="parar"
            variante="terciario"
            tamanho="sm"
            icone={<Stop size={18} weight="fill" />}
            carregando={fase === "cancelando"}
            rotuloCarregando="Parando…"
            aria-disabled={!temTurno || undefined}
            onClick={() => {
              if (temTurno) void loja.parar();
            }}
          >
            Parar
          </Botao>
        ) : (
          <Botao
            key="enviar"
            type="submit"
            variante="primario"
            tamanho="sm"
            icone={<PaperPlaneRight size={18} weight="fill" />}
            aria-disabled={naoEnvia || undefined}
            // O clique não tira o foco da caixa: ela segue escrevendo, e no
            // celular o teclado não fecha a cada mensagem.
            onMouseDown={(evento) => evento.preventDefault()}
          >
            Enviar
          </Botao>
        )}
      </div>
      <div className="flex min-h-5 items-start justify-between gap-3 px-1 text-xs">
        {toque ? <span /> : <span id={idDaDica} className="text-apagado">{DICA_DO_TECLADO}</span>}
        <Contador id={idDoContador} tamanho={caixa.texto.length} />
      </div>
    </form>
  );
}
