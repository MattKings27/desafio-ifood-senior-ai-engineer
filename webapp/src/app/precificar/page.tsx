import type { Metadata } from "next";

import { TelaDePorPreco } from "@/componentes/produto/precificar";
import type { ReceitaGuardada } from "@/lib/api/receitas";
import { receitasDeHoje } from "@/lib/api/receitas";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Pôr preço" };

/**
 * Pôr preço num prato. Vindo de outra tela com `?prato=`, abre com a receita
 * que ela já conferiu; se a receita sumiu, abre vazia em vez de quebrar.
 */
export default async function PaginaDePorPreco({ searchParams }: { searchParams: Promise<{ prato?: string }> }) {
  const { prato } = await searchParams;
  const inicial: ReceitaGuardada | null = prato ? await receitasDeHoje.receita(prato).catch(() => null) : null;
  return <TelaDePorPreco inicial={inicial} />;
}
