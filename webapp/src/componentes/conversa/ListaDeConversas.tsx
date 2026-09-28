"use client";

/**
 * A lista de conversas: começar outra, trocar, renomear e apagar (com
 * confirmação). Cada uma mostra o título, uma prévia da última mensagem, a
 * data que o backend escreveu e "respondendo…" quando o agente ainda está
 * trabalhando nela.
 *
 * Começar outra conversa não apaga nada da despensa nem do cardápio, e a lista
 * diz isso. "Apagar todas" mora nas Preferências, longe do dedo.
 */

import { ChatsCircle, Check, PencilSimple, Plus, Trash, X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { FormEvent } from "react";
import { useEffect, useId, useRef, useState } from "react";

import { Botao, BotaoIcone } from "@/componentes/compartilhados/Botao";
import { DialogoDeConfirmacao } from "@/componentes/compartilhados/Dialogo";
import { Esqueleto } from "@/componentes/compartilhados/Esqueleto";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import type { ResumoDaConversa } from "@/lib/api/conversa";
import { TITULO_PADRAO } from "@/lib/conversa/estado";

import { useLojaDaConversa, useSeletor } from "./useLoja";

export const NOTA_DA_NOVA_CONVERSA = "Começar outra conversa não apaga nada da despensa nem do cardápio.";

function FormularioDeNome({
  titulo,
  aoSalvar,
  aoCancelar,
}: {
  titulo: string;
  aoSalvar: (titulo: string) => Promise<void>;
  aoCancelar: () => void;
}) {
  const [valor, setValor] = useState(titulo);
  const [salvando, setSalvando] = useState(false);
  const campo = useRef<HTMLInputElement | null>(null);
  const id = useId();

  useEffect(() => {
    campo.current?.focus();
    campo.current?.select();
  }, []);

  const salvar = async (evento?: FormEvent) => {
    evento?.preventDefault();
    const limpo = valor.replace(/\s+/g, " ").trim();
    if (!limpo || limpo === titulo) {
      aoCancelar();
      return;
    }
    setSalvando(true);
    await aoSalvar(limpo);
    setSalvando(false);
  };

  return (
    <form onSubmit={(evento) => void salvar(evento)} className="flex items-center gap-1 px-2 py-1.5">
      <label htmlFor={id} className="sr-only">
        Novo nome da conversa
      </label>
      <input
        ref={campo}
        id={id}
        value={valor}
        maxLength={200}
        onChange={(evento) => setValor(evento.target.value)}
        onKeyDown={(evento) => {
          if (evento.key === "Escape") {
            evento.preventDefault();
            evento.stopPropagation();
            aoCancelar();
          }
        }}
        className="h-11 min-w-0 flex-1 rounded-sm border border-borda-campo bg-superficie px-3 text-base text-tinta"
      />
      <BotaoIcone rotulo="Salvar o nome" type="submit" aria-busy={salvando || undefined}>
        <Check size={20} weight="bold" />
      </BotaoIcone>
      <BotaoIcone rotulo="Cancelar" onClick={aoCancelar}>
        <X size={20} weight="bold" />
      </BotaoIcone>
    </form>
  );
}

function ItemDaLista({
  conversa,
  atual,
  aoAbrir,
  aoRenomear,
  aoApagar,
}: {
  conversa: ResumoDaConversa;
  atual: boolean;
  aoAbrir: () => void;
  aoRenomear: () => void;
  aoApagar: () => void;
}) {
  const titulo = conversa.titulo?.trim() || TITULO_PADRAO;
  return (
    <div
      className={clsx(
        "group flex items-stretch rounded-lg transition-colors duration-rapida",
        atual ? "bg-tinta/8" : "hover:bg-tinta/5",
      )}
    >
      <button
        type="button"
        onClick={aoAbrir}
        aria-current={atual ? "true" : undefined}
        className="min-w-0 flex-1 rounded-lg px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="truncate text-base font-semibold text-tinta">{titulo}</span>
          {conversa.respondendo ? (
            <span className="shrink-0 rounded-full bg-marca/10 px-2 text-xs font-semibold text-marca-escura">respondendo…</span>
          ) : null}
        </span>
        {conversa.previa ? <span className="mt-0.5 block truncate text-sm text-apagado">{conversa.previa}</span> : null}
        {conversa.atualizado_texto ? (
          <span className="mt-0.5 block text-xs text-apagado">{conversa.atualizado_texto}</span>
        ) : null}
      </button>
      <div className="flex shrink-0 items-center pr-1">
        <BotaoIcone rotulo={`Renomear ${titulo}`} onClick={aoRenomear} className="text-apagado hover:text-tinta">
          <PencilSimple size={18} weight="bold" />
        </BotaoIcone>
        <BotaoIcone rotulo={`Apagar ${titulo}`} onClick={aoApagar} className="text-apagado hover:text-perigo">
          <Trash size={18} weight="bold" />
        </BotaoIcone>
      </div>
    </div>
  );
}

export function ListaDeConversas({
  aoEscolher,
  className,
  comTitulo = true,
}: {
  /** Depois de trocar ou começar uma conversa (no celular, fecha a folha). */
  aoEscolher?: () => void;
  className?: string;
  /** Na folha "Conversas", o título já é o da folha. */
  comTitulo?: boolean;
}) {
  const loja = useLojaDaConversa();
  const lista = useSeletor(loja, (estado) => estado.lista);
  const idAtual = useSeletor(loja, (estado) => estado.conversa.id);
  const [renomeando, setRenomeando] = useState<string | null>(null);
  const [apagando, setApagando] = useState<ResumoDaConversa | null>(null);
  const [ocupada, setOcupada] = useState(false);
  const idDoTitulo = useId();

  useEffect(() => {
    void loja.carregarLista();
  }, [loja]);

  const nova = async () => {
    const criou = await loja.novaConversa();
    if (criou) aoEscolher?.();
  };

  const apagar = async () => {
    if (!apagando) return;
    setOcupada(true);
    await loja.apagarConversa(apagando.id);
    setOcupada(false);
    setApagando(null);
  };

  return (
    <section aria-labelledby={idDoTitulo} className={clsx("flex min-h-0 flex-col", className)}>
      <div className={clsx("flex items-center justify-between gap-2", !comTitulo && "sr-only")}>
        <h2 id={idDoTitulo} className="font-titulo text-lg font-bold text-tinta">
          Conversas
        </h2>
      </div>
      <Botao
        variante="secundario"
        tamanho="sm"
        larguraTotal
        icone={<Plus size={18} weight="bold" />}
        className={comTitulo ? "mt-3" : undefined}
        onClick={() => void nova()}
      >
        Começar outra conversa
      </Botao>
      <p className="mt-2 text-sm text-apagado">{NOTA_DA_NOVA_CONVERSA}</p>

      <div className="mt-4 min-h-0 flex-1">
        {lista.carregamento === "falhou" && lista.conversas.length === 0 ? (
          <div role="status" className="rounded-lg border border-borda p-3 text-sm text-texto">
            <p>Não consegui carregar a lista agora.</p>
            <button
              type="button"
              onClick={() => void loja.carregarLista()}
              className="-ml-2 mt-1 inline-flex min-h-11 items-center rounded-sm px-2 font-semibold text-marca hover:bg-marca/10"
            >
              Tentar de novo
            </button>
          </div>
        ) : lista.carregamento !== "pronta" && lista.conversas.length === 0 ? (
          <div role="status" className="space-y-2">
            <span className="sr-only">Carregando as conversas…</span>
            <Esqueleto className="h-16 w-full rounded-lg" />
            <Esqueleto className="h-16 w-full rounded-lg" />
          </div>
        ) : lista.conversas.length === 0 ? (
          <EstadoVazio
            compacto
            icone={<ChatsCircle size={20} weight="duotone" />}
            titulo="Nenhuma conversa ainda"
            descricao="A primeira começa quando a senhora mandar uma mensagem."
          />
        ) : (
          <ul className="space-y-1">
            {lista.conversas.map((conversa) => (
              <li key={conversa.id}>
                {renomeando === conversa.id ? (
                  <FormularioDeNome
                    titulo={conversa.titulo?.trim() || TITULO_PADRAO}
                    aoCancelar={() => setRenomeando(null)}
                    aoSalvar={async (titulo) => {
                      await loja.renomearConversa(conversa.id, titulo);
                      setRenomeando(null);
                    }}
                  />
                ) : (
                  <ItemDaLista
                    conversa={conversa}
                    atual={conversa.id === idAtual}
                    aoAbrir={() => {
                      void loja.trocarConversa(conversa.id);
                      aoEscolher?.();
                    }}
                    aoRenomear={() => setRenomeando(conversa.id)}
                    aoApagar={() => setApagando(conversa)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <DialogoDeConfirmacao
        aberto={apagando !== null}
        titulo="Apagar esta conversa?"
        descricao={
          <>
            A conversa <strong className="font-bold text-tinta">{apagando?.titulo?.trim() || TITULO_PADRAO}</strong> some
            da lista e não volta. O que a senhora anotou na despensa, na cozinha e no cardápio continua lá.
          </>
        }
        rotuloConfirmar="Apagar"
        perigoso
        carregando={ocupada}
        aoConfirmar={() => void apagar()}
        aoCancelar={() => setApagando(null)}
      />
    </section>
  );
}
