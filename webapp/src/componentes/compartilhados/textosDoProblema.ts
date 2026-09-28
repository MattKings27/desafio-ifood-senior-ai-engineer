/**
 * O que o Problema diz, por categoria. Sem diretiva, para servir também a
 * server components (ex.: montar a mensagem de uma página que falhou).
 */

import type { CategoriaDeErro } from "@/lib/api/base";
import { textoParaEla } from "@/lib/formato";

export const TITULO_DO_PROBLEMA: Readonly<Record<CategoriaDeErro, string>> = {
  rede: "Não consegui falar com o sistema",
  tempo: "Demorou demais",
  ausente: "Não encontrei",
  dado: "Falta uma informação",
  regra: "Ainda não dá para fazer isso",
  uso: "Não deu para registrar",
};

export const DESCRICAO_DO_PROBLEMA: Readonly<Record<CategoriaDeErro, string>> = {
  rede: "Pode ser a internet, ou o sistema fora do ar por um instante. Tente de novo daqui a pouco.",
  tempo: "A resposta não chegou a tempo. Tente de novo.",
  ausente: "Isso não está mais aqui. Pode ter sido tirado.",
  dado: "Preciso de uma informação da senhora para continuar.",
  regra: "Ainda falta confirmar alguma coisa antes deste passo.",
  uso: "Confira o que foi preenchido e tente de novo.",
};

/** O texto que ela lê: a pergunta, a mensagem limpa, ou a frase da categoria. */
export function textoDoProblema(
  categoria: CategoriaDeErro,
  mensagem?: string,
  pergunta?: string,
): string {
  const padrao = DESCRICAO_DO_PROBLEMA[categoria];
  if (categoria === "dado" && pergunta) return textoParaEla(pergunta, padrao);
  // Rede e tempo não têm nada de útil na mensagem: é o caminho que falhou.
  if (categoria === "rede" || categoria === "tempo") return padrao;
  return textoParaEla(mensagem, padrao);
}

