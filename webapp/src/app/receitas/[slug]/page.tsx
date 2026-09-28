import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { Problema } from "@/componentes/compartilhados/Problema";
import type { CustoNaTela } from "@/componentes/produto/receitas/CustoDaReceita";
import { DetalheDaReceita } from "@/componentes/produto/receitas/DetalheDaReceita";
import { api } from "@/lib/api";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { Estimativa } from "@/lib/api/preco";
import { textoParaEla } from "@/lib/formato";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ slug: string }> };

/** Uma leitura por pedido: o título da aba e a página usam a mesma resposta. */
const lerReceita = cache((slug: string) => api.receitas.detalhe(slug));

async function lerCusto(slug: string): Promise<CustoNaTela> {
  try {
    return { tipo: "pronto", custo: await api.receitas.custo(slug) };
  } catch (erro) {
    if (erro instanceof ErroDoMotor && (erro.categoria === "regra" || erro.status === 409)) {
      return { tipo: "recusado", motivo: textoParaEla(erro.message, "Ainda não calculo o custo desta receita.") };
    }
    const mensagem = erro instanceof ErroDoMotor ? textoParaEla(erro.message, MENSAGENS.rede) : MENSAGENS.rede;
    return { tipo: "falhou", mensagem: `Não consegui buscar o custo agora. ${mensagem}` };
  }
}

/** O preço preliminar é um extra da página: recusado, sem a rota ou fora do ar, a seção não aparece. */
async function lerEstimativa(slug: string): Promise<Estimativa | null> {
  try {
    return await api.preco.estimativa(slug);
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  try {
    return { title: (await lerReceita(slug)).nome };
  } catch {
    return { title: "Receita" };
  }
}

export default async function PaginaDaReceita({ params }: Props) {
  const { slug } = await params;
  let receita;
  try {
    receita = await lerReceita(slug);
  } catch (erro) {
    if (erro instanceof ErroDoMotor && erro.categoria === "ausente") notFound();
    const e = erro instanceof ErroDoMotor ? erro : null;
    return (
      <Problema
        titulo="Não consegui abrir esta receita"
        nivelTitulo={1}
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
  const [custo, estimativa] = await Promise.all([lerCusto(receita.slug), lerEstimativa(receita.slug)]);
  return <DetalheDaReceita receita={receita} custo={custo} estimativa={estimativa} />;
}
