/**
 * Os rascunhos em primeira pessoa: o começo da pergunta que a caixa da
 * conversa recebe quando ela toca em "Perguntar" num card.
 *
 * É ela quem fala, então é a voz dela: "Dá pra eu fazer Bolo de cenoura?",
 * "A embalagem de cobertura de chocolate tem ". O rascunho nunca é enviado
 * sozinho: ela lê, completa se quiser, e manda.
 *
 * As frases evitam o artigo ("do", "da"), que dependeria do gênero de cada
 * nome: "por uma porção de arroz com frango" serve para qualquer prato.
 * Quando o backend manda o rascunho pronto (`rascunho_chat`), vale o dele.
 */

import type { AcaoDoCartao, OpcaoSugerida } from "@/lib/api/conversa";
import type { OpcaoDeResposta, PerguntaDaReceita } from "@/lib/api/receitas";

/** "Bolo de cenoura" → "bolo de cenoura", para o meio da frase. Sigla ("CMV") fica como está. */
export function emMinusculas(nome: string): string {
  const limpo = nome.trim();
  if (/^\p{Lu}\p{Ll}/u.test(limpo)) return limpo.charAt(0).toLocaleLowerCase("pt-BR") + limpo.slice(1);
  return limpo;
}

export const rascunhos = {
  /** "Dá pra eu fazer Bolo de cenoura?" */
  podeFazer: (receita: string) => `Dá pra eu fazer ${receita.trim()}?`,

  /** "Quanto eu cobro por uma porção de arroz com frango?" */
  quantoCobrar: (prato: string) => `Quanto eu cobro por uma porção de ${emMinusculas(prato)}?`,

  /** "O que eu posso fazer com peito de frango?" */
  oQueFazerCom: (ingrediente: string) => `O que eu posso fazer com ${emMinusculas(ingrediente)}?`,

  /** "A embalagem de cobertura de chocolate tem ": ela completa com o peso. */
  embalagem: (ingrediente: string) => `A embalagem de ${emMinusculas(ingrediente)} tem `,

  /** "Me explica a conta do custo de arroz com frango?" */
  explicarConta: (assunto: string) => `Me explica essa conta de ${emMinusculas(assunto)}?`,

  /** "Quero mudar o preço de arroz com frango para ": ela completa com o valor. */
  mudarPreco: (prato: string) => `Quero mudar o preço de ${emMinusculas(prato)} para `,

  /** "Vou cobrar R$ 18,00 por porção de arroz com frango." O valor é o texto que o motor mandou. */
  vouCobrar: (precoTexto: string, prato: string) =>
    `Vou cobrar ${precoTexto.trim()} por porção de ${emMinusculas(prato)}.`,

  /** Depois de valores retirados do texto final: a conta de cada um. */
  trazerConta: () => "Me mostra a conta de cada valor que ficou de fora?",
} as const;

/**
 * O que ela "diz" ao tocar numa opção de pergunta: o texto pronto do backend,
 * quando vem; senão, o próprio rótulo da opção ("Faço.", "Tenho.").
 */
export function textoDaOpcao(opcao: { rotulo: string; texto?: unknown }): string {
  if (typeof opcao.texto === "string" && opcao.texto.trim()) return opcao.texto.trim();
  const rotulo = opcao.rotulo.trim();
  return /[.!?]$/.test(rotulo) ? rotulo : `${rotulo}.`;
}

/**
 * A resposta a uma pergunta de um card de receita (Tenho / Não tenho / Não
 * sei) como turno estruturado. "Não sei" vai só como texto: o motor não grava
 * "não sei" como "não tem", e quem decide o que fazer com a dúvida é o
 * agente.
 */
export function respostaDaPergunta(pergunta: Pick<PerguntaDaReceita, "tipo" | "campo">, opcao: OpcaoDeResposta & { texto?: unknown }): OpcaoSugerida {
  const texto = textoDaOpcao(opcao);
  if (opcao.resposta === "nao_sei" || !pergunta.campo) return { rotulo: opcao.rotulo, texto };
  const acao: AcaoDoCartao = {
    tipo: "responder",
    tipo_pergunta: pergunta.tipo,
    campo: pergunta.campo,
    resposta: opcao.resposta,
  };
  return { rotulo: opcao.rotulo, texto, acao };
}
