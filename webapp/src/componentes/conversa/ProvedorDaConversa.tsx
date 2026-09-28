"use client";

/**
 * O provedor da conversa, no layout raiz: a loja única (a conversa sobrevive à
 * navegação), o painel aberto ou fechado, e a API pública que o resto da
 * interface usa:
 *
 *     const { abrir } = useConversa();
 *     abrir({ rascunho: "Dá pra eu fazer Bolo de cenoura?", contexto: { tela: "receitas", tipo: "receita", id, rotulo } });
 *
 * `abrir` abre o painel (computador) ou a folha (celular) com o rascunho na
 * caixa e o chip do contexto. **Nunca envia sozinho**: quem manda é ela. Na
 * própria página /conversa, só preenche a caixa. `abrirDaPagina` é a entrada
 * geral (a pílula, o botão flutuante, o Conversar da barra de baixo): abre com
 * o contexto da página em que ela está ("Vendo: Despensa").
 *
 * O painel aberto entra no histórico (`?conversa=1`), para o "voltar" do
 * Android fechar o painel em vez de sair da página. Também moram aqui o
 * prefixo do título da aba ("Respondendo…", "(1)") e a checagem, ao carregar a
 * página, de um turno que ainda está rodando.
 */

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "@/componentes/compartilhados/Toast";
import type { ContextoDaConversa } from "@/lib/api/conversa";
import { useSincronizacao } from "@/lib/dados/sincronizacao";
import type { Loja } from "@/lib/conversa/loja";
import { criarLoja } from "@/lib/conversa/loja";
import { contextoDaPagina } from "@/lib/conversa/sugestoes";
import type { Transporte } from "@/lib/conversa/transporte";
import { transporteReal } from "@/lib/conversa/transporte";

import { ContextoDaLoja, useSeletor } from "./useLoja";
import { TELA_LARGA, consultarMidia } from "./useMidia";

export type PedidoDeAbertura = {
  /** O começo da pergunta, em primeira pessoa ("Dá pra eu fazer Bolo de cenoura?"). */
  rascunho?: string;
  /** De onde ela abriu: a tela e o que estava olhando. */
  contexto?: ContextoDaConversa;
  /** Quem abriu (o botão tocado): é para ele que o foco volta quando a conversa fecha. */
  origem?: HTMLElement | null;
};

export type ValorDaConversa = {
  abrir: (pedido?: PedidoDeAbertura) => void;
  /** A entrada geral: abre com o contexto da página em que ela está. */
  abrirDaPagina: (origem?: HTMLElement | null) => void;
  fechar: () => void;
  /** O painel (ou a folha) da conversa está aberto. */
  aberta: boolean;
  /** O agente está respondendo (acende o ponto no botão Conversar). */
  respondendo: boolean;
  /** Respostas que chegaram com a conversa fora da vista ("1 resposta nova"). */
  naoLidas: number;
};

/** O parâmetro da URL do painel aberto. */
export const PARAMETRO_DO_PAINEL = "conversa";

/** A marca no estado do histórico da entrada que o painel acrescentou. */
export const MARCA_DO_HISTORICO = "__painelDaConversa";

export const PREFIXO_RESPONDENDO = "Respondendo… ";

const PREFIXOS_DO_TITULO = /^(?:Respondendo… |\(\d+\) )/;

/** O endereço da página da conversa com o rascunho e o contexto (sem JavaScript, ou num link). */
export function enderecoDaConversa({ rascunho, contexto }: PedidoDeAbertura = {}): string {
  const busca = new URLSearchParams();
  if (rascunho?.trim()) busca.set("rascunho", rascunho);
  if (contexto) {
    busca.set("tela", contexto.tela);
    busca.set("tipo", contexto.tipo);
    if (contexto.id) busca.set("id", contexto.id);
    if (contexto.rotulo) busca.set("rotulo", contexto.rotulo);
  }
  const texto = busca.toString();
  return texto ? `/conversa?${texto}` : "/conversa";
}

/** A página inteira da conversa: ali não há painel, a conversa já é a página. */
export function ehPaginaDaConversa(caminho: string | null | undefined): boolean {
  return caminho === "/conversa" || Boolean(caminho?.startsWith("/conversa/"));
}

