/**
 * "Procurar mais receitas": a rodada de descoberta, acompanhada pelo fluxo de
 * eventos (o EventSource de mentira), com o progresso escrito e os cards
 * "chegando"; cada receita achada e o fim refazem a página pela
 * sincronização. Com a descoberta desligada ou sem a rota, o botão abre a
 * conversa com o pedido escrito. Na primeira visita com o catálogo vazio, a
 * tela pede a rodada sozinha, uma vez, e em silêncio se não der.
 */

import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({ avaliarReceita: vi.fn(), trazerReceita: vi.fn() }));

import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { EstadoDaDescoberta, InicioDaDescoberta } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";
import { EventSourceFalso } from "@/teste/eventsource-falso";
import { contrato } from "@/teste/fixturas";
import { irPara, roteador } from "@/teste/navegacao";
import { lista, montar } from "@/teste/receitas";

import { TelaDasReceitas } from "./TelaDasReceitas";
import { RASCUNHO_DA_DESCOBERTA } from "./textos";
import { CHAVE_DA_PROCURA_SOZINHA, PERDI_A_PROCURA } from "./useDescoberta";

const INICIO = contrato<InicioDaDescoberta>("descoberta-inicio.json");

beforeEach(() => {
  irPara("/receitas");
  EventSourceFalso.reiniciar();
  vi.stubGlobal("EventSource", EventSourceFalso);
  roteador.refresh.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function tela(descoberta?: EstadoDaDescoberta) {
  const inicial = descoberta ? lista({ descoberta }) : lista();
  return montar(<TelaDasReceitas inicial={inicial} chaveInicial="?aba=pode_fazer" />);
}

const botao = () => screen.getByRole("button", { name: /Procurar mais receitas|Procurando/ });

describe("procurar mais receitas", () => {
  it("abre o fluxo da rodada, escreve o progresso, mostra os cards chegando e refaz a página", async () => {
    vi.spyOn(receitas, "descobrir").mockResolvedValue(INICIO);
    tela();
    fireEvent.click(botao());
    expect(await screen.findByText(INICIO.texto)).toBeInTheDocument();
    expect(botao()).toHaveAttribute("aria-busy", "true");
    const fonte = EventSourceFalso.ultima();
    expect(fonte.url).toBe("/motor/receitas/descoberta/eventos?execucao=dx-0007");
    expect(screen.getByRole("list", { name: "Ainda não me disse se gosta" }).querySelectorAll('li[aria-hidden="true"]')).toHaveLength(4);

    act(() => {
      fonte.abrir();
      fonte.emitir({ seq: 1, tipo: "progresso", etapa: "lendo", texto: "Lendo a receita do TudoGostoso…", lidas: 1, encontradas: 1 });
    });
    expect(screen.getByText("Lendo a receita do TudoGostoso…")).toBeInTheDocument();
    expect(screen.getByText("1 página lida, 1 receita encontrada.")).toBeInTheDocument();

    act(() => fonte.emitir({ seq: 2, tipo: "receita.encontrada", aba: "pode_fazer", receita: lista().itens[0] }));
    await waitFor(() => expect(roteador.refresh).toHaveBeenCalledTimes(1));

    act(() => fonte.emitir({ seq: 3, tipo: "fim", estado: "parada", lidas: 1, encontradas: 1, texto: "Encontrei 1 receita nova." }));
    expect(screen.getByText("Encontrei 1 receita nova.")).toBeInTheDocument();
    expect(botao()).not.toHaveAttribute("aria-busy");
    expect(fonte.fechada).toBe(true);
    await waitFor(() => expect(roteador.refresh).toHaveBeenCalledTimes(2));
  });

  it("sem a rota da descoberta, abre a conversa com o pedido escrito, sem mandar", async () => {
    vi.spyOn(receitas, "descobrir").mockRejectedValue(new ErroDoMotor(MENSAGENS.uso, "uso", undefined, "HTTP 405", 405));
    const { loja } = tela();
    fireEvent.click(botao());
    await waitFor(() => expect(loja.ler().caixa.texto).toBe("Procure receitas reais que aproveitem a minha despensa"));
    expect(loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "tela", id: "receitas", rotulo: "Receitas" });
    expect(screen.getByText("Trouxe 2 receitas da internet que usam a despensa da senhora.")).toBeInTheDocument();
  });

  it("outro erro fica escrito na faixa, na língua dela", async () => {
    const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValueOnce(new ErroDoMotor("Já estou procurando receitas.", "regra"));
    tela();
    fireEvent.click(botao());
    expect(await screen.findByText("Já estou procurando receitas.")).toBeInTheDocument();
    descobrir.mockRejectedValueOnce(new TypeError("fetch failed"));
    fireEvent.click(botao());
    expect(await screen.findByText(MENSAGENS.rede)).toBeInTheDocument();
  });

  it("o erro da rodada fica escrito, e a página é refeita com o que ela achou", async () => {
    vi.spyOn(receitas, "descobrir").mockResolvedValue(INICIO);
    tela();
    fireEvent.click(botao());
    await screen.findByText(INICIO.texto);
    act(() => EventSourceFalso.ultima().emitir({ seq: 1, tipo: "erro", texto: "O site não respondeu." }));
    expect(screen.getByText("O site não respondeu.")).toBeInTheDocument();
    await waitFor(() => expect(roteador.refresh).toHaveBeenCalled());
  });

  it("o fluxo que não abre três vezes seguidas: desiste de acompanhar e avisa", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(receitas, "descobrir").mockResolvedValue(INICIO);
    tela();
    fireEvent.click(botao());
    await screen.findByText(INICIO.texto);
    for (let tentativa = 0; tentativa < 3; tentativa += 1) {
      act(() => EventSourceFalso.ultima().cair());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
    }
    expect(screen.getByText(PERDI_A_PROCURA)).toBeInTheDocument();
    expect(EventSourceFalso.abertas()).toHaveLength(0);
  });

  it("no meio de uma rodada acompanhada, a página refeita pelo servidor não apaga o progresso", async () => {
    vi.spyOn(receitas, "descobrir").mockResolvedValue(INICIO);
    const { refazer } = tela();
    fireEvent.click(botao());
    await screen.findByText(INICIO.texto);
    act(() => EventSourceFalso.ultima().abrir());
    refazer(<TelaDasReceitas inicial={lista({ descoberta: { estado: "parada", lidas: 0, encontradas: 0, texto: "Parada." } })} chaveInicial="?aba=pode_fazer" />);
    expect(screen.getByText(INICIO.texto)).toBeInTheDocument();
    expect(screen.queryByText("Parada.")).not.toBeInTheDocument();
    expect(EventSourceFalso.instancias).toHaveLength(1);
  });

  it("a página que abre no meio de uma rodada acompanha o fluxo geral", () => {
    tela({ estado: "procurando", lidas: 0, encontradas: 0, texto: "Procurando receitas com o que a senhora tem…" });
    expect(EventSourceFalso.ultima().url).toBe("/motor/receitas/descoberta/eventos");
    expect(botao()).toHaveAttribute("aria-busy", "true");
  });

  it("o servidor refaz a página: a faixa acompanha, e uma rodada começada em outro lugar passa a ser acompanhada", () => {
    const { refazer } = tela();
    refazer(
      <TelaDasReceitas
        inicial={lista({ descoberta: { estado: "parada", lidas: 3, encontradas: 2, texto: "Trouxe 2 receitas novas." } })}
        chaveInicial="?aba=pode_fazer"
      />,
    );
    expect(screen.getByText("Trouxe 2 receitas novas.")).toBeInTheDocument();
    expect(EventSourceFalso.instancias).toHaveLength(0);
    refazer(
      <TelaDasReceitas
        inicial={lista({ descoberta: { estado: "procurando", lidas: 0, encontradas: 0, texto: "Procurando pelo agente." } })}
        chaveInicial="?aba=pode_fazer"
      />,
    );
    expect(screen.getByText("Procurando pelo agente.")).toBeInTheDocument();
    expect(EventSourceFalso.ultima().url).toBe("/motor/receitas/descoberta/eventos");
  });

  it("sem texto de descoberta, a faixa não aparece", () => {
    const { container } = tela({ estado: "parada", lidas: 0, encontradas: 0, texto: "" });
    expect(screen.queryByText(/receitas da internet/)).not.toBeInTheDocument();
    expect(container.querySelector(".bg-creme")).toBeNull();
  });
});

