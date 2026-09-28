"use client";

/**
 * "Procurar mais receitas": pede uma rodada de descoberta e acompanha o fluxo
 * dela (quantas páginas leu, quantas receitas achou). Cada receita achada e o
 * fim da rodada avisam a sincronização, que refaz a página: a grade nova vem
 * da API, com as contagens certas, nunca montada aqui.
 *
 * A primeira visita da sessão com o catálogo vazio e nada procurando pede a
 * rodada sozinha, uma vez. Esse pedido não abre a conversa nem mostra erro:
 * ela não pediu nada. Se a rodada começa, a tela acompanha como no botão.
 *
 * Com a descoberta desligada (501) ou sem a rota (404, 405), o botão abre a
 * conversa com o pedido escrito, para o agente procurar: o botão sempre
 * leva a algum lugar.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ErroDoMotor, MENSAGENS, ehRotaQueFalta } from "@/lib/api/base";
import type { EstadoDaDescoberta, EventoDaDescoberta } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";
import { useSincronizacao } from "@/lib/dados/sincronizacao";
import type { Assinatura } from "@/lib/sse";
import { assinarFluxo } from "@/lib/sse";
import { textoParaEla } from "@/lib/formato";

/** Quantas tentativas seguidas sem abrir o fluxo antes de desistir de acompanhar. */
const TENTATIVAS_SEM_ABRIR = 3;

export const PERDI_A_PROCURA = "Perdi o contato com a procura. As receitas que já apareceram estão na lista.";

/** A marca, nesta aba do navegador, de que a procura sozinha já foi pedida. */
export const CHAVE_DA_PROCURA_SOZINHA = "descoberta-automatica";

/** Sem armazenamento (janela anônima, bloqueio do navegador), vale só a marca da página. */
function jaProcurouSozinha(): boolean {
  try {
    return window.sessionStorage.getItem(CHAVE_DA_PROCURA_SOZINHA) !== null;
  } catch {
    return false;
  }
}

function marcarQueProcurouSozinha(): void {
  try {
    window.sessionStorage.setItem(CHAVE_DA_PROCURA_SOZINHA, "1");
  } catch {
    // Sem armazenamento, a marca da página basta para esta visita.
  }
}

export function useDescoberta(
  inicial: EstadoDaDescoberta,
  {
    semRota,
    catalogoVazio = false,
  }: {
    semRota: (origem: HTMLElement | null) => void;
    /** O catálogo que ela vê está vazio. Vale o que a página trouxe ao abrir. */
    catalogoVazio?: boolean;
  },
) {
  const [procura, setProcura] = useState<EstadoDaDescoberta>(inicial);
  const { avisar } = useSincronizacao();
  const assinatura = useRef<Assinatura | null>(null);
  const semRotaAtual = useRef(semRota);
  const montada = useRef(false);

  useEffect(() => {
    semRotaAtual.current = semRota;
  });

  useEffect(() => {
    montada.current = true;
    return () => {
      montada.current = false;
    };
  }, []);

  const acompanhar = useCallback(
    (url: (desde: number) => string) => {
      assinatura.current?.fechar();
      const fluxo = assinarFluxo<EventoDaDescoberta>({
        url,
        aoEvento: (evento) => {
          if (evento.tipo === "progresso") {
            setProcura({ estado: "procurando", texto: evento.texto, lidas: evento.lidas, encontradas: evento.encontradas });
          } else if (evento.tipo === "fim") {
            setProcura({ estado: evento.estado, texto: evento.texto, lidas: evento.lidas, encontradas: evento.encontradas });
            avisar(["receitas"]);
          } else if (evento.tipo === "erro") {
            setProcura((antes) => ({ ...antes, estado: "erro", texto: evento.texto }));
            avisar(["receitas"]);
          } else {
            avisar(["receitas"]);
          }
        },
        ehFinal: (evento) => evento.tipo === "fim" || evento.tipo === "erro",
        aoFalhar: (falha) => {
          if (!falha.semAbrir || falha.tentativas < TENTATIVAS_SEM_ABRIR) return;
          fluxo.fechar();
          setProcura((antes) => ({ ...antes, estado: "erro", texto: PERDI_A_PROCURA }));
          avisar(["receitas"]);
        },
      });
      assinatura.current = fluxo;
    },
    [avisar],
  );

  const acompanhando = () => Boolean(assinatura.current && assinatura.current.estado !== "encerrada");

  // A página abriu com uma rodada já em andamento (pedida em outra aba, ou pelo
  // agente): acompanha o fluxo geral. Fechar a página fecha o fluxo.
  const doComeco = useRef(inicial);
  useEffect(() => {
    if (doComeco.current.estado === "procurando") acompanhar((desde) => receitas.urlDaDescoberta(desde || undefined));
    return () => assinatura.current?.fechar();
  }, [acompanhar]);

  // O servidor refez a página: o que ele diz da descoberta vale, menos no meio
  // de uma rodada que esta tela acompanha. Uma rodada que começou em outro
  // lugar passa a ser acompanhada.
  useEffect(() => {
    if (inicial === doComeco.current) return;
    doComeco.current = inicial;
    setProcura((antes) => (antes.estado === "procurando" && acompanhando() ? antes : inicial));
    if (inicial.estado === "procurando" && !acompanhando()) {
      acompanhar((desde) => receitas.urlDaDescoberta(desde || undefined));
    }
  }, [inicial, acompanhar]);

  /**
   * O pedido do botão mostra na hora que começou e responde por qualquer
   * falha. O pedido sozinho só aparece quando a rodada começa de fato. A
   * resposta que chega depois de a tela fechar não abre fluxo nenhum.
   */
  const pedir = useCallback(
    async (origem: HTMLElement | null, sozinha: boolean) => {
      if (!sozinha) setProcura((antes) => ({ ...antes, estado: "procurando", texto: "Começando a procurar receitas…" }));
      try {
        const inicio = await receitas.descobrir();
        if (!montada.current) return;
        setProcura({ estado: inicio.estado, texto: inicio.texto, lidas: 0, encontradas: 0 });
        acompanhar((desde) => receitas.urlDaRodada(inicio.eventos, desde || undefined));
      } catch (causa) {
        // Desligada, sem a rota ou recusada: quem não pediu não vê nada.
        if (sozinha) return;
        if (ehRotaQueFalta(causa)) {
          setProcura(inicial);
          semRotaAtual.current(origem);
          return;
        }
        const mensagem = causa instanceof ErroDoMotor ? textoParaEla(causa.message, MENSAGENS.rede) : MENSAGENS.rede;
        setProcura((antes) => ({ ...antes, estado: "erro", texto: mensagem }));
      }
    },
    [acompanhar, inicial],
  );

  const procurar = useCallback((origem: HTMLElement | null) => pedir(origem, false), [pedir]);

  // A primeira visita da sessão com o catálogo vazio e nada procurando: pede
  // uma rodada sozinha, uma vez. A marca desta montagem segura o efeito que o
  // React roda duas vezes em desenvolvimento; a da sessão, a volta à tela.
  const vazioAoAbrir = useRef(catalogoVazio);
  const jaPediuSozinha = useRef(false);
  useEffect(() => {
    if (jaPediuSozinha.current) return;
    jaPediuSozinha.current = true;
    if (!vazioAoAbrir.current || doComeco.current.estado !== "parada" || jaProcurouSozinha()) return;
    marcarQueProcurouSozinha();
    void pedir(null, true);
  }, [pedir]);

  return { procura, procurar };
}
