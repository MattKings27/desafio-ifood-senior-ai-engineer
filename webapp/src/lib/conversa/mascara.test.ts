/**
 * A máscara do navegador: nenhum dígito de dinheiro aparece antes da conta ser
 * conferida, nem quando o valor chega partido em dois pedaços.
 */

import { describe, expect, it } from "vitest";

import { contrato } from "@/teste/fixturas";

import {
  SENTINELA,
  comValoresEscondidos,
  corteSeguro,
  mascarar,
  mascararRascunho,
  temValorEmConferencia,
} from "./mascara";

const S = SENTINELA;

describe("mascarar", () => {
  it.each([
    ["A porção sai R$ 2,47 de ingrediente.", `A porção sai ${S} de ingrediente.`],
    ["Total R$ 1.234,56 hoje", `Total ${S} hoje`],
    ["R$12,5 e r$ 7", `${S} e ${S}`],
    ["custa 6 reais", `custa ${S}`],
    ["1 real só", `${S} só`],
    ["4,50 reais cada", `${S} cada`],
    ["1.234 reais", S],
    ["R$ 6 reais", `${S} reais`],
  ])("%s", (entrada, esperado) => {
    expect(mascarar(entrada)).toBe(esperado);
  });

  it("o resto de um valor colado no sentinela também some", () => {
    expect(mascarar(`${S}0,00 no total`)).toBe(`${S} no total`);
  });

  it("número que não é dinheiro fica", () => {
    expect(mascarar("Use 500 g de farinha e 2 ovos.")).toBe("Use 500 g de farinha e 2 ovos.");
    expect(mascarar("realmente bom")).toBe("realmente bom");
  });
});

describe("o valor partido entre pedaços", () => {
  it.each([
    ["A porção sai R", "A porção sai "],
    ["A porção sai R$", "A porção sai "],
    ["A porção sai R$ 7,", "A porção sai "],
    ["Custa 4,5", "Custa "],
    ["Custa 4,5 rea", "Custa "],
    ["Custa R$ 12 re", "Custa "],
  ])("%s: o fim que pode virar valor fica retido", (entrada, esperado) => {
    expect(corteSeguro(entrada)).toBe(esperado.length);
    expect(mascararRascunho(entrada)).toBe(esperado);
  });

  it("nenhum dígito do valor aparece em nenhuma partição do texto", () => {
    const texto = "Dá pra fazer. A porção sai R$ 663,39 de ingrediente e 6 reais de gás.";
    for (let corte = 0; corte <= texto.length; corte += 1) {
      const visivel = mascararRascunho(texto.slice(0, corte));
      expect(visivel).not.toMatch(/663|39|6 reais/);
    }
  });

  it("quando o pedaço seguinte mostra que não era dinheiro, o texto aparece", () => {
    expect(mascararRascunho("Faço em 2")).toBe("Faço em ");
    expect(mascararRascunho("Faço em 2 horas")).toBe("Faço em 2 horas");
  });
});

describe("apoios", () => {
  it("temValorEmConferencia", () => {
    expect(temValorEmConferencia(`sai ${S}`)).toBe(true);
    expect(temValorEmConferencia("sai de graça")).toBe(false);
  });

  it("comValoresEscondidos troca pelo brilho de uma linha", () => {
    expect(comValoresEscondidos("pesquisando receitas até R$ 30")).toBe("pesquisando receitas até R$ ···");
    expect(comValoresEscondidos(`anotei ${S}`)).toBe("anotei R$ ···");
  });
});

/**
 * Os mesmos exemplos que o backend confere (`gateway/tests/test_mascara.py`):
 * as duas portas escondem os mesmos valores. Onde o navegador vai além (o "r$"
 * minúsculo), o exemplo diz, no campo `_no_navegador`.
 */
type ExemploDaMascara = {
  texto: string;
  mascarado: string;
  rascunho: string;
  mascarado_no_navegador?: string;
  rascunho_no_navegador?: string;
};

const { casos } = contrato<{ casos: ExemploDaMascara[] }>("mascara.json");
const comSentinela = (texto: string) => texto.replaceAll("{S}", S);

describe("os exemplos que o backend também confere", () => {
  it.each(casos.map((caso) => [caso.texto, caso] as const))("%s", (_texto, caso) => {
    expect(mascarar(caso.texto)).toBe(comSentinela(caso.mascarado_no_navegador ?? caso.mascarado));
    expect(mascararRascunho(caso.texto)).toBe(comSentinela(caso.rascunho_no_navegador ?? caso.rascunho));
  });
});
