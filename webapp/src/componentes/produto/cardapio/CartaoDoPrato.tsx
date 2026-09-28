"use client";

/**
 * Um prato do cardápio: o preço que ela escolheu, o que chega para ela depois
 * da taxa, o custo e o lucro da porção, com a conta escrita embaixo (a conta
 * nunca fica escondida). O cartão inteiro leva à receita.
 *
 * No modo minimalista, o cartão fica com o preço e o lucro por porção: o que
 * chega para ela, o custo, a conta escrita, a data e as notas ficam na receita.
 *
 * "Mudar preço" abre a conversa com o pedido escrito: o preço é decisão dela,
 * com a conta do agente ao lado. "Tirar do cardápio" pede confirmação e
 * deixa desfazer no aviso.
 */

import { ChatCircleDots, Star, Trash, Warning } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { AcimaDoLink, CardLink } from "@/componentes/compartilhados/Card";
import { DialogoDeConfirmacao } from "@/componentes/compartilhados/Dialogo";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import { useConversa } from "@/componentes/conversa";
import type { PratoDoCardapio } from "@/lib/api/cardapio";
import { rascunhos } from "@/lib/conversa/perguntas";

function Linha({ rotulo, children, className }: { rotulo: string; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("flex items-baseline justify-between gap-3 py-1.5", className)}>
      <dt className="text-sm text-apagado">{rotulo}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

export function CartaoDoPrato({
  prato,
  aoTirar,
  tirando = false,
}: {
  prato: PratoDoCardapio;
  aoTirar: (prato: string) => Promise<unknown>;
  tirando?: boolean;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const { abrir } = useConversa();

  return (
    <>
      <CardLink
        href={prato.rota}
        titulo={prato.prato}
        como="article"
        densidade="nenhuma"
        className="flex h-full flex-col overflow-hidden"
        classeDoTitulo="px-4 pt-3 text-lg"
        midia={
          <div className="relative">
            <ImagemComFallback src={prato.imagem?.url} alt="" proporcao="16/9" tipo="prato" />
            {prato.nota ? (
              <span className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-full bg-superficie px-2 py-0.5 text-xs font-bold text-tinta shadow-cartao">
                <Star size={13} weight="fill" aria-hidden="true" className="text-atencao" />
                <span className="numero">{prato.nota.texto}</span>
                <span className="sr-only"> de pontuação</span>
              </span>
            ) : null}
          </div>
        }
      >
        <div className="flex flex-1 flex-col gap-3 px-4 pt-1 pb-4">
          <p className="text-sm text-apagado minimalista:hidden">Aceito {prato.decidido_texto}</p>
          <dl className="divide-y divide-borda">
            <Linha rotulo="Preço">
              <Valor dinheiro={prato.preco} tamanho="lg" />
            </Linha>
            <Linha rotulo="Chega para a senhora" className="minimalista:hidden">
              <Valor dinheiro={prato.recebe} tamanho="sm" />
            </Linha>
            <Linha rotulo="Custo de uma porção" className="minimalista:hidden">
              <Valor dinheiro={prato.custo_porcao} tamanho="sm" />
            </Linha>
            <Linha rotulo="Lucro por porção">
              <Valor dinheiro={prato.lucro_porcao} tamanho="md" tom={prato.da_prejuizo ? "negativo" : "positivo"} />
            </Linha>
          </dl>
          {prato.derivacao ? <Derivacao className="minimalista:hidden">{prato.derivacao}</Derivacao> : null}
          {prato.aviso ? (
            <p className="flex items-start gap-2 rounded-md border border-atencao/25 bg-atencao/10 p-2.5 text-sm text-texto">
              <Warning size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
              <span>{prato.aviso}</span>
            </p>
          ) : null}
          {prato.notas ? <p className="text-sm text-texto italic minimalista:hidden">“{prato.notas}”</p> : null}
          <AcimaDoLink className="mt-auto flex flex-col gap-2 pt-1 min-[420px]:flex-row">
            <Botao
              variante="secundario"
              tamanho="md"
              icone={<ChatCircleDots size={18} weight="bold" />}
              className="min-[420px]:flex-1"
              onClick={(evento) =>
                abrir({
                  rascunho: rascunhos.mudarPreco(prato.prato),
                  contexto: { tela: "cardapio", tipo: "prato", id: prato.slug, rotulo: prato.prato },
                  origem: evento.currentTarget,
                })
              }
            >
              Mudar preço
            </Botao>
            <Botao
              variante="terciario"
              tamanho="md"
              icone={<Trash size={18} weight="bold" />}
              className="min-[420px]:flex-1"
              onClick={() => setConfirmando(true)}
            >
              Tirar do cardápio
            </Botao>
          </AcimaDoLink>
        </div>
      </CardLink>
      <DialogoDeConfirmacao
        aberto={confirmando}
        titulo={`Tirar ${prato.prato} do cardápio?`}
        descricao="O prato sai do cardápio agora. Se mudar de ideia, dá para desfazer no aviso que aparece em seguida, ou no histórico."
        rotuloConfirmar="Tirar do cardápio"
        perigoso
        carregando={tirando}
        aoCancelar={() => setConfirmando(false)}
        aoConfirmar={() => {
          void aoTirar(prato.prato).then(() => setConfirmando(false));
        }}
      />
    </>
  );
}
