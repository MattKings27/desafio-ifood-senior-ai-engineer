/**
 * A correção de um valor pré-determinado, pela forma que a API manda. Módulo
 * puro, sem "use client": a página de detalhe, que roda no servidor, chama
 * `correcaoDe` para decidir o que o "corrigir" abre.
 */

import type { EntradaDaPergunta, LeiturasDoPeso, PerguntaDaReceita } from "@/lib/api/receitas";

/** O que se corrige, e por onde. */
export type Correcao =
  | { tipo: "preco"; ingrediente: string }
  | { tipo: "peso"; campo: string; pesoDe: LeiturasDoPeso | null }
  | { tipo: "numero"; campo: string; entrada: EntradaDaPergunta };

/** A correção de um valor pré-determinado, pela forma que a API manda (`editar`, a pergunta da medida). */
export function correcaoDe(pergunta: PerguntaDaReceita | null | undefined): Correcao | null {
  if (!pergunta) return null;
  if (pergunta.assunto === "preco_de_compra") {
    return { tipo: "preco", ingrediente: pergunta.compras[0]?.ingrediente ?? pergunta.campo };
  }
  if (pergunta.entrada?.tipo === "peso") return { tipo: "peso", campo: pergunta.campo, pesoDe: pergunta.entrada.peso_de ?? null };
  if (pergunta.entrada?.tipo === "inteiro") return { tipo: "numero", campo: pergunta.campo, entrada: pergunta.entrada };
  return null;
}
