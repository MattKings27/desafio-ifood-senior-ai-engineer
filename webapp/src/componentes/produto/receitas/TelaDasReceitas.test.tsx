/**
 * A grade de receitas: as abas com as contagens, a busca e os filtros na URL,
 * os vazios que dizem o que fazer, o erro com "Tentar de novo", e a lista que
 * o servidor manda de novo depois de uma escrita.
 *
 * A URL é a de verdade (o `history` do jsdom), com o `useSearchParams`
 * acompanhando como no Next; a API é trocada por espiões.
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
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

import { ErroDoMotor } from "@/lib/api/base";
import type { ListaDeReceitas } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";
import { irPara } from "@/teste/navegacao";
import { ARROZ, FRANGO, LISTA, PERGUNTA_DAS_BOCAS, PERGUNTA_DO_FORNO, adiado, item, lista, montar } from "@/teste/receitas";

import { TelaDasReceitas } from "./TelaDasReceitas";

let listar: MockInstance<typeof receitas.listar>;

beforeEach(() => {
  irPara("/receitas");
  listar = vi.spyOn(receitas, "listar");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function tela(inicial: ListaDeReceitas = lista(), chaveInicial = "?aba=pode_fazer") {
  return montar(<TelaDasReceitas inicial={inicial} chaveInicial={chaveInicial} />);
}

const aba = (nome: string) => screen.getByRole("tab", { name: new RegExp(`^${nome}`) });
const PENDENTE = item({
  slug: "pudim",
  nome: "Pudim de leite",
  selo: { codigo: "falta_resposta", texto: "Falta uma resposta da senhora" },
  pergunta: PERGUNTA_DAS_BOCAS,
});

describe("com nada para fazer ainda", () => {
  const ESPERANDO = { pode_fazer: 0, falta_resposta: 3, ranking: 0, nao_quer: 0 };

  const DO_FORNO = {
    pergunta: PERGUNTA_DO_FORNO,
    receitas: 1,
    liberadas: 1,
    sem_compra: 1,
    sem_compra_texto: "usa só o que a senhora tem",
    nomes: [PENDENTE.nome],
    slugs: [PENDENTE.slug],
    rota: PENDENTE.rota,
    texto: "libera 1 receita",
  };

  it("o painel traz a pergunta da cozinha das receitas que ela gosta de fazer, e nunca a de peso ou preço", () => {
    irPara("/receitas?aba=falta_resposta");
    tela(
      lista({
        aba: "falta_resposta",
        contagens: ESPERANDO,
        itens: [PENDENTE],
        perguntas_que_liberam: [...LISTA.perguntas_que_liberam, DO_FORNO],
      }),
      "?aba=falta_resposta",
    );
    const painel = screen.getByRole("region", { name: "Responda e eu libero mais receitas" });
    expect(within(painel).getAllByRole("listitem")).toHaveLength(1);
    expect(within(painel).getByText("Libera 1 receita")).toBeInTheDocument();
    expect(within(painel).getAllByText(PERGUNTA_DO_FORNO.texto).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Não entendi quanto vai|quanto pesa/i)).not.toBeInTheDocument();
  });

  it("o gosto vem antes da cozinha: sem receita que ela gosta, o painel não aparece", () => {
    irPara("/receitas?aba=falta_resposta");
    tela(
      lista({
        aba: "falta_resposta",
        contagens: ESPERANDO,
        itens: [{ ...PENDENTE, gosta: null }],
        perguntas_que_liberam: [DO_FORNO],
      }),
      "?aba=falta_resposta",
    );
    expect(screen.queryByRole("region", { name: "Responda e eu libero mais receitas" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: `A senhora gosta de fazer ${PENDENTE.nome}?` })).toBeInTheDocument();
  });

  it("com receita para fazer, o painel não aparece", () => {
    tela();
    expect(screen.queryByRole("region", { name: "Responda e eu libero mais receitas" })).not.toBeInTheDocument();
  });

  it("no alto de Falta uma resposta sua, quantas usam só o que ela tem e o que falta ela dizer", () => {
    const espera = {
      ...LISTA.esperando_resposta!,
      texto: "7 receitas usam só o que a senhora tem; falta só a senhora me dizer quanto tempo consegue ficar cozinhando de uma vez.",
    };
    irPara("/receitas?aba=falta_resposta");
    tela(lista({ aba: "falta_resposta", contagens: ESPERANDO, itens: [PENDENTE], esperando_resposta: espera }), "?aba=falta_resposta");
    expect(screen.getByText(espera.texto)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Gosto de fazer" })).toBeInTheDocument();
  });
});

describe("a grade", () => {
  it("mostra as abas com as contagens da API e os cards, sem pedir de novo", async () => {
    const { container } = tela();
    expect(aba("Dá para fazer")).toHaveAttribute("aria-selected", "true");
    expect(aba("Dá para fazer")).toHaveTextContent("2");
    expect(aba("Falta uma resposta sua")).toHaveTextContent("2");
    expect(aba("Ranking")).toHaveTextContent("2");
    const grade = screen.getByRole("list", { name: "Gosto de fazer" });
    const cards = within(grade).getAllByRole("article");
    expect(cards).toHaveLength(2);
    expect(within(cards[0] as HTMLElement).getByRole("link", { name: ARROZ.nome })).toHaveAttribute("href", ARROZ.rota);
    expect(within(cards[0] as HTMLElement).getByText("Receita da senhora · 40 min")).toBeInTheDocument();
    expect(within(cards[0] as HTMLElement).getByText("86,9")).toBeInTheDocument();
    // O "R$" fica preso ao número (espaço que não quebra), para o valor não se partir no card estreito.
    const selo = within(cards[1] as HTMLElement).getByText(/^Comprando R\$\s6,00, cabe nos R\$\s80,00$/);
    expect(selo.textContent).toBe("Comprando R$\u00a06,00, cabe nos R$\u00a080,00");
    expect(within(cards[1] as HTMLElement).getByText("falta comprar milho verde")).toBeInTheDocument();
    expect(screen.getByText(LISTA_TEXTO)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Não gosto de fazer/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Ainda não me disse se gosta/ })).not.toBeInTheDocument();
    expect(listar).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("trocar de aba pede a lista da aba, com esqueletos enquanto ela chega", async () => {
    const espera = adiado<ListaDeReceitas>();
    listar.mockReturnValue(espera.promessa);
    tela();
    fireEvent.click(aba("Falta uma resposta sua"));
    expect(window.location.search).toBe("?aba=falta_resposta");
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(1));
    expect(listar.mock.calls[0]?.[0]).toEqual({
      aba: "falta_resposta",
      q: undefined,
      usa: undefined,
      tempo_max: undefined,
      so_com_o_que_tenho: undefined,
      nota_min: undefined,
      ordem: undefined,
    });
    expect(aba("Falta uma resposta sua")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("list", { name: "Falta uma resposta sua" }).querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThan(0);
    await act(async () => espera.resolver(lista({ aba: "falta_resposta", itens: [PENDENTE] })));
    const pendentes = screen.getByRole("list", { name: "Gosto de fazer" });
    expect(within(pendentes).getByRole("link", { name: "Pudim de leite" })).toBeInTheDocument();
    // A pergunta inteira, e a linha curta que o modo minimalista mostra no lugar dela.
    expect(within(pendentes).getAllByText(PERGUNTA_DAS_BOCAS.texto)).toHaveLength(2);
    expect(within(pendentes).getByRole("textbox", { name: "Bocas" })).toBeInTheDocument();
  });

  it("as setas, Home e End trocam de aba e levam o foco", async () => {
    listar.mockResolvedValue(lista());
    tela();
    const primeira = aba("Dá para fazer");
    primeira.focus();
    fireEvent.keyDown(primeira, { key: "ArrowRight" });
    expect(aba("Falta uma resposta sua")).toHaveFocus();
    expect(window.location.search).toBe("?aba=falta_resposta");
    fireEvent.keyDown(aba("Falta uma resposta sua"), { key: "End" });
    expect(aba("Ranking")).toHaveFocus();
    fireEvent.keyDown(aba("Ranking"), { key: "ArrowDown" });
    expect(aba("Dá para fazer")).toHaveFocus();
    fireEvent.keyDown(aba("Dá para fazer"), { key: "ArrowLeft" });
    expect(aba("Ranking")).toHaveFocus();
    fireEvent.keyDown(aba("Ranking"), { key: "ArrowUp" });
    fireEvent.keyDown(aba("Falta uma resposta sua"), { key: "Home" });
    expect(aba("Dá para fazer")).toHaveFocus();
    fireEvent.keyDown(aba("Dá para fazer"), { key: "a" });
    expect(window.location.search).toBe("");
    await waitFor(() => expect(listar).toHaveBeenCalled());
  });

  it("a busca vai para a URL depois da pausa, e o chip dela tira a busca", async () => {
    listar.mockResolvedValue(lista({ itens: [ARROZ], contagens: { pode_fazer: 1, falta_resposta: 0, ranking: 1, nao_quer: 0 } }));
    tela();
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar receitas" }), { target: { value: " frango " } });
    expect(window.location.search).toBe("");
    await waitFor(() => expect(window.location.search).toBe("?q=frango"));
    await waitFor(() => expect(listar).toHaveBeenLastCalledWith(expect.objectContaining({ q: "frango" }), expect.anything()));
    expect(await screen.findByText("1 encontrada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Busca: frango: tirar este filtro" }));
    expect(window.location.search).toBe("");
    expect(screen.getByRole("searchbox", { name: "Buscar receitas" })).toHaveValue("");
  });

  it("a folha de filtros: tempo, só com o que tem, pontuação, e limpar", async () => {
    listar.mockResolvedValue(lista());
    tela();
    fireEvent.click(screen.getByRole("button", { name: "Filtros" }));
    const folha = screen.getByRole("dialog", { name: "Filtros" });
    fireEvent.click(within(folha).getByText("Até 30 min"));
    expect(new URLSearchParams(window.location.search).get("tempo_max")).toBe("30");
    fireEvent.click(within(folha).getByText("Só com o que a senhora tem"));
    expect(new URLSearchParams(window.location.search).get("so_com_o_que_tenho")).toBe("true");
    fireEvent.click(within(folha).getByText("80 ou mais"));
    expect(new URLSearchParams(window.location.search).get("nota_min")).toBe("80");
    const chips = screen.getByRole("list", { name: "Filtros ativos" });
    expect(within(chips).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Até 30 min",
      "Só com o que tenho",
      "Pontuação 80 ou mais",
    ]);
    expect(screen.getByRole("button", { name: /^Filtros 3/ })).toBeInTheDocument();
    fireEvent.click(within(folha).getByText("Qualquer tempo"));
    expect(window.location.search).not.toContain("tempo_max");
    fireEvent.click(within(folha).getByText("Só com o que a senhora tem"));
    expect(window.location.search).not.toContain("so_com_o_que_tenho");
    fireEvent.click(within(folha).getByText("Qualquer pontuação"));
    fireEvent.click(within(folha).getByText("90 ou mais"));
    fireEvent.click(within(folha).getByText("Mais rápida"));
    expect(new URLSearchParams(window.location.search).get("ordem")).toBe("tempo");
    expect(screen.getByRole("combobox", { name: "Ordenar por" })).toHaveValue("tempo");
    fireEvent.click(within(folha).getByText("Aproveita mais a despensa"));
    expect(window.location.search).not.toContain("ordem");
    fireEvent.click(within(folha).getByRole("button", { name: "Limpar filtros" }));
    expect(window.location.search).toBe("");
    await waitFor(() => expect(listar).toHaveBeenCalled());
    fireEvent.click(within(folha).getByRole("button", { name: "Ver 2 receitas" }));
    expect(folha).not.toHaveAttribute("open");
  });

  it("a ordem: a escolhida vai para a URL; a padrão da aba sai dela", () => {
    listar.mockResolvedValue(lista());
    tela();
    const ordem = screen.getByRole("combobox", { name: "Ordenar por" });
    expect(ordem).toHaveValue("aproveitamento");
    fireEvent.change(ordem, { target: { value: "tempo" } });
    expect(window.location.search).toBe("?ordem=tempo");
    fireEvent.change(ordem, { target: { value: "aproveitamento" } });
    expect(window.location.search).toBe("");
  });

  it("o filtro de um item da despensa vem da URL e vira chip; com dois ou mais, Limpar filtros", async () => {
    irPara("/receitas?usa=peito-de-frango&tempo_max=50");
    listar.mockResolvedValue(lista());
    tela(lista(), "?aba=pode_fazer&usa=peito-de-frango&tempo_max=50");
    expect(screen.getByRole("button", { name: "Usa peito de frango: tirar este filtro" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Até 50 min: tirar este filtro" })).toBeInTheDocument();
    expect(screen.getByText("2 encontradas")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Usa peito de frango: tirar este filtro" }));
    expect(window.location.search).toBe("?tempo_max=50");
    fireEvent.click(screen.getByRole("button", { name: "Até 50 min: tirar este filtro" }));
    await waitFor(() => expect(listar).toHaveBeenCalled());
  });

  it("no ranking inteiro, a posição de cada uma aparece na foto; com busca, não", () => {
    irPara("/receitas?aba=ranking");
    tela(lista({ aba: "ranking", itens: [FRANGO, ARROZ] }), "?aba=ranking");
    const grade = screen.getByRole("list", { name: "Gosto de fazer" });
    expect(within(grade).getAllByText(/lugar no ranking/)).toHaveLength(2);
    expect(within(grade).getByText("1º")).toBeInTheDocument();
  });

  it("sem avaliação o card não tem pontuação; o pendente sem pergunta mostra o que falta", async () => {
    listar.mockResolvedValue(lista({ aba: "falta_resposta", itens: [{ ...PENDENTE, pergunta: null, falta_texto: "falta comprar alho" }] }));
    tela(lista({ itens: [item({ pontuacao: null })] }));
    expect(screen.queryByText(/de pontuação/)).not.toBeInTheDocument();
    fireEvent.click(aba("Falta uma resposta sua"));
    const texto = await screen.findByText("falta comprar alho");
    const pendentes = screen.getByRole("list", { name: "Gosto de fazer" });
    expect(pendentes).toContainElement(texto);
    expect(within(pendentes).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("no ranking com busca, a posição não aparece (não é o ranking inteiro)", () => {
    irPara("/receitas?aba=ranking&q=frango");
    tela(lista({ aba: "ranking", itens: [FRANGO] }), "?aba=ranking&q=frango");
    expect(screen.queryByText(/lugar no ranking/)).not.toBeInTheDocument();
  });
});

const LISTA_TEXTO = "Trouxe 2 receitas da internet que usam a despensa da senhora.";

describe("os vazios dizem o que fazer", () => {
  const vazia = (extras: Partial<ListaDeReceitas> = {}) =>
    lista({ itens: [], contagens: { pode_fazer: 0, falta_resposta: 0, ranking: 0, nao_quer: 0 }, ...extras });

  // O catálogo vazio pede uma procura sozinha ao abrir; aqui a descoberta está desligada, como no CI.
  let descobrir: MockInstance<typeof receitas.descobrir>;
  beforeEach(() => {
    descobrir = vi
      .spyOn(receitas, "descobrir")
      .mockRejectedValue(new ErroDoMotor("Desligada aqui.", "regra", undefined, "HTTP 501", 501));
  });

  it("sem receita que dá, mas com respostas esperando: diz que ainda não confirmou, e leva à aba delas", () => {
    listar.mockResolvedValue(vazia({ aba: "falta_resposta" }));
    tela(vazia({ contagens: { pode_fazer: 0, falta_resposta: 2, ranking: 0, nao_quer: 0 } }));
    expect(screen.getByText("Nenhuma receita confirmada ainda")).toBeInTheDocument();
    expect(screen.queryByText("Ainda não há receita que a senhora consiga fazer")).not.toBeInTheDocument();
    expect(screen.getByText(LISTA.esperando_resposta!.texto)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ver o que falta responder" }));
    expect(window.location.search).toBe("?aba=falta_resposta");
  });

  it("sem nada esperando: procurar receitas", async () => {
    tela(vazia());
    expect(descobrir).toHaveBeenCalledTimes(1);
    descobrir.mockRejectedValue(new ErroDoMotor("fora", "rede"));
    fireEvent.click(screen.getByRole("button", { name: "Procurar receitas" }));
    await waitFor(() => expect(descobrir).toHaveBeenCalledTimes(2));
  });

  it("com filtros: nenhuma com esses filtros, e limpar", async () => {
    irPara("/receitas?q=xyz");
    listar.mockResolvedValue(vazia());
    tela(vazia(), "?aba=pode_fazer&q=xyz");
    expect(screen.getByText("Nenhuma receita com esses filtros")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma encontrada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(window.location.search).toBe("");
    await waitFor(() => expect(listar).toHaveBeenCalled());
  });

  it("nada esperando resposta, e nada avaliado", () => {
    irPara("/receitas?aba=falta_resposta");
    const { unmount } = tela(vazia({ aba: "falta_resposta" }), "?aba=falta_resposta");
    expect(screen.getByText("Nenhuma receita esperando a senhora")).toBeInTheDocument();
    unmount();
    irPara("/receitas?aba=ranking");
    tela(vazia({ aba: "ranking" }), "?aba=ranking");
    expect(screen.getByText("A senhora ainda não avaliou nenhuma receita")).toBeInTheDocument();
  });
});

describe("a lista que chega de novo", () => {
  it("o erro ao pedir a lista vira o problema, e Tentar de novo pede outra vez", async () => {
    listar.mockRejectedValueOnce(new ErroDoMotor("Não consegui falar com o sistema agora.", "rede"));
    tela();
    fireEvent.click(aba("Ranking"));
    expect(await screen.findByText("Não consegui falar com o sistema")).toBeInTheDocument();
    listar.mockResolvedValueOnce(lista({ aba: "ranking", itens: [FRANGO] }));
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByRole("link", { name: FRANGO.nome })).toBeInTheDocument();
    expect(listar).toHaveBeenCalledTimes(2);
  });

  it("a recusa com pergunta mostra a pergunta que destrava", async () => {
    listar.mockRejectedValueOnce(new ErroDoMotor("Falta um dado.", "dado", "Quanto pesa a embalagem?"));
    tela();
    fireEvent.click(aba("Ranking"));
    expect(await screen.findByText("Quanto pesa a embalagem?")).toBeInTheDocument();
  });

  it("o pedido cancelado que falha depois não vira erro na tela", async () => {
    const primeira = adiado<ListaDeReceitas>();
    listar.mockReturnValueOnce(primeira.promessa).mockResolvedValueOnce(lista({ aba: "ranking", itens: [FRANGO] }));
    tela();
    fireEvent.click(aba("Falta uma resposta sua"));
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(1));
    fireEvent.click(aba("Ranking"));
    await act(async () => primeira.rejeitar(new DOMException("cancelado", "AbortError")));
    expect(await screen.findByRole("link", { name: FRANGO.nome })).toBeInTheDocument();
    expect(screen.queryByText("Não consegui falar com o sistema")).not.toBeInTheDocument();
  });

  it("falha que não veio da API também vira o problema de caminho", async () => {
    listar.mockRejectedValueOnce(new TypeError("fetch failed"));
    tela();
    fireEvent.click(aba("Ranking"));
    expect(await screen.findByText("Não consegui falar com o sistema")).toBeInTheDocument();
  });

  it("o pedido que ficou para trás é cancelado e não troca a lista", async () => {
    const primeira = adiado<ListaDeReceitas>();
    listar.mockReturnValueOnce(primeira.promessa).mockResolvedValueOnce(lista({ aba: "ranking", itens: [FRANGO] }));
    tela();
    fireEvent.click(aba("Falta uma resposta sua"));
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(1));
    const sinal = (listar.mock.calls[0]?.[1] as RequestInit).signal as AbortSignal;
    fireEvent.click(aba("Ranking"));
    await waitFor(() => expect(sinal.aborted).toBe(true));
    await act(async () => primeira.resolver(lista({ aba: "falta_resposta", itens: [PENDENTE] })));
    expect(await screen.findByRole("link", { name: FRANGO.nome })).toBeInTheDocument();
    expect(screen.queryByText("Pudim de leite")).not.toBeInTheDocument();
  });

  it("a lista que o servidor refaz vale se for do pedido da tela; de outro pedido, não", () => {
    const { refazer } = tela();
    const nova = lista({ itens: [FRANGO], contagens: { pode_fazer: 1, falta_resposta: 2, ranking: 1, nao_quer: 0 } });
    refazer(<TelaDasReceitas inicial={nova} chaveInicial="?aba=pode_fazer" />);
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(aba("Falta uma resposta sua")).toHaveTextContent("2");
    refazer(<TelaDasReceitas inicial={lista()} chaveInicial="?aba=ranking" />);
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });
});
