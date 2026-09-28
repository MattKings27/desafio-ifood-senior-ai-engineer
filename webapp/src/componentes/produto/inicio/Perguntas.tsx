"use client";

/**
 * "Preciso perguntar uma coisa": as perguntas da cozinha que seguram receitas
 * (equipamento, técnica, rotina). Cada uma tem a resposta ali mesmo e, em cima,
 * o botão **Chat** em destaque, que abre a conversa com a pergunta (no chip
 * "Vendo:" e no começo da frase dela). Quem manda a mensagem é ela.
 *
 * A resposta é a mesma da tela de receitas (tem, não tem, não sei; o número das
 * bocas), que grava no perfil da cozinha. O que a despensa não diz (o peso da
 * embalagem, o preço pago) não é pergunta: a plataforma estima, com a fonte, e
 * ela corrige no item, se quiser.
 *
 * No modo minimalista, cada pergunta fica numa linha, com o Chat e o
 * Responder embaixo; a resposta abre ali mesmo, quando ela toca em Responder.
 */

import type { Icon } from "@phosphor-icons/react";
import { ChatCircleDots, CookingPot } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";
import { useId } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Card } from "@/componentes/compartilhados/Card";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { BotaoResponder, useRespostaRecolhida } from "@/componentes/compartilhados/RespostaRecolhida";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { useConversa } from "@/componentes/conversa";
import { PerguntaEmLinha } from "@/componentes/produto/receitas/RespostaInline";
import type { ContextoDaConversa } from "@/lib/api/conversa";
import type { PerguntaDaCozinha } from "@/lib/api/visao-geral";

import { perguntasDaCozinha } from "./perguntasDaCozinha";

/** O botão Chat da pergunta: abre a conversa com a pergunta e o começo da frase dela. */
export function BotaoChat({
  rascunho,
  contexto,
  descritoPor,
}: {
  rascunho: string;
  contexto: ContextoDaConversa;
  /** O id do texto da pergunta: o leitor de tela diz "Chat" e, depois, qual pergunta. */
  descritoPor: string;
}) {
  const { abrir } = useConversa();
  return (
    <Botao
      variante="primario"
      tamanho="sm"
      icone={<ChatCircleDots size={18} weight="bold" />}
      aria-describedby={descritoPor}
      onClick={(evento) => abrir({ rascunho, contexto, origem: evento.currentTarget })}
      className="shrink-0"
    >
      Chat
    </Botao>
  );
}

/**
 * A pergunta com o rótulo de onde ela vem e o Chat em cima; a resposta embaixo.
 * No modo minimalista, a pergunta toma o lugar do rótulo, numa linha, e a
 * resposta espera o Responder.
 */
function Bloco({
  Icone,
  rotulo,
  pergunta,
  rascunho,
  contexto,
  children,
}: {
  Icone: Icon;
  rotulo: string;
  pergunta: string;
  rascunho: string;
  contexto: ContextoDaConversa;
  children: ReactNode;
}) {
  const id = useId();
  const resposta = useRespostaRecolhida();
  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-apagado minimalista:hidden">
          <Icone size={18} weight="bold" aria-hidden="true" className="shrink-0 text-marca" />
          {rotulo}
        </p>
        <p className="hidden min-w-0 basis-full items-center gap-2 text-base font-semibold text-tinta [contain:inline-size] minimalista:flex">
          <Icone size={18} weight="bold" aria-hidden="true" className="shrink-0 text-marca" />
          <span className="truncate">{pergunta}</span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <BotaoChat rascunho={rascunho} contexto={contexto} descritoPor={`${id}-pergunta`} />
          <BotaoResponder
            aberta={resposta.aberta}
            controla={resposta.id}
            aoAlternar={resposta.alternar}
            descritoPor={`${id}-pergunta`}
          />
        </div>
      </div>
      {/* No modo minimalista a pergunta já está à vista, logo acima; esta fica só para descrever o Chat. */}
      <p id={`${id}-pergunta`} className="sr-only minimalista:hidden">
        {pergunta}
      </p>
      <div id={resposta.id} className={clsx("flex-1", resposta.classeDaResposta)}>
        {children}
      </div>
    </div>
  );
}

export function PerguntaDaCozinhaNoInicio({ pergunta }: { pergunta: PerguntaDaCozinha }) {
  return (
    <Bloco
      Icone={CookingPot}
      rotulo="Sobre a sua cozinha"
      pergunta={pergunta.pergunta.texto}
      rascunho={pergunta.rascunho_chat}
      contexto={{ tela: "inicio", tipo: "pergunta", id: pergunta.id, rotulo: pergunta.pergunta.texto }}
    >
      <Card como="article" className="flex h-full flex-col gap-3">
        <PerguntaEmLinha receita={pergunta.receita} pergunta={pergunta.pergunta} />
        <Link
          href={pergunta.rota}
          className="mt-auto inline-flex min-h-11 items-center self-start rounded-sm px-2 -ml-2 text-sm font-semibold text-marca hover:bg-marca/10"
        >
          Ver as receitas que esperam
        </Link>
      </Card>
    </Bloco>
  );
}

export function Perguntas({ perguntas }: { perguntas: readonly PerguntaDaCozinha[] }) {
  const entradas = perguntasDaCozinha(perguntas);
  if (entradas.length === 0) return null;
  return (
    <section id="perguntas" aria-labelledby="titulo-das-perguntas" className="scroll-mt-24">
      <TituloSecao
        id="titulo-das-perguntas"
        titulo={entradas.length === 1 ? "Preciso perguntar uma coisa" : "Preciso perguntar algumas coisas"}
        apoio="Responda aqui mesmo, ou toque em Chat para conversar sobre a pergunta."
        resumivel
      />
      <ListaExpansivel
        itens={entradas}
        visiveis={3}
        chave={(entrada) => entrada.id}
        className="grid gap-4 md:grid-cols-2"
        classeDoItem="min-w-0"
        descricaoDoResto="perguntas"
        renderizar={(entrada) => <PerguntaDaCozinhaNoInicio pergunta={entrada} />}
      />
    </section>
  );
}
