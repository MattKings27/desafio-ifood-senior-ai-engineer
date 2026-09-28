/**
 * As receitas de cada aba separadas pelo gosto dela, sem conta nenhuma: "Gosto
 * de fazer", "Ainda não me disse se gosta" e "Não gosto de fazer".
 *
 * A aba diz o que a cozinha permite (dá para fazer, falta uma resposta, o
 * ranking); a seção diz o que ela acha do prato. As que ela não quer vêm da API
 * à parte (`aba=nao_quer`, com os mesmos filtros), e cada uma fica na aba em
 * que estaria se ela gostasse: o selo diz qual. No ranking, a que ela não quer
 * já vem na lista, por último.
 *
 * A resposta dela vale na hora (`mudancas`, o otimista da tela): a receita muda
 * de seção antes de a API responder, e volta sozinha se a API recusar.
 */

import type { AbaDeReceitas, ItemDaGrade } from "@/lib/api/receitas";

export type SecaoDoGosto = "gosta" | "ainda_nao" | "nao_gosta";

export const ROTULO_DA_SECAO: Readonly<Record<SecaoDoGosto, string>> = {
  gosta: "Gosto de fazer",
  ainda_nao: "Ainda não me disse se gosta",
  nao_gosta: "Não gosto de fazer",
};

/** O gosto que ela acabou de dizer, por receita: `null` volta a "ainda não disse". */
export type MudancasDoGosto = Readonly<Record<string, boolean | null>>;

export type ReceitasPorGosto = Readonly<Record<SecaoDoGosto, ItemDaGrade[]>>;

const DA_PARA_FAZER = new Set(["com_o_que_tem", "comprando"]);

/** Em que aba a receita que ela não quer estaria, se ela gostasse: o selo é da cozinha, sem o gosto. */
export function ficaNaAba(aba: AbaDeReceitas, item: ItemDaGrade): boolean {
  const daParaFazer = DA_PARA_FAZER.has(item.selo.codigo);
  if (aba === "falta_resposta") return item.selo.codigo === "falta_resposta";
  if (aba === "ranking") return daParaFazer && item.pontuacao !== null;
  return daParaFazer;
}

/** O gosto que vale agora: o que ela acabou de dizer, ou o da API. A que ela não quer conta como "não gosto". */
export function gostoDe(item: ItemDaGrade, mudancas: MudancasDoGosto, naoQuer: ReadonlySet<string>): boolean | null {
  if (item.slug in mudancas) return mudancas[item.slug] ?? null;
  if (naoQuer.has(item.slug)) return false;
  // Sem o campo, ela ainda não disse.
  return item.gosta ?? null;
}

/**
 * As receitas da aba nas três seções, na ordem que a API mandou: primeiro as
 * da aba, depois as que ela não quer e que estariam nela. Cada uma leva o gosto
 * que vale agora, para o card saber o que perguntar.
 */
export function separarPorGosto(
  aba: AbaDeReceitas,
  daAba: readonly ItemDaGrade[],
  naoQuer: readonly ItemDaGrade[],
  mudancas: MudancasDoGosto,
): ReceitasPorGosto {
  const recusadas = new Set(naoQuer.map((item) => item.slug));
  const vistas = new Set<string>();
  const secoes: Record<SecaoDoGosto, ItemDaGrade[]> = { gosta: [], ainda_nao: [], nao_gosta: [] };
  for (const item of [...daAba, ...naoQuer.filter((recusada) => ficaNaAba(aba, recusada))]) {
    if (vistas.has(item.slug)) continue;
    vistas.add(item.slug);
    const gosta = gostoDe(item, mudancas, recusadas);
    const secao: SecaoDoGosto = gosta === true ? "gosta" : gosta === false ? "nao_gosta" : "ainda_nao";
    secoes[secao].push(gosta === item.gosta ? item : { ...item, gosta });
  }
  return secoes;
}

/** "1 receita", "3 receitas": o que o leitor de tela ouve depois da contagem da seção. */
export function receitasNaSecao(quantas: number): string {
  return quantas === 1 ? "1 receita" : `${quantas} receitas`;
}

/** O nome do prato no meio da frase: "pudim de leite", mas a sigla ("PF de frango") fica como está. */
export function pratoNaFrase(nome: string): string {
  const limpo = nome.trim();
  return /^\p{Lu}\p{Ll}/u.test(limpo) ? limpo.charAt(0).toLocaleLowerCase("pt-BR") + limpo.slice(1) : limpo;
}

/** O aviso depois da resposta: o que ela disse e para onde a receita foi. */
export function textoDoGosto(nome: string, gosta: boolean | null): string {
  const prato = pratoNaFrase(nome);
  if (gosta === true) return `Anotei que a senhora gosta de fazer ${prato}. Ela foi para ${ROTULO_DA_SECAO.gosta}.`;
  if (gosta === false) return `Anotei que a senhora não gosta de fazer ${prato}. Ela foi para ${ROTULO_DA_SECAO.nao_gosta}.`;
  return `Desfiz. ${nome} voltou para ${ROTULO_DA_SECAO.ainda_nao}.`;
}
