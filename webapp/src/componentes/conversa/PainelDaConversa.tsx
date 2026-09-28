"use client";

/**
 * O painel da conversa, por cima de qualquer tela (menos a própria /conversa).
 *
 * - **A partir de 1024 px**: um `<aside>` de 420 px preso à direita, não
 *   modal. A página anda para o lado (`data-painel` no `<html>`), então nada
 *   fica escondido atrás dele, e ela continua usando a tela enquanto conversa.
 * - **Abaixo disso**: uma folha modal de altura total, por cima da página.
 *
 * Os dois abrem pela pílula do cabeçalho, pelo botão flutuante, pelo
 * Conversar da barra de baixo e pelo "Perguntar" dos cards, sempre com o
 * contexto da página. Esc fecha, e o foco volta para quem abriu. "Abrir em
 * tela cheia" leva à página da conversa, com a lista de conversas ao lado.
 */

import { ArrowsOut, NotePencil, X } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { KeyboardEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { BotaoIcone } from "@/componentes/compartilhados/Botao";
import { useDialogoNativo } from "@/componentes/compartilhados/Dialogo";

import { Conversa } from "./Conversa";
import { AvatarDaConsultora } from "./Mensagem";
import { ehPaginaDaConversa, useConversa, useQuemAbriu } from "./ProvedorDaConversa";
import { ATRIBUTO_DA_ENTRADA } from "./useEntradaDaConversa";
import { useLojaDaConversa, useSeletor } from "./useLoja";
import { TELA_LARGA, useMidia } from "./useMidia";

/** O nome do painel para o leitor de tela (a região e a folha). */
export const TITULO_DO_PAINEL = "Conversa com o agente";

/** O que o cabeçalho do painel mostra: curto, porque divide a linha com três botões. */
export const TITULO_VISIVEL_DO_PAINEL = "Seu agente";

/** O tempo da folha descendo (a `duration-lenta` do CSS), antes de desmontar a conversa. */
export const TEMPO_DE_SAIDA_MS = 450;

const CLASSE_DO_ICONE_LINK =
  "inline-flex size-11 shrink-0 items-center justify-center rounded-sm text-texto transition-colors duration-rapida hover:bg-secao";

function CabecalhoDoPainel({ aoFechar }: { aoFechar: () => void }) {
  const loja = useLojaDaConversa();
  const titulo = useSeletor(loja, (estado) => estado.conversa.titulo);
  const id = useSeletor(loja, (estado) => estado.conversa.id);
  return (
    <div className="flex h-16 shrink-0 items-center gap-2 border-b border-borda pr-2 pl-4">
      <AvatarDaConsultora />
      <div className="min-w-0 flex-1 pl-1">
        <h2 className="truncate font-titulo text-base leading-tight font-bold text-tinta">{TITULO_VISIVEL_DO_PAINEL}</h2>
        {titulo ? <p className="truncate text-sm text-apagado">{titulo}</p> : null}
      </div>
      <BotaoIcone rotulo="Começar outra conversa" onClick={() => void loja.novaConversa()}>
        <NotePencil size={20} weight="bold" />
      </BotaoIcone>
      <Link
        href={id ? `/conversa?c=${encodeURIComponent(id)}` : "/conversa"}
        aria-label="Abrir em tela cheia"
        title="Abrir em tela cheia"
        className={CLASSE_DO_ICONE_LINK}
      >
        <ArrowsOut size={20} weight="bold" aria-hidden="true" />
      </Link>
      <BotaoIcone rotulo="Fechar a conversa" onClick={aoFechar}>
        <X size={20} weight="bold" />
      </BotaoIcone>
    </div>
  );
}

/** No computador: preso à direita, a página anda para o lado. */
function PainelAoLado({ caminho, aoFechar }: { caminho: string; aoFechar: () => void }) {
  useEffect(() => {
    const raiz = document.documentElement;
    raiz.setAttribute("data-painel", "aberto");
    return () => raiz.removeAttribute("data-painel");
  }, []);

  const aoTeclar = (evento: KeyboardEvent<HTMLElement>) => {
    if (evento.key !== "Escape" || evento.defaultPrevented) return;
    // O Esc de um diálogo aberto de dentro (confirmar um preço) é dele.
    if (evento.target instanceof Element && evento.target.closest("dialog[open]")) return;
    evento.preventDefault();
    aoFechar();
  };

  return (
    // O Esc fecha o painel a partir de qualquer coisa de dentro dele.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <aside
      aria-label={TITULO_DO_PAINEL}
      onKeyDown={aoTeclar}
      className="fixed inset-y-0 right-0 z-40 flex w-[var(--largura-do-painel)] flex-col border-l border-borda bg-superficie shadow-flutuante transition-[translate] duration-lenta ease-padrao starting:translate-x-full"
    >
      <CabecalhoDoPainel aoFechar={aoFechar} />
      <Conversa caminho={caminho} nivelTitulo={3} className="flex-1" />
    </aside>
  );
}

/** No celular: uma folha modal de altura total. */
function PainelEmFolha({ aberto, caminho, aoFechar }: { aberto: boolean; caminho: string; aoFechar: () => void }) {
  const { ref, aoFecharNativo, fechar } = useDialogoNativo(aberto, aoFechar);
  // A conversa entra depois de a folha abrir (e o foco ir para a caixa), e sai
  // depois de ela terminar de descer.
  const [comConversa, setComConversa] = useState(false);
  useEffect(() => {
    if (aberto) {
      setComConversa(true);
      return;
    }
    const relogio = setTimeout(() => setComConversa(false), TEMPO_DE_SAIDA_MS);
    return () => clearTimeout(relogio);
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      aria-label={TITULO_DO_PAINEL}
      onClose={aoFecharNativo}
      className="m-0 mt-auto h-dvh max-h-dvh w-full max-w-none overflow-hidden border-0 bg-superficie p-0 text-texto backdrop:bg-black/50 translate-y-full transition-[translate,display,overlay] transition-discrete duration-lenta ease-padrao open:translate-y-0 starting:open:translate-y-full"
    >
      <div className="flex h-full flex-col">
        <CabecalhoDoPainel aoFechar={fechar} />
        {comConversa ? <Conversa caminho={caminho} nivelTitulo={3} className="flex-1" /> : null}
      </div>
    </dialog>
  );
}

/** Quem estava visível para receber o foco de volta: quem abriu, ou uma das entradas. */
function devolverFoco(quemAbriu: { current: HTMLElement | null }) {
  const alvo = quemAbriu.current;
  quemAbriu.current = null;
  if (alvo?.isConnected && !alvo.hidden) {
    alvo.focus({ preventScroll: true });
    return;
  }
  const entradas = Array.from(document.querySelectorAll<HTMLElement>(`[${ATRIBUTO_DA_ENTRADA}]`));
  entradas.find((entrada) => entrada.getClientRects().length > 0)?.focus({ preventScroll: true });
}

export function PainelDaConversa() {
  const { aberta, fechar } = useConversa();
  const larga = useMidia(TELA_LARGA);
  const caminho = usePathname();
  const quemAbriu = useQuemAbriu();
  const estavaAberta = useRef(aberta);
  const caminhoAoAbrir = useRef(caminho);

  // Fechou na mesma página em que abriu: o foco volta para quem abriu. Se ela
  // foi para outra página (um link de dentro da conversa), o foco é da página nova.
  useEffect(() => {
    const abriu = !estavaAberta.current && aberta;
    const fechou = estavaAberta.current && !aberta;
    estavaAberta.current = aberta;
    if (abriu) caminhoAoAbrir.current = caminho;
    if (fechou && caminho === caminhoAoAbrir.current) devolverFoco(quemAbriu);
  }, [aberta, caminho, quemAbriu]);

  if (ehPaginaDaConversa(caminho)) return null;
  if (larga) return aberta ? <PainelAoLado caminho={caminho} aoFechar={fechar} /> : null;
  return <PainelEmFolha aberto={aberta} caminho={caminho} aoFechar={fechar} />;
}
