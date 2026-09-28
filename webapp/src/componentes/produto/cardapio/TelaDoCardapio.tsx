"use client";

/**
 * O cardápio: os pratos que ela aceitou, com o preço, o que chega e o lucro
 * de agora; o resumo com a linha dos R$ 80,00; os pratos que ela não quer; e
 * o histórico das decisões, com o desfazer.
 *
 * Tudo vem de `GET /api/cardapio`, com os textos prontos. A tela não soma
 * preço nem lucro: o preço médio e a sobra vêm do servidor.
 */

import { ArrowRight, ForkKnife, Prohibit } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Card, CardLink } from "@/componentes/compartilhados/Card";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { CabecalhoDaPagina, TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Valor } from "@/componentes/compartilhados/Valor";
import type { CardapioCompleto, PratoRecusado } from "@/lib/api/cardapio";

import { CartaoDoPrato } from "./CartaoDoPrato";
import { HistoricoDeDecisoes } from "./HistoricoDeDecisoes";
import { useMudancasNoCardapio } from "./useMudancasNoCardapio";

function Resumo({ resumo }: { resumo: CardapioCompleto["resumo"] }) {
  return (
    <Card tom="secao" aria-labelledby="titulo-do-resumo" className="space-y-3">
      <h2 id="titulo-do-resumo" className="sr-only">
        O resumo do cardápio
      </h2>
      <dl className="grid gap-3 min-[420px]:grid-cols-3">
        <div>
          <dt className="text-sm text-apagado">No cardápio</dt>
          <dd className="font-titulo text-lg font-bold text-tinta">{resumo.texto}</dd>
        </div>
        <div>
          <dt className="text-sm text-apagado">Preço médio</dt>
          <dd>
            <Valor dinheiro={resumo.preco_medio} tamanho="lg" />
          </dd>
        </div>
        <div>
          <dt className="text-sm text-apagado">Sobra</dt>
          <dd className="text-base font-semibold text-tinta">{resumo.margem_media_texto}</dd>
        </div>
      </dl>
      <p className="flex flex-wrap items-center gap-x-2 border-t border-borda pt-3 text-sm text-texto">
        <span className="minimalista:hidden">{resumo.orcamento_texto}</span>
        <Link
          href={resumo.orcamento_rota}
          className="-my-2 inline-flex min-h-11 items-center gap-1 font-semibold text-marca hover:underline"
        >
          Ver os complementos <ArrowRight size={14} weight="bold" aria-hidden="true" />
        </Link>
      </p>
    </Card>
  );
}

function NaoQuer({ pratos }: { pratos: readonly PratoRecusado[] }) {
  if (pratos.length === 0) return null;
  return (
    <section aria-labelledby="titulo-do-nao-quer">
      <TituloSecao
        id="titulo-do-nao-quer"
        titulo="Pratos que a senhora não quer"
        apoio="Ficam aqui para a senhora poder mudar de ideia."
        resumivel
      />
      <ListaExpansivel
        itens={pratos}
        visiveis={5}
        chave={(prato) => prato.prato}
        className="grid gap-2 sm:grid-cols-2"
        classeDoItem="min-w-0"
        descricaoDoResto="pratos"
        renderizar={(prato) => (
          <CardLink
            href={prato.rota}
            titulo={prato.prato}
            como="article"
            densidade="compacta"
            classeDoTitulo="text-base"
            midia={
              <Prohibit size={18} weight="bold" aria-hidden="true" className="float-right mt-0.5 ml-2 text-perigo" />
            }
          >
            <p className="text-sm text-texto">{prato.motivo_texto}</p>
            <p className="text-xs text-apagado minimalista:hidden">{prato.decidido_texto}</p>
          </CardLink>
        )}
      />
    </section>
  );
}

export function TelaDoCardapio({ cardapio }: { cardapio: CardapioCompleto }) {
  const { tirar, tirando, desfazer, desfazendo } = useMudancasNoCardapio();
  const { pratos, resumo, nao_quer: naoQuer, historico } = cardapio;
  return (
    <div className="space-y-8">
      <CabecalhoDaPagina
        titulo="O cardápio"
        descricao="Os pratos que a senhora aceitou, com o preço, o que chega para a senhora e o lucro de cada porção."
        resumivel
        className="mb-0"
      />
      <Resumo resumo={resumo} />

      <section aria-labelledby="titulo-dos-pratos" className="@container">
        <TituloSecao
          id="titulo-dos-pratos"
          titulo="Os pratos"
          apoio="A conta de cada um é refeita com a despensa de agora."
          resumivel
        />
        <ListaExpansivel
          itens={pratos}
          visiveis={6}
          chave={(prato) => prato.slug}
          className="grid grid-cols-1 gap-4 @2xl:grid-cols-2 @5xl:grid-cols-3"
          classeDoItem="min-w-0"
          descricaoDoResto="pratos"
          renderizar={(prato) => <CartaoDoPrato prato={prato} aoTirar={tirar} tirando={tirando} />}
          vazio={
            <EstadoVazio
              icone={<ForkKnife size={24} weight="duotone" />}
              titulo="Nenhum prato no cardápio ainda"
              descricao="Quando a senhora aceitar o preço de uma receita, o prato aparece aqui, com o lucro de cada porção."
              acao={
                <BotaoLink href="/receitas" variante="secundario">
                  Ver as receitas
                </BotaoLink>
              }
            />
          }
        />
      </section>

      <NaoQuer pratos={naoQuer} />

      <section aria-labelledby="titulo-do-historico">
        <TituloSecao
          id="titulo-do-historico"
          titulo="O que a senhora decidiu"
          apoio="Cada decisão, da mais nova para a mais antiga. A última de cada prato dá para desfazer."
          resumivel
          verMais={{ href: "/trilha?categoria=cardapio", rotulo: "Ver no histórico" }}
        />
        <HistoricoDeDecisoes historico={historico} aoDesfazer={desfazer} desfazendo={desfazendo} />
      </section>
    </div>
  );
}
