"use client";

/**
 * As compras com os R$ 80: o que ela comprou, quando, quanto, e "Devolver ao
 * orçamento" enquanto dá.
 *
 * Devolver pede confirmação (o item que a compra acrescentou sai da despensa
 * junto) e some da lista na hora; se a API recusar, a compra volta sozinha. O
 * aviso traz a frase da API ("Devolvi R$ 9,00 aos complementos; …").
 */

import { ArrowUUpLeft } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Chip } from "@/componentes/compartilhados/Chip";
import { DialogoDeConfirmacao } from "@/componentes/compartilhados/Dialogo";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { Valor } from "@/componentes/compartilhados/Valor";
import { devolverCompra } from "@/lib/acoes/despensa";
import type { CompraDoOrcamento } from "@/lib/api/despensa";
import { useAcaoOtimista } from "@/lib/dados/useAcao";
import { novoIdCliente } from "@/lib/dados/id";

/** Depois de devolver, a compra fica marcada até a lista vir de novo da API. */
function marcarDevolvida(compras: CompraDoOrcamento[], id: number): CompraDoOrcamento[] {
  return compras.map((compra) => (compra.id === id ? { ...compra, estornada: true, pode_estornar: false } : compra));
}

export function ListaDeCompras({
  compras,
  vazio,
  visiveis = 5,
  className,
}: {
  compras: CompraDoOrcamento[];
  vazio?: ReactNode;
  visiveis?: number;
  className?: string;
}) {
  const [aDevolver, setADevolver] = useState<CompraDoOrcamento | null>(null);
  // A mais nova em cima, como num extrato.
  const maisNovasPrimeiro = useMemo(() => [...compras].sort((a, b) => b.id - a.id), [compras]);
  const { estado, executar, pendente } = useAcaoOtimista(
    maisNovasPrimeiro,
    marcarDevolvida,
    (id: number) => devolverCompra(id, novoIdCliente()),
    { sucesso: (dados) => dados.texto },
  );

  return (
    <div className={className}>
      <ListaExpansivel
        itens={estado}
        visiveis={visiveis}
        chave={(compra) => String(compra.id)}
        descricaoDoResto="compras"
        className="divide-y divide-borda"
        vazio={vazio}
        renderizar={(compra) => (
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 py-3">
            <div className="min-w-0 flex-1 basis-40">
              <p className="font-semibold [overflow-wrap:anywhere] text-tinta">
                {compra.item_id && !compra.estornada ? (
                  <Link
                    href={`/despensa/${compra.item_id}`}
                    className="-my-2.5 inline-block py-2.5 underline-offset-4 hover:underline"
                  >
                    {compra.descricao}
                  </Link>
                ) : (
                  compra.descricao
                )}
              </p>
              <p className="text-sm text-apagado">
                {compra.quando_texto}
                {compra.canal === "conversa" ? ", pela conversa" : ""}
              </p>
              {compra.estornada ? (
                <Chip tom="neutro" className="mt-1">
                  Voltou para o orçamento
                </Chip>
              ) : null}
            </div>
            <Valor dinheiro={compra.valor} className={clsx(compra.estornada && "line-through")} />
            {compra.pode_estornar ? (
              <Botao
                variante="texto"
                tamanho="sm"
                icone={<ArrowUUpLeft size={18} weight="bold" />}
                className="-ml-3 basis-full justify-start sm:ml-0 sm:basis-auto"
                onClick={() => setADevolver(compra)}
              >
                Devolver ao orçamento
              </Botao>
            ) : null}
          </div>
        )}
      />
      <DialogoDeConfirmacao
        aberto={aDevolver !== null}
        titulo="Devolver ao orçamento?"
        descricao={
          aDevolver
            ? `${aDevolver.descricao}: ${aDevolver.valor.texto} voltam para os complementos. Se a compra entrou na despensa, o item sai junto.`
            : ""
        }
        rotuloConfirmar="Devolver"
        carregando={pendente}
        aoCancelar={() => setADevolver(null)}
        aoConfirmar={() => {
          const compra = aDevolver;
          setADevolver(null);
          if (compra) void executar(compra.id);
        }}
      />
    </div>
  );
}
