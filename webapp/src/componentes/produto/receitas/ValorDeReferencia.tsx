"use client";

/**
 * Um número que a plataforma estabeleceu sem perguntar: o preço médio em São
 * Paulo do que falta comprar, o peso de uma medida pela tabela do IBGE ou o
 * rendimento estimado pelo peso. Ele aparece como "Estimado", com o texto da
 * API, a fonte ao lado e o "corrigir" discreto, que abre o campo para ela pôr o
 * dela: o número dela sempre vale mais. Nunca é uma pergunta. O preço médio
 * mostra cada mercado de São Paulo, com o preço e o link do produto.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

import type { PrecoDeReferencia } from "@/lib/api/receitas";

import type { Correcao } from "./correcao";
import { CorrigirValor } from "./CorrigirValor";

type Receita = { slug: string; nome: string };

/** O selo do valor pré-determinado. */
export function Estimado() {
  return (
    <span className="mr-1 inline-flex items-center rounded-full border border-info/25 bg-info/10 px-1.5 py-px align-baseline text-[0.6875rem] font-bold text-info">
      Estimado
    </span>
  );
}

export function ValorDeReferencia({
  receita,
  texto,
  fonte,
  url,
  precos,
  correcao,
  oQue,
}: {
  receita: Receita;
  /** "Preço de referência: R$ 3,99 pela caixinha de 200 g no Savegnago, 27/09/2026; a senhora pode corrigir." */
  texto: string;
  /** O nome da fonte no link ("Savegnago", "IBGE"); sem `url`, não há link. */
  fonte?: string;
  url?: string | null;
  /** O preço médio em São Paulo, com cada mercado: no lugar do texto e da fonte única. */
  precos?: PrecoDeReferencia | null;
  /** Como ela corrige o valor; `null` quando não há o que corrigir aqui. */
  correcao: Correcao | null;
  /** O que o "corrigir" corrige, para o leitor de tela: "o preço de creme de leite". */
  oQue: string;
}) {
  if (precos) {
    return (
      <PrecoMedio precos={precos}>
        {correcao ? <CorrigirValor receita={receita} correcao={correcao} oQue={oQue} /> : null}
      </PrecoMedio>
    );
  }
  return (
    <div className="mt-1 text-xs text-texto-secundario">
      {
        <p>
          <Estimado />
          {texto}
          {url ? (
            <>
              {" "}
              <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold text-info underline underline-offset-2">
                Ver a fonte{fonte ? ` (${fonte})` : ""}
              </a>
            </>
          ) : null}
        </p>
      }
      {correcao ? <CorrigirValor receita={receita} correcao={correcao} oQue={oQue} /> : null}
    </div>
  );
}

/**
 * O preço estimado de um ingrediente que falta comprar, organizado para ela ler
 * de cima para baixo: de qual ingrediente é, o preço por kg (L, un) em destaque,
 * de quantos mercados saiu a média e, se ela quiser conferir, a tabela de cada
 * mercado com o preço e o tamanho da embalagem e o preço por kg, com o link do
 * produto. Três colunas, sem quebrar valor, para caber também no celular.
 * Tudo vem escrito pela API; a tela só organiza.
 */
function PrecoMedio({ precos, children }: { precos: PrecoDeReferencia; children?: ReactNode }) {
  const nome = maiuscula(precos.ingrediente);
  const fora = precos.fontes.filter((fonte) => !fonte.na_media);
  const media =
    precos.mercados_na_media === 1
      ? "preço de 1 mercado de São Paulo"
      : `média de ${precos.mercados_na_media} mercados de São Paulo`;
  return (
    <section aria-label={`Preço de ${precos.ingrediente}`} className="mt-2 rounded-lg border border-borda bg-secao/60 p-3 text-sm text-texto">
      <p className="font-semibold text-tinta">
        {nome} <Estimado />
      </p>
      <p className="mt-1.5 text-xs text-apagado">{precos.titulo}</p>
      <p className="mt-0.5">
        <span className="text-base font-bold text-tinta tabular-nums">{precos.preco_medio_texto}</span>{" "}
        <span className="text-texto-secundario">{media}</span>
      </p>
      {precos.fontes.length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-semibold text-info underline-offset-2 hover:underline">
            Ver o preço em cada mercado
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs tabular-nums">
              <caption className="sr-only">Preço de {precos.ingrediente} em cada mercado de São Paulo</caption>
              <thead>
                <tr className="text-left text-apagado">
                  <th scope="col" className="py-1 pr-2 font-semibold">
                    Mercado
                  </th>
                  <th scope="col" className="py-1 pr-2 text-right font-semibold">
                    Embalagem
                  </th>
                  <th scope="col" className="py-1 text-right font-semibold whitespace-nowrap">
                    Por {precos.unidade_base}
                  </th>
                </tr>
              </thead>
              <tbody>
                {precos.fontes.map((fonte) => (
                  <tr key={`${fonte.site}-${fonte.url}`} className={clsx("border-t border-borda/60", !fonte.na_media && "text-apagado")}>
                    <td className="py-1 pr-2">
                      <a href={fonte.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-info underline underline-offset-2">
                        {fonte.site}
                      </a>
                      {fonte.na_media ? null : <span className="block text-[0.6875rem]">fora da média</span>}
                    </td>
                    <td className="py-1 pr-2 text-right">
                      <span className="block whitespace-nowrap">{fonte.preco_embalagem_texto}</span>
                      <span className="block text-[0.6875rem] whitespace-nowrap text-apagado">{fonte.embalagem_texto}</span>
                    </td>
                    <td className="py-1 text-right whitespace-nowrap">{fonte.por_unidade_texto}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-apagado">
            Preços de {precos.data_texto}.{" "}
            {fora.length > 0 ? "O que ficou fora da média estava mais de 50% longe da mediana dos mercados." : null}
          </p>
        </details>
      ) : null}
      {children ? <div className="mt-2">{children}</div> : null}
    </section>
  );
}

function maiuscula(texto: string): string {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto;
}
