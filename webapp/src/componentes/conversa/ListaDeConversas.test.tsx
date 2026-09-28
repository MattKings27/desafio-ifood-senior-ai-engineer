/**
 * A lista de conversas: começar outra, trocar, renomear e apagar com
 * confirmação, e os estados de carregando, falhou e vazia.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversa",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import { esperarPromessas, lojaDeTeste, resumo } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import { ListaDeConversas, NOTA_DA_NOVA_CONVERSA } from "./ListaDeConversas";
import { ProvedorDaConversa } from "./ProvedorDaConversa";

const DUAS = {
  atual: "cv-1",
  conversas: [
    resumo("cv-1", { titulo: "Arroz com frango", previa: "Gravado.", atualizado_texto: "hoje, 15:02" }),
    resumo("cv-2", { titulo: "  ", previa: "", atualizado_texto: "", respondendo: true }),
  ],
};

async function montar(t: LojaDeTeste, aoEscolher?: () => void, comTitulo = true) {
  const resultado = render(
    <ProvedorDaConversa loja={t.loja}>
      <ListaDeConversas aoEscolher={aoEscolher} comTitulo={comTitulo} />
    </ProvedorDaConversa>,
  );
  await act(async () => {
    await esperarPromessas();
  });
  return resultado;
}

describe("ListaDeConversas", () => {
  it("mostra título, prévia, data e quem está respondendo; a aberta fica marcada", async () => {
    const t = lojaDeTeste({ listar: async () => DUAS });
    await t.loja.abrirConversa("cv-1");
    const { container } = await montar(t);
    expect(screen.getByRole("heading", { level: 2, name: "Conversas" })).toBeInTheDocument();
    expect(screen.getByText(NOTA_DA_NOVA_CONVERSA)).toBeInTheDocument();
    const aberta = screen.getByRole("button", { name: /^Arroz com frango/ });
    expect(aberta).toHaveAttribute("aria-current", "true");
    expect(within(aberta).getByText("Gravado.")).toBeInTheDocument();
    expect(within(aberta).getByText("hoje, 15:02")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Conversa nova/ })).toHaveTextContent("respondendo…");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("começar outra e trocar avisam quem usa (a folha do celular fecha)", async () => {
    const t = lojaDeTeste({ listar: async () => DUAS });
    const aoEscolher = vi.fn();
    await montar(t, aoEscolher, false);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Começar outra conversa" }));
      await esperarPromessas();
    });
    expect(t.transporte.criar).toHaveBeenCalled();
    expect(aoEscolher).toHaveBeenCalledTimes(1);

    t.transporte.criar.mockRejectedValueOnce(new Error("caiu"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Começar outra conversa" }));
      await esperarPromessas();
    });
    expect(aoEscolher).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Arroz com frango/ }));
      await esperarPromessas();
    });
    expect(t.transporte.marcarAtual).toHaveBeenCalledWith("cv-1");
    expect(aoEscolher).toHaveBeenCalledTimes(2);
  });

  it("renomear: o nome muda com Enter; Esc e nome igual cancelam", async () => {
    const t = lojaDeTeste({ listar: async () => DUAS });
    await montar(t);
    fireEvent.click(screen.getByRole("button", { name: "Renomear Arroz com frango" }));
    const campo = screen.getByRole("textbox", { name: "Novo nome da conversa" });
    expect(campo).toHaveFocus();
    fireEvent.keyDown(campo, { key: "a" });
    fireEvent.keyDown(campo, { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Renomear Arroz com frango" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar o nome" }));
    expect(t.transporte.renomear).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Renomear Arroz com frango" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  Arroz   de domingo " } });
    await act(async () => {
      fireEvent.submit(screen.getByRole("textbox").closest("form")!);
      await esperarPromessas();
    });
    expect(t.transporte.renomear).toHaveBeenCalledWith("cv-1", "Arroz de domingo");
    expect(screen.getByRole("button", { name: /^Arroz de domingo/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Renomear Conversa nova" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("apagar pede confirmação; cancelar não apaga", async () => {
    const t = lojaDeTeste({ listar: async () => DUAS });
    await montar(t);
    fireEvent.click(screen.getByRole("button", { name: "Apagar Arroz com frango" }));
    const dialogo = screen.getByRole("alertdialog", { name: "Apagar esta conversa?" });
    expect(dialogo).toHaveTextContent("Arroz com frango");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(t.transporte.apagar).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apagar Conversa nova" }));
    await act(async () => {
      fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Apagar" }));
      await esperarPromessas();
    });
    expect(t.transporte.apagar).toHaveBeenCalledWith("cv-2");
  });

  it("carregando, falhou (com tentar de novo) e vazia", async () => {
    const lenta = lojaDeTeste({ listar: () => new Promise(() => {}) });
    const { unmount } = await montar(lenta);
    expect(screen.getByText("Carregando as conversas…")).toBeInTheDocument();
    unmount();

    const falha = lojaDeTeste({ listar: vi.fn().mockRejectedValueOnce(new Error("caiu")).mockResolvedValue({ atual: null, conversas: [] }) as never });
    const segunda = await montar(falha);
    expect(screen.getByText("Não consegui carregar a lista agora.")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
      await esperarPromessas();
    });
    expect(screen.getByText("Nenhuma conversa ainda")).toBeInTheDocument();
    segunda.unmount();
  });
});
