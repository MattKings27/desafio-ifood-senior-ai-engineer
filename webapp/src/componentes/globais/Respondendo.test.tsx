/**
 * Com o agente respondendo, o Conversar acende um ponto e diz isso a quem
 * usa leitor de tela, na barra de baixo e no botão flutuante.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/despensa", useRouter: () => ({ push: vi.fn() }) }));

const respondendo = { abrir: vi.fn(), fechar: vi.fn(), aberta: false, respondendo: true };
vi.mock("@/componentes/conversa/ProvedorDaConversa", async (original) => ({
  ...(await original<typeof import("@/componentes/conversa/ProvedorDaConversa")>()),
  useConversa: () => respondendo,
}));

import { BotaoConversa } from "@/componentes/conversa/BotaoConversa";

import { BarraInferior } from "./BarraInferior";

describe("agente respondendo", () => {
  it("a barra de baixo avisa", () => {
    render(<BarraInferior />);
    expect(screen.getByRole("link", { name: "Conversar: o agente está respondendo" })).toBeInTheDocument();
  });

  it("o botão flutuante avisa", () => {
    render(<BotaoConversa />);
    expect(screen.getByRole("link", { name: "Conversar: o agente está respondendo" })).toBeInTheDocument();
  });
});
