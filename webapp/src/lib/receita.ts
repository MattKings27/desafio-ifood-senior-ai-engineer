import type { ReceitaEntrada } from "./api/receitas";

/**
 * O exemplo que a tela de preço mostra no campo de ingredientes.
 *
 * Fica aqui, e não no componente, porque é também o caso do teste de contrato:
 * o que a Dona Maria vê como exemplo tem que ser algo que o motor sabe precificar.
 */
export const EXEMPLO_DE_INGREDIENTES =
  "2 xícaras (chá) de farinha de trigo\n4 ovos\n1/2 xícara de óleo\nsal a gosto";

/**
 * O corpo que a tela manda para `/api/avaliar` e `/api/cmv`.
 *
 * Função pura para poder ser fixada num arquivo de contrato que o lado Python
 * também lê. Os dois lados testados contra o mesmo JSON: se um mudar o formato
 * sem o outro, algum teste fica vermelho.
 */
export function montarReceita(
  nome: string,
  linhas: string,
  rendimento: number,
  extras: { preparo?: string; url?: string; fonte?: string; tempo?: number | null } = {},
): ReceitaEntrada | null {
  const ingredientes = linhas
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((texto) => ({ texto, nome: nomeDaLinha(texto) }));

  if (!nome.trim() || ingredientes.length === 0) return null;
  const receita: ReceitaEntrada = { nome: nome.trim(), ingredientes, rendimento_porcoes: rendimento };
  // Só entra o que ela preencheu: campo vazio não vira passo nem fonte.
  const passos = (extras.preparo ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (passos.length > 0) receita.modo_preparo = passos;
  // O tempo no fogo é opcional: sem ele, a conferência pergunta (e a resposta volta aqui).
  if (extras.tempo && extras.tempo > 0) receita.tempo_cozimento_min = Math.round(extras.tempo);
  if (extras.url?.trim()) {
    receita.url = extras.url.trim();
    receita.fonte = extras.fonte?.trim() || null;
  }
  return receita;
}

/**
 * O nome do ingrediente a partir da linha crua.
 *
 * É um palpite grosseiro de propósito: quem interpreta de verdade é o
 * `retrieval` no servidor, com o vocabulário de medidas do motor. Aqui basta
 * mandar algo que o casamento consiga usar, e o texto original vai junto.
 */
export function nomeDaLinha(texto: string): string {
  const semQuantidade = texto.replace(/^[\d\s.,/¼½¾⅓⅔]+/, "");
  const depoisDoDe = semQuantidade.split(/\bde\s+/i).slice(1).join("de ");
  return (depoisDoDe || semQuantidade).replace(/\(.*?\)/g, "").trim() || texto;
}
