"use client";

/**
 * A cozinha dela: o que toda cozinha tem (confirmado de uma vez), o quanto ela
 * já contou, os limites da rotina e cada equipamento e técnica, com a busca e o
 * filtro pela situação na URL.
 *
 * O progresso usa os textos da API ("3 de 63 respondidos pela senhora" e o
 * resumo, que separa o que ela disse que não sabe do que ninguém perguntou).
 * Cada mudança grava sozinha e diz, numa região viva só, o que mudou nas
 * receitas.
 */

import { CookingPot } from "@phosphor-icons/react/dist/ssr";
import { useMemo, useState } from "react";

import { Barra } from "@/componentes/compartilhados/Barra";
import { Botao } from "@/componentes/compartilhados/Botao";
import { Busca } from "@/componentes/compartilhados/Campos";
import { Card } from "@/componentes/compartilhados/Card";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import type { FiltroAtivo } from "@/componentes/compartilhados/Filtros";
import { ChipsAtivos, FiltroChips } from "@/componentes/compartilhados/Filtros";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import { Derivacao } from "@/componentes/compartilhados/Valor";
import { BotaoPerguntar } from "@/componentes/conversa/BotaoPerguntar";
import type { ItemDaCozinha as Item, PerfilDaCozinha } from "@/lib/api/perfil";
import { useFiltrosNaUrl } from "@/lib/dados/useFiltrosNaUrl";
import type { SituacaoNaCozinha } from "@/lib/filtros/cozinha";
import {
  FILTROS_DA_COZINHA,
  ROTULO_DA_SITUACAO,
  SITUACOES_DA_COZINHA,
  agruparPorCategoria,
  contarPorSituacao,
  passaNaCozinha,
} from "@/lib/filtros/cozinha";
import { contar } from "@/lib/filtros/despensa";

import { ItemDaCozinha } from "./ItemDaCozinha";
import { LimitesDaRotina } from "./LimitesDaRotina";
import { TodaCozinha } from "./TodaCozinha";

export function ProgressoDaCozinha({ perfil, className }: { perfil: PerfilDaCozinha; className?: string }) {
  return (
    <Card aria-labelledby="titulo-do-progresso" className={className}>
      <h2 id="titulo-do-progresso" className="text-lg font-bold text-tinta">
        O que a senhora já me contou
      </h2>
      <p className="mt-2 font-titulo text-2xl font-bold text-tinta">{perfil.progresso_texto}</p>
      <Barra
        className="mt-3"
        tom="sucesso"
        espessura="lg"
        fracao={perfil.fracao_respondida}
        rotulo="Respondidos pela senhora"
        valorTexto={perfil.progresso_texto}
      />
      <p className="mt-2 text-sm text-texto">{perfil.resumo}</p>
      <Derivacao className="text-sm">
        Suposto é o que toda cozinha costuma ter e eu ainda não perguntei. Se não for o caso, é só marcar.
      </Derivacao>
    </Card>
  );
}

function SecaoDaCozinha({
  id,
  titulo,
  tipo,
  itens,
  aoGravar,
}: {
  id: string;
  titulo: string;
  tipo: "equipamentos" | "tecnicas";
  itens: readonly Item[];
  aoGravar: (texto: string) => void;
}) {
  if (itens.length === 0) return null;
  return (
    <section aria-labelledby={id} className="mt-6">
      <h2 id={id} className="text-lg font-bold text-tinta">
        {titulo}
      </h2>
      {agruparPorCategoria(itens).map((grupo) => (
        <Card key={grupo.categoria} tom="plano" className="mt-3 py-1 sm:py-1">
          <h3 className="pt-3 text-sm font-bold tracking-wide text-apagado uppercase">{grupo.rotulo}</h3>
          <ul className="divide-y divide-borda">
            {grupo.itens.map((item) => (
              <ItemDaCozinha key={item.id} item={item} tipo={tipo} aoGravar={aoGravar} />
            ))}
          </ul>
        </Card>
      ))}
    </section>
  );
}

