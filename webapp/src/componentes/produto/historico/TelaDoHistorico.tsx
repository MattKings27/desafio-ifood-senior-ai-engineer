"use client";

/**
 * O histórico: tudo o que aconteceu, em frases, agrupado por dia, do mais novo
 * para o mais antigo. A busca e os filtros (o que, quem e o dia) moram na URL;
 * cada linha leva à coisa de que fala, e o "Ver mais" traz as anteriores.
 *
 * Nada aqui é nome de ferramenta nem caminho de arquivo: as frases vêm prontas
 * de `GET /api/atividades`.
 */

import type { Icon } from "@phosphor-icons/react";
import {
  Basket,
  BookOpenText,
  CaretDown,
  ClockCounterClockwise,
  CookingPot,
  CurrencyCircleDollar,
  ListChecks,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Busca } from "@/componentes/compartilhados/Campos";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { FiltroChips } from "@/componentes/compartilhados/Filtros";
import { Problema } from "@/componentes/compartilhados/Problema";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import type { Atividade, OpcaoDoHistorico, PaginaDeAtividades } from "@/lib/api/atividades";
import { useFiltrosNaUrl } from "@/lib/dados/useFiltrosNaUrl";

import { ESQUEMA_DO_HISTORICO, chaveDoPedido, paraPedido } from "./filtros";
import { useHistorico } from "./useHistorico";

/** Espera depois da última tecla antes de a busca ir à URL. */
export const PAUSA_DA_BUSCA_MS = 300;

const ICONE_DA_CATEGORIA: Readonly<Record<string, { Icone: Icon; cor: string }>> = {
  despensa: { Icone: Basket, cor: "bg-info/10 text-info" },
  receitas: { Icone: BookOpenText, cor: "bg-sucesso/10 text-sucesso" },
  cozinha: { Icone: CookingPot, cor: "bg-atencao/10 text-atencao" },
  preco: { Icone: CurrencyCircleDollar, cor: "bg-marca/10 text-marca" },
  cardapio: { Icone: ListChecks, cor: "bg-secao text-texto" },
};

const SEM_CATEGORIA = { Icone: ClockCounterClockwise, cor: "bg-secao text-apagado" };

function CampoDeBusca({ valor, aoMudar }: { valor: string; aoMudar: (q: string) => void }) {
  const [texto, setTexto] = useState(valor);
  const escrito = useRef(valor);
  const relogio = useRef<ReturnType<typeof setTimeout>>(undefined);

  // A busca mudou por fora (o voltar do navegador): o campo acompanha.
  useEffect(() => {
    if (valor === escrito.current) return;
    escrito.current = valor;
    setTexto(valor);
  }, [valor]);

  useEffect(() => () => clearTimeout(relogio.current), []);

  return (
    <Busca
      valor={texto}
      aoMudar={(novo) => {
        setTexto(novo);
        clearTimeout(relogio.current);
        relogio.current = setTimeout(() => {
          escrito.current = novo.trim();
          aoMudar(novo.trim());
        }, PAUSA_DA_BUSCA_MS);
      }}
      rotulo="Buscar no histórico"
      placeholder="Buscar: frango, forno, preço…"
    />
  );
}

function comTudo(opcoes: readonly OpcaoDoHistorico[], rotuloDoTudo: string) {
  return [{ valor: "", rotulo: rotuloDoTudo }, ...opcoes.map((opcao) => ({ valor: opcao.id, rotulo: opcao.rotulo }))];
}

function LinhaDoHistorico({ atividade }: { atividade: Atividade }) {
  const { Icone, cor } = ICONE_DA_CATEGORIA[atividade.categoria] ?? SEM_CATEGORIA;
  const detalhes = [atividade.hora_texto, atividade.canal_texto].filter(Boolean).join(" · ");
  const corpo = (
    <>
      <span aria-hidden="true" className={clsx("flex size-9 shrink-0 items-center justify-center rounded-full", cor)}>
        <Icone size={18} weight="bold" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-base text-texto">{atividade.texto}</span>
        <span className="mt-0.5 block text-sm text-apagado">
          <span className="font-semibold">{atividade.quem_rotulo}</span> · {atividade.categoria_rotulo} · {detalhes}
        </span>
      </span>
    </>
  );
  const classes = "flex gap-3 rounded-md p-2 -mx-2";
  return atividade.link ? (
    <Link href={atividade.link} className={clsx(classes, "transition-colors duration-rapida hover:bg-secao")}>
      {corpo}
    </Link>
  ) : (
    <div className={classes}>{corpo}</div>
  );
}

