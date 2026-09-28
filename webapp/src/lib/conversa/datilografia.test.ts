import { describe, expect, it } from "vitest";

import {
  CONSTANTE_DE_TEMPO_S,
  RITMO_BASE,
  caracteresNoQuadro,
  corteLegivel,
  posicaoNoFinal,
  pontoQueCasa,
  reposicionar,
  trechoVisivel,
} from "./datilografia";
import { SENTINELA } from "./mascara";

/** Revela `atraso` caracteres em quadros de `quadroMs` e diz quanto tempo levou. */
function tempoParaZerar(atraso: number, quadroMs: number): number {
  let restante = atraso;
  let resto = 0;
  let tempo = 0;
  while (restante > 0 && tempo < 60_000) {
    const avanco = caracteresNoQuadro(restante, quadroMs) + resto;
    const inteiros = Math.floor(avanco);
    resto = avanco - inteiros;
    restante -= Math.min(restante, inteiros);
    tempo += quadroMs;
  }
  return tempo;
}

describe("o ritmo", () => {
  it("com pouco acumulado, escreve perto da base, e não inventa texto", () => {
    const umSegundo = Array.from({ length: 60 }).reduce<number>((soma) => soma + caracteresNoQuadro(5, 1000 / 60), 0);
    expect(caracteresNoQuadro(0, 16)).toBe(0);
    expect(caracteresNoQuadro(5, 0)).toBe(0);
    expect(caracteresNoQuadro(3, 10_000)).toBe(3);
    // Cinco caracteres esperando o tempo todo: base mais 5/τ por segundo.
    expect(umSegundo).toBeGreaterThan(RITMO_BASE);
    expect(umSegundo).toBeLessThan(RITMO_BASE + 5 / CONSTANTE_DE_TEMPO_S + 1);
  });

  it("acelera quando chega um bloco grande, e uma resposta inteira aparece em pouco mais de 2 s", () => {
    expect(caracteresNoQuadro(800, 16)).toBeGreaterThan(10 * caracteresNoQuadro(20, 16));
    const oitocentos = tempoParaZerar(800, 1000 / 60);
    expect(oitocentos).toBeGreaterThan(1_900);
    expect(oitocentos).toBeLessThan(2_700);
    // Mesmo um texto enorme termina logo: o tempo cresce com o logaritmo do tamanho.
    expect(tempoParaZerar(4_000, 1000 / 60)).toBeLessThan(3_600);
  });

  it("não depende de quantos quadros por segundo a tela faz", () => {
    const a30 = tempoParaZerar(500, 1000 / 30);
    const a120 = tempoParaZerar(500, 1000 / 120);
    expect(Math.abs(a30 - a120)).toBeLessThan(120);
  });

  it("a aba em segundo plano não despeja tudo de uma vez quando volta", () => {
    expect(caracteresNoQuadro(1_000, 30_000)).toBe(caracteresNoQuadro(1_000, 250));
    expect(caracteresNoQuadro(1_000, 250)).toBeLessThan(1_000);
  });

  it("rajadas de 80 caracteres por segundo viram um fluxo contínuo, sem ficar para trás", () => {
    // O padrão medido: dez pedaços no mesmo milissegundo, e nada por um segundo.
    let chegou = 0;
    let revelado = 0;
    let resto = 0;
    let maiorAtraso = 0;
    let paradas = 0;
    for (let t = 0; t < 6_000; t += 16) {
      if (t % 992 === 0 && t < 5_000) chegou += 80;
      const avanco = caracteresNoQuadro(chegou - revelado, 16) + resto;
      const inteiros = Math.floor(avanco);
      resto = avanco - inteiros;
      revelado = Math.min(chegou, revelado + inteiros);
      maiorAtraso = Math.max(maiorAtraso, chegou - revelado);
      if (t > 100 && t < 4_900 && chegou === revelado) paradas += 1;
    }
    expect(revelado).toBe(chegou);
    // Nunca mais do que um bloco atrás, e quase sem parar entre um bloco e outro.
    expect(maiorAtraso).toBeLessThanOrEqual(80);
    expect(paradas).toBeLessThan(15);
  });
});

describe("o texto conferido no lugar do rascunho", () => {
  it("cada valor escondido casa com o valor conferido no mesmo ponto", () => {
    const rascunho = `A porção sai ${SENTINELA} e o prato ${SENTINELA}. Dá lucro.`;
    const final = "A porção sai **R$ 2,47** e o prato R$ 18,90. Dá lucro.";
    // O revelado parou logo depois do segundo valor.
    const revelado = rascunho.slice(0, rascunho.indexOf(".") + 1);
    const ponto = posicaoNoFinal(revelado, final.replaceAll("**", ""));
    expect(final.replaceAll("**", "").slice(0, ponto)).toBe("A porção sai R$ 2,47 e o prato R$ 18,90.");
  });

  it("o valor retirado e o dinheiro falado também casam", () => {
    expect(posicaoNoFinal(`Sai ${SENTINELA} a porção`, "Sai [valor retirado] a porção, e só.")).toBe(
      "Sai [valor retirado] a porção".length,
    );
    expect(posicaoNoFinal(`Custa ${SENTINELA} cada`, "Custa 6 reais cada um.")).toBe("Custa 6 reais cada".length);
  });

  it("quando os textos divergem, nunca mostra menos do que já mostrava", () => {
    const revelado = "Olá, Dona Maria! Tudo certo por aí";
    const final = "Olá, Dona Maria! Estou aqui.";
    expect(posicaoNoFinal(revelado, final)).toBe(final.length);
    expect(pontoQueCasa(revelado, final)).toBeNull();
    expect(pontoQueCasa("Olá, Dona", final)).toBe(9);
  });

  it("reposicionar: o mesmo texto crescendo mantém o ponto, e o rascunho recomeçado volta ao zero", () => {
    expect(reposicionar("Olá", 3, "Olá, Dona Maria")).toBe(3);
    expect(reposicionar(`Sai ${SENTINELA}`, 5, "Sai R$ 2,47.")).toBe("Sai R$ 2,47".length);
    expect(reposicionar("Vou olhar a despensa", 0, "Com o que a senhora tem")).toBe(0);
  });
});

describe("o corte legível", () => {
  it("negrito aberto aparece negrito, sem os asteriscos à mostra", () => {
    const texto = "**Dá para fazer agora:** três pratos.";
    expect(trechoVisivel(texto, 8)).toBe("**Dá par**");
    expect(trechoVisivel(texto, 2)).toBe("");
    expect(trechoVisivel(texto, 1)).toBe("");
    expect(trechoVisivel(texto, texto.length)).toBe(texto);
    expect(trechoVisivel("Um **dois**", 10)).toBe("Um **dois**");
  });

  it("link aparece inteiro, emoji não se parte, e o hífen da lista vem com o espaço", () => {
    const comLink = "Veja [a receita](https://exemplo.com.br/bolo) aqui.";
    expect(corteLegivel(comLink, 10)).toBe(comLink.indexOf(")") + 1);
    expect(corteLegivel("Oi 😊 tudo", 4)).toBe(5);
    expect(corteLegivel("Opções:\n- arroz", 9)).toBe(10);
    expect(corteLegivel("abc", 0)).toBe(0);
    expect(corteLegivel("abc", 9)).toBe(3);
  });
});
