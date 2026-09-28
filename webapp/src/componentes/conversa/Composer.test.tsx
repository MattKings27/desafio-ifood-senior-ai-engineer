/**
 * A caixa de texto: Enter envia no computador e pula linha no toque, Parar no
 * lugar de Enviar durante a resposta, o limite com o contador, o chip do que
 * vai junto, e a caixa parada quando não dá para mandar.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/despensa",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import { LIMITE_DE_CARACTERES } from "@/lib/conversa/loja";
import { definirMidia } from "@/teste/midia";
import { esperarPromessas, lojaDeTeste } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import { CONTADOR_A_PARTIR_DE, Composer, DICA_DO_TECLADO } from "./Composer";
import { ProvedorDaConversa } from "./ProvedorDaConversa";
import { TOQUE } from "./useMidia";

async function montar(t: LojaDeTeste = lojaDeTeste()) {
  await t.loja.abrirConversa("cv-1");
  const resultado = render(
    <ProvedorDaConversa loja={t.loja}>
      <Composer />
    </ProvedorDaConversa>,
  );
  return { ...resultado, ...t, caixa: () => screen.getByRole("textbox", { name: "Mensagem para o agente" }) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("escrever e enviar", () => {
  it("Enter envia no computador; Shift e Enter, não; a dica aparece", async () => {
    const t = await montar();
    expect(screen.getByText(DICA_DO_TECLADO)).toBeInTheDocument();
    fireEvent.change(t.caixa(), { target: { value: "Oi, tudo bem?" } });
    expect(t.loja.ler().caixa.texto).toBe("Oi, tudo bem?");
    fireEvent.keyDown(t.caixa(), { key: "Enter", shiftKey: true });
    fireEvent.keyDown(t.caixa(), { key: "a" });
    fireEvent.keyDown(t.caixa(), { key: "Enter", isComposing: true });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.keyDown(t.caixa(), { key: "Enter" });
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({ texto: "Oi, tudo bem?" }));
    expect(t.loja.ler().caixa.texto).toBe("");
  });

  it("no toque, Enter pula linha e quem envia é o botão", async () => {
    definirMidia(TOQUE, true);
    const t = await montar();
    expect(screen.queryByText(DICA_DO_TECLADO)).toBeNull();
    expect(t.caixa()).toHaveAttribute("enterkeyhint", "enter");
    fireEvent.change(t.caixa(), { target: { value: "Oi" } });
    fireEvent.keyDown(t.caixa(), { key: "Enter" });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalled();
  });

  it("vazio não envia, e o botão diz que ainda não dá", async () => {
    const t = await montar();
    const enviar = screen.getByRole("button", { name: "Enviar" });
    expect(enviar).toHaveAttribute("aria-disabled", "true");
    await act(async () => {
      fireEvent.click(enviar);
      fireEvent.keyDown(t.caixa(), { key: "Enter" });
      await esperarPromessas();
    });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });

  it("cresce com o texto, até cinco linhas", async () => {
    const t = await montar();
    Object.assign(t.caixa().style, { lineHeight: "20px", paddingTop: "4px", paddingBottom: "6px" });
    Object.defineProperty(t.caixa(), "scrollHeight", { configurable: true, value: 300 });
    fireEvent.change(t.caixa(), { target: { value: "linha\n".repeat(10) } });
    expect(t.caixa().style.height).toBe("110px");
    expect(t.caixa().style.overflowY).toBe("auto");
  });
});

describe("durante a resposta", () => {
  it("Parar toma o lugar de Enviar, e ela pode continuar escrevendo", async () => {
    const t = await montar();
    await act(async () => {
      await t.loja.enviar("Primeira");
    });
    expect(screen.queryByRole("button", { name: "Enviar" })).toBeNull();
    fireEvent.change(t.caixa(), { target: { value: "Segunda" } });
    fireEvent.keyDown(t.caixa(), { key: "Enter" });
    expect(t.transporte.enviar).toHaveBeenCalledTimes(1);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Parar" }));
      await esperarPromessas();
    });
    expect(t.transporte.parar).toHaveBeenCalledWith("cv-1", "t-1");
    expect(screen.getByRole("button", { name: "Parando…" })).toHaveAttribute("aria-busy", "true");
  });

  it("antes de o backend aceitar o envio, ainda não há o que parar", async () => {
    const t = lojaDeTeste({ enviar: () => new Promise(() => {}) });
    await montar(t);
    await act(async () => {
      void t.loja.enviar("Oi");
      await esperarPromessas();
    });
    const parar = screen.getByRole("button", { name: "Parar" });
    expect(parar).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(parar);
    expect(t.transporte.parar).not.toHaveBeenCalled();
  });
});

describe("o limite, o contexto e a caixa parada", () => {
  it("o contador aparece perto do limite, e avisa quando chega", async () => {
    const t = await montar();
    fireEvent.change(t.caixa(), { target: { value: "a".repeat(CONTADOR_A_PARTIR_DE - 1) } });
    expect(screen.queryByText(/caracteres/)).toBeNull();
    fireEvent.change(t.caixa(), { target: { value: "a".repeat(CONTADOR_A_PARTIR_DE) } });
    expect(screen.getByText("1.500 de 2.000 caracteres")).toBeInTheDocument();
    expect(t.caixa().getAttribute("aria-describedby")).toContain("-contador");
    fireEvent.change(t.caixa(), { target: { value: "a".repeat(LIMITE_DE_CARACTERES) } });
    expect(screen.getByText("Chegou ao limite de 2.000 caracteres.")).toBeInTheDocument();
    expect(t.caixa()).toHaveAttribute("maxlength", "2000");
  });

  it("o chip diz o que vai junto, e o ✕ tira", async () => {
    const t = await montar();
    act(() => t.loja.definirContexto({ tela: "despensa", tipo: "ingrediente", id: "arroz", rotulo: "Arroz branco tipo 1" }));
    expect(screen.getByText("Vendo:")).toBeInTheDocument();
    expect(screen.getByText(/Arroz branco tipo 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tirar da mensagem: Arroz branco tipo 1" }));
    expect(t.loja.ler().caixa.contexto).toBeNull();
  });

  it("sem internet ou fora do ar, a caixa fica parada", async () => {
    const t = await montar();
    act(() => t.loja.definirOnline(false));
    expect(t.caixa()).toBeDisabled();
    expect(t.caixa()).toHaveAttribute("placeholder", "A conversa volta quando o agente estiver de novo no ar");
    expect(screen.getByRole("button", { name: "Enviar" })).toHaveAttribute("aria-disabled", "true");
  });
});

describe("o foco", () => {
  it("quem pede a caixa ganha o foco, com o cursor no fim", async () => {
    const t = await montar();
    act(() => t.loja.preencher({ rascunho: "Dá pra eu fazer Bolo?" }));
    expect(t.caixa()).toHaveFocus();
    const caixa = t.caixa() as HTMLTextAreaElement;
    expect(caixa.selectionStart).toBe("Dá pra eu fazer Bolo?".length);
  });

  it("no toque, só com rascunho (senão o teclado cobriria a conversa)", async () => {
    definirMidia(TOQUE, true);
    const t = await montar();
    act(() => t.loja.pedirFoco());
    expect(t.caixa()).not.toHaveFocus();
    act(() => t.loja.preencher({ rascunho: "Tenho " }));
    expect(t.caixa()).toHaveFocus();
  });

  it("parada, a caixa não recebe foco", async () => {
    const t = await montar();
    act(() => t.loja.definirOnline(false));
    act(() => t.loja.pedirFoco());
    expect(t.caixa()).not.toHaveFocus();
  });
});
