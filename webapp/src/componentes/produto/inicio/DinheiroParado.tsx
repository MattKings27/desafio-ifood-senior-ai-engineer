"use client";

/**
 * "Onde o dinheiro está parado": todos os itens com preço, do que mais custou
 * ao que menos custou. A tela mostra cinco e o "Ver mais" abre o resto; cada
 * item é um cartão clicável que leva ao ingrediente. A barra e a porcentagem
 * vêm prontas da API.
 */

import { Barra } from "@/componentes/compartilhados/Barra";
import { CardLink } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Valor } from "@/componentes/compartilhados/Valor";
import type { ItemParado, VisaoGeral } from "@/lib/api/visao-geral";

function ItemDoDinheiroParado({ item }: { item: ItemParado }) {
  return (
    <CardLink
      href={item.rota}
      titulo={item.nome}
      como="article"
      densidade="compacta"
      className="grid grid-cols-[3rem_minmax(0,1fr)] items-center gap-x-3"
      classeDoTitulo="truncate text-sm sm:text-base"
      midia={
        <div className="row-span-2 overflow-hidden rounded-md">
          <ImagemComFallback src={item.imagem?.url} alt="" proporcao="1/1" tipo="ingrediente" />
        </div>
      }
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <Valor dinheiro={item.pago} tamanho="sm" />
          <span className="numero text-xs text-apagado minimalista:hidden">{item.fracao_texto} do que a senhora pagou</span>
        </div>
        <Barra
          fracao={item.fracao}
          tom="marca"
          espessura="sm"
          rotulo={`${item.nome} no que a senhora pagou`}
          valorTexto={item.fracao_texto}
          className="mt-1.5"
        />
        {item.sem_receita ? (
          <Chip tom="atencao" className="mt-2">
            nenhuma receita usa ainda
          </Chip>
        ) : null}
      </div>
    </CardLink>
  );
}

export function DinheiroParado({ parado }: { parado: VisaoGeral["dinheiro_parado"] }) {
  return (
    <section aria-labelledby="titulo-do-dinheiro-parado">
      <TituloSecao
        id="titulo-do-dinheiro-parado"
        titulo="Onde o dinheiro está parado"
        apoio={parado.dois_maiores.texto}
        resumivel
        verMais={{ href: "/despensa", rotulo: "Ver a despensa" }}
      />
      <ListaExpansivel
        itens={parado.itens}
        visiveis={5}
        chave={(item) => item.id}
        className="grid gap-2"
        classeDoItem="min-w-0"
        descricaoDoResto="ingredientes"
        renderizar={(item) => <ItemDoDinheiroParado item={item} />}
      />
    </section>
  );
}
