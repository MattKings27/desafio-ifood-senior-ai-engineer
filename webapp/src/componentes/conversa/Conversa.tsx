"use client";

/**
 * A conversa em si: as mensagens, a resposta em andamento, as respostas
 * rápidas e a caixa de texto. A mesma peça vive no painel (ao lado da tela ou
 * em folha) e na página /conversa; a loja por trás é uma só.
 *
 * Acessibilidade (plano, 9.7):
 * - as mensagens são um `role="log"`; enquanto o agente responde, ele fica
 *   `aria-busy`, e nada do rascunho é lido;
 * - um `role="status"` escondido anuncia cada passo que o agente começa ("Olhando
 *   sua despensa") e, no fim, só o texto conferido ("Resposta pronta: …");
 * - o foco nunca pula no fim da resposta.
 *
 * A rolagem acompanha o fim enquanto ela está lá embaixo; se ela subiu para
 * reler, a tela não a arrasta, e aparece "Ir para o fim".
 */

import { ArrowDown } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { Esqueleto } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import { comMaiuscula } from "@/lib/conversa/atividades";
import type { EstadoDaConversa } from "@/lib/conversa/estado";
import { textoPlano } from "@/lib/conversa/markdown";

import { Composer } from "./Composer";
import { EstadoInicial } from "./EstadoInicial";
import { FaixasDaConversa } from "./FaixasDaConversa";
import { MensagemDela, RespostaDaConsultoraNaTela, RespostaEmAndamento, TEXTO_DO_CANCELADO } from "./Mensagem";
import { RespostasRapidas } from "./RespostasRapidas";
import { useLojaDaConversa, useSeletor } from "./useLoja";

/** Até esta distância do fim, ela está "lá embaixo", e a tela acompanha. */
export const PERTO_DO_FIM_PX = 96;

/* -------------------------------------------------------------------------- */
/* O anúncio para o leitor de tela                                             */
/* -------------------------------------------------------------------------- */

/** O que o `role="status"` diz agora, a partir do estado da conversa. */
function useAnuncio(conversa: EstadoDaConversa): string {
  const [anuncio, setAnuncio] = useState("");
  const turno = conversa.turno;
  const ultimaAtividade = turno?.atividades.at(-1);
  const chaveDaAtividade = ultimaAtividade && ultimaAtividade.estado === "fazendo" ? ultimaAtividade.id : null;
  const rotuloDaAtividade = ultimaAtividade?.rotulo ?? "";

  useEffect(() => {
    if (chaveDaAtividade) setAnuncio(`${comMaiuscula(rotuloDaAtividade)}…`);
  }, [chaveDaAtividade, rotuloDaAtividade]);

  // A resposta que acabou de terminar é o último item da lista.
  const ultimo = conversa.itens.at(-1);
  const terminou = ultimo?.tipo === "consultora" && ultimo.id === null ? ultimo : null;
  const chaveDoFim = terminou?.chave ?? null;
  useEffect(() => {
    if (!terminou) return;
    if (terminou.estado === "concluido") {
      const plano = terminou.rascunho ? "" : textoPlano(terminou.texto);
      setAnuncio(plano ? `Resposta pronta: ${plano}` : "Resposta pronta.");
    } else if (terminou.estado === "cancelado") {
      setAnuncio(TEXTO_DO_CANCELADO);
    } else {
      setAnuncio("A resposta não chegou ao fim. A senhora pode perguntar de novo.");
    }
    // Anuncia uma vez por resposta que termina: a chave identifica a resposta.
  }, [chaveDoFim]);

  return anuncio;
}

/* -------------------------------------------------------------------------- */
/* A rolagem                                                                   */
/* -------------------------------------------------------------------------- */

function assinaturaDoConteudo(conversa: EstadoDaConversa): string {
  const turno = conversa.turno;
  return [
    conversa.id,
    conversa.itens.length,
    turno?.rascunho.length ?? -1,
    turno?.textoFinal?.length ?? -1,
    turno?.cartoes.length ?? -1,
    turno?.atividades.length ?? -1,
    turno?.resultados.length ?? -1,
  ].join(":");
}

function useRolagem(conversa: EstadoDaConversa) {
  const rolagem = useRef<HTMLDivElement | null>(null);
  const noFim = useRef(true);
  const [longeDoFim, setLongeDoFim] = useState(false);
  const assinatura = assinaturaDoConteudo(conversa);
  const idDaConversa = conversa.id;
  const ultimo = conversa.itens.at(-1);
  const mandouAgora = ultimo?.tipo === "senhora" ? ultimo.chave : null;

  const irParaOFim = useCallback((suave: boolean) => {
    const elemento = rolagem.current;
    if (!elemento) return;
    const reduzir =
      document.documentElement.getAttribute("data-movimento") === "reduzir" ||
      (typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (typeof elemento.scrollTo === "function") {
      elemento.scrollTo({ top: elemento.scrollHeight, behavior: suave && !reduzir ? "smooth" : "auto" });
    } else {
      elemento.scrollTop = elemento.scrollHeight;
    }
    noFim.current = true;
    setLongeDoFim(false);
  }, []);

  // Ela mandou uma mensagem, ou trocou de conversa: vai para o fim.
  useLayoutEffect(() => {
    noFim.current = true;
  }, [idDaConversa, mandouAgora]);

  // O conteúdo cresceu: acompanha, se ela estava lá embaixo.
  useLayoutEffect(() => {
    if (noFim.current) irParaOFim(false);
  }, [assinatura, irParaOFim]);

  // A resposta aparece letra a letra, depois que o evento já chegou: quem
  // avisa que ela cresceu é o tamanho do conteúdo, não o estado da loja.
  const conteudo = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const elemento = conteudo.current;
    if (!elemento || typeof ResizeObserver !== "function") return;
    const observador = new ResizeObserver(() => {
      if (noFim.current) irParaOFim(false);
    });
    observador.observe(elemento);
    return () => observador.disconnect();
  }, [irParaOFim]);

  const aoRolar = useCallback(() => {
    const elemento = rolagem.current;
    if (!elemento) return;
    const distancia = elemento.scrollHeight - elemento.scrollTop - elemento.clientHeight;
    noFim.current = distancia <= PERTO_DO_FIM_PX;
    setLongeDoFim(!noFim.current);
  }, []);

  return { rolagem, conteudo, longeDoFim, aoRolar, irParaOFim };
}

