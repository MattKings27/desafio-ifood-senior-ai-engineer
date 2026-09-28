"use client";

/**
 * O gosto dela na grade: a pergunta "A senhora gosta de fazer este prato?" no
 * card, o "Mudei de ideia" de quem está em "Não gosto de fazer", e o que liga
 * os dois às seções da tela.
 *
 * A resposta vale na hora: a receita muda de seção antes de a API responder
 * (`useOptimistic`), e a página refeita pela Server Action chega na mesma ida e
 * volta. Se a API recusar, a receita volta para onde estava e o aviso diz por
 * quê. Deu certo, o aviso diz para onde ela foi, com o "Desfazer", que manda o
 * gosto de antes de volta pelo mesmo caminho (a avaliação da receita, que grava
 * na mesma tabela de gostos que a conferência e o agente leem).
 */

import { ArrowCounterClockwise } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useMemo, useOptimistic, useTransition } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { useToast } from "@/componentes/compartilhados/Toast";
import { avaliarReceita } from "@/lib/acoes/receitas";
import type { Resultado } from "@/lib/acoes/base";
import type { ItemDaGrade, RespostaDaAvaliacao } from "@/lib/api/receitas";
import { MENSAGENS } from "@/lib/api/base";

import { GrupoDeOpcoes } from "./GrupoDeOpcoes";
import type { MudancasDoGosto } from "./gosto";
import { textoDoGosto } from "./gosto";

type Receita = Pick<ItemDaGrade, "slug" | "nome" | "gosta">;

type ValorDoGosto = {
  mudancas: MudancasDoGosto;
  /** Grava o gosto; `antes` é o que volta no "Desfazer" (sem ele, o aviso não oferece desfazer). */
  responder: (receita: Receita, gosta: boolean | null, antes?: boolean | null) => void;
};

const SEM_MUDANCAS: MudancasDoGosto = {};

const Contexto = createContext<ValorDoGosto>({ mudancas: SEM_MUDANCAS, responder: () => {} });

export function useGostoDaGrade(): ValorDoGosto {
  return useContext(Contexto);
}

function mudar(atuais: MudancasDoGosto, [slug, gosta]: [string, boolean | null]): MudancasDoGosto {
  return { ...atuais, [slug]: gosta };
}

/** A ação nunca lança; se lançar (servidor fora), vira o aviso de caminho. */
async function avaliarComSeguranca(slug: string, gosta: boolean | null): Promise<Resultado<RespostaDaAvaliacao>> {
  try {
    return await avaliarReceita(slug, { gosta });
  } catch {
    return { ok: false, erro: { categoria: "rede", mensagem: MENSAGENS.rede } };
  }
}

export function ProvedorDoGosto({ children }: { children: ReactNode }) {
  const [mudancas, aplicar] = useOptimistic(SEM_MUDANCAS, mudar);
  const [, iniciar] = useTransition();
  const toast = useToast();

  const responder = useCallback(
    (receita: Receita, gosta: boolean | null, antes?: boolean | null) => {
      iniciar(async () => {
        aplicar([receita.slug, gosta]);
        const resultado = await avaliarComSeguranca(receita.slug, gosta);
        if (!resultado.ok) {
          toast.mostrar({ texto: resultado.erro.pergunta ?? resultado.erro.mensagem, tom: "erro" });
          return;
        }
        toast.mostrar({
          texto: textoDoGosto(receita.nome, gosta),
          tom: "sucesso",
          acao:
            antes === undefined
              ? undefined
              : { rotulo: "Desfazer", aoClicar: () => responder({ ...receita, gosta }, antes) },
        });
      });
    },
    [aplicar, toast],
  );

  const valor = useMemo(() => ({ mudancas, responder }), [mudancas, responder]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

const OPCOES_DO_GOSTO = [
  { rotulo: "Gosto de fazer", valor: "gosta" },
  { rotulo: "Não gosto", valor: "nao_gosta" },
] as const;

/**
 * A pergunta do gosto no card, antes de qualquer pergunta da cozinha: se ela
 * não gosta, não há o que conferir. O nome do prato vai no nome do grupo, para
 * quem usa leitor de tela saber de qual receita é a pergunta.
 */
export function PerguntaDoGosto({ item, className }: { item: ItemDaGrade; className?: string }) {
  const { responder } = useGostoDaGrade();
  return (
    <div className={className}>
      <div className="rounded-md border border-marca/20 bg-marca/5 p-2.5">
        <p aria-hidden="true" className="text-sm font-semibold text-tinta">
          A senhora gosta de fazer este prato?
        </p>
        <GrupoDeOpcoes
          rotulo={`A senhora gosta de fazer ${item.nome}?`}
          opcoes={OPCOES_DO_GOSTO}
          escolhida={null}
          pendente={false}
          aoEscolher={(valor) => responder(item, valor === "gosta", item.gosta)}
          className="mt-2"
        />
      </div>
    </div>
  );
}

/** "Mudei de ideia": ela passa a gostar de fazer, e a receita volta para "Gosto de fazer". */
export function MudeiDeIdeia({ item }: { item: ItemDaGrade }) {
  const { responder } = useGostoDaGrade();
  return (
    <Botao
      variante="terciario"
      tamanho="sm"
      larguraTotal
      icone={<ArrowCounterClockwise size={16} weight="bold" />}
      aria-label={`Mudei de ideia: gosto de fazer ${item.nome}`}
      onClick={() => responder(item, true, false)}
    >
      Mudei de ideia
    </Botao>
  );
}