const SEM_PROVEDOR: ValorDaConversa = {
  abrir: () => {},
  abrirDaPagina: () => {},
  fechar: () => {},
  aberta: false,
  respondendo: false,
  naoLidas: 0,
};

const Contexto = createContext<ValorDaConversa>(SEM_PROVEDOR);

/** Quem estava com o foco quando o painel abriu: é para lá que o foco volta. */
const ContextoDeQuemAbriu = createContext<{ current: HTMLElement | null }>({ current: null });

export function useQuemAbriu() {
  return useContext(ContextoDeQuemAbriu);
}

function urlSemPainel(): URL {
  const url = new URL(window.location.href);
  url.searchParams.delete(PARAMETRO_DO_PAINEL);
  return url;
}

/** O contexto da página aberta agora, com o nome que o título dela mostra. */
export function contextoDaPaginaAtual(): ContextoDaConversa | undefined {
  const titulo = document.querySelector("main h1")?.textContent ?? null;
  return contextoDaPagina(window.location.pathname, titulo);
}

function mesmoAssunto(a: ContextoDaConversa | null, b: ContextoDaConversa): boolean {
  return Boolean(a) && a?.tela === b.tela && a?.tipo === b.tipo && (a?.id ?? "") === (b.id ?? "");
}

function marcadoNoHistorico(): boolean {
  const estado: unknown = window.history.state;
  return typeof estado === "object" && estado !== null && (estado as Record<string, unknown>)[MARCA_DO_HISTORICO] === true;
}

