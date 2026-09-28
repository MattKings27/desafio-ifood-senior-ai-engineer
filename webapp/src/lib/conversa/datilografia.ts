/**
 * A resposta aparecendo letra a letra, num ritmo que acompanha a chegada.
 *
 * O texto não chega em fluxo regular. Medido no agente real: numa resposta
 * sem ferramenta vêm dez pedaços no mesmo milissegundo e nada por quase um
 * segundo; depois de uma ferramenta, a resposta inteira chega de uma vez, 80
 * pedaços em 30 ms. Mostrar do jeito que chega faz o texto pular em blocos.
 * Aqui a tela revela o que já chegou num ritmo contínuo:
 *
 * - **Ritmo que se adapta.** A velocidade é uma base mais o atraso dividido
 *   por uma constante de tempo: com pouco acumulado, a tela escreve na
 *   velocidade da base; quando chega um bloco grande, ela acelera, e o atraso
 *   cai pela metade a cada 0,45 s. As rajadas de 80 caracteres por segundo
 *   viram um fluxo contínuo, e uma resposta de 800 caracteres que chega de uma
 *   vez termina de aparecer em pouco mais de 2 s.
 * - **O texto conferido entra no lugar sem piscar.** Quando o texto final
 *   chega, a posição já revelada do rascunho é levada para ele
 *   (`posicaoNoFinal`): cada valor escondido do rascunho casa com o valor
 *   conferido no mesmo ponto, e só esses pontos mudam.
 * - **Sem Markdown pela metade.** O corte nunca deixa um `**` aberto à mostra
 *   (o negrito aparece já negrito), não parte um link nem um emoji.
 *
 * Quem pediu menos movimento vê o texto do jeito que ele chega.
 */

import { SENTINELA } from "./mascara";

/** Caracteres por segundo quando quase nada está esperando para aparecer. */
export const RITMO_BASE = 35;

/**
 * Em segundos: quanto maior o acúmulo, mais rápido. O atraso cai como
 * `e^(-t/τ)`, e com a base somada ele zera num tempo finito.
 */
export const CONSTANTE_DE_TEMPO_S = 0.65;

/** O maior salto de tempo que conta num quadro (a aba em segundo plano congela o relógio). */
export const QUADRO_MAXIMO_MS = 250;

/**
 * Chave global, como a do `motion`: nos testes de interface o texto aparece de
 * uma vez, e só os testes da datilografia ligam o ritmo.
 */
export const configuracaoDaDatilografia = { instantanea: false };

/**
 * Quantos caracteres revelar em `dtMs`, com `atraso` caracteres esperando.
 *
 * A solução exata de `d(atraso)/dt = -(base + atraso/τ)`, e não um passo de
 * Euler: o resultado não depende de quantos quadros por segundo a tela faz.
 */
export function caracteresNoQuadro(atraso: number, dtMs: number): number {
  if (atraso <= 0 || dtMs <= 0) return 0;
  const dt = Math.min(dtMs, QUADRO_MAXIMO_MS) / 1000;
  const piso = RITMO_BASE * CONSTANTE_DE_TEMPO_S;
  const depois = (atraso + piso) * Math.exp(-dt / CONSTANTE_DE_TEMPO_S) - piso;
  return Math.min(atraso, atraso - Math.max(0, depois));
}

/** Um valor conferido no ponto em que o rascunho tinha o sentinela. */
const VALOR_NO_FINAL = /^(?:[Rr]\$\s*\d(?:[\d.,]*\d)?|\[valor retirado\]|\d(?:[\d.,]*\d)?\s*(?:reais|real)(?![\p{L}\p{N}_]))/u;

/**
 * Onde, no texto final, fica o ponto que o rascunho revelado alcançou.
 *
 * Anda pelos dois ao mesmo tempo: caractere igual avança nos dois; o
 * sentinela do rascunho consome o valor conferido do final ("R$ 2,47",
 * "[valor retirado]", "6 reais"). Se os dois divergem (o guard-rail tirou a
 * nota do fim, o agente reescreveu), fica no ponto da divergência, mas nunca
 * mostra menos caracteres do que já mostrava: a tela não apaga o que ela leu.
 */
export function posicaoNoFinal(revelado: string, final: string): number {
  const [i, j] = caminharJuntos(revelado, final);
  if (i >= revelado.length) return j;
  return Math.min(final.length, Math.max(j, revelado.length));
}

/**
 * O mesmo ponto no texto novo, só se o revelado inteiro casa com o começo dele
 * (igual, ou com os valores conferidos no lugar dos sentinelas); `null` se não.
 */