/* -------------------------------------------------------------------------- */
/* A conversa                                                                  */
/* -------------------------------------------------------------------------- */

function Carregando() {
  return (
    <div role="status" className="space-y-6 py-2">
      <span className="sr-only">Carregando a conversa…</span>
      <div className="flex justify-end">
        <Esqueleto className="h-11 w-2/3 rounded-2xl" />
      </div>
      <div className="flex gap-3">
        <Esqueleto forma="circulo" className="size-9" />
        <div className="flex-1 space-y-2">
          <Esqueleto forma="linha" className="w-11/12" />
          <Esqueleto forma="linha" className="w-4/5" />
          <Esqueleto forma="linha" className="w-1/2" />
        </div>
      </div>
    </div>
  );
}

function Mensagens({ conversa, nivelTitulo, caminho }: { conversa: EstadoDaConversa; nivelTitulo: 2 | 3; caminho: string | null | undefined }) {
  const loja = useLojaDaConversa();

  if (conversa.carregamento === "falhou") {
    return (
      <Problema
        categoria="rede"
        titulo="Não consegui abrir a conversa"
        mensagem={conversa.erro?.mensagem}
        aoTentarDeNovo={() => void loja.abrirConversa(conversa.id)}
      />
    );
  }
  if (conversa.carregamento === "ausente") {
    return (
      <EstadoVazio
        titulo="Essa conversa não existe mais"
        descricao="Ela pode ter sido apagada. Começar outra não apaga nada da despensa nem do cardápio."
        acao={
          <button
            type="button"
            onClick={() => void loja.novaConversa()}
            className="inline-flex min-h-11 items-center rounded-sm px-3 font-semibold text-marca hover:bg-marca/10"
          >
            Começar outra conversa
          </button>
        }
      />
    );
  }
  const vazia = conversa.itens.length === 0 && !conversa.turno;
  if (vazia && conversa.carregamento === "pronto") return <EstadoInicial caminho={caminho} nivelTitulo={nivelTitulo} />;
  if (vazia) return <Carregando />;

  return (
    <div
      role="log"
      aria-live="off"
      aria-label="Mensagens da conversa"
      aria-busy={conversa.turno ? true : undefined}
      className="flex flex-col gap-6"
    >
      {conversa.itens.map((item) =>
        item.tipo === "senhora" ? (
          <MensagemDela key={item.chave} mensagem={item} />
        ) : (
          <RespostaDaConsultoraNaTela key={item.chave} resposta={item} />
        ),
      )}
      {conversa.turno ? <RespostaEmAndamento turno={conversa.turno} /> : null}
    </div>
  );
}

export function Conversa({
  caminho,
  nivelTitulo = 3,
  className,
}: {
  /** A página de onde ela abriu (as sugestões de começo mudam com ela). */
  caminho: string | null | undefined;
  nivelTitulo?: 2 | 3;
  className?: string;
}) {
  const loja = useLojaDaConversa();
  const conversa = useSeletor(loja, (estado) => estado.conversa);
  const anuncio = useAnuncio(conversa);
  const { rolagem, conteudo, longeDoFim, aoRolar, irParaOFim } = useRolagem(conversa);

  useEffect(() => {
    loja.ativar();
  }, [loja]);

  return (
    <div className={clsx("flex h-full min-h-0 flex-col", className)}>
      <FaixasDaConversa />
      <div className="relative min-h-0 flex-1">
        <div ref={rolagem} onScroll={aoRolar} className="rolagem-fina h-full overflow-y-auto overscroll-contain">
          <div ref={conteudo} className="mx-auto w-full max-w-[720px] px-4 py-5 sm:px-5">
            <Mensagens conversa={conversa} nivelTitulo={nivelTitulo} caminho={caminho} />
          </div>
        </div>
        {longeDoFim ? (
          <button
            type="button"
            onClick={() => irParaOFim(true)}
            className={clsx(
              "absolute bottom-3 left-1/2 inline-flex min-h-11 -translate-x-1/2 items-center gap-1.5 rounded-full border border-borda",
              "bg-superficie px-4 text-sm font-semibold text-tinta shadow-flutuante hover:bg-secao",
            )}
          >
            <ArrowDown size={16} weight="bold" aria-hidden="true" />
            Ir para o fim
          </button>
        ) : null}
      </div>
      <div className="border-t border-borda bg-superficie">
        <div className="mx-auto w-full max-w-[720px] space-y-3 px-4 pt-3 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-5">
          <RespostasRapidas caminho={caminho} />
          <Composer />
        </div>
      </div>
      <div role="status" aria-live="polite" className="sr-only">
        {anuncio}
      </div>
    </div>
  );
}
