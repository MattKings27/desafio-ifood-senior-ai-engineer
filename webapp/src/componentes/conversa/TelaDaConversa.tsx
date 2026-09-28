"use client";

/**
 * A página /conversa: a conversa em tela cheia.
 *
 * - No computador, a lista de conversas (300 px) ao lado da conversa, que
 *   ocupa no máximo 720 px de largura, para as linhas não ficarem compridas
 *   demais de ler.
 * - No celular, a conversa ocupa a tela entre o cabeçalho e a barra de baixo,
 *   e a lista abre numa folha, pelo botão "Conversas".
 *
 * O endereço acompanha a conversa aberta (`?c=`), então recarregar volta para
 * ela, inclusive no meio de uma resposta. Quem chega por um link com
 * `?rascunho=` (sem JavaScript no card, ou de outra aba) encontra a caixa já
 * escrita, e nada é enviado sozinho.
 */

import { List, NotePencil } from "@phosphor-icons/react/dist/ssr";
import { useEffect, useId, useRef, useState } from "react";

import { BotaoIcone } from "@/componentes/compartilhados/Botao";
import { Folha } from "@/componentes/compartilhados/Folha";
import type { ChegadaNaConversa } from "@/lib/conversa/chegada";

import { Conversa } from "./Conversa";
import { ListaDeConversas } from "./ListaDeConversas";
import { TITULO_DO_PAINEL } from "./PainelDaConversa";
import { useLojaDaConversa, useSeletor } from "./useLoja";

/** Os parâmetros de chegada que saem do endereço depois de usados. */
export const PARAMETROS_DE_CHEGADA = ["rascunho", "tela", "tipo", "id", "rotulo", "comecar"] as const;

/** O que o "Responder agora" do Início diz por ela: uma resposta rápida, como os chips da conversa. */
export const PEDIDO_DA_COZINHA = "Quero descobrir o que eu consigo cozinhar com certeza.";

export function TelaDaConversa({ chegada = {} }: { chegada?: ChegadaNaConversa }) {
  const loja = useLojaDaConversa();
  const idDaConversa = useSeletor(loja, (estado) => estado.conversa.id);
  const titulo = useSeletor(loja, (estado) => estado.conversa.titulo);
  const [listaAberta, setListaAberta] = useState(false);
  const idDoTitulo = useId();

  // A chegada vale uma vez: a conversa pedida e o rascunho do link.
  const [{ conversa, rascunho, contexto, comecar }] = useState(chegada);
  useEffect(() => {
    if (comecar) return;
    if (conversa) void loja.trocarConversa(conversa);
    if (rascunho?.trim() || contexto) loja.preencher({ rascunho, contexto: contexto ?? null });
  }, [loja, conversa, rascunho, contexto, comecar]);

  // "Responder agora" no Início: quando a loja estiver pronta para mandar, uma
  // conversa nova com o pedido dela, uma vez só, e o agente conduz dali.
  const pronto = useSeletor(
    loja,
    (e) => e.online && e.disponibilidade.disponivel && e.conversa.carregamento !== "carregando" && !e.conversa.turno,
  );
  const comecou = useRef(false);
  useEffect(() => {
    if (comecar !== "cozinha" || comecou.current || !pronto) return;
    comecou.current = true;
    void (async () => {
      if (await loja.novaConversa()) {
        await loja.enviar(PEDIDO_DA_COZINHA, { contexto: { tela: "inicio", tipo: "proximo_passo", rotulo: "Responder agora" } });
      }
    })();
  }, [loja, comecar, pronto]);

  // O endereço acompanha a conversa aberta, sem o rascunho de chegada.
  useEffect(() => {
    if (!idDaConversa) return;
    const url = new URL(window.location.href);
    const tinhaChegada = PARAMETROS_DE_CHEGADA.some((nome) => url.searchParams.has(nome));
    if (url.searchParams.get("c") === idDaConversa && !tinhaChegada) return;
    url.searchParams.set("c", idDaConversa);
    for (const nome of PARAMETROS_DE_CHEGADA) url.searchParams.delete(nome);
    window.history.replaceState(window.history.state, "", url);
  }, [idDaConversa]);

  return (
    <div className="-mx-4 -mt-6 -mb-10 flex h-[calc(100dvh-3.5rem-var(--altura-barra-inferior)-env(safe-area-inset-bottom))] sm:-mx-6 lg:mx-0 lg:mt-0 lg:-mb-18 lg:h-[calc(100dvh-10.5rem)] lg:overflow-hidden lg:rounded-xl lg:border lg:border-borda lg:bg-superficie lg:shadow-cartao">
      <h1 className="sr-only">{TITULO_DO_PAINEL}</h1>
      <div className="hidden w-[300px] shrink-0 overflow-y-auto border-r border-borda p-4 lg:block">
        <ListaDeConversas />
      </div>
      <section aria-labelledby={idDoTitulo} className="flex min-w-0 flex-1 flex-col bg-superficie">
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-borda px-2 sm:px-4 lg:h-16">
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={listaAberta}
            onClick={() => setListaAberta(true)}
            className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-texto hover:bg-tinta/5 lg:hidden"
          >
            <List size={20} weight="bold" aria-hidden="true" />
            Conversas
          </button>
          <h2 id={idDoTitulo} className="min-w-0 flex-1 truncate font-titulo text-lg font-bold text-tinta lg:px-2">
            {titulo || TITULO_DO_PAINEL}
          </h2>
          <BotaoIcone rotulo="Começar outra conversa" className="lg:hidden" onClick={() => void loja.novaConversa()}>
            <NotePencil size={20} weight="bold" />
          </BotaoIcone>
        </div>
        <Conversa caminho="/conversa" nivelTitulo={3} className="flex-1" />
      </section>
      <Folha aberto={listaAberta} aoFechar={() => setListaAberta(false)} titulo="Conversas" lado="baixo">
        {listaAberta ? <ListaDeConversas comTitulo={false} aoEscolher={() => setListaAberta(false)} /> : null}
      </Folha>
    </div>
  );
}
