import type { Metadata } from "next";
import { Suspense } from "react";

import { EsqueletoDaPagina } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import {
  ESQUEMA_DO_HISTORICO,
  TelaDoHistorico,
  chaveDoPedido,
  paraBusca,
  paraPedido,
} from "@/componentes/produto/historico";
import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";
import { lerFiltros } from "@/lib/filtros/url";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Histórico" };

/**
 * O histórico, agrupado por dia. A busca e os filtros vêm da URL: a primeira
 * página chega pronta do servidor, e a tela pede as próximas.
 */
export default async function PaginaDoHistorico({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const pedido = paraPedido(lerFiltros(paraBusca(await searchParams), ESQUEMA_DO_HISTORICO));
  try {
    const pagina = await api.atividades.listar(pedido);
    return (
      <Suspense fallback={<EsqueletoDaPagina variante="lista" rotulo="Carregando o histórico…" />}>
        <TelaDoHistorico inicial={pagina} chaveInicial={chaveDoPedido(pedido)} />
      </Suspense>
    );
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir o histórico"
        nivelTitulo={1}
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
}
