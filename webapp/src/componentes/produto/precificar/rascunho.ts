/**
 * O prato que ela está escrevendo na tela de preço: o que o formulário guarda
 * e o que vai para a API. Puro, para o teste e para a tela usarem o mesmo.
 */

import type { ReceitaEntrada, ReceitaGuardada } from "@/lib/api/receitas";
import { montarReceita } from "@/lib/receita";

export type Rascunho = {
  nome: string;
  /** Os ingredientes, um por linha, do jeito que ela escreve. */
  linhas: string;
  /** Como ela faz, um passo por linha. */
  preparo: string;
  rende: number | null;
  /** Quanto tempo fica no fogo, em minutos; opcional. */
  tempo: number | null;
  /** A página de onde a receita veio, quando veio da internet. */
  origem: { url: string; fonte: string } | null;
};

/** Quantas porções o formulário sugere antes de ela dizer. */
export const PORCOES_PADRAO = 4;

export const RASCUNHO_VAZIO: Rascunho = {
  nome: "",
  linhas: "",
  preparo: "",
  rende: PORCOES_PADRAO,
  tempo: null,
  origem: null,
};

/** O rascunho de uma receita guardada (vinda da conversa, da grade ou da internet). */
export function rascunhoDe(receita: ReceitaGuardada | null): Rascunho {
  if (!receita) return RASCUNHO_VAZIO;
  return {
    nome: receita.nome,
    linhas: receita.ingredientes.map((ingrediente) => ingrediente.texto).join("\n"),
    preparo: receita.modo_preparo.join("\n"),
    rende: receita.rendimento_porcoes,
    tempo: receita.tempo_cozimento_min ?? null,
    origem: receita.url ? { url: receita.url, fonte: receita.fonte ?? "" } : null,
  };
}

/** A receita que vai para a conferência; `null` sem nome ou sem ingrediente. */
export function receitaDo(rascunho: Rascunho): ReceitaEntrada | null {
  return montarReceita(rascunho.nome, rascunho.linhas, rascunho.rende ?? PORCOES_PADRAO, {
    preparo: rascunho.preparo,
    url: rascunho.origem?.url,
    fonte: rascunho.origem?.fonte,
    tempo: rascunho.tempo,
  });
}
