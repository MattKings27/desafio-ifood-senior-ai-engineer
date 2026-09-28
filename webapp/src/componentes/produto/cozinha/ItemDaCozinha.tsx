"use client";

/**
 * Um equipamento ou uma técnica da cozinha, com a resposta dela.
 *
 * A miniatura do Commons ao lado do nome (ou o ícone da cozinha, quando não
 * há foto livre que mostre o item), com o crédito em letra pequena; o nome, o
 * que se sabe dele (suposto: confirme; atualizado pela conversa; ainda não
 * perguntei), o seletor Tenho / Não tenho / Não sei, as receitas que dependem
 * dele e, depois de gravar, o que mudou nas receitas, com a frase da API ("Sem
 * forno, Frango assado fica dependendo de uma resposta da senhora.").
 *
 * No modo minimalista, o item fica com a foto, o nome, o seletor e o
 * "Suposto: confirme"; as receitas que dependem dele, o que mudou nelas e o
 * crédito da foto somem (o crédito continua ao passar o mouse na foto).
 */

import { CaretDown, ChatCircleDots, CookingPot, Info, Lightning } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";

import { Chip } from "@/componentes/compartilhados/Chip";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { definirPosse } from "@/lib/acoes/cozinha";
import type { ImpactoDaMudanca, ItemDaCozinha as Item, RespostaDaCozinha, RespostaDePosse } from "@/lib/api/perfil";
import { respostaDoItem, situacaoDoItem } from "@/lib/filtros/cozinha";

import { SeletorDePosse } from "./SeletorDePosse";
import type { EstadoDaGravacao } from "./useGravacaoAdiada";
import { useGravacaoAdiada } from "./useGravacaoAdiada";

export function TextoDaGravacao({ estado, className }: { estado: EstadoDaGravacao; className?: string }) {
  if (estado === "salvando" || estado === "esperando") {
    return <p className={clsx("text-sm text-apagado", className)}>Salvando…</p>;
  }
  if (estado === "salvo") return <p className={clsx("text-sm text-sucesso", className)}>Salvo</p>;
  if (estado === "erro") return <p className={clsx("text-sm font-semibold text-perigo", className)}>Não salvou</p>;
  return null;
}

/** O que a última gravação mudou nas receitas, com a frase da API. */
export function NotaDoImpacto({ impacto }: { impacto: ImpactoDaMudanca }) {
  const mudou = impacto.liberadas.length + impacto.bloqueadas.length + impacto.pendentes.length > 0;
  return (
    <p
      className={clsx(
        "mt-2 flex items-start gap-2 rounded-sm p-2.5 text-sm",
        mudou ? "bg-info/10 text-texto" : "bg-secao text-apagado",
      )}
    >
      {mudou ? (
        <Lightning size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-info" />
      ) : (
        <Info size={18} weight="bold" aria-hidden="true" className="mt-px shrink-0" />
      )}
      <span>{impacto.texto}</span>
    </p>
  );
}

/**
 * A foto pequena do item, sempre do mesmo tamanho: carregando, sem foto ou com
 * a foto, a linha não pula. O crédito aparece ao passar o mouse e, em letra
 * pequena, embaixo do nome.
 */
export function MiniaturaDoItem({ item }: { item: Item }) {
  const { imagem } = item;
  return (
    <div data-miniatura="" title={imagem?.credito} className="size-16 shrink-0 overflow-hidden rounded-md border border-borda">
      <ImagemComFallback
        src={imagem?.url}
        alt={imagem ? `Foto ilustrativa: ${item.nome}` : ""}
        proporcao="1/1"
        icone={<CookingPot size={28} weight="duotone" />}
      />
    </div>
  );
}

