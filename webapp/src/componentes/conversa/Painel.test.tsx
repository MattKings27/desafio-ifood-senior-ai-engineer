/**
 * O painel da conversa (aside ao lado no computador, folha no celular) e a
 * página /conversa em tela cheia.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const caminhoAtual = vi.fn(() => "/despensa");
vi.mock("next/navigation", () => ({
  usePathname: () => caminhoAtual(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import { definirMidia } from "@/teste/midia";
import { conversaVazia, esperarPromessas, lojaDeTeste, resumo } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import { BotaoConversa } from "./BotaoConversa";
import { PainelDaConversa, TEMPO_DE_SAIDA_MS, TITULO_DO_PAINEL, TITULO_VISIVEL_DO_PAINEL } from "./PainelDaConversa";
import { ProvedorDaConversa, useConversa } from "./ProvedorDaConversa";
import { PEDIDO_DA_COZINHA, TelaDaConversa } from "./TelaDaConversa";
import { TELA_LARGA } from "./useMidia";

function Abridor() {
  const { abrir } = useConversa();
  return (
    <button type="button" onClick={() => abrir()}>
      Abrir a conversa
    </button>
  );
}

function montar(t: LojaDeTeste, filhos: ReactNode = null) {
  return render(
    <ProvedorDaConversa loja={t.loja}>
      <Abridor />
      <BotaoConversa />
      {filhos}
      <PainelDaConversa />
    </ProvedorDaConversa>,
  );
}

async function abrir() {
  const botao = screen.getByRole("button", { name: "Abrir a conversa" });
  botao.focus();
  await act(async () => {
    fireEvent.click(botao);
    await esperarPromessas();
  });
  return botao;
}

beforeEach(() => {
  window.history.replaceState(null, "", "/despensa");
  caminhoAtual.mockReturnValue("/despensa");
  vi.spyOn(window.history, "back").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("no computador: ao lado da tela", () => {
  beforeEach(() => definirMidia(TELA_LARGA, true));

  it("abre como aside nomeado, a página anda para o lado, e o foco vai para a caixa", async () => {
    const t = lojaDeTeste({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1")] }),
      ler: async (id: string) => conversaVazia(id, "Arroz com frango"),
    });
    montar(t);
    expect(screen.queryByRole("complementary")).toBeNull();
    await abrir();
    const painel = screen.getByRole("complementary", { name: TITULO_DO_PAINEL });
    expect(document.documentElement).toHaveAttribute("data-painel", "aberto");
    expect(within(painel).getByText("Arroz com frango")).toBeInTheDocument();
    expect(within(painel).getByRole("textbox", { name: "Mensagem para o agente" })).toHaveFocus();
    expect(within(painel).getByRole("link", { name: "Abrir em tela cheia" })).toHaveAttribute("href", "/conversa?c=cv-1");
    await act(async () => {
      fireEvent.click(within(painel).getByRole("button", { name: "Começar outra conversa" }));
      await esperarPromessas();
    });
    expect(t.transporte.criar).toHaveBeenCalled();
  });

  it("Esc fecha e devolve o foco a quem abriu; o Esc de um diálogo de dentro é dele", async () => {
    const t = lojaDeTeste();
    montar(t);
    const botao = await abrir();
    const painel = screen.getByRole("complementary", { name: TITULO_DO_PAINEL });

    const dialogo = document.createElement("dialog");
    dialogo.setAttribute("open", "");
    const dentro = document.createElement("button");
    dialogo.appendChild(dentro);
    painel.appendChild(dialogo);
    fireEvent.keyDown(dentro, { key: "Escape" });
    expect(t.loja.ler().painelAberto).toBe(true);
    dialogo.remove();

    fireEvent.keyDown(within(painel).getByRole("textbox"), { key: "a" });
    fireEvent.keyDown(within(painel).getByRole("textbox"), { key: "Escape" });
    expect(t.loja.ler().painelAberto).toBe(false);
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(document.documentElement).not.toHaveAttribute("data-painel");
    expect(botao).toHaveFocus();
  });

  it("quem abriu sumiu: o foco vai para uma entrada da conversa à vista", async () => {
    const t = lojaDeTeste();
    montar(t);
    // Quem abriu foi um botão de fora do React, que some com o painel aberto.
    const deFora = document.createElement("button");
    document.body.appendChild(deFora);
    deFora.focus();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Abrir a conversa" }));
      await esperarPromessas();
    });
    deFora.remove();
    const entrada = document.querySelector<HTMLElement>("a[data-abre-conversa]")!;
    vi.spyOn(entrada, "getClientRects").mockReturnValue([{}] as unknown as DOMRectList);
    fireEvent.click(screen.getByRole("button", { name: "Fechar a conversa" }));
    expect(entrada).toHaveFocus();
  });

  it("na própria página da conversa, o painel não existe", () => {
    caminhoAtual.mockReturnValue("/conversa");
    const t = lojaDeTeste();
    const { container } = render(
      <ProvedorDaConversa loja={t.loja}>
        <PainelDaConversa />
      </ProvedorDaConversa>,
    );
    act(() => t.loja.definirPainel(true));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("no celular: a folha", () => {
  it("abre a folha modal, com a conversa dentro; fechar tira a conversa depois da descida", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const t = lojaDeTeste();
    montar(t);
    const folha = document.querySelector("dialog") as HTMLDialogElement;
    expect(folha.open).toBe(false);
    await abrir();
    expect(folha.open).toBe(true);
    expect(folha).toHaveAccessibleName(TITULO_DO_PAINEL);
    expect(within(folha).getByRole("heading", { name: TITULO_VISIVEL_DO_PAINEL })).toBeInTheDocument();
    expect(within(folha).getByRole("textbox", { name: "Mensagem para o agente" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: "Fechar a conversa" }));
      await esperarPromessas();
    });
    expect(folha.open).toBe(false);
    expect(t.loja.ler().painelAberto).toBe(false);
    expect(screen.getByRole("button", { name: "Abrir a conversa" })).toHaveFocus();
    expect(within(folha).queryByRole("textbox", { hidden: true })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(TEMPO_DE_SAIDA_MS);
    });
    expect(within(folha).queryByRole("textbox", { hidden: true })).toBeNull();
  });
});

describe("a página /conversa", () => {
  beforeEach(() => {
    caminhoAtual.mockReturnValue("/conversa");
    window.history.replaceState(null, "", "/conversa?rascunho=Oi&tela=receitas&tipo=receita&id=bolo&rotulo=Bolo");
  });

  function pagina(t: LojaDeTeste, chegada: Parameters<typeof TelaDaConversa>[0]["chegada"]) {
    return render(
      <ProvedorDaConversa loja={t.loja}>
        <main>
          <TelaDaConversa chegada={chegada} />
        </main>
      </ProvedorDaConversa>,
    );
  }

  it("abre a conversa do endereço, preenche o rascunho sem enviar, e o endereço acompanha", async () => {
    const t = lojaDeTeste({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2", { titulo: "Bolo de milho" })] }),
      ler: async (id: string) => conversaVazia(id, id === "cv-2" ? "Bolo de milho" : "Primeira"),
    });
    pagina(t, { conversa: "cv-2", rascunho: "Dá pra eu fazer Bolo?", contexto: { tela: "receitas", tipo: "receita", id: "bolo", rotulo: "Bolo" } });
    await act(async () => {
      await esperarPromessas(20);
    });
    expect(screen.getByRole("heading", { level: 1, name: TITULO_DO_PAINEL })).toHaveClass("sr-only");
    expect(screen.getByRole("heading", { level: 2, name: "Bolo de milho" })).toBeInTheDocument();
    expect(t.transporte.marcarAtual).toHaveBeenCalledWith("cv-2");
    expect(t.loja.ler().caixa).toMatchObject({ texto: "Dá pra eu fazer Bolo?", contexto: { id: "bolo" } });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    expect(window.location.search).toBe("?c=cv-2");
  });

  it("o Responder agora do Início abre uma conversa nova e manda o pedido dela uma vez só", async () => {
    window.history.replaceState(null, "", "/conversa?comecar=cozinha");
    const t = lojaDeTeste({});
    pagina(t, { comecar: "cozinha" });
    await act(async () => {
      await esperarPromessas(30);
    });
    expect(t.transporte.criar).toHaveBeenCalledTimes(1);
    expect(t.transporte.enviar).toHaveBeenCalledTimes(1);
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-nova", expect.objectContaining({ texto: PEDIDO_DA_COZINHA }));
    expect(window.location.search).toBe("?c=cv-nova");
  });

  it("sem nada no endereço, abre a atual; no celular, a lista abre numa folha", async () => {
    window.history.replaceState(null, "", "/conversa");
    const t = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1", { titulo: "Primeira" }), resumo("cv-2")] }) });
    pagina(t, {});
    await act(async () => {
      await esperarPromessas(20);
    });
    expect(window.location.search).toBe("?c=cv-1");
    const botao = screen.getByRole("button", { name: "Conversas" });
    fireEvent.click(botao);
    const folha = screen.getByRole("dialog", { name: "Conversas" });
    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: /^Conversa cv-2/ }));
      await esperarPromessas(10);
    });
    expect(folha).not.toHaveAttribute("open");
    expect(t.loja.ler().conversa.id).toBe("cv-2");
    expect(window.location.search).toBe("?c=cv-2");
    fireEvent.click(screen.getAllByRole("button", { name: "Começar outra conversa" }).at(-1)!);
    fireEvent.click(botao);
    fireEvent.keyDown(within(screen.getByRole("dialog", { name: "Conversas" })).getAllByRole("button")[0]!, { key: "Escape" });
  });
});
