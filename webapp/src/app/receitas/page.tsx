import type { Metadata } from "next";
import { Suspense } from "react";

import { EsqueletoDaPagina } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import {
  ESQUEMA_DAS_RECEITAS,
  chaveDoPedido,
  esquemaComAba,
  paraBusca,
  paraPedido,
  pedidoDasQueNaoQuer,
} from "@/componentes/produto/receitas/filtros";
import { TelaDasReceitas } from "@/componentes/produto/receitas/TelaDasReceitas";
import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";
import { lerFiltros } from "@/lib/filtros/url";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Receitas" };

/**
 * As receitas que ela consegue fazer. A aba e os filtros vêm da URL: a
 * primeira lista chega pronta do servidor, e a tela pede as próximas quando
 * ela troca de aba ou de filtro.
 *
 * Sem aba escolhida, nada para fazer ainda e receitas esperando resposta, a
 * página abre em "Falta uma resposta sua": é onde está o que ela pode fazer.
 *
 * As que ela não quer vêm junto, com os mesmos filtros: cada aba mostra, no
 * fim, as suas em "Não gosto de fazer", com a contagem à vista.
 */
export default async function PaginaReceitas({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const busca = paraBusca(await searchParams);
  const pedido = paraPedido(lerFiltros(busca, ESQUEMA_DAS_RECEITAS));
  const pedidoNaoQuer = pedidoDasQueNaoQuer(pedido);
  let lista: Awaited<ReturnType<typeof api.receitas.listar>>;
  let naoQuer: Awaited<ReturnType<typeof api.receitas.listar>>;
  try {
    [lista, naoQuer] = await Promise.all([api.receitas.listar(pedido), api.receitas.listar(pedidoNaoQuer)]);
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir as receitas"
        nivelTitulo={1}
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
  // Sem aba escolhida e nada para fazer ainda, abre em "Falta uma resposta sua" na
  // mesma ida ao servidor: um redirect refazia a página inteira, com a tela vazia no meio.
  let pedidoInicial = pedido;
  let abaPadrao: "falta_resposta" | undefined;
  if (!busca.has("aba") && lista.contagens.pode_fazer === 0 && lista.contagens.falta_resposta > 0) {
    const pedidoFalta = paraPedido(lerFiltros(busca, esquemaComAba("falta_resposta")));
    try {
      lista = await api.receitas.listar(pedidoFalta);
      pedidoInicial = pedidoFalta;
      abaPadrao = "falta_resposta";
    } catch {
      // Sem a outra aba, fica a padrão: a tela diz que não há nada para fazer ainda.
    }
  }
  return (
    <Suspense fallback={<EsqueletoDaPagina variante="grade" rotulo="Carregando as receitas…" />}>
      <TelaDasReceitas
        inicial={lista}
        chaveInicial={chaveDoPedido(pedidoInicial)}
        abaPadrao={abaPadrao}
        naoQuerInicial={naoQuer}
        chaveDasQueNaoQuerInicial={chaveDoPedido(pedidoNaoQuer)}
      />
    </Suspense>
  );
}
