"use client";

/**
 * A busca, a ordem e os filtros da grade, todos na URL.
 *
 * A busca vai à URL depois de uma pausa na digitação (a API ignora acento e
 * caixa). Tempo máximo, "só com o que tenho", pontuação mínima e a ordem ficam
 * numa folha (a ordem também à vista, ao lado do botão); o que está filtrando
 * aparece em chips, cada um com o ✕ para tirar, e o resumo diz quantas
 * receitas sobraram.
 */

import { Check } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useEffect, useId, useRef, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Busca, Selecao } from "@/componentes/compartilhados/Campos";
import type { FiltroAtivo } from "@/componentes/compartilhados/Filtros";
import { BotaoFiltros, ChipsAtivos, FiltroChips } from "@/componentes/compartilhados/Filtros";
import { Folha } from "@/componentes/compartilhados/Folha";
import type { OrdemDeReceitas } from "@/lib/api/receitas";
import type { FiltrosDe } from "@/lib/filtros/url";

import type { ESQUEMA_DAS_RECEITAS, FiltrosDaGrade } from "./filtros";
import {
  OPCOES_DE_NOTA,
  OPCOES_DE_TEMPO,
  ORDEM_DA_ABA,
  ORDENS,
  ROTULO_DA_ORDEM,
  receitasTexto,
  resumoDaBusca,
  rotuloDoTempo,
  rotuloDoUsa,
} from "./filtros";

type Definir = (parcial: Partial<FiltrosDe<typeof ESQUEMA_DAS_RECEITAS>>) => void;

/** Espera depois da última tecla antes de a busca ir à URL. */
export const PAUSA_DA_BUSCA_MS = 300;

function CampoDeBusca({ valor, definir }: { valor: string; definir: Definir }) {
  const [texto, setTexto] = useState(valor);
  const escrito = useRef(valor);
  const relogio = useRef<ReturnType<typeof setTimeout>>(undefined);

  // A busca mudou por fora (o chip tirado, o voltar do navegador): o campo acompanha.
  useEffect(() => {
    if (valor === escrito.current) return;
    escrito.current = valor;
    setTexto(valor);
  }, [valor]);

  useEffect(() => () => clearTimeout(relogio.current), []);

  const mudar = (novo: string) => {
    setTexto(novo);
    clearTimeout(relogio.current);
    relogio.current = setTimeout(() => {
      escrito.current = novo.trim();
      definir({ q: novo.trim() });
    }, PAUSA_DA_BUSCA_MS);
  };

  return (
    <Busca
      valor={texto}
      aoMudar={mudar}
      rotulo="Buscar receitas"
      placeholder="Buscar por nome ou ingrediente"
      className="min-w-0 flex-1 basis-64"
    />
  );
}

function SeletorDeOrdem({ filtros, definir }: { filtros: FiltrosDaGrade; definir: Definir }) {
  const id = useId();
  const padrao = ORDEM_DA_ABA[filtros.aba];
  const efetiva: OrdemDeReceitas = filtros.ordem || padrao;
  return (
    <div className="flex min-w-0 items-center gap-2">
      <label htmlFor={`ordem${id}`} className="shrink-0 text-sm text-apagado max-sm:sr-only">
        Ordenar por
      </label>
      <Selecao
        id={`ordem${id}`}
        value={efetiva}
        onChange={(evento) => {
          const escolhida = evento.target.value as OrdemDeReceitas;
          definir({ ordem: escolhida === padrao ? "" : escolhida });
        }}
        opcoes={ORDENS.map((ordem) => ({ valor: ordem, rotulo: ROTULO_DA_ORDEM[ordem] }))}
        className="h-11 text-sm"
      />
    </div>
  );
}

/** Os filtros que estão valendo, como chips que se tiram. */
export function filtrosAtivos(filtros: FiltrosDaGrade, definir: Definir): FiltroAtivo[] {
  const ativos: FiltroAtivo[] = [];
  if (filtros.q.trim()) ativos.push({ id: "q", rotulo: `Busca: ${filtros.q.trim()}`, aoRemover: () => definir({ q: "" }) });
  if (filtros.tempo_max !== null && filtros.tempo_max > 0) {
    ativos.push({ id: "tempo_max", rotulo: rotuloDoTempo(filtros.tempo_max), aoRemover: () => definir({ tempo_max: null }) });
  }
  if (filtros.so_com_o_que_tenho) {
    ativos.push({ id: "so_com_o_que_tenho", rotulo: "Só com o que tenho", aoRemover: () => definir({ so_com_o_que_tenho: false }) });
  }
  if (filtros.nota_min !== null) {
    ativos.push({ id: "nota_min", rotulo: `Pontuação ${filtros.nota_min} ou mais`, aoRemover: () => definir({ nota_min: null }) });
  }
  if (filtros.usa.trim()) ativos.push({ id: "usa", rotulo: rotuloDoUsa(filtros.usa.trim()), aoRemover: () => definir({ usa: "" }) });
  return ativos;
}

