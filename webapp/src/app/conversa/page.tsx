import type { Metadata } from "next";

import { TelaDaConversa } from "@/componentes/conversa/TelaDaConversa";
import type { BuscaDaPagina } from "@/lib/conversa/chegada";
import { chegadaDaBusca } from "@/lib/conversa/chegada";

export const metadata: Metadata = { title: "Conversa" };

/** A conversa em tela cheia. As mensagens vêm da loja do chat, no navegador. */
export default async function PaginaDaConversa({ searchParams }: { searchParams: Promise<BuscaDaPagina> }) {
  return <TelaDaConversa chegada={chegadaDaBusca(await searchParams)} />;
}
