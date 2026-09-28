"use client";

/**
 * A conferência do prato, antes de qualquer preço: se dá pra fazer, o que
 * impede, o que eu ainda preciso saber (com a resposta ali mesmo) e o que a
 * senhora já tem e o que falta comprar.
 *
 * Preço só aparece depois que a conferência libera, e quem decide isso é a
 * API: esta tela só mostra o que veio.
 */

import { CheckCircle, Prohibit, Question, ShoppingCartSimple } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

import { Card } from "@/componentes/compartilhados/Card";
import { Chip, SeloVeredito } from "@/componentes/compartilhados/Chip";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { Derivacao } from "@/componentes/compartilhados/Valor";
import type { Avaliacao } from "@/lib/api/preco";
import type { Veredito } from "@/lib/formato";

import type { RespostaDaReceita } from "./RespostaDaConferencia";
import { RespostaDaConferencia } from "./RespostaDaConferencia";

const ICONE: Record<Veredito, ReactNode> = {
  APTO: <CheckCircle size={24} weight="fill" className="text-sucesso" />,
  "APTO COM COMPRA": <ShoppingCartSimple size={24} weight="fill" className="text-info" />,
  "FALTA INFO": <Question size={24} weight="fill" className="text-atencao" />,
  BLOQUEADO: <Prohibit size={24} weight="fill" className="text-perigo" />,
};

/** O nome de cada parte da conferência, dito para ela. */
export const NOME_DA_PARTE: Readonly<Record<string, string>> = {
  ingrediente: "Ingredientes",
  equipamento: "Equipamentos",
  tecnica: "Técnicas",
  operacional: "Rotina da cozinha",
  gosto: "Se a senhora quer fazer",
};

export function ConferenciaDoPrato({
  avaliacao,
  aoResponder,
  aoResponderNaReceita,
}: {
  avaliacao: Avaliacao;
  aoResponder: () => void;
  aoResponderNaReceita: (resposta: RespostaDaReceita) => void;
}) {
  return (
    <Card aria-labelledby="titulo-da-conferencia" className="space-y-5">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 shrink-0">
          {ICONE[avaliacao.veredito]}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="titulo-da-conferencia" className="text-lg font-bold text-tinta">
              {avaliacao.prato}
            </h2>
            <SeloVeredito veredito={avaliacao.veredito} />
          </div>
          <p className="mt-1 text-base text-texto">{avaliacao.resumo}</p>
          {avaliacao.pode_precificar ? null : (
            <Derivacao className="mt-2">
              O preço só aparece depois que eu confirmo que a senhora consegue fazer este prato.
            </Derivacao>
          )}
        </div>
      </div>

      {avaliacao.impedimentos.length > 0 ? (
        <section aria-labelledby="titulo-do-que-impede">
          <h3 id="titulo-do-que-impede" className="text-sm font-bold text-perigo">
            O que impede
          </h3>
          <ListaExpansivel
            itens={avaliacao.impedimentos}
            visiveis={4}
            chave={(impedimento) => `${impedimento.tipo}:${impedimento.id}`}
            className="mt-2 space-y-2"
            descricaoDoResto="impedimentos"
            renderizar={(impedimento) => (
              <p className="flex flex-wrap items-start gap-2 text-sm">
                <Chip tom="perigo">{NOME_DA_PARTE[impedimento.tipo] ?? "Cozinha"}</Chip>
                <span className="min-w-0 text-texto">{impedimento.motivo}</span>
              </p>
            )}
          />
        </section>
      ) : null}

      {avaliacao.perguntas.length > 0 ? (
        <section aria-labelledby="titulo-do-que-falta-saber">
          <h3 id="titulo-do-que-falta-saber" className="text-sm font-bold text-atencao">
            O que eu ainda preciso saber
          </h3>
          <ListaExpansivel
            itens={avaliacao.perguntas}
            visiveis={3}
            chave={(pergunta) => `${pergunta.tipo}:${pergunta.campo}`}
            className="mt-2 space-y-4"
            descricaoDoResto="perguntas"
            renderizar={(pergunta) => (
              <div className="rounded-md border border-atencao/25 bg-atencao/10 p-3">
                <p className="text-sm font-semibold text-tinta">{pergunta.texto}</p>
                {pergunta.motivo ? <p className="mt-0.5 text-xs text-texto-secundario">{pergunta.motivo}</p> : null}
                <div className="mt-3">
                  <RespostaDaConferencia
                    pergunta={pergunta}
                    prato={avaliacao.prato}
                    receitaId={avaliacao.receita_id}
                    aoResponder={aoResponder}
                    aoResponderNaReceita={aoResponderNaReceita}
                  />
                </div>
              </div>
            )}
          />
        </section>
      ) : null}
    </Card>
  );
}

/**
 * O que ela tem e o que falta, lado a lado. O que falta comprar aparece com o
 * custo quando ele é conhecido, e com a falta dita quando não é: nunca some
 * nem entra como zero.
 */
export function IngredientesDoPrato({ avaliacao }: { avaliacao: Avaliacao }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card aria-labelledby="titulo-do-que-tem">
        <h3 id="titulo-do-que-tem" className="text-base font-bold text-tinta">
          A senhora já tem
        </h3>
        <ListaExpansivel
          itens={avaliacao.ingredientes_na_despensa}
          visiveis={6}
          chave={(item) => item.ingrediente}
          className="mt-2 space-y-2"
          descricaoDoResto="ingredientes"
          renderizar={(item) => (
            <div className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-tinta">{item.ingrediente}</span>
                <span className="numero shrink-0 font-semibold">{item.custo.texto}</span>
              </div>
              <Derivacao>
                {item.quantidade}: {item.derivacao}
              </Derivacao>
            </div>
          )}
          vazio={<p className="mt-2 text-sm text-apagado">Nada desta receita está na despensa.</p>}
        />
      </Card>
      <Card aria-labelledby="titulo-do-que-falta" className={avaliacao.falta_comprar.length > 0 ? "border-info/30" : undefined}>
        <h3 id="titulo-do-que-falta" className="text-base font-bold text-tinta">
          Falta comprar
        </h3>
        <ListaExpansivel
          itens={avaliacao.falta_comprar}
          visiveis={6}
          chave={(item) => item.ingrediente}
          className="mt-2 space-y-2"
          descricaoDoResto="ingredientes"
          renderizar={(item) => (
            <div className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-tinta">{item.ingrediente}</span>
                {item.custo ? (
                  <span className="numero shrink-0 font-semibold">{item.custo.texto}</span>
                ) : (
                  <Chip tom="atencao">falta o preço</Chip>
                )}
              </div>
              <Derivacao>{item.quanto}</Derivacao>
            </div>
          )}
          vazio={<p className="mt-2 text-sm text-apagado">Nada: a despensa cobre a receita inteira.</p>}
        />
        {avaliacao.a_gosto.length > 0 ? (
          <Derivacao className="mt-3">A gosto, com custo pequeno mas contado: {avaliacao.a_gosto.join(", ")}.</Derivacao>
        ) : null}
      </Card>
    </div>
  );
}
