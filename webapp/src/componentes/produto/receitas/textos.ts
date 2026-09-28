/**
 * As frases da tela de receitas que não vêm prontas da API: para onde uma
 * receita foi depois de uma resposta, por que ainda não dá para pôr preço, e
 * os tons de cada situação na cozinha. Nenhum número é calculado aqui.
 */

import type { CodigoDaCozinha, DetalheDaReceita, VereditoDaCozinha } from "@/lib/api/receitas";

import { ROTULO_DA_ABA } from "./filtros";
import { daCozinha } from "./perguntas";

export type TomDaSituacao = "sucesso" | "info" | "atencao" | "perigo";

export const TOM_DA_COZINHA: Readonly<Record<CodigoDaCozinha, TomDaSituacao>> = {
  com_o_que_tem: "sucesso",
  comprando: "info",
  falta_resposta: "atencao",
  nao_da: "perigo",
};

/** As classes de cada tom: texto, fundo a 10% e borda (o par que o teste de contraste confere). */
export const CLASSES_DO_TOM: Readonly<Record<TomDaSituacao, { texto: string; caixa: string }>> = {
  sucesso: { texto: "text-sucesso", caixa: "border-sucesso/25 bg-sucesso/10" },
  info: { texto: "text-info", caixa: "border-info/25 bg-info/10" },
  atencao: { texto: "text-atencao", caixa: "border-atencao/25 bg-atencao/10" },
  perigo: { texto: "text-perigo", caixa: "border-perigo/25 bg-perigo/10" },
};

const daParaFazer = (codigo: CodigoDaCozinha) => codigo === "com_o_que_tem" || codigo === "comprando";

/** O motivo da API sem o ponto final, para caber no meio de uma frase. */
function semPonto(texto: string): string {
  return texto.trim().replace(/[.!]+$/, "");
}

/**
 * Onde a receita ficou depois da resposta dela, em uma frase ("Anotei. Pudim
 * foi para Dá para fazer."). A que ela não quer continua lá.
 */
export function ondeFicou(nome: string, cozinha: VereditoDaCozinha, gosta: boolean | null = null): string {
  if (daParaFazer(cozinha.codigo)) {
    return gosta === false
      ? `Anotei. ${nome} continua em ${ROTULO_DA_ABA.nao_quer}.`
      : `Anotei. ${nome} foi para ${ROTULO_DA_ABA.pode_fazer}.`;
  }
  if (cozinha.codigo === "falta_resposta") return `Anotei. ${nome} ainda espera uma resposta: ${semPonto(cozinha.motivo)}.`;
  return `Anotei. ${nome} saiu da lista, porque a cozinha não dá conta: ${semPonto(cozinha.motivo)}.`;
}

/** Onde a receita trazida pelo endereço entrou (ou por que não entrou em aba nenhuma). */
export function ondeEntrou(cozinha: VereditoDaCozinha, gosta: boolean | null): string {
  if (daParaFazer(cozinha.codigo)) {
    return gosta === false ? `Ela está em ${ROTULO_DA_ABA.nao_quer}.` : `Ela está em ${ROTULO_DA_ABA.pode_fazer}.`;
  }
  if (cozinha.codigo === "falta_resposta") return `Ela está em ${ROTULO_DA_ABA.falta_resposta}: ${cozinha.motivo}`;
  return `Ela não entra na lista, porque a cozinha da senhora não dá conta: ${cozinha.motivo}`;
}

export type PermissaoDePreco = { pode: true } | { pode: false; motivo: string; faltam: readonly string[] };

/**
 * "Pôr preço" só quando o checklist de produção libera o aceite: a cozinha dá
 * conta, ela gosta do prato e confirmou o que toda cozinha tem. O motivo e cada
 * coisa que falta vêm prontos da API (`checklist.resumo` e `falta_para_aceitar`),
 * menos a frase que repete uma pergunta que não é dela (peso, medida,
 * quantidade, preço): essa não é pergunta, e não aparece.
 */
export function permissaoDePreco(receita: DetalheDaReceita): PermissaoDePreco {
  const { pode_aceitar, resumo, falta_para_aceitar } = receita.checklist;
  if (pode_aceitar) return { pode: true };
  const naoPerguntadas = receita.perguntas.filter((pergunta) => !daCozinha(pergunta)).map((pergunta) => pergunta.texto);
  const faltam = falta_para_aceitar.filter((falta) => !naoPerguntadas.some((texto) => falta.includes(texto)));
  return { pode: false, motivo: resumo, faltam };
}

/** O que ela diria ao agente para pôr preço: o rascunho, que ela mesma manda. */
export function rascunhoDoPreco(nome: string): string {
  return `Quero pôr preço na ${nome}`;
}

/** O que ela diria ao agente para responder pela conversa. */
export function rascunhoDaPergunta(nome: string): string {
  const limpo = nome.trim();
  const prato = /^\p{Lu}\p{Ll}/u.test(limpo) ? limpo.charAt(0).toLocaleLowerCase("pt-BR") + limpo.slice(1) : limpo;
  return `O que falta para eu poder fazer ${prato}?`;
}

export const RASCUNHO_DA_DESCOBERTA = "Procure receitas reais que aproveitem a minha despensa";

/** "1 página lida, 2 receitas encontradas". */
export function progressoDaDescoberta(lidas: number, encontradas: number): string {
  const paginas = lidas === 1 ? "1 página lida" : `${lidas} páginas lidas`;
  const receitas = encontradas === 1 ? "1 receita encontrada" : `${encontradas} receitas encontradas`;
  return `${paginas}, ${receitas}`;
}

/**
 * O texto da API com o "R$" preso ao número: no card estreito, "R$" sozinho no
 * fim de uma linha e "6,00" no começo da outra se lê como dois valores.
 */
export function semQuebrarValor(texto: string): string {
  return texto.replace(/R\$\s+/g, "R$\u00a0");
}

/** Com a primeira letra maiúscula: a recusa da API às vezes começa em minúscula. */
export function comMaiuscula(texto: string): string {
  return texto.charAt(0).toLocaleUpperCase("pt-BR") + texto.slice(1);
}
