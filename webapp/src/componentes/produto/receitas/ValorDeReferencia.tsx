"use client";

/**
 * Um número que a plataforma estabeleceu sem perguntar: o preço médio em São
 * Paulo do que falta comprar, o peso de uma medida pela tabela do IBGE ou o
 * rendimento estimado pelo peso. Ele aparece como "Estimado", com o texto da
 * API, a fonte ao lado e o "corrigir" discreto, que abre o campo para ela pôr o
 * dela: o número dela sempre vale mais. Nunca é uma pergunta. O preço médio
 * mostra cada mercado de São Paulo, com o preço e o link do produto.
 */

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
  return (
    <div className="mt-1 text-xs text-texto-secundario">
      {precos ? (
        <PrecoMedio precos={precos} />
      ) : (
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
      )}
      {correcao ? <CorrigirValor receita={receita} correcao={correcao} oQue={oQue} /> : null}
    </div>
  );
}

/** "Preço médio em São Paulo: R$ 16,60 o quilo", a conta da média e cada mercado com o link. */
function PrecoMedio({ precos }: { precos: PrecoDeReferencia }) {
  return (
    <div>
      <p>
        <Estimado />
        <span className="font-semibold text-tinta">{precos.titulo}:</span> {precos.preco_medio_texto}
      </p>
      <p className="mt-0.5">{maiuscula(precos.media_texto)}.</p>
      {precos.fontes.length > 0 ? (
        <ul className="mt-1 space-y-0.5" aria-label={`Mercados de São Paulo com ${precos.ingrediente}`}>
          {precos.fontes.map((item) => (
            <li key={`${item.site}-${item.url}`}>
              <a href={item.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-info underline underline-offset-2">
                {item.site}
              </a>
              {`: ${item.preco_texto} (${item.por_unidade_texto})`}
              {item.na_media ? null : ", fora da média"}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function maiuscula(texto: string): string {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto;
}
