"use client";

/**
 * Busca, categorias, ordem e a folha "Filtros" da despensa, e os filtros ativos
 * com a contagem ("37 ingredientes", "3 encontrados").
 *
 * Tudo vive na URL (`useFiltrosNaUrl`): recarregar ou mandar o link mostra a
 * mesma lista. A busca ignora acento e caixa; as contagens das categorias são
 * as da API, da despensa inteira.
 */

import { useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Busca } from "@/componentes/compartilhados/Campos";
import type { FiltroAtivo, OpcaoDeFiltro } from "@/componentes/compartilhados/Filtros";
import { BotaoFiltros, ChipsAtivos, FiltroChips, Ordenacao } from "@/componentes/compartilhados/Filtros";
import { Folha } from "@/componentes/compartilhados/Folha";
import type { CategoriaDaDespensa, Confianca, OrigemDoItem } from "@/lib/api/despensa";
import type { FiltrosDaDespensaNaUrl, OrdemDaDespensa } from "@/lib/filtros/despensa";
import {
  ORDENS_DA_DESPENSA,
  ROTULO_DA_CONFIANCA,
  ROTULO_DA_ORDEM,
  ROTULO_DA_ORIGEM,
  contar,
} from "@/lib/filtros/despensa";

const CONFIANCAS: readonly Confianca[] = ["alta", "media", "desconhecida"];
const ORIGENS: readonly OrigemDoItem[] = ["planilha", "ja_tinha", "orcamento"];
const SO_ISSO = ["sem_receita", "pendentes"] as const;
type SoIsso = (typeof SO_ISSO)[number];
const ROTULO_DO_SO_ISSO: Record<SoIsso, string> = {
  sem_receita: "Sem receita ainda",
  pendentes: "Com pergunta em aberto",
};

export function FiltrosDaDespensa({
  filtros,
  definir,
  limpar,
  categorias,
  totalItens,
  encontrados,
}: {
  filtros: FiltrosDaDespensaNaUrl;
  definir: (parcial: Partial<FiltrosDaDespensaNaUrl>) => void;
  limpar: () => void;
  categorias: readonly CategoriaDaDespensa[];
  totalItens: number;
  encontrados: number;
}) {
  const [folhaAberta, setFolhaAberta] = useState(false);
  const rotuloDaCategoria = new Map(categorias.map((c) => [c.id, c.rotulo]));
  const naFolha =
    filtros.confianca.length + filtros.origem.length + (filtros.sem_receita ? 1 : 0) + (filtros.pendentes ? 1 : 0);

  const opcoesDeCategoria: OpcaoDeFiltro<string>[] = categorias.map((c) => ({
    valor: c.id,
    rotulo: c.rotulo,
    contagem: c.quantidade,
  }));

  const ativos: FiltroAtivo[] = [
    ...(filtros.q.trim()
      ? [{ id: "q", rotulo: `Busca: ${filtros.q.trim()}`, aoRemover: () => definir({ q: "" }) }]
      : []),
    ...filtros.categoria.map((id) => ({
      id: `categoria-${id}`,
      rotulo: rotuloDaCategoria.get(id) ?? id,
      aoRemover: () => definir({ categoria: filtros.categoria.filter((c) => c !== id) }),
    })),
    ...filtros.confianca.map((id) => ({
      id: `confianca-${id}`,
      rotulo: ROTULO_DA_CONFIANCA[id as Confianca] ?? id,
      aoRemover: () => definir({ confianca: filtros.confianca.filter((c) => c !== id) }),
    })),
    ...filtros.origem.map((id) => ({
      id: `origem-${id}`,
      rotulo: ROTULO_DA_ORIGEM[id as OrigemDoItem] ?? id,
      aoRemover: () => definir({ origem: filtros.origem.filter((c) => c !== id) }),
    })),
    ...SO_ISSO.filter((chave) => filtros[chave]).map((chave) => ({
      id: chave,
      rotulo: ROTULO_DO_SO_ISSO[chave],
      aoRemover: () => definir(chave === "sem_receita" ? { sem_receita: false } : { pendentes: false }),
    })),
  ];

  const filtrando = ativos.length > 0;
  const resumo = filtrando
    ? contar(encontrados, "encontrado", "encontrados")
    : contar(totalItens, "ingrediente", "ingredientes");

  return (
    <div className="flex flex-col gap-3">
      <Busca
        valor={filtros.q}
        aoMudar={(q) => definir({ q })}
        rotulo="Buscar ingrediente"
        placeholder="Buscar ingrediente"
      />
      <FiltroChips
        legenda="Categorias"
        opcoes={opcoesDeCategoria}
        selecionados={filtros.categoria}
        aoMudar={(categoria) => definir({ categoria })}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Ordenacao<OrdemDaDespensa>
          opcoes={ORDENS_DA_DESPENSA.map((valor) => ({ valor, rotulo: ROTULO_DA_ORDEM[valor] }))}
          valor={filtros.ordem}
          aoMudar={(ordem) => definir({ ordem })}
        />
        <BotaoFiltros quantidade={naFolha} aberto={folhaAberta} aoAbrir={() => setFolhaAberta(true)} />
      </div>
      <ChipsAtivos filtros={ativos} resumo={resumo} aoLimparTudo={limpar} />

      <Folha
        aberto={folhaAberta}
        aoFechar={() => setFolhaAberta(false)}
        titulo="Filtros"
        descricao="Escolha o que quer ver na despensa."
        rodape={
          <>
            {naFolha > 0 ? (
              <Botao
                variante="texto"
                onClick={() => definir({ confianca: [], origem: [], sem_receita: false, pendentes: false })}
              >
                Limpar estes filtros
              </Botao>
            ) : null}
            <Botao onClick={() => setFolhaAberta(false)}>
              Ver {filtrando ? contar(encontrados, "ingrediente", "ingredientes") : "todos"}
            </Botao>
          </>
        }
      >
        <div className="flex flex-col gap-6">
          <FiltroChips
            legenda="A conta do custo"
            legendaVisivel
            opcoes={CONFIANCAS.map((valor) => ({ valor, rotulo: ROTULO_DA_CONFIANCA[valor] }))}
            selecionados={filtros.confianca as Confianca[]}
            aoMudar={(confianca) => definir({ confianca })}
          />
          <FiltroChips
            legenda="De onde veio"
            legendaVisivel
            opcoes={ORIGENS.map((valor) => ({ valor, rotulo: ROTULO_DA_ORIGEM[valor] }))}
            selecionados={filtros.origem as OrigemDoItem[]}
            aoMudar={(origem) => definir({ origem })}
          />
          <FiltroChips
            legenda="Mostrar só"
            legendaVisivel
            opcoes={SO_ISSO.map((valor) => ({ valor, rotulo: ROTULO_DO_SO_ISSO[valor] }))}
            selecionados={SO_ISSO.filter((chave) => filtros[chave])}
            aoMudar={(escolhidos) =>
              definir({ sem_receita: escolhidos.includes("sem_receita"), pendentes: escolhidos.includes("pendentes") })
            }
          />
        </div>
      </Folha>
    </div>
  );
}
