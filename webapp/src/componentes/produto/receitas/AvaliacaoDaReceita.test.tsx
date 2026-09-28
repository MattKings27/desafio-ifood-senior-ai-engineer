/**
 * A avaliação dela: gosta de fazer, as estrelas de cada categoria (marcadas
 * na hora, e de volta se a API recusar), a pontuação com "Como calculamos", e
 * as notas que se salvam sozinhas uma pausa depois da última tecla.
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({ avaliarReceita: vi.fn(), anotarReceita: vi.fn() }));

import * as acoes from "@/lib/acoes/receitas";
import type { AvaliacaoDaReceita as Avaliacao, RespostaDaAvaliacao, RespostaDasNotas } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { adiado, deuCerto, deuErrado, montar } from "@/teste/receitas";

import { AvaliacaoDaReceita, PAUSA_DAS_NOTAS_MS } from "./AvaliacaoDaReceita";

const acao = vi.mocked(acoes);
const RESPOSTA = contrato<{ resposta: RespostaDaAvaliacao }>("avaliacao-escrita.json").resposta;
const NOTAS = contrato<{ resposta: RespostaDasNotas }>("notas-escrita.json").resposta;
const SEM_NADA: Avaliacao = {
  gosta: null,
  estrelas: { sabor: null, facilidade: null, tempo: null, entrega: null, apelo: null },
  notas: "",
  pontuacao: null,
};

afterEach(() => {
  vi.resetAllMocks();
  vi.useRealTimers();
});

function avaliacao(inicial: Avaliacao = RESPOSTA.avaliacao, posicao: number | null = 1) {
  return montar(<AvaliacaoDaReceita slug={RESPOSTA.slug} nome={RESPOSTA.nome} avaliacao={inicial} posicao={posicao} />);
}

describe("gosta de fazer e as estrelas", () => {
  it("mostra o que ela já deu, a pontuação, a posição e a conta", async () => {
    const { container } = avaliacao();
    expect(screen.getByRole("group", { name: "Gosta de fazer?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sim" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("group", { name: "Sabor" })).getByRole("radio", { name: "4 estrelas" })).toBeChecked();
    expect(within(screen.getByRole("group", { name: "Apelo de venda" })).getByRole("radio", { name: "4 estrelas" })).not.toBeChecked();
    expect(screen.getByText("88,8")).toBeInTheDocument();
    expect(screen.getByText("1º lugar no ranking")).toBeInTheDocument();
    const conta = screen.getByText(RESPOSTA.avaliacao.pontuacao?.derivacao ?? "");
    expect(conta.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Como calculamos"));
    expect(conta.closest("details")).toHaveAttribute("open");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sem estrela, diz como entrar no ranking", () => {
    avaliacao(SEM_NADA, null);
    expect(screen.getByText(/Dê as estrelas que a pontuação aparece aqui/)).toBeInTheDocument();
    expect(screen.queryByText(/lugar no ranking/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sim" })).toHaveAttribute("aria-pressed", "false");
  });

  it("o toque marca na hora, manda só o que mudou, e a frase da API aparece", async () => {
    acao.avaliarReceita.mockResolvedValue(deuCerto(RESPOSTA));
    avaliacao(SEM_NADA, null);
    fireEvent.click(screen.getByRole("button", { name: "Não" }));
    await waitFor(() => expect(acao.avaliarReceita).toHaveBeenCalledWith(RESPOSTA.slug, { gosta: false }));
    expect(await screen.findByText(RESPOSTA.texto)).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("group", { name: "Sabor" })).getByRole("radio", { name: "5 estrelas" }));
    await waitFor(() => expect(acao.avaliarReceita).toHaveBeenLastCalledWith(RESPOSTA.slug, { estrelas: { sabor: 5 } }));
  });

  it("Tirar nota manda nulo, que apaga a estrela", async () => {
    acao.avaliarReceita.mockResolvedValue(deuCerto(RESPOSTA));
    avaliacao();
    fireEvent.click(within(screen.getByRole("group", { name: "Sabor" })).getByRole("button", { name: "Tirar nota" }));
    await waitFor(() => expect(acao.avaliarReceita).toHaveBeenCalledWith(RESPOSTA.slug, { estrelas: { sabor: null } }));
  });

  it("enquanto vai, a estrela aparece marcada; se a API recusar, volta e diz por quê", async () => {
    const espera = adiado<Awaited<ReturnType<typeof acao.avaliarReceita>>>();
    acao.avaliarReceita.mockReturnValue(espera.promessa);
    avaliacao(SEM_NADA, null);
    const sabor = screen.getByRole("group", { name: "Sabor" });
    fireEvent.click(within(sabor).getByRole("radio", { name: "3 estrelas" }));
    await waitFor(() => expect(within(sabor).getByRole("radio", { name: "3 estrelas" })).toBeChecked());
    await act(async () => espera.resolver(deuErrado("A estrela vai de 1 a 5.")));
    await waitFor(() => expect(within(sabor).getByRole("radio", { name: "3 estrelas" })).not.toBeChecked());
    expect(screen.getByText("A estrela vai de 1 a 5.")).toHaveAttribute("role", "alert");
  });
});

describe("as notas", () => {
  it("se salvam sozinhas depois da pausa, com o Salvando e o Salvo com a hora da API", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const espera = adiado<Awaited<ReturnType<typeof acao.anotarReceita>>>();
    acao.anotarReceita.mockReturnValue(espera.promessa);
    avaliacao(SEM_NADA, null);
    const campo = screen.getByRole("textbox", { name: "Notas da senhora" });
    fireEvent.change(campo, { target: { value: "Servir com arroz branco." } });
    expect(acao.anotarReceita).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PAUSA_DAS_NOTAS_MS + 10);
    });
    expect(acao.anotarReceita).toHaveBeenCalledWith(RESPOSTA.slug, "Servir com arroz branco.");
    expect(screen.getByText("Salvando…")).toBeInTheDocument();
    await act(async () => espera.resolver(deuCerto(NOTAS)));
    expect(screen.getByText(`Salvo ${NOTAS.atualizado_texto}`)).toBeInTheDocument();
    // Sair do campo sem mudar nada não manda de novo.
    fireEvent.blur(campo);
    expect(acao.anotarReceita).toHaveBeenCalledTimes(1);
  });

  it("sair do campo salva na hora; se não salvar, Tentar de novo manda outra vez", async () => {
    acao.anotarReceita.mockResolvedValueOnce(deuErrado("Não consegui falar com o sistema.")).mockResolvedValueOnce(deuCerto(NOTAS));
    avaliacao(SEM_NADA, null);
    const campo = screen.getByRole("textbox", { name: "Notas da senhora" });
    fireEvent.change(campo, { target: { value: "Testar com açafrão." } });
    fireEvent.blur(campo);
    expect(await screen.findByText("Não salvou.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText(`Salvo ${NOTAS.atualizado_texto}`)).toBeInTheDocument();
    expect(acao.anotarReceita).toHaveBeenCalledTimes(2);
  });

  it("duas teclas seguidas contam uma pausa só; sair do campo antes dela salva na hora", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    acao.anotarReceita.mockResolvedValue(deuCerto(NOTAS));
    avaliacao(SEM_NADA, null);
    const campo = screen.getByRole("textbox", { name: "Notas da senhora" });
    fireEvent.change(campo, { target: { value: "Com" } });
    fireEvent.change(campo, { target: { value: "Com farofa" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(acao.anotarReceita).toHaveBeenCalledWith(RESPOSTA.slug, "Com farofa"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PAUSA_DAS_NOTAS_MS * 2);
    });
    expect(acao.anotarReceita).toHaveBeenCalledTimes(1);
  });

  it("a ação que lança conta como não salvo", async () => {
    acao.anotarReceita.mockRejectedValue(new Error("a ação sumiu no deploy"));
    avaliacao(SEM_NADA, null);
    const campo = screen.getByRole("textbox", { name: "Notas da senhora" });
    fireEvent.change(campo, { target: { value: "Com farofa." } });
    fireEvent.blur(campo);
    expect(await screen.findByText("Não salvou.")).toBeInTheDocument();
  });

  it("se ela continuou escrevendo enquanto a nota ia, vale o que está no campo", async () => {
    const primeira = adiado<Awaited<ReturnType<typeof acao.anotarReceita>>>();
    acao.anotarReceita.mockReturnValueOnce(primeira.promessa).mockResolvedValueOnce(deuCerto({ ...NOTAS, notas: "Com farofa e ovo." }));
    avaliacao(SEM_NADA, null);
    const campo = screen.getByRole("textbox", { name: "Notas da senhora" });
    fireEvent.change(campo, { target: { value: "Com farofa" } });
    fireEvent.blur(campo);
    fireEvent.change(campo, { target: { value: "Com farofa e ovo." } });
    await act(async () => primeira.resolver(deuCerto({ ...NOTAS, notas: "Com farofa" })));
    expect(screen.getByText("Salvando…")).toBeInTheDocument();
    fireEvent.blur(campo);
    await waitFor(() => expect(acao.anotarReceita).toHaveBeenLastCalledWith(RESPOSTA.slug, "Com farofa e ovo."));
    expect(await screen.findByText(`Salvo ${NOTAS.atualizado_texto}`)).toBeInTheDocument();
  });
});
