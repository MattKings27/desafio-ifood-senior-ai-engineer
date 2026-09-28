/**
 * O cartão de um ingrediente na grade da despensa (a tela inicial usa também).
 *
 * O cartão inteiro leva à página do item. Mostra a foto (ou o desenho da
 * categoria), o nome, quanto ela tem, quanto pagou e o custo por quilo, litro
 * ou unidade, com a conta logo abaixo: número sem a conta não aparece. Os
 * selos dizem o que falta responder, de onde o item veio (quando não foi da
 * planilha) e se alguma receita já usa.
 *
 * No modo minimalista, o cartão fica com a foto, o nome, quanto ela tem e
 * quanto pagou, e só o selo do que falta responder: o custo por quilo e a
 * conta ficam na página do item.
 */

import { CheckCircle, Question, ShoppingCartSimple, Tray } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

import { CardLink } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { ItemDaDespensa } from "@/lib/api/despensa";

import { FotoDoIngrediente } from "./FotoDoIngrediente";
import { comMaiuscula, semQuebrarNumero } from "./texto";

export function SelosDoIngrediente({ item, className }: { item: ItemDaDespensa; className?: string }) {
  return (
    <ul aria-label="Situação" className={clsx("flex flex-wrap gap-1.5", className)}>
      {item.pendente ? (
        <li>
          <Chip tom="atencao" icone={<Question size={14} weight="fill" />}>
            Falta uma resposta
          </Chip>
        </li>
      ) : null}
      {item.origem !== "planilha" ? (
        <li className="minimalista:hidden">
          <Chip
            tom={item.origem === "orcamento" ? "info" : "neutro"}
            icone={item.origem === "orcamento" ? <ShoppingCartSimple size={14} weight="fill" /> : undefined}
          >
            {comMaiuscula(item.origem_rotulo)}
          </Chip>
        </li>
      ) : null}
      <li className="minimalista:hidden">
        {item.receitas_que_usam > 0 ? (
          <Chip tom="sucesso" icone={<CheckCircle size={14} weight="fill" />}>
            {comMaiuscula(item.receitas_que_usam_texto)}
          </Chip>
        ) : (
          <Chip tom="neutro" icone={<Tray size={14} weight="bold" />}>
            {comMaiuscula(item.receitas_que_usam_texto)}
          </Chip>
        )}
      </li>
    </ul>
  );
}

export function CartaoIngrediente({
  item,
  nivelTitulo = 3,
  className,
}: {
  item: ItemDaDespensa;
  nivelTitulo?: 2 | 3 | 4;
  className?: string;
}) {
  return (
    <CardLink
      href={item.rota}
      titulo={item.nome}
      nivelTitulo={nivelTitulo}
      densidade="nenhuma"
      className={clsx("flex h-full flex-col overflow-hidden", className)}
      classeDoTitulo="px-3 pt-3 [overflow-wrap:anywhere] hyphens-auto"
      midia={<FotoDoIngrediente imagem={item.imagem} categoria={item.categoria} />}
    >
      <div className="flex flex-1 flex-col gap-1 px-3 pt-1 pb-3">
        <p className="text-sm text-texto">
          <span className="sr-only">Tem </span>
          {item.estoque_texto}
        </p>
        <p className="text-sm text-apagado">
          {item.pago ? (
            <>
              Pagou <Valor dinheiro={item.pago} tamanho="sm" />
            </>
          ) : (
            "Ainda sem o preço"
          )}
        </p>
        <p className="mt-1 minimalista:hidden">
          {item.custo_unitario ? (
            <Valor dinheiro={item.custo_unitario} tamanho="md" />
          ) : (
            <span className="text-sm font-semibold text-atencao">Custo ainda desconhecido</span>
          )}
        </p>
        <Derivacao className="mt-0 minimalista:hidden">{semQuebrarNumero(item.derivacao)}</Derivacao>
        <SelosDoIngrediente item={item} className="mt-auto pt-2" />
      </div>
    </CardLink>
  );
}