function ReceitasQueDependem({ item, impacto }: { item: Item; impacto: ImpactoDaMudanca | null }) {
  const [aberto, setAberto] = useState(false);
  if (item.receitas_afetadas === 0) return null;
  const nomes = impacto ? [...impacto.liberadas, ...impacto.bloqueadas, ...impacto.pendentes] : [];
  return (
    <div className="mt-1">
      <button
        type="button"
        aria-expanded={aberto}
        onClick={() => setAberto((antes) => !antes)}
        className="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
      >
        Muda o que dá para fazer em {item.receitas_afetadas_texto}
        <CaretDown
          size={14}
          weight="bold"
          aria-hidden="true"
          className={clsx("transition-transform duration-padrao", aberto && "rotate-180")}
        />
      </button>
      {aberto ? (
        <div className="mt-1 rounded-sm bg-secao p-3 text-sm text-texto">
          {nomes.length > 0 ? (
            <ul className="list-inside list-disc">
              {nomes.map((nome) => (
                <li key={nome}>{nome}</li>
              ))}
            </ul>
          ) : (
            <p>São receitas que a senhora está avaliando e pedem isso num dos passos.</p>
          )}
          <Link href="/receitas" className="mt-2 inline-flex min-h-11 items-center font-semibold text-marca hover:underline">
            Ver as receitas
          </Link>
        </div>
      ) : null}
    </div>
  );
}

export function ItemDaCozinha({
  item,
  tipo,
  aoGravar,
}: {
  item: Item;
  tipo: "equipamentos" | "tecnicas";
  /** Recebe a frase do impacto, para a tela anunciar numa região viva só. */
  aoGravar?: (texto: string) => void;
}) {
  const [impacto, setImpacto] = useState<ImpactoDaMudanca | null>(null);
  const gravacao = useGravacaoAdiada<RespostaDePosse | null, RespostaDaCozinha>(
    respostaDoItem(item),
    (resposta) => definirPosse(tipo, item.id, resposta ?? "nao_sei"),
    {
      aoGravar: (dados) => {
        setImpacto(dados.impacto);
        aoGravar?.(`${item.nome}: ${dados.impacto.texto}`);
      },
    },
  );
  const situacao = situacaoDoItem(item);

  return (
    <li className="flex flex-col gap-3 py-4 md:flex-row md:items-start md:justify-between md:gap-6">
      <div className="flex min-w-0 items-start gap-3 md:flex-1">
        <MiniaturaDoItem item={item} />
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold [overflow-wrap:anywhere] text-tinta">{item.nome}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {situacao === "suposto" ? (
              <Chip tom="neutro" icone={<Info size={14} weight="bold" />}>
                Suposto: confirme
              </Chip>
            ) : null}
            {situacao === "sem_resposta" ? (
              <Chip tom="neutro" className="minimalista:hidden">
                Ainda não perguntei
              </Chip>
            ) : null}
            {situacao === "nao_sei" ? (
              <Chip tom="neutro" className="minimalista:hidden">
                A senhora disse que não sabe
              </Chip>
            ) : null}
            {item.atualizado_por === "conversa" ? (
              <Chip tom="info" icone={<ChatCircleDots size={14} weight="fill" />} className="minimalista:hidden">
                Atualizado pela conversa{item.atualizado_texto ? `, ${item.atualizado_texto}` : ""}
              </Chip>
            ) : null}
          </div>
          <div className="minimalista:hidden">
            <ReceitasQueDependem item={item} impacto={impacto} />
            {impacto ? <NotaDoImpacto impacto={impacto} /> : null}
            {item.imagem ? <p className="mt-1 text-xs [overflow-wrap:anywhere] text-apagado">{item.imagem.credito}</p> : null}
          </div>
        </div>
      </div>
      <div className="md:w-[25rem] md:shrink-0">
        <SeletorDePosse
          tipo={tipo === "tecnicas" ? "tecnica" : "equipamento"}
          legenda={item.nome}
          valor={gravacao.valor}
          aoMudar={gravacao.mudar}
        />
        <TextoDaGravacao estado={gravacao.estado} className="mt-1 md:text-right" />
      </div>
    </li>
  );
}
