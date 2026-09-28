"use client";

/**
 * A prévia do cardápio: cada prato aceito com o preço dela e o lucro por
 * porção, clicável até a receita. Os números são os da API, com a conta de
 * agora; o cardápio inteiro (e o que mudar nele) fica na tela do cardápio.
 */

import { ListChecks } from "@phosphor-icons/react/dist/ssr";

import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { CardLink } from "@/componentes/compartilhados/Card";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Valor } from "@/componentes/compartilhados/Valor";
import type { PratoDoCardapio } from "@/lib/api/cardapio";

function PratoNaPrevia({ prato }: { prato: PratoDoCardapio }) {
  return (
    <CardLink href={prato.rota} titulo={prato.prato} como="article" densidade="compacta" className="flex h-full flex-col gap-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <Valor dinheiro={prato.preco} tamanho="lg" />
        <span className="text-sm text-apagado">
          lucro por porção <Valor dinheiro={prato.lucro_porcao} tamanho="sm" tom={prato.da_prejuizo ? "negativo" : "positivo"} />
        </span>
      </div>
      {prato.aviso ? <p className="text-xs text-atencao">{prato.aviso}</p> : null}
    </CardLink>
  );
}

export function PreviaDoCardapio({ pratos }: { pratos: readonly PratoDoCardapio[] }) {
  return (
    <section aria-labelledby="titulo-da-previa">
      <TituloSecao
        id="titulo-da-previa"
        titulo="O cardápio"
        apoio="Os pratos que a senhora aceitou, com o preço e o lucro de agora."
        resumivel
        verMais={{ href: "/cardapio", rotulo: "Ver o cardápio" }}
      />
      <ListaExpansivel
        itens={pratos}
        visiveis={4}
        chave={(prato) => prato.slug}
        className="grid gap-3 sm:grid-cols-2"
        classeDoItem="min-w-0"
        descricaoDoResto="pratos"
        renderizar={(prato) => <PratoNaPrevia prato={prato} />}
        vazio={
          <EstadoVazio
            compacto
            icone={<ListChecks size={20} weight="duotone" />}
            titulo="Nenhum prato no cardápio ainda"
            descricao="Quando a senhora aceitar um preço, o prato aparece aqui."
            acao={
              <BotaoLink href="/receitas" variante="secundario" tamanho="sm">
                Escolher nas receitas
              </BotaoLink>
            }
          />
        }
      />
    </section>
  );
}
