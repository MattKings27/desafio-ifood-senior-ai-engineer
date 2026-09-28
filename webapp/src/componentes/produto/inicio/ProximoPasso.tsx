"use client";

/**
 * O próximo passo, dito para ela, com o que fazer em seguida: um link (a
 * pergunta logo abaixo, as receitas, o cardápio) ou a conversa com o pedido já
 * escrito. Quem decide o passo é a API; a tela só mostra.
 */

import { ArrowRight, Compass } from "@phosphor-icons/react/dist/ssr";

import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Card } from "@/componentes/compartilhados/Card";
import { BotaoPerguntar } from "@/componentes/conversa/BotaoPerguntar";
import type { VisaoGeral } from "@/lib/api/visao-geral";

/** O texto do botão de cada destino: "Ver as receitas", não "Continuar". */
const ROTULO_DO_LINK: Readonly<Record<string, string>> = {
  "/#perguntas": "Responder agora",
  "/conversa?comecar=cozinha": "Responder agora",
  "/receitas": "Ver as receitas",
  "/cardapio": "Ver o cardápio",
};

export function ProximoPasso({ passo }: { passo: VisaoGeral["proximo_passo"] }) {
  const { acao } = passo;
  return (
    <Card tom="creme" aria-labelledby="titulo-do-proximo-passo" className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-full bg-marca/10 text-marca">
          <Compass size={22} weight="fill" />
        </span>
        <div className="min-w-0">
          <h2 id="titulo-do-proximo-passo" className="text-sm font-semibold text-apagado">
            O próximo passo
          </h2>
          <p className="mt-0.5 text-base font-semibold text-tinta sm:text-lg">{passo.texto}</p>
        </div>
      </div>
      {acao.tipo === "perguntar" && acao.rascunho ? (
        <BotaoPerguntar
          rascunho={acao.rascunho}
          contexto={{ tela: "inicio", tipo: "proximo_passo", rotulo: "O próximo passo" }}
          rotulo="Pedir ao agente"
          variante="primario"
          tamanho="md"
          className="sm:shrink-0"
        />
      ) : acao.rota ? (
        <BotaoLink href={acao.rota} variante="primario" iconeDepois={<ArrowRight size={18} weight="bold" />} className="sm:shrink-0">
          {ROTULO_DO_LINK[acao.rota] ?? "Ir agora"}
        </BotaoLink>
      ) : null}
    </Card>
  );
}
