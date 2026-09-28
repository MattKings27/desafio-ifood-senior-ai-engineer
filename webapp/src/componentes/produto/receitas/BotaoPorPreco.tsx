"use client";

/**
 * "Pôr preço": abre a conversa com o pedido escrito ("Quero pôr preço na …") e
 * o contexto da receita. Quem manda é ela; o agente conduz o preço.
 *
 * Só fica liberado quando o checklist de produção libera o aceite: a cozinha
 * dando conta, ela gostando do prato e o que toda cozinha tem confirmado. Fora
 * disso o botão fica desabilitado, mas continua no caminho do teclado, com o
 * que falta escrito embaixo, item por item, e ligado a ele: quem usa leitor de
 * tela ouve o porquê.
 */

import { CurrencyCircleDollar } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";
import { useId } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { useConversa } from "@/componentes/conversa";

import type { PermissaoDePreco } from "./textos";
import { rascunhoDoPreco } from "./textos";

export function BotaoPorPreco({
  slug,
  nome,
  permissao,
  aoLado,
  className,
}: {
  slug: string;
  nome: string;
  permissao: PermissaoDePreco;
  /** Outra ação na mesma linha (o "Perguntar"); o motivo fica embaixo das duas. */
  aoLado?: ReactNode;
  className?: string;
}) {
  const { abrir } = useConversa();
  const id = useId();
  const idDoMotivo = `motivo${id}`;
  return (
    <div className={className}>
      <div className="flex flex-col gap-2 min-[420px]:flex-row">
        <Botao
          className="aria-disabled:opacity-50 aria-disabled:hover:bg-marca-fundo min-[420px]:flex-1"
          icone={<CurrencyCircleDollar size={20} weight="bold" />}
          aria-disabled={!permissao.pode || undefined}
          aria-describedby={permissao.pode ? undefined : idDoMotivo}
          onClick={(evento) => {
            if (!permissao.pode) return;
            abrir({
              rascunho: rascunhoDoPreco(nome),
              contexto: { tela: "receitas", tipo: "receita", id: slug, rotulo: nome },
              origem: evento.currentTarget,
            });
          }}
        >
          Pôr preço
        </Botao>
        {aoLado}
      </div>
      {permissao.pode ? null : (
        <div id={idDoMotivo} className="mt-2 text-sm text-texto-secundario">
          <p>{permissao.motivo}</p>
          {permissao.faltam.length > 0 ? (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {permissao.faltam.map((falta) => (
                <li key={falta} className="[overflow-wrap:anywhere]">
                  {falta}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}
