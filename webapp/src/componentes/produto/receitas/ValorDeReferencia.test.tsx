/**
 * O que a plataforma estabelece sem perguntar aparece como "Estimado", com a
 * fonte, e ela corrige ali mesmo pelo "corrigir" discreto: o preço de
 * referência no card da grade, e o campo que manda o preço dela, que vale
 * mais. Nada disso é pergunta.
 */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({
  responderSobreAReceita: vi.fn(),
  responderSobreACozinha: vi.fn(),
  responderLimiteDaCozinha: vi.fn(),
  informarPrecoDoQueFalta: vi.fn(),
  avaliarReceita: vi.fn(),
  anotarReceita: vi.fn(),
  trazerReceita: vi.fn(),
}));

import * as acoes from "@/lib/acoes/receitas";
import type { ItemDaGrade, PerguntaDaReceita, PrecoDeReferencia } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { deuCerto, deuErrado, montar } from "@/teste/receitas";

import { CartaoDeReceita } from "./CartaoDeReceita";
import { correcaoDe } from "./correcao";
import { CorrigirValor } from "./CorrigirValor";

const acao = vi.mocked(acoes);

const REFERENCIA = contrato<{ ingrediente_com_preco_de_referencia_exemplo: { referencia: PrecoDeReferencia } }>("custo.json")
  .ingrediente_com_preco_de_referencia_exemplo.referencia;

