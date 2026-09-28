"use client";

/**
 * As receitas que já dão pra fazer, nos mesmos cards da grade de receitas:
 * quatro à vista, "Ver mais" para o resto das que vieram, e o caminho para a
 * grade inteira. Sem receita nenhuma, o convite para o agente procurar.
 */

import { ForkKnife } from "@phosphor-icons/react/dist/ssr";

import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { BotaoPerguntar } from "@/componentes/conversa/BotaoPerguntar";
import { CartaoDeReceita } from "@/componentes/produto/receitas/CartaoDeReceita";
import { CLASSE_DA_GRADE } from "@/componentes/produto/receitas/GradeDeReceitas";
import type { ItemDaGrade } from "@/lib/api/receitas";

export const RASCUNHO_DE_RECEITAS = "Que receitas eu consigo fazer com o que tenho na despensa?";

export function ReceitasRecomendadas({ receitas }: { receitas: readonly ItemDaGrade[] }) {
  return (
    <section aria-labelledby="titulo-das-receitas" className="@container">
      <TituloSecao
        id="titulo-das-receitas"
        titulo="Receitas que dão pra fazer"
        apoio="Com o que a senhora tem, ou comprando pouco dentro dos complementos."
        resumivel
        verMais={{ href: "/receitas", rotulo: "Ver todas" }}
      />
      <ListaExpansivel
        itens={receitas}
        visiveis={4}
        chave={(item) => item.slug}
        className={CLASSE_DA_GRADE}
        classeDoItem="min-w-0"
        descricaoDoResto="receitas"
        renderizar={(item, indice) => <CartaoDeReceita item={item} prioridade={indice < 2} />}
        vazio={
          <EstadoVazio
            compacto
            icone={<ForkKnife size={20} weight="duotone" />}
            titulo="Nenhuma receita dá pra fazer ainda"
            descricao="O agente procura na internet receitas que aproveitam a sua despensa."
            acao={
              <BotaoPerguntar
                rascunho={RASCUNHO_DE_RECEITAS}
                contexto={{ tela: "inicio", tipo: "receitas", rotulo: "Receitas que dão pra fazer" }}
                rotulo="Pedir receitas"
              />
            }
          />
        }
      />
    </section>
  );
}
