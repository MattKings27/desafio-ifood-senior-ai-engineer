"use client";

/**
 * O que ela decidiu, prato a prato, do mais novo para o mais antigo, em
 * frases dela ("A senhora tirou o arroz com frango do cardápio."). A decisão
 * que vale hoje de cada prato pode ser desfeita dali mesmo: o prato volta ao
 * que era, e o histórico ganha a linha "voltou atrás".
 */

import type { Icon } from "@phosphor-icons/react";
import {
  ArrowCounterClockwise,
  CheckCircle,
  Clock,
  CurrencyCircleDollar,
  MinusCircle,
  Prohibit,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";

import { Botao } from "@/componentes/compartilhados/Botao";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import type { DecisaoNoHistorico } from "@/lib/api/cardapio";

const ICONE: Readonly<Record<string, { Icone: Icon; cor: string }>> = {
  aceito: { Icone: CheckCircle, cor: "bg-sucesso/10 text-sucesso" },
  preco: { Icone: CurrencyCircleDollar, cor: "bg-info/10 text-info" },
  retirado: { Icone: MinusCircle, cor: "bg-atencao/10 text-atencao" },
  recusado: { Icone: Prohibit, cor: "bg-perigo/10 text-perigo" },
  adiado: { Icone: Clock, cor: "bg-secao text-apagado" },
  desfeito: { Icone: ArrowCounterClockwise, cor: "bg-marca/10 text-marca" },
};

const SEM_TIPO = { Icone: Clock, cor: "bg-secao text-apagado" };

export const CANAL_TEXTO: Readonly<Record<string, string>> = {
  tela: "pela tela",
  conversa: "pela conversa",
};

function Passo({
  decisao,
  aoDesfazer,
  desfazendo,
}: {
  decisao: DecisaoNoHistorico;
  aoDesfazer: (prato: string) => void;
  desfazendo: boolean;
}) {
  const { Icone, cor } = ICONE[decisao.tipo] ?? SEM_TIPO;
  const canal = CANAL_TEXTO[decisao.canal];
  return (
    <div className="flex gap-3">
      <span aria-hidden="true" className={clsx("flex size-9 shrink-0 items-center justify-center rounded-full", cor)}>
        <Icone size={18} weight="bold" />
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <p className="text-base text-texto">{decisao.texto_humano}</p>
        <p className="mt-0.5 text-sm text-apagado">
          <span className="font-semibold">{decisao.tipo_rotulo}</span> · {decisao.quando_texto}
          {canal ? ` · ${canal}` : null}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2">
          {decisao.rota !== "/cardapio" ? (
            <Link
              href={decisao.rota}
              className="-ml-2 inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
            >
              Ver a receita<span className="sr-only">: {decisao.prato}</span>
            </Link>
          ) : null}
          {decisao.pode_desfazer ? (
            <Botao
              variante="texto"
              tamanho="sm"
              icone={<ArrowCounterClockwise size={16} weight="bold" />}
              carregando={desfazendo}
              rotuloCarregando="Desfazendo…"
              onClick={() => aoDesfazer(decisao.prato)}
            >
              Desfazer<span className="sr-only">: {decisao.texto_humano}</span>
            </Botao>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function HistoricoDeDecisoes({
  historico,
  aoDesfazer,
  desfazendo = false,
}: {
  historico: readonly DecisaoNoHistorico[];
  aoDesfazer: (prato: string) => void;
  desfazendo?: boolean;
}) {
  return (
    <ListaExpansivel
      itens={historico}
      visiveis={6}
      como="ol"
      chave={(decisao) => String(decisao.id)}
      className="space-y-4"
      descricaoDoResto="decisões"
      renderizar={(decisao) => <Passo decisao={decisao} aoDesfazer={aoDesfazer} desfazendo={desfazendo} />}
      vazio={<p className="text-sm text-apagado">Nenhuma decisão ainda: quando a senhora aceitar um preço, ele aparece aqui.</p>}
    />
  );
}