/** O card "Frango com milho verde" do contrato da grade. */
function cardDoContrato(): ItemDaGrade {
  const item = contrato<{ itens: ItemDaGrade[] }>("receitas.json").itens[1];
  if (!item) throw new Error("o contrato da grade tem dois cards");
  return item;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("o preço de referência no card", () => {
  it("diz que é estimado, mostra o preço médio em São Paulo com cada mercado e o link, e deixa ela corrigir sem pergunta", async () => {
    acao.informarPrecoDoQueFalta.mockResolvedValue(deuCerto({ texto: "Anotei: creme de leite custa R$ 3,50 por 1 caixinha." }));
    const item: ItemDaGrade = { ...cardDoContrato(), referencias: [REFERENCIA] };
    montar(<CartaoDeReceita item={item} />);

    // De qual ingrediente é, em destaque, com o selo; o preço por kg e de quantos mercados saiu.
    const bloco = screen.getByRole("region", { name: "Preço de creme de leite" });
    expect(within(bloco).getByText("Creme de leite")).toBeInTheDocument();
    expect(within(bloco).getByText("Estimado")).toBeInTheDocument();
    expect(within(bloco).getByText("Preço médio em São Paulo")).toBeInTheDocument();
    expect(within(bloco).getByText(REFERENCIA.preco_medio_texto)).toBeInTheDocument();
    expect(REFERENCIA.preco_medio_texto).toMatch(/\/kg$/);
    expect(within(bloco).getByText(`média de ${REFERENCIA.mercados_na_media} mercados de São Paulo`)).toBeInTheDocument();
    // A tabela de cada mercado: embalagem, preço e preço por kg, com o link do produto.
    const mercados = within(bloco).getByRole("table", { name: "Preço de creme de leite em cada mercado de São Paulo" });
    expect(within(mercados).getByRole("columnheader", { name: "Por kg" })).toBeInTheDocument();
    for (const fonte of REFERENCIA.fontes) {
      expect(within(mercados).getByRole("link", { name: fonte.site })).toHaveAttribute("href", fonte.url);
      expect(within(mercados).getAllByText(fonte.embalagem_texto).length).toBeGreaterThan(0);
      expect(within(mercados).getAllByText(fonte.por_unidade_texto).length).toBeGreaterThan(0);
    }
    const fora = REFERENCIA.fontes.filter((f) => !f.na_media);
    expect(within(mercados).queryAllByText("fora da média")).toHaveLength(fora.length);

    const corrigir = screen.getByRole("button", { name: "corrigir o preço de creme de leite" });
    expect(corrigir).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(corrigir);
    expect(corrigir).toHaveAttribute("aria-expanded", "true");
    fireEvent.change(screen.getByRole("textbox", { name: "Preço" }), { target: { value: "3,50" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Medida" }), { target: { value: "caixinha" } });
    expect(screen.getByText("O preço de creme de leite que a senhora paga")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Quanto custa/);
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(acao.informarPrecoDoQueFalta).toHaveBeenCalledWith([{ ingrediente: "creme de leite", valor: 3.5, quantidade: 1, unidade: "caixinha" }]),
    );
  });

  it("sem preço de referência, o card não mostra nada a mais", () => {
    montar(<CartaoDeReceita item={cardDoContrato()} />);
    expect(screen.queryByText(/Preço médio em São Paulo/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /corrigir o preço/ })).not.toBeInTheDocument();
  });

  it("sem o preço e a quantidade, avisa antes de mandar; a recusa da API aparece perto", async () => {
    acao.informarPrecoDoQueFalta.mockResolvedValue(deuErrado("Não entendi a medida."));
    const item: ItemDaGrade = { ...cardDoContrato(), referencias: [REFERENCIA] };
    montar(<CartaoDeReceita item={item} />);
    fireEvent.click(screen.getByRole("button", { name: "corrigir o preço de creme de leite" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByText(/^Escreva o preço de creme de leite e por qual quantidade/)).toHaveAttribute("role", "alert");
    expect(acao.informarPrecoDoQueFalta).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Preço" }), { target: { value: "3,50" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Quantidade" }), { target: { value: "" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Medida" }), { target: { value: "caixinha" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(acao.informarPrecoDoQueFalta).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Quantidade" }), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Não entendi a medida.")).toBeInTheDocument();
  });
});

describe("o corrigir do peso e do número", () => {
  const RECEITA = { slug: "frango", nome: "Frango com alcaparras" };

  it("o peso vai em gramas ou quilos, de uma unidade ou da linha inteira, e sem número avisa", async () => {
    acao.responderSobreAReceita.mockResolvedValueOnce(deuErrado("Esse peso a receita já diz.")).mockResolvedValueOnce(
      deuCerto({ slug: "frango", nome: RECEITA.nome, cozinha: { codigo: "com_o_que_tem", rotulo: "", motivo: "" } }),
    );
    montar(
      <CorrigirValor
        receita={RECEITA}
        correcao={{ tipo: "peso", campo: "2 colheres de sopa de alcaparras", pesoDe: { cada: "1 colher de sopa", tudo: "2 colheres de sopa" } }}
        oQue="o peso das alcaparras"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "corrigir o peso das alcaparras" }));
    expect(screen.getByText("O peso de 2 colheres de sopa de alcaparras na cozinha da senhora")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByText("Escreva o peso, por exemplo: 300 g.")).toHaveAttribute("role", "alert");
    fireEvent.change(screen.getByRole("textbox", { name: "Peso" }), { target: { value: "0,3" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Unidade" }), { target: { value: "kg" } });
    fireEvent.click(screen.getByText("2 colheres de sopa"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(acao.responderSobreAReceita).toHaveBeenCalledWith("frango", "2 colheres de sopa de alcaparras", "0,3 kg", false));
    expect(await screen.findByText("Esse peso a receita já diz.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Unidade" }), { target: { value: "g" } });
    fireEvent.click(screen.getByText("1 colher de sopa"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(acao.responderSobreAReceita).toHaveBeenLastCalledWith("frango", "2 colheres de sopa de alcaparras", "0,3 g", true));
    expect(document.body.textContent).not.toMatch(/quanto pesa/i);
  });

  it("o número (as porções) vai para a receita; sem unidade, o campo se chama número; e fecha de novo", async () => {
    acao.responderSobreAReceita.mockResolvedValue(deuCerto({ slug: "frango", nome: RECEITA.nome, cozinha: { codigo: "com_o_que_tem", rotulo: "", motivo: "" } }));
    const { rerender } = montar(
      <CorrigirValor receita={RECEITA} correcao={{ tipo: "numero", campo: "rendimento_porcoes", entrada: { tipo: "inteiro" } }} oQue="o rendimento" />,
    );
    const corrigir = screen.getByRole("button", { name: "corrigir o rendimento" });
    fireEvent.click(corrigir);
    expect(screen.getByText("O valor da senhora")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByText("Escreva o número.")).toHaveAttribute("role", "alert");
    fireEvent.change(screen.getByRole("textbox", { name: "Número" }), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(acao.responderSobreAReceita).toHaveBeenCalledWith("frango", "rendimento_porcoes", "6"));
    fireEvent.click(corrigir);
    expect(screen.queryByRole("textbox", { name: "Número" })).not.toBeInTheDocument();
    rerender(<CorrigirValor receita={RECEITA} correcao={{ tipo: "peso", campo: "1 peito", pesoDe: null }} oQue="o peso do peito" />);
    fireEvent.click(screen.getByRole("button", { name: "corrigir o peso do peito" }));
    expect(screen.queryByRole("group", { name: "Esse peso é de" })).not.toBeInTheDocument();
  });

  it("a correção sai da forma da API: o preço, o peso, o número; o resto não tem corrigir", () => {
    const base: PerguntaDaReceita = { tipo: "ingrediente", assunto: "ingrediente", campo: "creme de leite", texto: "?", motivo: "", compras: [], opcoes: [], entrada: null, passos: [] };
    expect(correcaoDe(null)).toBeNull();
    expect(correcaoDe({ ...base, assunto: "preco_de_compra", compras: [{ ingrediente: "leite", quantidade_texto: "1 L" }] })).toEqual({ tipo: "preco", ingrediente: "leite" });
    expect(correcaoDe({ ...base, assunto: "preco_de_compra" })).toEqual({ tipo: "preco", ingrediente: "creme de leite" });
    expect(correcaoDe({ ...base, assunto: "medida", entrada: { tipo: "peso", unidade: "g" } })).toEqual({ tipo: "peso", campo: "creme de leite", pesoDe: null });
    expect(correcaoDe({ ...base, assunto: "rendimento", entrada: { tipo: "inteiro", unidade: "porções" } })).toMatchObject({ tipo: "numero" });
    expect(correcaoDe({ ...base, assunto: "modo_preparo", entrada: { tipo: "texto" } })).toBeNull();
  });
});
