/**
 * O gosto dela na grade: as três seções de cada aba ("Gosto de fazer", "Ainda
 * não me disse se gosta" e, fechada no fim, "Não gosto de fazer"), a pergunta
 * do gosto no card antes de qualquer pergunta da cozinha, a receita que muda de
 * seção na hora com o "Desfazer" no aviso, o "Mudei de ideia", e a pergunta
 * que não é dela (peso, preço, a linha, o item parecido) que nunca aparece.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

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
import type { Resultado } from "@/lib/acoes/base";
import { ErroDoMotor } from "@/lib/api/base";
import type { ItemDaGrade, ListaDeReceitas, RespostaDaAvaliacao } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";
import { irPara } from "@/teste/navegacao";
import {
  ARROZ,
  FRANGO,
  PERGUNTAS_QUE_NAO_SAO_DELA,
  PERGUNTA_DAS_BOCAS,
  TEXTOS_QUE_NUNCA_APARECEM,
  adiado,
  deuCerto,
  deuErrado,
  item,
  lista,
  montar,
} from "@/teste/receitas";

import { PerguntaDoGosto } from "./GostoDaGrade";
import { ficaNaAba, pratoNaFrase, receitasNaSecao, separarPorGosto, textoDoGosto } from "./gosto";
import { TelaDasReceitas } from "./TelaDasReceitas";

const acao = vi.mocked(acoes);
let listar: MockInstance<typeof receitas.listar>;

beforeEach(() => {
  irPara("/receitas");
  listar = vi.spyOn(receitas, "listar");
});

afterEach(() => {
  vi.resetAllMocks();
  vi.restoreAllMocks();
});

const NOVA = item({ slug: "bolo-de-fuba", nome: "Bolo de fubá", gosta: null, pontuacao: null, rota: "/receitas/bolo-de-fuba" });
const RECUSADA = { ...FRANGO, gosta: false };
const RECUSADA_PENDENTE = item({
  slug: "pudim",
  nome: "Pudim de leite",
  gosta: false,
  selo: { codigo: "falta_resposta", texto: "Falta uma resposta da senhora" },
  rota: "/receitas/pudim",
});
const CONTAGENS = { pode_fazer: 2, falta_resposta: 1, ranking: 1, nao_quer: 2 };

function naoQuer(itens: ItemDaGrade[] = [RECUSADA, RECUSADA_PENDENTE]): ListaDeReceitas {
  return lista({ aba: "nao_quer", contagens: CONTAGENS, itens });
}

function tela(inicial: ListaDeReceitas = lista({ contagens: CONTAGENS, itens: [ARROZ, NOVA] }), recusadas = naoQuer(), chave = "?aba=pode_fazer") {
  return montar(
    <TelaDasReceitas
      inicial={inicial}
      chaveInicial={chave}
      naoQuerInicial={recusadas}
      chaveDasQueNaoQuerInicial="?aba=nao_quer"
    />,
  );
}

function resposta(slug: string, nome: string, gosta: boolean | null): Resultado<RespostaDaAvaliacao> {
  return deuCerto({
    slug,
    nome,
    avaliacao: { gosta, estrelas: { sabor: null, facilidade: null, tempo: null, entrega: null, apelo: null }, notas: "", pontuacao: null },
    posicao_no_ranking: null,
    atualizado_texto: "hoje, 14:30",
    texto: "Anotei.",
  });
}

const secao = (nome: string) => screen.getByRole("list", { name: nome });
const naoGosto = () => screen.getByRole("button", { name: /^Não gosto de fazer/ });

describe("as seções de cada aba", () => {
  it("Gosto de fazer, Ainda não me disse se gosta, e Não gosto de fazer fechada no fim, cada uma com a contagem", async () => {
    const { container } = tela();
    const titulos = screen.getAllByRole("heading", { level: 3 }).map((titulo) => titulo.textContent);
    expect(titulos).toEqual([
      "Gosto de fazer1, 1 receita",
      "Ainda não me disse se gosta1, 1 receita",
      "Não gosto de fazer1, 1 receita",
    ]);
    expect(within(secao("Gosto de fazer")).getByRole("link", { name: ARROZ.nome })).toBeInTheDocument();
    expect(within(secao("Ainda não me disse se gosta")).getByRole("link", { name: NOVA.nome })).toBeInTheDocument();
    // Fechada: só a contagem; o pudim, que espera uma resposta, fica na seção da aba dele.
    expect(naoGosto()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: RECUSADA.nome })).not.toBeInTheDocument();
    fireEvent.click(naoGosto());
    expect(naoGosto()).toHaveAttribute("aria-expanded", "true");
    const recusadas = secao("Não gosto de fazer");
    expect(within(recusadas).getByRole("link", { name: RECUSADA.nome })).toBeInTheDocument();
    expect(within(recusadas).queryByRole("link", { name: RECUSADA_PENDENTE.nome })).not.toBeInTheDocument();
    expect(within(recusadas).getByRole("button", { name: `Mudei de ideia: gosto de fazer ${RECUSADA.nome}` })).toBeInTheDocument();
    expect(listar).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sem nenhuma de que ela gosta, a seção dela diz o que fazer; e sem nenhuma recusada, a fechada não aparece", () => {
    tela(lista({ contagens: CONTAGENS, itens: [NOVA] }), naoQuer([]));
    expect(screen.getByText(/Nenhuma ainda\. Diga em cada receita logo abaixo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Não gosto de fazer/ })).not.toBeInTheDocument();
  });

  it("no ranking, a que ela não quer vai para Não gosto de fazer", () => {
    irPara("/receitas?aba=ranking");
    tela(lista({ aba: "ranking", contagens: CONTAGENS, itens: [ARROZ, RECUSADA] }), naoQuer(), "?aba=ranking");
    expect(within(secao("Gosto de fazer")).getByText("1º")).toBeInTheDocument();
    expect(within(naoGosto()).getByText("1")).toBeInTheDocument();
  });

  it("a lista das que ela não quer que não chega vira o problema na seção, com Tentar de novo", async () => {
    irPara("/receitas?q=frango");
    listar.mockImplementation(async (pedido) => {
      if (pedido?.aba === "nao_quer") throw new ErroDoMotor("Não consegui falar com o sistema agora.", "rede");
      return lista({ contagens: CONTAGENS, itens: [ARROZ] });
    });
    tela(lista({ contagens: CONTAGENS, itens: [ARROZ] }), naoQuer(), "?aba=pode_fazer");
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(2));
    fireEvent.click(await screen.findByRole("button", { name: /^Não gosto de fazer/ }));
    expect(await screen.findByText("Não consegui falar com o sistema")).toBeInTheDocument();
    listar.mockResolvedValue(naoQuer([]));
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("Nenhuma, com esses filtros.")).toBeInTheDocument();
  });
});

describe("a pergunta do gosto no card", () => {
  it("Gosto de fazer muda a receita de seção na hora, e o aviso traz o Desfazer", async () => {
    const espera = adiado<Resultado<RespostaDaAvaliacao>>();
    acao.avaliarReceita.mockReturnValueOnce(espera.promessa).mockResolvedValueOnce(resposta(NOVA.slug, NOVA.nome, null));
    const { refazer } = tela();
    const pergunta = screen.getByRole("group", { name: `A senhora gosta de fazer ${NOVA.nome}?` });
    expect(screen.getByText("A senhora gosta de fazer este prato?")).toBeInTheDocument();
    fireEvent.click(within(pergunta).getByRole("button", { name: "Gosto de fazer" }));
    // Antes de a API responder, ela já está em "Gosto de fazer".
    await waitFor(() => expect(within(secao("Gosto de fazer")).getByRole("link", { name: NOVA.nome })).toBeInTheDocument());
    expect(screen.queryByRole("list", { name: "Ainda não me disse se gosta" })).not.toBeInTheDocument();
    expect(acao.avaliarReceita).toHaveBeenCalledWith(NOVA.slug, { gosta: true });
    await act(async () => espera.resolver(resposta(NOVA.slug, NOVA.nome, true)));
    refazer(
      <TelaDasReceitas
        inicial={lista({ contagens: CONTAGENS, itens: [ARROZ, { ...NOVA, gosta: true }] })}
        chaveInicial="?aba=pode_fazer"
        naoQuerInicial={naoQuer()}
        chaveDasQueNaoQuerInicial="?aba=nao_quer"
      />,
    );
    expect(await screen.findByText("Anotei que a senhora gosta de fazer bolo de fubá. Ela foi para Gosto de fazer.")).toBeInTheDocument();
    expect(within(secao("Gosto de fazer")).getByRole("link", { name: NOVA.nome })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    await waitFor(() => expect(acao.avaliarReceita).toHaveBeenLastCalledWith(NOVA.slug, { gosta: null }));
    expect(await screen.findByText("Desfiz. Bolo de fubá voltou para Ainda não me disse se gosta.")).toBeInTheDocument();
  });

  it("Não gosto leva a receita para Não gosto de fazer, fechada, e a contagem sobe", async () => {
    const espera = adiado<Resultado<RespostaDaAvaliacao>>();
    acao.avaliarReceita.mockReturnValueOnce(espera.promessa);
    tela();
    fireEvent.click(screen.getByRole("button", { name: "Não gosto" }));
    await waitFor(() => expect(within(naoGosto()).getByText("2")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: NOVA.nome })).not.toBeInTheDocument();
    expect(acao.avaliarReceita).toHaveBeenCalledWith(NOVA.slug, { gosta: false });
    await act(async () => espera.resolver(resposta(NOVA.slug, NOVA.nome, false)));
    expect(await screen.findByText("Anotei que a senhora não gosta de fazer bolo de fubá. Ela foi para Não gosto de fazer.")).toBeInTheDocument();
  });

  it("Mudei de ideia volta a receita para Gosto de fazer, e o Desfazer devolve", async () => {
    const espera = adiado<Resultado<RespostaDaAvaliacao>>();
    acao.avaliarReceita.mockReturnValueOnce(espera.promessa).mockResolvedValueOnce(resposta(RECUSADA.slug, RECUSADA.nome, false));
    tela();
    fireEvent.click(naoGosto());
    fireEvent.click(screen.getByRole("button", { name: `Mudei de ideia: gosto de fazer ${RECUSADA.nome}` }));
    await waitFor(() => expect(within(secao("Gosto de fazer")).getByRole("link", { name: RECUSADA.nome })).toBeInTheDocument());
    expect(acao.avaliarReceita).toHaveBeenCalledWith(RECUSADA.slug, { gosta: true });
    await act(async () => espera.resolver(resposta(RECUSADA.slug, RECUSADA.nome, true)));
    fireEvent.click(await screen.findByRole("button", { name: "Desfazer" }));
    await waitFor(() => expect(acao.avaliarReceita).toHaveBeenLastCalledWith(RECUSADA.slug, { gosta: false }));
  });

  it("a recusa da API devolve a receita para onde estava e o aviso diz por quê; a falha de caminho também", async () => {
    acao.avaliarReceita.mockResolvedValueOnce(deuErrado("Não consegui salvar agora.")).mockRejectedValueOnce(new Error("fora"));
    tela();
    fireEvent.click(screen.getByRole("button", { name: "Gosto de fazer" }));
    expect(await screen.findByText("Não consegui salvar agora.")).toBeInTheDocument();
    await waitFor(() => expect(within(secao("Ainda não me disse se gosta")).getByRole("link", { name: NOVA.nome })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Gosto de fazer" }));
    expect(await screen.findByText(/Não consegui falar com o sistema/)).toBeInTheDocument();
  });

  it("fora da grade, a pergunta aparece e o toque não quebra nada", () => {
    render(<PerguntaDoGosto item={NOVA} />);
    fireEvent.click(screen.getByRole("button", { name: "Gosto de fazer" }));
    expect(screen.getByText("A senhora gosta de fazer este prato?")).toBeInTheDocument();
  });
});

describe("em Falta uma resposta sua, uma pergunta de cada vez", () => {
  const PENDENTE = item({
    slug: "torta",
    nome: "Torta de frango",
    selo: { codigo: "falta_resposta", texto: "Falta uma resposta da senhora" },
    pergunta: PERGUNTA_DAS_BOCAS,
    rota: "/receitas/torta",
  });

  it("primeiro o gosto; com o gosto dito, a pergunta da cozinha", () => {
    irPara("/receitas?aba=falta_resposta");
    tela(
      lista({ aba: "falta_resposta", contagens: CONTAGENS, itens: [{ ...PENDENTE, gosta: null }, { ...PENDENTE, slug: "empadao", nome: "Empadão" }] }),
      naoQuer([]),
      "?aba=falta_resposta",
    );
    const aindaNao = secao("Ainda não me disse se gosta");
    expect(within(aindaNao).getByRole("group", { name: `A senhora gosta de fazer ${PENDENTE.nome}?` })).toBeInTheDocument();
    expect(within(aindaNao).queryByRole("textbox", { name: "Bocas" })).not.toBeInTheDocument();
    const gosto = secao("Gosto de fazer");
    expect(within(gosto).getByRole("textbox", { name: "Bocas" })).toBeInTheDocument();
    expect(screen.getByText("Falta só a resposta da cozinha, uma pergunta de cada vez.")).toBeInTheDocument();
  });

  it("pergunta de peso, preço, a linha e o item parecido nunca aparecem: o card diz o que falta", () => {
    irPara("/receitas?aba=falta_resposta");
    const itens = PERGUNTAS_QUE_NAO_SAO_DELA.map((pergunta, indice) =>
      item({ ...PENDENTE, slug: `r${indice}`, nome: `Receita ${indice}`, pergunta, falta_texto: "falta comprar creme de leite" }),
    );
    const { container } = tela(lista({ aba: "falta_resposta", contagens: CONTAGENS, itens }), naoQuer([]), "?aba=falta_resposta");
    for (const texto of TEXTOS_QUE_NUNCA_APARECEM) expect(container.textContent).not.toMatch(texto);
    expect(within(secao("Gosto de fazer")).getAllByText("falta comprar creme de leite")).toHaveLength(itens.length);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("as contas puras do gosto", () => {
  it("cada receita que ela não quer fica na aba em que estaria", () => {
    const comprando = { ...FRANGO, gosta: false };
    const pendente = { ...RECUSADA_PENDENTE };
    expect(ficaNaAba("pode_fazer", comprando)).toBe(true);
    expect(ficaNaAba("falta_resposta", comprando)).toBe(false);
    expect(ficaNaAba("falta_resposta", pendente)).toBe(true);
    expect(ficaNaAba("ranking", comprando)).toBe(true);
    expect(ficaNaAba("ranking", { ...comprando, pontuacao: null })).toBe(false);
  });

  it("o gosto que ela acabou de dizer vale mais que o da API, e a receita não repete", () => {
    const secoes = separarPorGosto("pode_fazer", [ARROZ, NOVA], [RECUSADA, { ...ARROZ, gosta: false }], { [NOVA.slug]: false, [ARROZ.slug]: null });
    expect(secoes.gosta).toEqual([]);
    expect(secoes.ainda_nao.map((i) => [i.slug, i.gosta])).toEqual([[ARROZ.slug, null]]);
    expect(secoes.nao_gosta.map((i) => [i.slug, i.gosta])).toEqual([
      [NOVA.slug, false],
      [RECUSADA.slug, false],
    ]);
  });

  it("o card que vem sem o gosto é de quem ainda não disse", () => {
    const semGosto = { ...NOVA } as Partial<ItemDaGrade>;
    delete semGosto.gosta;
    const secoes = separarPorGosto("pode_fazer", [semGosto as ItemDaGrade], [], {});
    expect(secoes.ainda_nao.map((i) => [i.slug, i.gosta])).toEqual([[NOVA.slug, null]]);
  });

  it("os textos: a contagem, o prato no meio da frase e o aviso de cada resposta", () => {
    expect(receitasNaSecao(1)).toBe("1 receita");
    expect(receitasNaSecao(3)).toBe("3 receitas");
    expect(pratoNaFrase(" Bolo de fubá ")).toBe("bolo de fubá");
    expect(pratoNaFrase("PF de frango")).toBe("PF de frango");
    expect(textoDoGosto("Bolo", true)).toBe("Anotei que a senhora gosta de fazer bolo. Ela foi para Gosto de fazer.");
    expect(textoDoGosto("Bolo", false)).toBe("Anotei que a senhora não gosta de fazer bolo. Ela foi para Não gosto de fazer.");
    expect(textoDoGosto("Bolo", null)).toBe("Desfiz. Bolo voltou para Ainda não me disse se gosta.");
  });
});
