/**
 * A grade de cards e a lista de "Falta uma resposta sua".
 *
 * As colunas seguem a largura que a grade tem (consulta de contêiner), não a
 * da janela: 2 no celular, 3 a partir de 672 px, 4 a partir de 1024 px. Com o
 * painel da conversa aberto ao lado, a grade estreita e perde uma coluna em
 * vez de espremer os cards. Os esqueletos no fim da grade são as receitas que
 * a procura ainda está trazendo.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

import { EsqueletoCartao } from "@/componentes/compartilhados/Esqueleto";
import type { ItemDaGrade } from "@/lib/api/receitas";

import { CartaoDeReceita, CartaoPendente } from "./CartaoDeReceita";

export const CLASSE_DA_GRADE = "grid grid-cols-2 gap-3 sm:gap-4 @2xl:grid-cols-3 @5xl:grid-cols-4";

const CLASSE_DA_LISTA = "grid grid-cols-1 gap-3 sm:gap-4 @2xl:grid-cols-2 @5xl:grid-cols-3";

export function GradeDeReceitas({
  itens,
  rotulo,
  posicoes,
  esqueletos = 0,
  nivelTitulo = 3,
  acaoDe,
  className,
}: {
  itens: readonly ItemDaGrade[];
  /** O nome da lista para o leitor de tela ("Gosto de fazer"). */
  rotulo: string;
  /** No ranking inteiro, a posição de cada uma aparece na foto. */
  posicoes?: ReadonlyMap<string, number>;
  /** Cards que ainda estão chegando (a procura em andamento). */
  esqueletos?: number;
  /** Dentro de uma seção, o nome do card fica um nível abaixo do título dela. */
  nivelTitulo?: 3 | 4;
  /** O que fica por cima do link de cada card (a pergunta do gosto). */
  acaoDe?: (item: ItemDaGrade) => ReactNode;
  className?: string;
}) {
  return (
    <ul aria-label={rotulo} className={clsx(CLASSE_DA_GRADE, className)}>
      {itens.map((item, indice) => (
        <li key={item.slug} className="min-w-0">
          <CartaoDeReceita
            item={item}
            posicao={posicoes?.get(item.slug)}
            prioridade={indice < 4}
            nivelTitulo={nivelTitulo}
            acao={acaoDe?.(item)}
          />
        </li>
      ))}
      {Array.from({ length: esqueletos }, (_, indice) => (
        <li key={`chegando-${indice}`} aria-hidden="true" className="min-w-0">
          <EsqueletoCartao comImagem className="h-full" />
        </li>
      ))}
    </ul>
  );
}

export function ListaPendente({
  itens,
  rotulo,
  nivelTitulo = 3,
  className,
}: {
  itens: readonly ItemDaGrade[];
  rotulo: string;
  nivelTitulo?: 3 | 4;
  className?: string;
}) {
  return (
    <ul aria-label={rotulo} className={clsx(CLASSE_DA_LISTA, className)}>
      {itens.map((item) => (
        <li key={item.slug} className="min-w-0">
          <CartaoPendente item={item} nivelTitulo={nivelTitulo} />
        </li>
      ))}
    </ul>
  );
}
