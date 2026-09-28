/**
 * Como cada pergunta que segura uma receita é respondida ali mesmo.
 *
 * Ela só responde o que é dela: se gosta de fazer o prato (a pergunta do gosto
 * da grade e da avaliação), o equipamento, a técnica e os limites da rotina.
 * Peso, medida, quantidade, rendimento, o tempo da própria receita, preço e o
 * "é o seu?" do item parecido nunca são pergunta: vêm pré-determinados da
 * receita e da pesquisa, com a fonte, e ela muda pelo "corrigir" do valor
 * (`./CorrigirValor`). A pergunta de outro assunto que ainda chegar da API não
 * aparece: `comoResponder` devolve `nenhuma`.
 *
 * A pergunta vem da API na forma de `receita.json#perguntas[]` (`tipo`,
 * `assunto`, `campo`, `opcoes`, `entrada`), e cada uma tem a sua rota:
 *
 * - equipamento ou técnica com opções (Tenho, Não tenho, Não sei): o perfil
 *   da cozinha (`PUT /api/perfil/{equipamentos|tecnicas}/{id}`);
 * - um limite da rotina (bocas do fogão, horas cozinhando de uma vez, gás
 *   sobrando): `PUT /api/perfil/restricoes/{campo}`, o tempo em horas;
 * - a da cozinha sem opções que a tela entenda, e o modo de preparo da receita
 *   que ela ditou (é dele que sai o equipamento): pela conversa.
 *
 * Quem decide é o `assunto`; o texto nunca é lido para decidir.
 */

import type { RespostaDePosse } from "@/lib/api/perfil";
import type { AssuntoDaPergunta, EntradaDaPergunta, OpcaoDeResposta, PerguntaDaReceita } from "@/lib/api/receitas";

export type FormaDeResponder =
  | { tipo: "posse"; lista: "equipamentos" | "tecnicas"; id: string; opcoes: readonly OpcaoDaPosse[] }
  | { tipo: "limite"; campo: string; entrada: EntradaDaPergunta; comNaoSei: boolean }
  | { tipo: "sim_nao"; campo: string }
  | { tipo: "conversa" }
  | { tipo: "nenhuma" };

export type OpcaoDaPosse = { rotulo: string; estado: RespostaDePosse };

/** O que é da cozinha dela, e por isso se pergunta. */
const DA_COZINHA: ReadonlySet<AssuntoDaPergunta> = new Set(["equipamento", "tecnica", "rotina", "modo_preparo"]);

/** A pergunta é da cozinha dela (equipamento, técnica, rotina, ou o modo de preparo da receita que ela ditou). */
export function daCozinha(pergunta: Pick<PerguntaDaReceita, "assunto">): boolean {
  return DA_COZINHA.has(pergunta.assunto);
}

const ESTADO_DA_RESPOSTA: Readonly<Record<string, RespostaDePosse>> = {
  sim: "tem",
  nao: "nao_tem",
  nao_sei: "nao_sei",
};

/** As opções que o perfil entende; a que ele não entende fica de fora. */
function opcoesDaPosse(opcoes: readonly OpcaoDeResposta[]): OpcaoDaPosse[] {
  return opcoes.flatMap((opcao) => {
    const estado = ESTADO_DA_RESPOSTA[opcao.resposta];
    return estado ? [{ rotulo: opcao.rotulo, estado }] : [];
  });
}

export function comoResponder(pergunta: PerguntaDaReceita): FormaDeResponder {
  if (!daCozinha(pergunta)) return { tipo: "nenhuma" };
  const { tipo, campo, entrada } = pergunta;

  if (tipo === "equipamento" || tipo === "tecnica") {
    const opcoes = opcoesDaPosse(pergunta.opcoes);
    if (opcoes.length === 0) return { tipo: "conversa" };
    return { tipo: "posse", lista: tipo === "equipamento" ? "equipamentos" : "tecnicas", id: campo, opcoes };
  }

  if (tipo === "operacional") {
    if (entrada?.tipo === "inteiro" || entrada?.tipo === "horas") {
      return { tipo: "limite", campo, entrada, comNaoSei: pergunta.opcoes.some((o) => o.resposta === "nao_sei") };
    }
    if (pergunta.opcoes.some((o) => o.resposta === "sim")) return { tipo: "sim_nao", campo };
  }

  return { tipo: "conversa" };
}

/** Os rótulos das opções de quem ainda não foi perguntada (no passo da receita). */
export const OPCOES_DE_EQUIPAMENTO: readonly OpcaoDaPosse[] = [
  { rotulo: "Tenho", estado: "tem" },
  { rotulo: "Não tenho", estado: "nao_tem" },
  { rotulo: "Não sei", estado: "nao_sei" },
];

export const OPCOES_DE_TECNICA: readonly OpcaoDaPosse[] = [
  { rotulo: "Faço", estado: "tem" },
  { rotulo: "Não faço", estado: "nao_tem" },
  { rotulo: "Não sei", estado: "nao_sei" },
];
