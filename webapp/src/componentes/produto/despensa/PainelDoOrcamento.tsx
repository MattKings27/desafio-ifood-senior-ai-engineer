"use client";

/**
 * O orçamento dos complementos (`/despensa#orcamento`, o destino do cartão da
 * tela inicial): quanto resta, a barra do que já foi, a frase da API que diz
 * a conta, e as compras, cada uma com "Devolver ao orçamento".
 *
 * "Registrar compra" abre o formulário já em "Comprei com os R$ 80". Os
 * valores vêm prontos da API; a tela só mostra.
 */

import { ShoppingCartSimple, Wallet } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

import { Barra } from "@/componentes/compartilhados/Barra";
import { Botao } from "@/componentes/compartilhados/Botao";
import { Card } from "@/componentes/compartilhados/Card";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { OrcamentoDaDespensa } from "@/lib/api/despensa";

import { ListaDeCompras } from "./ListaDeCompras";

export function PainelDoOrcamento({
  orcamento,
  aoRegistrarCompra,
  className,
}: {
  orcamento: OrcamentoDaDespensa;
  aoRegistrarCompra: () => void;
  className?: string;
}) {
  return (
    <Card id="orcamento" aria-labelledby="titulo-do-orcamento" className={clsx("scroll-mt-32", className)}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-marca/10 text-marca"
        >
          <Wallet size={22} weight="bold" />
        </span>
        <div className="min-w-0">
          <h2 id="titulo-do-orcamento" className="text-lg font-bold text-tinta">
            Orçamento dos complementos
          </h2>
          <p className="text-sm text-apagado minimalista:hidden">
            O que sobra dos {orcamento.inicial.texto} para comprar o que falta.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <p className="flex flex-col">
          <span className="text-sm text-apagado">Restam</span>
          <Valor dinheiro={orcamento.restante} tamanho="xl" />
        </p>
        <p className="text-sm text-apagado">
          Já foram <Valor dinheiro={orcamento.gasto} tamanho="sm" />
        </p>
      </div>
      <Barra
        className="mt-2"
        fracao={orcamento.fracao_gasta}
        rotulo="Parte do orçamento já gasta"
        valorTexto={orcamento.texto}
      />
      <Derivacao className="mt-2 text-sm minimalista:hidden">{orcamento.texto}</Derivacao>

      <Botao
        variante="secundario"
        className="mt-4 w-full sm:w-auto"
        icone={<ShoppingCartSimple size={18} weight="bold" />}
        onClick={aoRegistrarCompra}
      >
        Registrar compra
      </Botao>

      <h3 className="mt-5 text-base font-bold text-tinta">Compras com os {orcamento.inicial.texto}</h3>
      <ListaDeCompras
        compras={orcamento.compras}
        className="mt-1"
        vazio={
          <EstadoVazio
            compacto
            className="mt-2"
            titulo="Nenhuma compra ainda"
            descricao="Quando a senhora comprar com os complementos, a compra aparece aqui, com o valor."
          />
        }
      />
    </Card>
  );
}
