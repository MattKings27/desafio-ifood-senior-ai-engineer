/**
 * O histórico: agrupado por dia, cada linha levando à coisa de que fala, a
 * busca e os filtros (o que, quem, o dia) na URL, o "Ver mais" pelo cursor, o
 * erro com "Tentar de novo" e os vazios.
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

import type { Atividade, PaginaDeAtividades } from "@/lib/api/atividades";
import { atividades } from "@/lib/api/atividades";
import { ErroDoMotor } from "@/lib/api/base";
import { lerFiltros } from "@/lib/filtros/url";
import { contrato } from "@/teste/fixturas";
import { irPara } from "@/teste/navegacao";
import { montar } from "@/teste/receitas";

import { ESQUEMA_DO_HISTORICO, chaveDoPedido, paraBusca, paraPedido } from "./filtros";
import { PAUSA_DA_BUSCA_MS, TelaDoHistorico } from "./TelaDoHistorico";
import { juntarGrupos } from "./useHistorico";

const PAGINA = contrato<PaginaDeAtividades>("atividades.json");

function pagina(extras: Partial<PaginaDeAtividades> = {}): PaginaDeAtividades {
  return { ...structuredClone(PAGINA), ...extras };
}

let listar: MockInstance<typeof atividades.listar>;

beforeEach(() => {
  irPara("/trilha");
  listar = vi.spyOn(atividades, "listar");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function tela(inicial = pagina(), chaveInicial = "") {
  return montar(<TelaDoHistorico inicial={inicial} chaveInicial={chaveInicial} />);
}

describe("a linha do tempo", () => {
  it("agrupa por dia, e cada linha é um link para a coisa de que fala", () => {
    tela();
    expect(screen.getByRole("heading", { level: 1, name: "Histórico" })).toBeInTheDocument();
    const [hoje, ontem] = PAGINA.grupos;
    const deHoje = screen.getByRole("region", { name: hoje?.rotulo });
    expect(within(deHoje).getAllByRole("listitem")).toHaveLength(hoje?.itens.length ?? 0);
    const [primeira] = hoje?.itens ?? [];
    const texto = primeira?.texto ?? "";
    expect(within(deHoje).getByRole("link", { name: (nome) => nome.includes(texto) })).toHaveAttribute("href", primeira?.link);
    expect(within(deHoje).getAllByText(/pela conversa/).length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: ontem?.rotulo })).toBeInTheDocument();
    expect(screen.getByText(PAGINA.texto)).toHaveAttribute("role", "status");
    expect(listar).not.toHaveBeenCalled();
  });

  it("uma atividade sem link não vira link, e categoria desconhecida tem o marcador neutro", () => {
    const [grupo] = PAGINA.grupos;
    const semLink: Atividade = { ...(grupo?.itens[0] as Atividade), id: "x", link: null, categoria: "outra", canal_texto: null, texto: "Algo sem lugar." };
    tela(pagina({ grupos: [{ dia: "2026-09-26", rotulo: "Hoje", itens: [semLink] }] }));
    expect(screen.getByText("Algo sem lugar.").closest("a")).toBeNull();
  });
});

describe("os filtros na URL", () => {
  it("o chip do que troca a URL e pede a página filtrada", async () => {
    const soCardapio = pagina({ total: 1, texto: "1 registro" });
    listar.mockResolvedValue(soCardapio);
    tela();
    fireEvent.click(screen.getByRole("radio", { name: "Cardápio" }));
    expect(window.location.search).toBe("?categoria=cardapio");
    await waitFor(() => expect(listar).toHaveBeenCalledWith({ categoria: "cardapio" }, expect.anything()));
    expect(await screen.findByText("1 registro")).toBeInTheDocument();
  });

  it("quem e o dia também vão para a URL, e Tirar os filtros limpa tudo", async () => {
    listar.mockResolvedValue(pagina());
    tela();
    fireEvent.click(screen.getByRole("radio", { name: "O agente" }));
    fireEvent.click(screen.getByRole("radio", { name: "Ontem" }));
    expect(new URLSearchParams(window.location.search).get("quem")).toBe("consultora");
    expect(new URLSearchParams(window.location.search).get("dia")).toBe("2026-09-25");
    await waitFor(() => expect(listar).toHaveBeenLastCalledWith({ quem: "consultora", dia: "2026-09-25" }, expect.anything()));
    fireEvent.click(screen.getByRole("button", { name: "Tirar os filtros" }));
    expect(window.location.search).toBe("");
  });

  it("a busca espera ela parar de digitar antes de ir à URL", async () => {
    vi.useFakeTimers();
    listar.mockResolvedValue(pagina());
    tela();
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar no histórico" }), { target: { value: "forno " } });
    expect(window.location.search).toBe("");
    act(() => vi.advanceTimersByTime(PAUSA_DA_BUSCA_MS));
    expect(window.location.search).toBe("?q=forno");
    vi.useRealTimers();
    await waitFor(() => expect(listar).toHaveBeenCalledWith({ q: "forno" }, expect.anything()));
  });

  it("a busca que muda por fora (o voltar do navegador) aparece no campo", () => {
    irPara("/trilha?q=milho");
    listar.mockResolvedValue(pagina());
    tela(pagina(), "?q=milho");
    expect(screen.getByRole("searchbox", { name: "Buscar no histórico" })).toHaveValue("milho");
    act(() => irPara("/trilha?q=forno"));
    expect(screen.getByRole("searchbox", { name: "Buscar no histórico" })).toHaveValue("forno");
  });

  it("sem dias com atividade, o filtro de dia some; com filtro e nada achado, diz para tirar o filtro", () => {
    irPara("/trilha?quem=tela");
    tela(pagina({ grupos: [], dias: [], total: 0, texto: "nada por aqui ainda" }), "?quem=tela");
    expect(screen.queryByRole("group", { name: "Dia" })).not.toBeInTheDocument();
    expect(screen.getByText("Nada com esses filtros")).toBeInTheDocument();
  });

  it("sem filtro e sem nada, explica o que vai aparecer", () => {
    tela(pagina({ grupos: [], total: 0, texto: "nada por aqui ainda", proximo_cursor: null }));
    expect(screen.getByText("Nada por aqui ainda")).toBeInTheDocument();
  });
});

describe("Ver mais e o erro", () => {
  it("Ver mais pede a página seguinte pelo cursor e junta o mesmo dia", async () => {
    const [, ontem] = PAGINA.grupos;
    const seguinte = pagina({
      grupos: [{ dia: ontem?.dia ?? "", rotulo: ontem?.rotulo ?? "", itens: [{ ...(ontem?.itens[0] as Atividade), id: "mais-1", texto: "Uma coisa de antes." }] }],
      proximo_cursor: null,
    });
    listar.mockResolvedValue(seguinte);
    tela();
    fireEvent.click(screen.getByRole("button", { name: "Ver mais" }));
    await waitFor(() => expect(listar).toHaveBeenCalledWith({ cursor: PAGINA.proximo_cursor }));
    expect(await screen.findByText("Uma coisa de antes.")).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: ontem?.rotulo })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Ver mais" })).not.toBeInTheDocument();
  });

  it("o erro de uma página aparece com Tentar de novo, que pede de novo", async () => {
    listar.mockRejectedValueOnce(new ErroDoMotor("O histórico não veio.", "rede"));
    listar.mockResolvedValue(pagina());
    tela();
    fireEvent.click(screen.getByRole("radio", { name: "Receitas" }));
    expect(await screen.findByText("Não consegui trazer o histórico")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(2));
  });

  it("o erro do Ver mais aparece sem apagar o que já veio", async () => {
    listar.mockRejectedValueOnce(new Error("rede caiu"));
    tela();
    fireEvent.click(screen.getByRole("button", { name: "Ver mais" }));
    expect(await screen.findByText("Não consegui trazer o histórico")).toBeInTheDocument();
    expect(screen.getByText(PAGINA.grupos[0]?.itens[0]?.texto ?? "")).toBeInTheDocument();
  });
});

describe("as peças puras", () => {
  it("os filtros viram o pedido, e dia mal escrito é ignorado", () => {
    const filtros = lerFiltros(paraBusca({ q: " forno ", categoria: "cozinha", quem: "senhora", dia: "ontem" }), ESQUEMA_DO_HISTORICO);
    expect(paraPedido(filtros)).toEqual({ q: "forno", categoria: "cozinha", quem: "senhora" });
    expect(chaveDoPedido({ categoria: "cozinha" })).toBe("?categoria=cozinha");
    expect(paraBusca({ categoria: ["a", "b"], vazio: undefined }).getAll("categoria")).toEqual(["a", "b"]);
  });

  it("juntar as páginas não mistura dias diferentes", () => {
    const [hoje, ontem] = PAGINA.grupos;
    const juntos = juntarGrupos([hoje as never], [ontem as never]);
    expect(juntos.map((grupo) => grupo.dia)).toEqual([hoje?.dia, ontem?.dia]);
  });
});

describe("acessibilidade", () => {
  it("a tela inteira não tem violação do axe", async () => {
    const { container } = tela();
    expect(await axe(container)).toHaveNoViolations();
  });
});
