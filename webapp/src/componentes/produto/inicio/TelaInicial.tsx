/**
 * A tela inicial: o próximo passo, as perguntas, os cinco números, onde o
 * dinheiro está parado, as receitas que dão pra fazer e a prévia do cardápio,
 * numa leitura só da API (`GET /api/visao-geral`).
 */

import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import type { VisaoGeral } from "@/lib/api/visao-geral";

import { DinheiroParado } from "./DinheiroParado";
import { Indicadores } from "./Indicadores";
import { Perguntas } from "./Perguntas";
import { perguntasDaCozinha } from "./perguntasDaCozinha";
import { PreviaDoCardapio } from "./PreviaDoCardapio";
import { ProximoPasso } from "./ProximoPasso";
import { ReceitasRecomendadas } from "./ReceitasRecomendadas";

/** O próximo passo que aponta para as perguntas só aparece se houver pergunta para ela responder aqui. */
function temPasso(visao: VisaoGeral): boolean {
  return visao.proximo_passo.acao.rota !== "/#perguntas" || perguntasDaCozinha(visao.perguntas_da_cozinha).length > 0;
}

export function TelaInicial({ visao }: { visao: VisaoGeral }) {
  return (
    <div className="space-y-8">
      <CabecalhoDaPagina
        titulo="Início"
        descricao="O que falta responder, o que já dá pra fazer e onde está o dinheiro da senhora."
        resumivel
        className="mb-0"
      />
      {temPasso(visao) ? <ProximoPasso passo={visao.proximo_passo} /> : null}
      <Indicadores kpis={visao.kpis} />
      <Perguntas perguntas={visao.perguntas_da_cozinha} />
      <div className="grid gap-8 xl:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
        <DinheiroParado parado={visao.dinheiro_parado} />
        <PreviaDoCardapio pratos={visao.cardapio_previa} />
      </div>
      <ReceitasRecomendadas receitas={visao.receitas_recomendadas} />
    </div>
  );
}
