/**
 * A base das Server Actions: toda escrita devolve `Resultado`, nunca lança.
 *
 * Em produção o Next mascara a mensagem de uma exceção que atravessa a
 * fronteira servidor → navegador ("An error occurred in the Server Components
 * render"). Uma recusa com pergunta ("quanto pesa a embalagem?") viraria uma
 * frase genérica. Por isso a ação captura o erro e devolve a categoria, a
 * mensagem e a pergunta como dados.
 *
 * Depois de uma escrita que deu certo, `refresh()` refaz a rota atual na mesma
 * ida e volta: a tela reflete a mudança sem um segundo pedido e sem piscar.
 *
 * Uso, num arquivo com "use server" (ex.: `src/lib/acoes/despensa.ts`):
 *
 *     export async function adicionarItem(novo: NovoItem) {
 *       return executarAcao(() => api.despensa.adicionar(novo));
 *     }
 */

import { refresh } from "next/cache";

import type { CategoriaDeErro } from "@/lib/api/base";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";

export type ErroDaAcao = {
  categoria: CategoriaDeErro;
  /** Texto que pode ir para a tela dela, como veio da API ou da tradução do caminho. */
  mensagem: string;
  /** Presente quando falta um dado: é a pergunta que destrava. */
  pergunta?: string;
};

export type Resultado<T> = { ok: true; dados: T } | { ok: false; erro: ErroDaAcao };

export function paraErroDaAcao(causa: unknown): ErroDaAcao {
  if (causa instanceof ErroDoMotor) {
    return {
      categoria: causa.categoria,
      mensagem: causa.message,
      ...(causa.pergunta ? { pergunta: causa.pergunta } : {}),
    };
  }
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

export type OpcoesDaExecucao = {
  /** Refazer a rota atual depois do sucesso. Padrão: sim. */
  atualizar?: boolean;
};

export async function executarAcao<T>(
  trabalho: () => Promise<T>,
  { atualizar = true }: OpcoesDaExecucao = {},
): Promise<Resultado<T>> {
  try {
    const dados = await trabalho();
    if (atualizar) refresh();
    return { ok: true, dados };
  } catch (causa) {
    if (!(causa instanceof ErroDoMotor)) {
      // Falha que não veio da API (bug nosso): fica no log do servidor, e ela
      // vê a mensagem de caminho, não o texto da exceção.
      console.error("ação do servidor falhou", causa);
    }
    return { ok: false, erro: paraErroDaAcao(causa) };
  }
}

/** Um resultado de erro montado à mão (validação antes de chamar a API). */
export function falha(categoria: CategoriaDeErro, mensagem: string, pergunta?: string): Resultado<never> {
  return { ok: false, erro: { categoria, mensagem, ...(pergunta ? { pergunta } : {}) } };
}
