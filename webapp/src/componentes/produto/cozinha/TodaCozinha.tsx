"use client";

/**
 * "O que toda cozinha tem": o fogão, a panela funda, a faca, o refogar e o
 * arroz do dia a dia, que eu supus sem perguntar. Cada um com a foto e o que se
 * sabe dele; "Tenho tudo isso" confirma de uma vez o que ainda é suposto, e o
 * "Não tenho" de um item grava só ele. Antes de ela aceitar um prato, é isso
 * que o aceite confere.
 *
 * O texto, a contagem e o estado de cada item vêm da API; quando tudo já foi
 * respondido, o cartão fica calmo, com os itens guardados num "Ver os itens".
 */

import { CheckCircle, CookingPot, SealQuestion } from "@phosphor-icons/react/dist/ssr";
import { useId } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Card } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import type { TomDoChip } from "@/componentes/compartilhados/Chip";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { confirmarSupostos, definirPosse } from "@/lib/acoes/cozinha";
import type { ItemDeTodaCozinha, TodaCozinha as Bloco } from "@/lib/api/perfil";
import { useAcao } from "@/lib/dados/useAcao";

const TOM_DO_ESTADO: Readonly<Record<ItemDeTodaCozinha["status"], TomDoChip>> = {
  confirmado: "sucesso",
  suposto: "atencao",
  falta_saber: "neutro",
  nao_da: "perigo",
};

function Miniatura({ item }: { item: ItemDeTodaCozinha }) {
  return (
    <div data-miniatura="" title={item.imagem?.credito} className="size-14 shrink-0 overflow-hidden rounded-md border border-borda">
      <ImagemComFallback
        src={item.imagem?.url}
        alt={item.imagem ? `Foto ilustrativa: ${item.nome}` : ""}
        proporcao="1/1"
        icone={<CookingPot size={24} weight="duotone" />}
      />
    </div>
  );
}

function NaoTenho({ item }: { item: ItemDeTodaCozinha }) {
  const { executar, pendente } = useAcao(definirPosse, { sucesso: (dados) => `${item.nome}: ${dados.impacto.texto}` });
  const rotulo = item.tipo === "tecnica" ? "Não faço" : "Não tenho";
  return (
    <Botao
      variante="terciario"
      tamanho="sm"
      carregando={pendente}
      rotuloCarregando="Anotando…"
      aria-label={`${rotulo}: ${item.nome}`}
      onClick={() => void executar(item.tipo === "tecnica" ? "tecnicas" : "equipamentos", item.id, "nao_tem")}
    >
      {rotulo}
    </Botao>
  );
}

function ListaDeItens({ itens }: { itens: readonly ItemDeTodaCozinha[] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {itens.map((item) => (
        <li key={`${item.tipo}-${item.id}`} className="flex items-center gap-3 rounded-md border border-borda p-2.5">
          <Miniatura item={item} />
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold [overflow-wrap:anywhere] text-tinta">{item.nome}</p>
            <Chip tom={TOM_DO_ESTADO[item.status]} className="mt-1">
              {item.status_texto.charAt(0).toLocaleUpperCase("pt-BR") + item.status_texto.slice(1)}
            </Chip>
          </div>
          {item.status === "suposto" ? <NaoTenho item={item} /> : null}
        </li>
      ))}
    </ul>
  );
}

export function TodaCozinha({ bloco, className }: { bloco: Bloco; className?: string }) {
  const id = useId();
  const { executar, pendente } = useAcao(confirmarSupostos, { sucesso: (dados) => dados.texto });

  if (bloco.tudo_confirmado) {
    return (
      <Card aria-labelledby={`toda${id}`} className={className}>
        <div className="flex items-start gap-3">
          <CheckCircle size={28} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0 text-sucesso" />
          <div className="min-w-0">
            <h2 id={`toda${id}`} className="text-lg font-bold text-tinta">
              {bloco.titulo}
            </h2>
            <p className="mt-1 text-sm text-texto">{bloco.texto}</p>
          </div>
        </div>
        <details className="mt-3">
          <summary className="inline-flex min-h-11 cursor-pointer items-center rounded-sm text-sm font-semibold text-marca hover:underline">
            Ver os itens
          </summary>
          <div className="mt-2">
            <ListaDeItens itens={bloco.itens} />
          </div>
        </details>
      </Card>
    );
  }

  return (
    <Card aria-labelledby={`toda${id}`} className={className}>
      <div className="flex items-start gap-3">
        <SealQuestion size={28} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0 text-atencao" />
        <div className="min-w-0">
          <h2 id={`toda${id}`} className="text-lg font-bold text-tinta">
            {bloco.titulo}
          </h2>
          <p className="mt-1 text-sm text-texto">{bloco.texto}</p>
          <p className="mt-1 text-sm font-semibold text-tinta">{bloco.a_confirmar_texto}</p>
        </div>
      </div>
      <div className="mt-4">
        <ListaDeItens itens={bloco.itens} />
      </div>
      <div className="mt-4">
        <Botao
          icone={<CheckCircle size={20} weight="bold" />}
          carregando={pendente}
          rotuloCarregando="Anotando…"
          onClick={() => void executar({})}
        >
          Tenho tudo isso
        </Botao>
      </div>
    </Card>
  );
}