function FolhaDeFiltros({
  aberta,
  aoFechar,
  filtros,
  definir,
  limpar,
  quantas,
}: {
  aberta: boolean;
  aoFechar: () => void;
  filtros: FiltrosDaGrade;
  definir: Definir;
  limpar: () => void;
  quantas: number;
}) {
  const tempo = filtros.tempo_max === null ? "" : String(filtros.tempo_max);
  const nota = filtros.nota_min === null ? "" : String(filtros.nota_min);
  return (
    <Folha
      aberto={aberta}
      aoFechar={aoFechar}
      titulo="Filtros"
      descricao="A lista muda na hora."
      rodape={
        <>
          <Botao variante="texto" onClick={limpar}>
            Limpar filtros
          </Botao>
          <Botao onClick={aoFechar}>Ver {receitasTexto(quantas)}</Botao>
        </>
      }
    >
      <div className="space-y-6">
        <FiltroChips
          legenda="Tempo de preparo"
          legendaVisivel
          multiplo={false}
          nome="tempo_max"
          opcoes={OPCOES_DE_TEMPO}
          selecionados={[tempo]}
          aoMudar={([valor]) => definir({ tempo_max: valor ? Number(valor) : null })}
        />
        <label className="flex min-h-11 cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={filtros.so_com_o_que_tenho}
            onChange={(evento) => definir({ so_com_o_que_tenho: evento.target.checked })}
            className="peer sr-only"
          />
          <span
            aria-hidden="true"
            className={clsx(
              "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-xs border-2 transition-colors duration-rapida",
              "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marca",
              filtros.so_com_o_que_tenho ? "border-tinta bg-tinta text-superficie" : "border-borda-campo bg-superficie",
            )}
          >
            {filtros.so_com_o_que_tenho ? <Check size={16} weight="bold" /> : null}
          </span>
          <span>
            <span className="block text-sm font-semibold text-tinta">Só com o que a senhora tem</span>
            <span className="block text-sm text-apagado">Sem nada para comprar.</span>
          </span>
        </label>
        <FiltroChips
          legenda="Pontuação mínima"
          legendaVisivel
          multiplo={false}
          nome="nota_min"
          opcoes={OPCOES_DE_NOTA}
          selecionados={[nota]}
          aoMudar={([valor]) => definir({ nota_min: valor ? Number(valor) : null })}
        />
        <FiltroChips
          legenda="Ordenar por"
          legendaVisivel
          multiplo={false}
          nome="ordem"
          opcoes={ORDENS.map((ordem) => ({ valor: ordem, rotulo: ROTULO_DA_ORDEM[ordem] }))}
          selecionados={[filtros.ordem || ORDEM_DA_ABA[filtros.aba]]}
          aoMudar={([valor]) => definir({ ordem: !valor || valor === ORDEM_DA_ABA[filtros.aba] ? "" : valor })}
        />
      </div>
    </Folha>
  );
}

export function BarraDeFiltros({
  filtros,
  definir,
  limpar,
  quantas,
  className,
}: {
  filtros: FiltrosDaGrade;
  definir: Definir;
  /** Tira todos os filtros (a aba fica). */
  limpar: () => void;
  /** Quantas receitas a aba de agora mostra, com os filtros. */
  quantas: number;
  className?: string;
}) {
  const [folhaAberta, setFolhaAberta] = useState(false);
  const ativos = filtrosAtivos(filtros, definir);
  const naFolha = ativos.filter((ativo) => ativo.id !== "q").length;
  return (
    <div className={clsx("space-y-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <CampoDeBusca valor={filtros.q} definir={definir} />
        <div className="flex w-full items-center justify-between gap-2 sm:w-auto sm:justify-end">
          <BotaoFiltros quantidade={naFolha} aberto={folhaAberta} aoAbrir={() => setFolhaAberta(true)} />
          <SeletorDeOrdem filtros={filtros} definir={definir} />
        </div>
      </div>
      {ativos.length > 0 ? <ChipsAtivos filtros={ativos} aoLimparTudo={limpar} resumo={resumoDaBusca(quantas)} /> : null}
      <FolhaDeFiltros
        aberta={folhaAberta}
        aoFechar={() => setFolhaAberta(false)}
        filtros={filtros}
        definir={definir}
        limpar={limpar}
        quantas={quantas}
      />
    </div>
  );
}
