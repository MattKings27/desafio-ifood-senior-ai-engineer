import type { Metadata } from "next";
import { Suspense } from "react";

import { EsqueletoDaPagina } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import { TelaDaDespensa } from "@/componentes/produto/despensa/TelaDaDespensa";
import type { ListaDaDespensa } from "@/lib/api/despensa";
import { api, ErroDoMotor } from "@/lib/api";

export const metadata: Metadata = { title: "Despensa" };
export const dynamic = "force-dynamic";

/**
 * A despensa inteira numa leitura só: os itens, as perguntas e o orçamento.
 * Filtrar e ordenar é no navegador, com os filtros na URL (daí o Suspense).
 */
export default async function PaginaDaDespensa() {
  let lista: ListaDaDespensa;
  try {
    lista = await api.despensa.listar();
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir a despensa"
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
  return (
    <Suspense fallback={<EsqueletoDaPagina variante="grade" rotulo="Carregando a despensa…" />}>
      <TelaDaDespensa lista={lista} />
    </Suspense>
  );
}
