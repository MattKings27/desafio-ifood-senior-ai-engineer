/**
 * Nenhum valor em reais aparece antes de ser conferido.
 *
 * Enquanto o agente escreve, o rascunho pode trazer um "R$ 7,50" que o
 * modelo fez de cabeça: o guard-rail só confere o texto no fim do turno. O
 * backend já manda o rascunho mascarado (todo valor vira o caractere
 * sentinela U+E000), e a tela desenha o sentinela como o brilho "R$ ···".
 *
 * Esta máscara é a segunda porta, no navegador: se um valor escapar do backend
 * (um pedaço partido, um bug), ele também não aparece. Ela usa os mesmos
 * padrões do guard-rail e do backend (`gateway/mascara.py`):
 *
 * - valor com cifrão: "R$ 1.234,56", "R$ 12", "R$12,5" (e o "r$" minúsculo);
 * - o resto de um valor que o padrão não alcançou, colado no sentinela ("0,00"
 *   de "R$ 1500,00");
 * - dinheiro falado: "6 reais", "1 real", "4,50 reais", "1.234 reais".
 *
 * **O valor partido.** "R$ 66" num pedaço e "3,39" no seguinte não podem
 * mostrar nenhum dígito. A máscara roda sobre o rascunho inteiro, não pedaço a
 * pedaço, e segura o fim que ainda pode virar valor: um "R" solto, "R$",
 * "R$ 7,", um número no fim (pode ganhar "reais"), "4,5 rea". O que fica
 * retido aparece quando o próximo pedaço mostrar que não era dinheiro.
 */

/** O caractere que o backend põe no lugar de cada valor ainda não conferido. */
export const SENTINELA = "";

/** O que o texto final tem no lugar de um valor que nada na conversa sustenta. */
export const VALOR_RETIRADO = "[valor retirado]";

/** O valor com cifrão, como o `_VALOR` do guard-rail (com o "r" minúsculo também). */
const COM_CIFRAO = /[Rr]\$\s*(?:\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)/g;

/** O resto de um valor colado no sentinela: o "0,00" de "R$ 1500,00". */
const RESTO_COLADO = new RegExp(`${SENTINELA}[\\d.,]*\\d`, "g");

/** O dinheiro falado: qualquer número colado em "reais" ou "real", palavra inteira. */
const FALADO = /\d(?:[\d.,]*\d)?\s*(?:reais|real)(?![\p{L}\p{N}_])/giu;

/** O fim que ainda pode crescer para um valor com cifrão: "R", "R$", "R$ 7,", "r$ 1.2". */
const CAUDA_COM_CIFRAO = /(?:R|[Rr]\$\s*[\d.,]*)$/u;

/** O fim que ainda pode virar dinheiro falado: "4,5", "4,5 ", "4,5 rea", "R$ 12 re". */
const CAUDA_FALADA = /(?:[Rr]\$\s*)?\d[\d.,]*\s*(?:r(?:e(?:a(?:is?|l)?)?)?)?$/iu;

/** Troca todo valor em reais do texto pelo sentinela, de uma vez. */
export function mascarar(texto: string): string {
  // O cifrão primeiro: em "R$ 6 reais", o "R$ 6" vira sentinela e o " reais"
  // que sobra não tem mais número para casar.
  return texto.replace(COM_CIFRAO, SENTINELA).replace(RESTO_COLADO, SENTINELA).replace(FALADO, SENTINELA);
}

/** Onde o rascunho pode ser cortado com segurança: antes do fim que ainda pode virar valor. */
export function corteSeguro(texto: string): number {
  let corte = texto.length;
  for (const cauda of [CAUDA_COM_CIFRAO, CAUDA_FALADA]) {
    const achado = cauda.exec(texto);
    if (achado) corte = Math.min(corte, achado.index);
  }
  return corte;
}

/**
 * O rascunho como pode aparecer: mascarado, e sem o fim que ainda pode virar
 * valor. Serve para o turno em andamento e para o rascunho de um turno que
 * parou ou falhou, que fica mascarado para sempre.
 */
export function mascararRascunho(texto: string): string {
  return mascarar(texto.slice(0, corteSeguro(texto)));
}

/** O texto tem algum valor ainda em conferência (o sentinela)? */
export function temValorEmConferencia(texto: string): boolean {
  return texto.includes(SENTINELA);
}

/** Para um texto curto de uma linha (rótulo, prévia): o sentinela vira "R$ ···". */
export function comValoresEscondidos(texto: string): string {
  return mascarar(texto).replaceAll(SENTINELA, "R$ ···");
}
