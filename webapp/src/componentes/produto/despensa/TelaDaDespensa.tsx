"use client";

/**
 * A tela da despensa: o que ela tem, quanto pagou e quanto custa cada quilo,
 * o orçamento dos complementos e a grade filtrável. O que a planilha não diz
 * (o peso da embalagem, o preço pago) não é pergunta: a plataforma estima, com
 * a fonte, e ela corrige no próprio item, pelo Editar.
 *
 * A lista chega inteira do server component; filtrar e ordenar é no navegador,
 * com os filtros na URL (por isso a tela fica dentro de um `<Suspense>`). O
 * formulário de acrescentar abre pelo cabeçalho ("Adicionar ingrediente") e
 * pelo orçamento ("Registrar compra", já em "Comprei com os R$ 80").
 *
 * No modo minimalista, a descrição e a conta do orçamento somem, e os cartões
 * ficam com o essencial.
 */

import { Plus } from "@phosphor-icons/react/dist/ssr";
import { useMemo, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import { Valor } from "@/componentes/compartilhados/Valor";
import type { ListaDaDespensa } from "@/lib/api/despensa";
import { useFiltrosNaUrl } from "@/lib/dados/useFiltrosNaUrl";
import { FILTROS_DA_DESPENSA, contar, itensVisiveis } from "@/lib/filtros/despensa";

import { CartaoIngrediente } from "./CartaoIngrediente";
import { FiltrosDaDespensa } from "./FiltrosDaDespensa";
import type { PedidoDoFormulario } from "./FormularioDoItem";
import { FormularioDoItem } from "./FormularioDoItem";
import { PainelDoOrcamento } from "./PainelDoOrcamento";

export function TelaDaDespensa({ lista }: { lista: ListaDaDespensa }) {
  const { filtros, definir, limpar } = useFiltrosNaUrl(FILTROS_DA_DESPENSA);
  const [formulario, setFormulario] = useState<PedidoDoFormulario | null>(null);
  const visiveis = useMemo(() => itensVisiveis(lista.itens, filtros), [lista.itens, filtros]);

  return (
    <>
      <CabecalhoDaPagina
        titulo="Despensa"
        descricao="O que a senhora tem, quanto pagou e quanto custa cada quilo. Toda conta aparece ao lado do número."
        resumivel
        acoes={
          <Botao icone={<Plus size={18} weight="bold" />} onClick={() => setFormulario({ modo: "novo", origem: "ja_tinha" })}>
            Adicionar ingrediente
          </Botao>
        }
      >
        <p className="mt-2 text-base text-texto">
          <Valor dinheiro={lista.total_investido} tamanho="md" /> pagos em{" "}
          {contar(lista.total_itens, "ingrediente", "ingredientes")}.
        </p>
      </CabecalhoDaPagina>

      <div className="grid items-start gap-4 lg:grid-cols-5">
        <PainelDoOrcamento
          orcamento={lista.orcamento}
          aoRegistrarCompra={() => setFormulario({ modo: "novo", origem: "orcamento" })}
          className="lg:col-span-5"
        />
      </div>

      <section aria-labelledby="titulo-dos-ingredientes" className="mt-8">
        <h2 id="titulo-dos-ingredientes" className="mb-3 text-lg font-bold text-tinta">
          Ingredientes
        </h2>
        <FiltrosDaDespensa
          filtros={filtros}
          definir={definir}
          limpar={() => limpar()}
          categorias={lista.categorias}
          totalItens={lista.total_itens}
          encontrados={visiveis.length}
        />
        {visiveis.length > 0 ? (
          <ul className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {visiveis.map((item) => (
              <li key={item.id} className="min-w-0">
                <CartaoIngrediente item={item} />
              </li>
            ))}
          </ul>
        ) : (
          <EstadoVazio
            className="mt-4"
            titulo={lista.itens.length === 0 ? "A despensa está vazia" : "Nenhum ingrediente com esses filtros"}
            descricao={
              lista.itens.length === 0
                ? "Acrescente o que a senhora tem, e eu faço as contas."
                : "Tire um filtro ou procure com outra palavra."
            }
            acao={
              lista.itens.length === 0 ? (
                <Botao icone={<Plus size={18} weight="bold" />} onClick={() => setFormulario({ modo: "novo", origem: "ja_tinha" })}>
                  Adicionar ingrediente
                </Botao>
              ) : (
                <Botao variante="secundario" onClick={() => limpar()}>
                  Limpar filtros
                </Botao>
              )
            }
          />
        )}
      </section>

      <FormularioDoItem
        pedido={formulario}
        aoFechar={() => setFormulario(null)}
        categorias={lista.categorias_para_escolher}
        orcamento={lista.orcamento}
      />
    </>
  );
}