export function TelaDaCozinha({ perfil }: { perfil: PerfilDaCozinha }) {
  const { filtros, definir, limpar } = useFiltrosNaUrl(FILTROS_DA_COZINHA);
  const [anuncio, setAnuncio] = useState("");
  const todos = useMemo(() => [...perfil.equipamentos, ...perfil.tecnicas], [perfil.equipamentos, perfil.tecnicas]);
  const contagem = useMemo(() => contarPorSituacao(todos), [todos]);
  const equipamentos = perfil.equipamentos.filter((item) => passaNaCozinha(item, filtros));
  const tecnicas = perfil.tecnicas.filter((item) => passaNaCozinha(item, filtros));
  const encontrados = equipamentos.length + tecnicas.length;

  const ativos: FiltroAtivo[] = [
    ...(filtros.q.trim() ? [{ id: "q", rotulo: `Busca: ${filtros.q.trim()}`, aoRemover: () => definir({ q: "" }) }] : []),
    ...filtros.situacao.map((situacao) => ({
      id: `situacao-${situacao}`,
      rotulo: ROTULO_DA_SITUACAO[situacao as SituacaoNaCozinha] ?? situacao,
      aoRemover: () => definir({ situacao: filtros.situacao.filter((s) => s !== situacao) }),
    })),
  ];

  return (
    <>
      <CabecalhoDaPagina
        titulo="Cozinha"
        descricao="Equipamentos, técnicas e a rotina da senhora. Eu confiro isso antes de sugerir qualquer receita."
        resumivel
        acoes={
          <BotaoPerguntar
            rascunho="O que ainda falta eu contar da minha cozinha?"
            contexto={{ tela: "cozinha", tipo: "tela", id: "cozinha", rotulo: "Cozinha" }}
            tamanho="md"
          />
        }
      />

      <TodaCozinha bloco={perfil.toda_cozinha} className="mb-4" />

      <div className="grid items-start gap-4 lg:grid-cols-5">
        <ProgressoDaCozinha perfil={perfil} className="lg:col-span-2" />
        <LimitesDaRotina restricoes={perfil.restricoes} aoGravar={setAnuncio} className="lg:col-span-3" />
      </div>

      <div className="mt-8">
        <div className="flex flex-col gap-3">
          <Busca
            valor={filtros.q}
            aoMudar={(q) => definir({ q })}
            rotulo="Buscar equipamento ou técnica"
            placeholder="Buscar equipamento ou técnica"
          />
          <FiltroChips
            legenda="Situação"
            opcoes={SITUACOES_DA_COZINHA.map((valor) => ({
              valor,
              rotulo: ROTULO_DA_SITUACAO[valor],
              contagem: contagem[valor],
            }))}
            selecionados={filtros.situacao as SituacaoNaCozinha[]}
            aoMudar={(situacao) => definir({ situacao })}
          />
          <ChipsAtivos
            filtros={ativos}
            aoLimparTudo={() => limpar()}
            resumo={
              ativos.length > 0
                ? contar(encontrados, "encontrado", "encontrados")
                : contar(todos.length, "item na cozinha", "itens na cozinha")
            }
          />
        </div>

        {encontrados === 0 ? (
          <EstadoVazio
            className="mt-4"
            icone={<CookingPot size={24} weight="duotone" />}
            titulo="Nada com esses filtros"
            descricao="Tire um filtro ou procure com outra palavra."
            acao={
              <Botao variante="secundario" onClick={() => limpar()}>
                Limpar filtros
              </Botao>
            }
          />
        ) : null}
        <SecaoDaCozinha id="titulo-dos-equipamentos" titulo="Equipamentos" tipo="equipamentos" itens={equipamentos} aoGravar={setAnuncio} />
        <SecaoDaCozinha id="titulo-das-tecnicas" titulo="Técnicas" tipo="tecnicas" itens={tecnicas} aoGravar={setAnuncio} />
      </div>

      <p role="status" className="sr-only">
        {anuncio}
      </p>
    </>
  );
}
