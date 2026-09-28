/**
 * Como cada pergunta da conferência é respondida na tela de preço, a antiga
 * (`/precificar`), que ainda recebe da API as perguntas de peso, de preço e do
 * item parecido e manda cada uma para o seu lugar. A tela de receitas, o
 * início e a despensa não perguntam nada disso (`@/componentes/produto/receitas/perguntas`).
 *
 * Cada tipo tem a sua rota: equipamento ou técnica, o perfil da cozinha; um
 * limite da rotina, as restrições; o tempo no fogo e o rendimento, a receita
 * que ela escreveu; a linha que a leitura não entendeu, o peso de uma linha e o
 * item parecido, a receita guardada; o preço do que falta, os preços; o resto,
 * a conversa. Quem decide é o `assunto`, e as listas do detalhe confirmam.
 */

import type { RespostaDePosse } from "@/lib/api/perfil";
import type { EntradaDaPergunta, LeiturasDoPeso, OpcaoDeResposta, PerguntaDaReceita } from "@/lib/api/receitas";

export type FormaDeResponder =
  | { tipo: "posse"; lista: "equipamentos" | "tecnicas"; id: string; opcoes: readonly OpcaoDaPosse[] }
  | { tipo: "limite"; campo: string; entrada: EntradaDaPergunta; comNaoSei: boolean }
  | { tipo: "sim_nao"; campo: string }
  | { tipo: "receita"; campo: string; entrada: EntradaDaPergunta }
  | { tipo: "linha"; campo: string }
  | { tipo: "mesmo_item"; campo: string; opcoes: readonly OpcaoDeResposta[] }
  | { tipo: "peso"; campo: string; pesoDe: LeiturasDoPeso | null }
  | { tipo: "preco"; ingredientes: string[] }
  | { tipo: "conversa" };

export type OpcaoDaPosse = { rotulo: string; estado: RespostaDePosse };

/** O que a própria receita não dizia e volta nela (não no perfil da cozinha). */
const CAMPOS_DA_RECEITA = new Set(["tempo_cozimento_min", "rendimento_porcoes"]);

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

/** O que o detalhe da receita sabe e a pergunta sozinha não diz. */
export type PistasDaReceita = {
  /** O texto das linhas que a leitura não entendeu. */
  linhas?: readonly string[];
  /** Os nomes do que falta comprar sem preço conhecido. */
  semPreco?: readonly string[];
};

const semAcento = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();

function ingredientesDoCampo(campo: string): string[] {
  return campo
    .split(",")
    .map((nome) => nome.trim())
    .filter(Boolean);
}

function doIngrediente(pergunta: PerguntaDaReceita, pistas: PistasDaReceita | undefined): FormaDeResponder {
  if (pergunta.assunto === "mesmo_ingrediente" && pergunta.opcoes.length > 0) {
    return { tipo: "mesmo_item", campo: pergunta.campo, opcoes: pergunta.opcoes };
  }
  if (pergunta.assunto === "medida" && pergunta.entrada?.tipo === "peso") {
    return { tipo: "peso", campo: pergunta.campo, pesoDe: pergunta.entrada.peso_de ?? null };
  }
  if (pergunta.assunto === "linha_nao_lida" || pistas?.linhas?.includes(pergunta.campo)) {
    return { tipo: "linha", campo: pergunta.campo };
  }
  const nomes =
    pergunta.compras.length > 0 ? pergunta.compras.map((compra) => compra.ingrediente) : ingredientesDoCampo(pergunta.campo);
  if (pergunta.assunto === "preco_de_compra" && nomes.length > 0) return { tipo: "preco", ingredientes: nomes };
  const semPreco = new Set((pistas?.semPreco ?? []).map(semAcento));
  if (nomes.length > 0 && nomes.every((nome) => semPreco.has(semAcento(nome)))) {
    return { tipo: "preco", ingredientes: nomes };
  }
  return { tipo: "conversa" };
}

export function formaDaConferencia(pergunta: PerguntaDaReceita, pistas?: PistasDaReceita): FormaDeResponder {
  const { tipo, campo, entrada } = pergunta;

  if (tipo === "equipamento" || tipo === "tecnica") {
    const opcoes = opcoesDaPosse(pergunta.opcoes);
    if (opcoes.length === 0) return { tipo: "conversa" };
    return { tipo: "posse", lista: tipo === "equipamento" ? "equipamentos" : "tecnicas", id: campo, opcoes };
  }

  if (CAMPOS_DA_RECEITA.has(campo) && entrada?.tipo === "inteiro") return { tipo: "receita", campo, entrada };

  if (tipo === "operacional") {
    if (entrada?.tipo === "inteiro" || entrada?.tipo === "horas") {
      return { tipo: "limite", campo, entrada, comNaoSei: pergunta.opcoes.some((o) => o.resposta === "nao_sei") };
    }
    if (pergunta.opcoes.some((o) => o.resposta === "sim")) return { tipo: "sim_nao", campo };
    return { tipo: "conversa" };
  }

  if (tipo === "ingrediente") return doIngrediente(pergunta, pistas);

  return { tipo: "conversa" };
}
