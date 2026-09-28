/**
 * O corpo que a tela de preço envia, fixado no arquivo de contrato.
 *
 * O teste de Python `gateway/tests/test_contrato_da_tela.py` manda este mesmo
 * JSON para a API. Mudar `montarReceita` sem regenerar o contrato quebra aqui;
 * mudar a API sem aceitar este corpo quebra lá.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { EXEMPLO_DE_INGREDIENTES, montarReceita, nomeDaLinha } from "./receita";

// O vitest roda na raiz do `webapp`; o contrato mora na raiz do repositório.
// (`import.meta.url` não serve: sob jsdom ele é `http:`, não `file:`.)
const CONTRATO = resolve(process.cwd(), "..", "contratos", "precificar-exemplo-da-tela.json");

describe("montarReceita", () => {
  it("manda para a API exatamente o que o contrato fixa", () => {
    const contrato = JSON.parse(readFileSync(CONTRATO, "utf-8"));
    expect(montarReceita("Bolo de cenoura", EXEMPLO_DE_INGREDIENTES, 4)).toEqual(contrato);
  });

  it("ignora linhas em branco e espaços nas pontas", () => {
    const receita = montarReceita("  Arroz  ", "\n  2 xícaras de arroz  \n\n", 2);
    expect(receita).toEqual({
      nome: "Arroz",
      ingredientes: [{ texto: "2 xícaras de arroz", nome: "arroz" }],
      rendimento_porcoes: 2,
    });
  });

  it("leva o preparo linha a linha e a fonte quando vem da internet", () => {
    const receita = montarReceita("Arroz", "1 kg de arroz", 4, {
      preparo: "Refogue.\n\n Cozinhe 20 minutos. ",
      url: " https://www.exemplo.com.br/arroz ",
      fonte: "Exemplo",
    });
    expect(receita?.modo_preparo).toEqual(["Refogue.", "Cozinhe 20 minutos."]);
    expect(receita?.url).toBe("https://www.exemplo.com.br/arroz");
    expect(receita?.fonte).toBe("Exemplo");
    const semFonte = montarReceita("Arroz", "1 kg", 4, { url: "https://x.com.br/a" });
    expect(semFonte?.fonte).toBeNull();
    expect(montarReceita("Arroz", "1 kg", 4, { preparo: "  " })?.modo_preparo).toBeUndefined();
  });

  it("leva o tempo no fogo quando ela diz, em minutos inteiros", () => {
    expect(montarReceita("Arroz", "1 kg", 4, { tempo: 39.6 })?.tempo_cozimento_min).toBe(40);
    expect(montarReceita("Arroz", "1 kg", 4, { tempo: null })?.tempo_cozimento_min).toBeUndefined();
    expect(montarReceita("Arroz", "1 kg", 4, { tempo: 0 })?.tempo_cozimento_min).toBeUndefined();
  });

  it("não monta nada sem nome ou sem ingrediente", () => {
    expect(montarReceita(" ", "4 ovos", 4)).toBeNull();
    expect(montarReceita("Omelete", "\n \n", 4)).toBeNull();
  });
});

describe("nomeDaLinha", () => {
  it.each([
    ["2 xícaras (chá) de farinha de trigo", "farinha de trigo"],
    ["4 ovos", "ovos"],
    ["½ xícara de óleo", "óleo"],
    ["300 g de peito de frango", "peito de frango"],
  ])("%s → %s", (linha, nome) => {
    expect(nomeDaLinha(linha)).toBe(nome);
  });

  it("devolve a linha inteira quando não sobra nome", () => {
    expect(nomeDaLinha("12")).toBe("12");
  });
});
