/**
 * Pequenos acertos de apresentação nos textos que vêm prontos da API. Nenhum
 * deles muda palavra nem número: só a caixa da primeira letra e onde a linha
 * pode quebrar.
 */

/** "a senhora já tinha" vira "A senhora já tinha", para abrir um selo ou uma linha. */
export function comMaiuscula(texto: string): string {
  return texto.charAt(0).toLocaleUpperCase("pt-BR") + texto.slice(1);
}

/**
 * Espaço que não quebra entre "R$" e o valor, e entre o número e a unidade
 * ("0,4 kg"): a conta numa coluna estreita não deixa "R$" sozinho no fim da
 * linha.
 */
export function semQuebrarNumero(texto: string): string {
  return texto.replace(/R\$ /g, "R$ ").replace(/(\d) (kg|g|L|ml|un|embalagens?)\b/g, "$1 $2");
}