describe("a primeira visita com o catálogo vazio", () => {
  const PARADA: EstadoDaDescoberta = { estado: "parada", lidas: 0, encontradas: 0, texto: "" };
  const SEM_RECEITA = { pode_fazer: 0, falta_resposta: 0, ranking: 0, nao_quer: 0 };
  const DESLIGADA = "A procura de receitas está desligada aqui.";
  const recusa = (status: number) => new ErroDoMotor(DESLIGADA, "regra", undefined, `HTTP ${status}`, status);
  const VAZIO = "Ainda não há receita que a senhora consiga fazer";

  const vazia = (descoberta: EstadoDaDescoberta = PARADA) => (
    <TelaDasReceitas inicial={lista({ itens: [], contagens: SEM_RECEITA, descoberta })} chaveInicial="?aba=pode_fazer" />
  );

  it("pede uma rodada sozinha, uma vez: a página refeita e a volta na mesma sessão não pedem de novo", async () => {
    const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValue(recusa(501));
    const { refazer, unmount } = montar(vazia());
    expect(descobrir).toHaveBeenCalledTimes(1);
    refazer(vazia({ ...PARADA }));
    unmount();
    montar(vazia());
    await act(async () => {});
    expect(descobrir).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(CHAVE_DA_PROCURA_SOZINHA)).not.toBeNull();
  });

  it("com receita no catálogo, ou com um filtro ligado, não pede nada", () => {
    const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValue(recusa(501));
    vi.spyOn(receitas, "listar").mockResolvedValue(lista({ itens: [], contagens: SEM_RECEITA }));
    const { unmount } = tela(PARADA);
    unmount();
    irPara("/receitas?q=xyz");
    montar(
      <TelaDasReceitas
        inicial={lista({ itens: [], contagens: SEM_RECEITA, descoberta: PARADA })}
        chaveInicial="?aba=pode_fazer&q=xyz"
      />,
    );
    expect(descobrir).not.toHaveBeenCalled();
  });

  it("com uma rodada já procurando, não pede outra e acompanha a que está rodando", () => {
    const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValue(recusa(501));
    montar(vazia({ estado: "procurando", lidas: 0, encontradas: 0, texto: "Procurando receitas com o que a senhora tem…" }));
    expect(descobrir).not.toHaveBeenCalled();
    expect(EventSourceFalso.ultima().url).toBe("/motor/receitas/descoberta/eventos");
  });

  it.each([501, 404, 405])(
    "a resposta %i fica em silêncio: sem conversa, sem erro, e o botão continua abrindo a conversa",
    async (status) => {
      const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValue(recusa(status));
      const { loja } = montar(vazia());
      await waitFor(() => expect(descobrir).toHaveBeenCalledTimes(1));
      await act(async () => {});
      expect(loja.ler().caixa.texto).not.toBe(RASCUNHO_DA_DESCOBERTA);
      expect(screen.queryByText(DESLIGADA)).not.toBeInTheDocument();
      expect(screen.getByText(VAZIO)).toBeInTheDocument();
      expect(botao()).not.toHaveAttribute("aria-busy");

      fireEvent.click(botao());
      await waitFor(() => expect(loja.ler().caixa.texto).toBe(RASCUNHO_DA_DESCOBERTA));
      expect(descobrir).toHaveBeenCalledTimes(2);
    },
  );

  it("a rodada que começa é acompanhada como a do botão", async () => {
    vi.spyOn(receitas, "descobrir").mockResolvedValue(INICIO);
    montar(vazia());
    expect(await screen.findByText(INICIO.texto)).toBeInTheDocument();
    const fonte = EventSourceFalso.ultima();
    expect(fonte.url).toBe("/motor/receitas/descoberta/eventos?execucao=dx-0007");
    expect(botao()).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("list", { name: "Ainda não me disse se gosta" }).querySelectorAll('li[aria-hidden="true"]')).toHaveLength(4);

    act(() => {
      fonte.abrir();
      fonte.emitir({ seq: 1, tipo: "fim", estado: "parada", lidas: 2, encontradas: 1, texto: "Encontrei 1 receita nova." });
    });
    expect(screen.getByText("Encontrei 1 receita nova.")).toBeInTheDocument();
    expect(fonte.fechada).toBe(true);
    await waitFor(() => expect(roteador.refresh).toHaveBeenCalled());
  });

  it("sem o armazenamento da sessão, a tela funciona e pede uma vez nesta visita", async () => {
    const sessao = window.sessionStorage;
    const bloqueado = (): never => {
      throw new DOMException("O armazenamento está bloqueado.", "SecurityError");
    };
    const ler = Storage.prototype.getItem;
    const gravar = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, chave: string) {
      return this === sessao ? bloqueado() : ler.call(this, chave);
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, chave: string, valor: string) {
      return this === sessao ? bloqueado() : gravar.call(this, chave, valor);
    });
    const descobrir = vi.spyOn(receitas, "descobrir").mockRejectedValue(recusa(501));
    const { refazer } = montar(vazia());
    refazer(vazia({ ...PARADA }));
    await act(async () => {});
    expect(descobrir).toHaveBeenCalledTimes(1);
    expect(screen.getByText(VAZIO)).toBeInTheDocument();
  });
});