export function TelaDoHistorico({ inicial, chaveInicial }: { inicial: PaginaDeAtividades; chaveInicial: string }) {
  const { filtros, definir, limpar, ativos } = useFiltrosNaUrl(ESQUEMA_DO_HISTORICO);
  const pedido = paraPedido(filtros);
  const chave = chaveDoPedido(pedido);
  const historico = useHistorico({ inicial, chaveInicial, pedido, chave });
  const { pagina } = historico;

  return (
    <div className="space-y-6">
      <CabecalhoDaPagina
        titulo="Histórico"
        descricao="Tudo o que a senhora e o agente fizeram, dia a dia. Toque numa linha para ver a coisa de que ela fala."
        resumivel
        className="mb-0"
      />

      <div className="space-y-3">
        <CampoDeBusca valor={filtros.q} aoMudar={(q) => definir({ q })} />
        <FiltroChips
          legenda="O que"
          legendaVisivel
          multiplo={false}
          opcoes={comTudo(pagina.categorias, "Tudo")}
          selecionados={[filtros.categoria]}
          aoMudar={([valor]) => definir({ categoria: (valor ?? "") as typeof filtros.categoria })}
        />
        <FiltroChips
          legenda="Quem"
          legendaVisivel
          multiplo={false}
          opcoes={comTudo(pagina.quem, "Todos")}
          selecionados={[filtros.quem]}
          aoMudar={([valor]) => definir({ quem: (valor ?? "") as typeof filtros.quem })}
        />
        {pagina.dias.length > 0 ? (
          <FiltroChips
            legenda="Dia"
            legendaVisivel
            multiplo={false}
            opcoes={comTudo(pagina.dias, "Todos os dias")}
            selecionados={[filtros.dia]}
            aoMudar={([valor]) => definir({ dia: valor ?? "" })}
          />
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p role="status" className="text-sm text-apagado">
            {historico.carregando ? "Procurando…" : pagina.texto}
          </p>
          {ativos > 0 ? (
            <Botao variante="texto" tamanho="sm" onClick={() => limpar()}>
              Tirar os filtros
            </Botao>
          ) : null}
        </div>
      </div>

      {historico.erro ? (
        <Problema
          titulo="Não consegui trazer o histórico"
          mensagem={historico.erro.mensagem}
          categoria={historico.erro.categoria}
          aoTentarDeNovo={historico.tentarDeNovo}
        />
      ) : null}

      <div aria-busy={historico.carregando || undefined} className={clsx("space-y-6", historico.desatualizada && "opacity-60")}>
        {pagina.grupos.length === 0 ? (
          <EstadoVazio
            icone={<ClockCounterClockwise size={24} weight="duotone" />}
            titulo={ativos > 0 ? "Nada com esses filtros" : "Nada por aqui ainda"}
            descricao={
              ativos > 0
                ? "Tire um filtro ou mude a busca para ver mais."
                : "Quando a senhora ou o agente mexerem na despensa, na cozinha, nas receitas ou no cardápio, fica tudo aqui."
            }
          />
        ) : (
          pagina.grupos.map((grupo) => (
            <section key={grupo.dia} aria-labelledby={`dia-${grupo.dia}`}>
              <h2 id={`dia-${grupo.dia}`} className="mb-2 text-sm font-bold text-tinta">
                {grupo.rotulo}
              </h2>
              <ol className="space-y-1">
                {grupo.itens.map((atividade) => (
                  <li key={atividade.id}>
                    <LinhaDoHistorico atividade={atividade} />
                  </li>
                ))}
              </ol>
            </section>
          ))
        )}
      </div>

      {pagina.proximo_cursor ? (
        <button
          type="button"
          onClick={() => void historico.verMais()}
          aria-busy={historico.carregandoMais || undefined}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 -ml-2 text-sm font-semibold text-marca transition-colors duration-rapida hover:bg-marca/10"
        >
          {historico.carregandoMais ? "Trazendo…" : "Ver mais"}
          <CaretDown size={16} weight="bold" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}
