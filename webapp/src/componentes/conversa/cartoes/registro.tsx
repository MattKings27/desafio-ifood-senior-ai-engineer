"use client";

/**
 * O registro dos cards da conversa: `tipo_cartao` → componente.
 *
 * O card vem do backend, com os dados do motor lidos da rota em `ref.rota`
 * (a mesma que a tela chamaria), nunca do texto do modelo. Cada componente lê
 * esses dados com as leituras seguras de `leitura.ts` e mostra o que tiver.
 *
 * Tipo que a tela não conhece, ou que ainda não tem componente, é ignorado: um
 * card novo do backend não quebra a conversa, só não aparece até a tela
 * aprender. E cada card fica na sua fronteira de erro: um card que quebra vira
 * uma linha dizendo isso, e a conversa continua.
 *
 * Uma resposta não vira uma parede de cards: o mesmo card repetido no turno
 * (mesmo tipo, mesma rota) fica só no último, e 3 ou mais do mesmo tipo viram
 * um grupo com os 2 primeiros à mostra e o resto atrás de "Ver mais".
 */

import { Stack } from "@phosphor-icons/react/dist/ssr";
import type { ComponentType } from "react";
import { useId } from "react";

import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import type { TipoDeCartao } from "@/lib/conversa/cartoes";
import {
  CARTOES_VISIVEIS_NO_GRUPO,
  PLURAL_DO_CARTAO,
  agruparCartoes,
  ehTipoDeCartao,
  semCartoesRepetidos,
} from "@/lib/conversa/cartoes";

import { CartaoFontes } from "./CartaoFontes";
import { CartaoCozinhaAtualizada, CartaoPergunta } from "./CartoesDaCozinha";
import { CartaoDespensaResumo, CartaoIngredienteChat, CartaoOrcamento } from "./CartoesDaDespensa";
import {
  CartaoCenarios,
  CartaoCustoPorcao,
  CartaoDecisao,
  CartaoPontoDePreco,
  CartaoPrecoPreliminar,
} from "./CartoesDePreco";
import { CartaoAvaliacaoDaReceita, CartaoComparacao, CartaoReceitaChat, CartaoViabilidade } from "./CartoesDeReceita";
import type { PropsDoCartao } from "./Moldura";
import { LimiteDoCartao } from "./Moldura";

/** Um componente para cada um dos 15 tipos do contrato (`contratos/web/cartoes/`). */
export const COMPONENTES_DOS_CARTOES: Readonly<Partial<Record<TipoDeCartao, ComponentType<PropsDoCartao>>>> = {
  despensa_resumo: CartaoDespensaResumo,
  ingrediente: CartaoIngredienteChat,
  receita: CartaoReceitaChat,
  viabilidade: CartaoViabilidade,
  comparacao: CartaoComparacao,
  pergunta: CartaoPergunta,
  cozinha_atualizada: CartaoCozinhaAtualizada,
  orcamento: CartaoOrcamento,
  custo_porcao: CartaoCustoPorcao,
  cenarios: CartaoCenarios,
  ponto_de_preco: CartaoPontoDePreco,
  preco_preliminar: CartaoPrecoPreliminar,
  decisao: CartaoDecisao,
  avaliacao_da_receita: CartaoAvaliacaoDaReceita,
  fontes: CartaoFontes,
};

/** O componente de um tipo de card, ou `null` quando a tela ainda não sabe mostrá-lo. */
export function componenteDoCartao(tipo: unknown): ComponentType<PropsDoCartao> | null {
  return ehTipoDeCartao(tipo) ? (COMPONENTES_DOS_CARTOES[tipo] ?? null) : null;
}

/** Um card da conversa, na sua fronteira de erro; nada, se o tipo não tem componente. */
export function CartaoDaConversa({ cartao, historico }: PropsDoCartao) {
  const Componente = componenteDoCartao(cartao.tipo);
  if (!Componente) return null;
  return (
    <LimiteDoCartao>
      <Componente cartao={cartao} historico={historico} />
    </LimiteDoCartao>
  );
}

type CartaoDaResposta = PropsDoCartao["cartao"];

/** Vários cards do mesmo tipo: um grupo com o nome e a contagem, 2 à mostra e o resto em "Ver mais". */
function GrupoDeCartoes({ tipo, cartoes }: { tipo: TipoDeCartao; cartoes: readonly CartaoDaResposta[] }) {
  const id = useId();
  const idDoTitulo = `grupo${id}`;
  const plural = PLURAL_DO_CARTAO[tipo];
  return (
    <section aria-labelledby={idDoTitulo} className="rounded-xl border border-borda bg-secao/60 p-2 sm:p-3">
      <h3 id={idDoTitulo} className="flex items-center gap-1.5 px-1 pb-2 text-sm font-semibold text-tinta">
        <Stack size={16} weight="bold" aria-hidden="true" className="text-marca" />
        <span>
          <span className="numero">{cartoes.length}</span> {plural}
        </span>
      </h3>
      <ListaExpansivel
        itens={cartoes}
        visiveis={CARTOES_VISIVEIS_NO_GRUPO}
        chave={(cartao) => cartao.id}
        renderizar={(cartao) => <CartaoDaConversa cartao={cartao} historico={!cartao.aoVivo} />}
        className="space-y-3"
        rotuloVerMais="Ver mais"
        descricaoDoResto={plural}
      />
    </section>
  );
}

/**
 * Os cards de uma resposta, sem os que a tela ainda não sabe mostrar, sem
 * repetição, e com os muitos do mesmo tipo juntos num grupo.
 */
export function CartoesDaResposta({ cartoes }: { cartoes: readonly CartaoDaResposta[] }) {
  const conhecidos = cartoes.filter((cartao) => componenteDoCartao(cartao.tipo) !== null);
  if (conhecidos.length === 0) return null;
  const blocos = agruparCartoes(semCartoesRepetidos(conhecidos));
  return (
    <div className="space-y-3">
      {blocos.map((bloco) =>
        bloco.tipo === "um" ? (
          <CartaoDaConversa key={bloco.cartao.id} cartao={bloco.cartao} historico={!bloco.cartao.aoVivo} />
        ) : (
          <GrupoDeCartoes key={`grupo-${bloco.tipoDeCartao}`} tipo={bloco.tipoDeCartao} cartoes={bloco.cartoes} />
        ),
      )}
    </div>
  );
}