export function ProvedorDaConversa({
  children,
  loja: lojaDeFora,
  transporte,
}: {
  children: ReactNode;
  /** Para os testes: uma loja pronta. */
  loja?: Loja;
  /** Para os testes: o transporte da loja que o provedor cria. */
  transporte?: Transporte;
}) {
  const { avisar } = useSincronizacao();
  const avisarAtual = useRef(avisar);
  useEffect(() => {
    avisarAtual.current = avisar;
  });

  const [loja] = useState<Loja>(
    () =>
      lojaDeFora ??
      criarLoja({
        transporte: transporte ?? transporteReal(),
        avisar: (recursos) => avisarAtual.current(recursos),
      }),
  );
  const quemAbriu = useRef<HTMLElement | null>(null);
  const caminho = usePathname();
  const caminhoAnterior = useRef(caminho);

  const aberta = useSeletor(loja, (estado) => estado.painelAberto);
  const respondendo = useSeletor(loja, (estado) => estado.conversa.turno !== null);
  const naoLidas = useSeletor(loja, (estado) => estado.naoLidas);

  const abrirPainel = useCallback(() => {
    if (loja.ler().painelAberto) return;
    const url = new URL(window.location.href);
    url.searchParams.set(PARAMETRO_DO_PAINEL, "1");
    window.history.pushState({ [MARCA_DO_HISTORICO]: true }, "", url);
    loja.definirPainel(true);
  }, [loja]);

  const fechar = useCallback(() => {
    if (!loja.ler().painelAberto) return;
    loja.definirPainel(false);
    if (marcadoNoHistorico()) {
      // A entrada que o painel acrescentou sai do histórico: "voltar" não reabre.
      window.history.back();
      return;
    }
    if (new URLSearchParams(window.location.search).has(PARAMETRO_DO_PAINEL)) {
      window.history.replaceState(window.history.state, "", urlSemPainel());
    }
  }, [loja]);

  const abrir = useCallback(
    (pedido: PedidoDeAbertura = {}) => {
      const temRascunho = Boolean(pedido.rascunho?.trim());
      if (temRascunho || pedido.contexto) {
        loja.preencher({ rascunho: pedido.rascunho, contexto: pedido.contexto ?? null });
      } else {
        loja.pedirFoco();
      }
      loja.ativar();
      if (ehPaginaDaConversa(window.location.pathname)) return;
      if (!loja.ler().painelAberto) {
        const ativo = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        quemAbriu.current = pedido.origem ?? ativo;
      }
      abrirPainel();
    },
    [abrirPainel, loja],
  );

  const abrirDaPagina = useCallback(
    (origem?: HTMLElement | null) => {
      const daPagina = contextoDaPaginaAtual();
      const atual = loja.ler().caixa.contexto;
      // Um contexto mais preciso da mesma página (o card que ela tocou) fica.
      if (!daPagina || mesmoAssunto(atual, daPagina) || (atual && atual.tela === daPagina.tela && daPagina.tipo === "tela")) {
        abrir({ origem });
        return;
      }
      abrir({ contexto: daPagina, origem });
    },
    [abrir, loja],
  );

  // Os avisos da loja (não consegui apagar, ainda estou respondendo) viram toast.
  const { mostrar } = useToast();
  const aviso = useSeletor(loja, (estado) => estado.aviso);
  useEffect(() => {
    if (!aviso) return;
    mostrar({ texto: aviso.texto, tom: aviso.tom });
    loja.limparAviso();
  }, [aviso, loja, mostrar]);

  // O "voltar" e o "avançar" do navegador abrem e fecham o painel; a URL com
  // `?conversa=1` ao carregar (ela recarregou com o painel aberto) também abre.
  useEffect(() => {
    const aoNavegar = () => {
      const quer =
        new URLSearchParams(window.location.search).get(PARAMETRO_DO_PAINEL) === "1" &&
        !ehPaginaDaConversa(window.location.pathname);
      if (quer) loja.ativar();
      loja.definirPainel(quer);
    };
    aoNavegar();
    window.addEventListener("popstate", aoNavegar);
    return () => window.removeEventListener("popstate", aoNavegar);
  }, [loja]);

  // Na página da conversa, o painel não existe. No celular, trocar de página
  // fecha a folha (ela cobre a tela inteira: a página nova ficaria escondida).
  useEffect(() => {
    const mudou = caminhoAnterior.current !== caminho;
    caminhoAnterior.current = caminho;
    if (!loja.ler().painelAberto) return;
    if (ehPaginaDaConversa(caminho) || (mudou && !consultarMidia(TELA_LARGA))) loja.definirPainel(false);
  }, [caminho, loja]);

  // A conversa está à vista? Então nada é "resposta nova".
  useEffect(() => {
    const atualizar = () =>
      loja.definirVisivel((aberta || ehPaginaDaConversa(caminho)) && document.visibilityState === "visible");
    atualizar();
    document.addEventListener("visibilitychange", atualizar);
    return () => document.removeEventListener("visibilitychange", atualizar);
  }, [aberta, caminho, loja]);

  // Sem internet, a caixa não manda (e diz por quê).
  useEffect(() => {
    const ligar = () => loja.definirOnline(true);
    const desligar = () => loja.definirOnline(false);
    loja.definirOnline(typeof navigator === "undefined" || navigator.onLine !== false);
    window.addEventListener("online", ligar);
    window.addEventListener("offline", desligar);
    return () => {
      window.removeEventListener("online", ligar);
      window.removeEventListener("offline", desligar);
    };
  }, [loja]);

  // O título da aba: "Respondendo… " enquanto ela trabalha, "(1) " com resposta nova.
  useEffect(() => {
    const prefixo = respondendo ? PREFIXO_RESPONDENDO : naoLidas > 0 ? `(${naoLidas}) ` : "";
    const aplicar = () => {
      const novo = prefixo + document.title.replace(PREFIXOS_DO_TITULO, "");
      if (document.title !== novo) document.title = novo;
    };
    aplicar();
    if (!prefixo) return;
    // O Next troca o título a cada página: o prefixo volta junto.
    const observador = new MutationObserver(aplicar);
    observador.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => observador.disconnect();
  }, [respondendo, naoLidas]);

  // Recarregou a página no meio de uma resposta? O selo do Conversar acende
  // (e a resposta nova é contada) mesmo sem ela abrir a conversa.
  useEffect(() => {
    const relogio = setTimeout(() => void loja.verificarEmSegundoPlano(), 1_500);
    return () => clearTimeout(relogio);
  }, [loja]);

  const valor = useMemo<ValorDaConversa>(
    () => ({ abrir, abrirDaPagina, fechar, aberta, respondendo, naoLidas }),
    [abrir, abrirDaPagina, fechar, aberta, respondendo, naoLidas],
  );

  return (
    <ContextoDaLoja.Provider value={loja}>
      <ContextoDeQuemAbriu.Provider value={quemAbriu}>
        <Contexto.Provider value={valor}>{children}</Contexto.Provider>
      </ContextoDeQuemAbriu.Provider>
    </ContextoDaLoja.Provider>
  );
}

export function useConversa(): ValorDaConversa {
  return useContext(Contexto);
}