export function pontoQueCasa(revelado: string, novo: string): number | null {
  const [i, j] = caminharJuntos(revelado, novo);
  return i >= revelado.length ? j : null;
}

function caminharJuntos(revelado: string, final: string): [number, number] {
  let i = 0;
  let j = 0;
  while (i < revelado.length && j < final.length) {
    if (revelado[i] === final[j]) {
      i += 1;
      j += 1;
      continue;
    }
    if (revelado[i] === SENTINELA) {
      const valor = VALOR_NO_FINAL.exec(final.slice(j));
      if (!valor) break;
      i += 1;
      j += valor[0].length;
      continue;
    }
    break;
  }
  return [i, j];
}

/**
 * A posição revelada quando o texto muda: o mesmo texto crescendo mantém a
 * posição; outro texto (o final no lugar do rascunho) recebe a posição
 * equivalente; um rascunho que recomeçou (veio uma ferramenta) volta ao zero.
 */
export function reposicionar(anterior: string, revelados: number, novo: string): number {
  if (novo.startsWith(anterior.slice(0, revelados))) return Math.min(revelados, novo.length);
  if (revelados === 0) return 0;
  return posicaoNoFinal(anterior.slice(0, revelados), novo);
}

/** Um link inteiro em Markdown: `[texto](https://...)`. */
const LINK = /\[[^\]\n]*\]\([^)\s]*\)/g;

/**
 * Até onde mostrar, a partir de `revelados`, sem deixar Markdown pela metade:
 * um link parcial aparece inteiro, um emoji não é partido, um `*` que é metade
 * de `**` vem junto com a outra, e o hífen de uma lista vem com o espaço.
 */
export function corteLegivel(texto: string, revelados: number): number {
  let corte = Math.max(0, Math.min(texto.length, Math.floor(revelados)));
  if (corte === 0 || corte >= texto.length) return corte;
  for (const link of texto.matchAll(LINK)) {
    const inicio = link.index;
    const fim = inicio + link[0].length;
    if (inicio < corte && corte < fim) {
      corte = fim;
      break;
    }
  }
  const codigo = texto.charCodeAt(corte - 1);
  if (codigo >= 0xd800 && codigo <= 0xdbff) corte += 1;
  if (texto[corte - 1] === "*" && texto[corte] === "*") corte += 1;
  if (texto[corte - 1] === "-" && texto[corte] === " " && (corte === 1 || texto[corte - 2] === "\n")) corte += 1;
  return Math.min(corte, texto.length);
}

/**
 * O pedaço revelado, pronto para o Markdown: um negrito ainda aberto ganha o
 * fecho, e aparece negrito enquanto é escrito, em vez de mostrar os asteriscos.
 */
export function trechoVisivel(texto: string, revelados: number): string {
  const trecho = texto.slice(0, corteLegivel(texto, revelados));
  if (trecho.length === texto.length) return trecho;
  const ultimoParagrafo = trecho.slice(trecho.lastIndexOf("\n") + 1);
  const marcas = ultimoParagrafo.split("**").length - 1;
  if (marcas % 2 === 1 && !ultimoParagrafo.endsWith("**")) return `${trecho}**`;
  if (marcas % 2 === 1) return trecho.slice(0, -2);
  return trecho;
}

/* -------------------------------------------------------------------------- */
/* O progresso de cada resposta                                                */
/* -------------------------------------------------------------------------- */

/**
 * Quanto de cada resposta ao vivo já apareceu. A resposta em andamento e a
 * resposta guardada são peças diferentes na tela: quando o turno termina, a
 * guardada continua de onde a outra parou, em vez de aparecer inteira de uma
 * vez. Resposta que não passou por aqui (a do histórico) aparece inteira.
 */
export type Progresso = { texto: string; revelados: number };

const LIMITE_DE_PROGRESSOS = 20;
const progressos = new Map<string, Progresso>();

export function lerProgresso(chave: string): Progresso | undefined {
  return progressos.get(chave);
}

export function gravarProgresso(chave: string, progresso: Progresso): void {
  progressos.delete(chave);
  progressos.set(chave, progresso);
  while (progressos.size > LIMITE_DE_PROGRESSOS) {
    const maisAntigo = progressos.keys().next().value;
    if (maisAntigo === undefined) break;
    progressos.delete(maisAntigo);
  }
}

export function esquecerProgresso(chave: string): void {
  progressos.delete(chave);
}

/** Para os testes: começa do zero. */
export function esquecerTodosOsProgressos(): void {
  progressos.clear();
}
