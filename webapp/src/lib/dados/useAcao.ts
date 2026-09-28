"use client";

/**
 * O lado do navegador de uma escrita: pendente, aviso de erro, valor otimista.
 *
 * Embrulha uma Server Action que devolve `Resultado` (ver `@/lib/acoes/base`).
 * Nada é lançado: quem chama recebe o `Resultado` e decide. O erro, por
 * padrão, vira um aviso (toast) com a frase da API ou a pergunta que destrava.
 *
 *     const { executar, pendente } = useAcao(adicionarItem, {
 *       sucesso: (dados) => dados.texto,
 *     });
 *
 *     const { estado, executar } = useAcaoOtimista(itens, tirarDaLista, removerItem);
 */

import { useOptimistic, useState, useTransition } from "react";

import { useToast } from "@/componentes/compartilhados/Toast";
import type { ErroDaAcao, Resultado } from "@/lib/acoes/base";
import { MENSAGENS } from "@/lib/api/base";

export type OpcoesDaAcao<T> = {
  /** O aviso de sucesso: um texto fixo, ou tirado dos dados (ex.: `dados.texto`). */
  sucesso?: string | ((dados: T) => string | null | undefined);
  /** Mostrar o erro num aviso. Padrão: sim. */
  avisarErro?: boolean;
  aoConcluir?: (dados: T) => void;
  aoFalhar?: (erro: ErroDaAcao) => void;
};

/** A ação nunca lança; se lançar (servidor fora, ação sumiu no deploy), vira erro de rede. */
async function chamarComSeguranca<A extends unknown[], T>(
  acao: (...args: A) => Promise<Resultado<T>>,
  args: A,
): Promise<Resultado<T>> {
  try {
    return await acao(...args);
  } catch {
    return { ok: false, erro: { categoria: "rede", mensagem: MENSAGENS.rede } };
  }
}

function useExecucao<A extends unknown[], T>(
  acao: (...args: A) => Promise<Resultado<T>>,
  opcoes: OpcoesDaAcao<T>,
  antes?: (...args: A) => void,
) {
  const [pendente, iniciarTransicao] = useTransition();
  const [erro, setErro] = useState<ErroDaAcao | null>(null);
  const toast = useToast();

  const executar = (...args: A): Promise<Resultado<T>> =>
    new Promise((resolver) => {
      iniciarTransicao(async () => {
        antes?.(...args);
        const resultado = await chamarComSeguranca(acao, args);
        if (resultado.ok) {
          setErro(null);
          const texto =
            typeof opcoes.sucesso === "function" ? opcoes.sucesso(resultado.dados) : opcoes.sucesso;
          if (texto) toast.mostrar({ texto, tom: "sucesso" });
          opcoes.aoConcluir?.(resultado.dados);
        } else {
          setErro(resultado.erro);
          if (opcoes.avisarErro !== false) {
            toast.mostrar({ texto: resultado.erro.pergunta ?? resultado.erro.mensagem, tom: "erro" });
          }
          opcoes.aoFalhar?.(resultado.erro);
        }
        resolver(resultado);
      });
    });

  return { executar, pendente, erro, limparErro: () => setErro(null) };
}

export function useAcao<A extends unknown[], T>(
  acao: (...args: A) => Promise<Resultado<T>>,
  opcoes: OpcoesDaAcao<T> = {},
) {
  return useExecucao(acao, opcoes);
}

/**
 * Mostra a mudança na hora e confirma com a resposta. Se a API recusar, o
 * estado volta sozinho quando a transição termina (a base não mudou); se
 * aceitar, o `refresh()` da ação traz a base nova na mesma ida e volta.
 */
export function useAcaoOtimista<S, P, T>(
  estado: S,
  aplicar: (atual: S, pedido: P) => S,
  acao: (pedido: P) => Promise<Resultado<T>>,
  opcoes: OpcoesDaAcao<T> = {},
) {
  const [otimista, aplicarOtimista] = useOptimistic(estado, aplicar);
  const execucao = useExecucao<[P], T>(acao, opcoes, (pedido) => aplicarOtimista(pedido));
  return { ...execucao, estado: otimista };
}
