import type { Metadata } from "next";
import { Suspense } from "react";

import { EsqueletoDaPagina } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import { TelaDaCozinha } from "@/componentes/produto/cozinha/TelaDaCozinha";
import type { PerfilDaCozinha } from "@/lib/api/perfil";
import { api, ErroDoMotor } from "@/lib/api";

export const metadata: Metadata = { title: "Cozinha" };
export const dynamic = "force-dynamic";

/**
 * A cozinha dela: equipamentos, técnicas e os limites da rotina, cada um com a
 * resposta dela, gravada item a item. Os filtros moram na URL (daí o Suspense).
 */
export default async function PaginaDaCozinha() {
  let perfil: PerfilDaCozinha;
  try {
    perfil = await api.perfil.ler();
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir a cozinha"
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
  return (
    <Suspense fallback={<EsqueletoDaPagina variante="lista" rotulo="Carregando a cozinha…" />}>
      <TelaDaCozinha perfil={perfil} />
    </Suspense>
  );
}
