import type { Metadata } from "next";

import { Problema } from "@/componentes/compartilhados/Problema";
import { TelaDoCardapio } from "@/componentes/produto/cardapio";
import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Cardápio" };

/** Os pratos aceitos, com o preço e o lucro de agora, e as decisões em frases. */
export default async function PaginaDoCardapio() {
  try {
    return <TelaDoCardapio cardapio={await api.cardapio.ler()} />;
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir o cardápio"
        nivelTitulo={1}
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
}
