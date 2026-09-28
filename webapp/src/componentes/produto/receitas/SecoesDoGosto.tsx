"use client";

/**
 * As seções de cada aba, pelo gosto dela: "Gosto de fazer", "Ainda não me
 * disse se gosta" (cada card com a pergunta do gosto) e, no fim e fechada,
 * "Não gosto de fazer", com o "Mudei de ideia" em cada card. Cada seção diz
 * quantas tem; a fechada também, para ela saber o que está guardado ali.
 */

import { CaretDown, Heart, HeartBreak, Question } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useId, useState } from "react";

import { Problema } from "@/componentes/compartilhados/Problema";
import type { ItemDaGrade } from "@/lib/api/receitas";

import { CartaoDeReceita } from "./CartaoDeReceita";
import { MudeiDeIdeia } from "./GostoDaGrade";
import type { SecaoDoGosto } from "./gosto";
import { ROTULO_DA_SECAO, receitasNaSecao } from "./gosto";
import { CLASSE_DA_GRADE } from "./GradeDeReceitas";
import type { ErroDaLista } from "./useListaDeReceitas";

const ICONE_DA_SECAO: Readonly<Record<SecaoDoGosto, ReactNode>> = {
  gosta: <Heart size={18} weight="fill" className="text-marca" />,
  ainda_nao: <Question size={18} weight="fill" className="text-atencao" />,
  nao_gosta: <HeartBreak size={18} weight="bold" className="text-apagado" />,
};

function Contagem({ quantas }: { quantas: number }) {
  return (
    <span className="numero inline-flex min-w-6 justify-center rounded-full bg-secao px-1.5 text-xs font-bold text-texto">
      <span aria-hidden="true">{quantas}</span>
      <span className="sr-only">, {receitasNaSecao(quantas)}</span>
    </span>
  );
}

/** Uma seção aberta: o título com a contagem, o apoio e os cards. */
export function SecaoAberta({
  secao,
  quantas,
  apoio,
  children,
}: {
  secao: Exclude<SecaoDoGosto, "nao_gosta">;
  quantas: number;
  /** O que a seção pede dela, numa frase. Some no modo minimalista. */
  apoio?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div>
        <h3 id={id} className="flex items-center gap-2 text-base font-bold text-tinta">
          <span aria-hidden="true" className="inline-flex shrink-0">
            {ICONE_DA_SECAO[secao]}
          </span>
          {ROTULO_DA_SECAO[secao]}
          <Contagem quantas={quantas} />
        </h3>
        {apoio ? <p className="mt-0.5 text-sm text-apagado minimalista:hidden">{apoio}</p> : null}
      </div>
      {children}
    </section>
  );
}

/**
 * "Não gosto de fazer (n)": fechada no fim da aba, à mão para ela mudar de
 * ideia. Aberta, cada card traz o "Mudei de ideia", que leva a receita de volta
 * para "Gosto de fazer".
 */
export function SecaoNaoGosto({
  itens,
  erro,
  aoTentarDeNovo,
}: {
  itens: readonly ItemDaGrade[];
  /** A lista das que ela não quer não chegou. */
  erro: ErroDaLista | null;
  aoTentarDeNovo: () => void;
}) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  if (itens.length === 0 && !erro && !aberta) return null;
  return (
    <section aria-labelledby={`${id}-titulo`} className="border-t border-borda pt-4">
      <h3 id={`${id}-titulo`} className="text-base font-bold">
        <button
          type="button"
          aria-expanded={aberta}
          aria-controls={`${id}-lista`}
          onClick={() => setAberta((antes) => !antes)}
          className="-ml-2 inline-flex min-h-11 items-center gap-2 rounded-sm px-2 text-tinta hover:bg-secao"
        >
          <span aria-hidden="true" className="inline-flex shrink-0">
            {ICONE_DA_SECAO.nao_gosta}
          </span>
          {ROTULO_DA_SECAO.nao_gosta}
          <Contagem quantas={itens.length} />
          <CaretDown
            size={18}
            weight="bold"
            aria-hidden="true"
            className={clsx("transition-transform duration-padrao ease-padrao", aberta && "rotate-180")}
          />
        </button>
      </h3>
      <div id={`${id}-lista`} hidden={!aberta} className="pt-3">
        {aberta ? (
          <>
            <p className="mb-3 text-sm text-apagado">
              São as que a senhora disse que não gosta de fazer. Se mudar de ideia, ela volta para {ROTULO_DA_SECAO.gosta}.
            </p>
            {erro ? (
              <Problema categoria={erro.categoria} mensagem={erro.mensagem} aoTentarDeNovo={aoTentarDeNovo} />
            ) : itens.length === 0 ? (
              <p className="text-sm text-texto">Nenhuma, com esses filtros.</p>
            ) : (
              <ul aria-label={ROTULO_DA_SECAO.nao_gosta} className={CLASSE_DA_GRADE}>
                {itens.map((item) => (
                  <li key={item.slug} className="min-w-0">
                    <CartaoDeReceita item={item} nivelTitulo={4} acao={<MudeiDeIdeia item={item} />} />
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}
      </div>
    </section>
  );
}
