import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problema } from "@/componentes/compartilhados/Problema";
import type { ReceitaQueUsaNaTela } from "@/componentes/produto/despensa/DetalheDoIngrediente";
import { DetalheDoIngrediente } from "@/componentes/produto/despensa/DetalheDoIngrediente";
import type { DetalheDoItem, ListaDaDespensa } from "@/lib/api/despensa";
import type { ListaDeReceitas } from "@/lib/api/receitas";
import { api, ErroDoMotor } from "@/lib/api";

export const dynamic = "force-dynamic";

type Parametros = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Parametros): Promise<Metadata> {
  const { id } = await params;
  try {
    return { title: (await api.despensa.item(id)).nome };
  } catch {
    return { title: "Despensa" };
  }
}

/** As receitas que usam o item: as do catálogo primeiro, depois as que ela está avaliando. */
function receitasQueUsam(detalhe: DetalheDoItem, catalogo: ListaDeReceitas | null): ReceitaQueUsaNaTela[] {
  const vistas = new Set<string>();
  const todas: ReceitaQueUsaNaTela[] = [];
  for (const receita of catalogo?.itens ?? []) {
    vistas.add(receita.slug);
    todas.push({
      slug: receita.slug,
      nome: receita.nome,
      imagem: receita.imagem,
      rota: receita.rota,
      usa_texto: receita.usa_texto,
      selo: { texto: receita.selo.texto, codigo: receita.selo.codigo },
    });
  }
  for (const receita of detalhe.receitas) {
    if (vistas.has(receita.slug)) continue;
    todas.push({
      slug: receita.slug,
      nome: receita.nome,
      imagem: receita.imagem,
      rota: receita.rota,
      usa_texto: receita.usa_texto,
      selo: { texto: receita.veredito_rotulo, veredito: receita.veredito },
    });
  }
  return todas;
}

/** A página de um ingrediente. Item que não existe (ou que saiu) é "não encontrei". */
export default async function PaginaDoIngrediente({ params }: Parametros) {
  const { id } = await params;
  let detalhe: DetalheDoItem;
  let lista: ListaDaDespensa | null;
  let catalogo: ListaDeReceitas | null;
  try {
    [detalhe, lista, catalogo] = await Promise.all([
      api.despensa.item(id),
      api.despensa.listar().catch(() => null),
      api.receitas.listar({ usa: id }).catch(() => null),
    ]);
  } catch (erro) {
    const e = erro instanceof ErroDoMotor ? erro : null;
    if (e?.categoria === "ausente") notFound();
    return (
      <Problema
        titulo="Não consegui abrir este ingrediente"
        mensagem={e?.message}
        categoria={e?.categoria ?? "rede"}
        pergunta={e?.pergunta}
        recarregar
      />
    );
  }
  return (
    <DetalheDoIngrediente
      detalhe={detalhe}
      receitas={receitasQueUsam(detalhe, catalogo)}
      categorias={lista?.categorias_para_escolher ?? []}
      orcamento={lista?.orcamento ?? null}
    />
  );
}
