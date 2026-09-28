import type { Metadata } from "next";

import { Problema } from "@/componentes/compartilhados/Problema";
import { TelaInicial } from "@/componentes/produto/inicio";
import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Início" };

/**
 * A tela inicial numa leitura só (`GET /api/visao-geral`): o próximo passo, as
 * perguntas, os números, o dinheiro parado, as receitas e o cardápio.
 */
export default async function PaginaInicial() {
  try {
    return <TelaInicial visao={await api.visaoGeral.ler()} />;
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir o início"
        nivelTitulo={1}
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
}
