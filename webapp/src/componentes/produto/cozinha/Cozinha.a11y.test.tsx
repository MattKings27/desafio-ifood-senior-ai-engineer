/**
 * Acessibilidade da cozinha, pelo axe: o que toda cozinha tem, o progresso, os
 * limites da rotina e as duas listas com o seletor em cada item. O contraste fica com o axe do
 * Playwright, na tela pintada de verdade.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("@/lib/acoes/cozinha", () => ({ definirPosse: vi.fn(), definirRestricao: vi.fn(), confirmarSupostos: vi.fn() }));
vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import type { PerfilDaCozinha } from "@/lib/api/perfil";
import { contrato } from "@/teste/fixturas";

import { MiniaturaDoItem } from "./ItemDaCozinha";
import { TelaDaCozinha } from "./TelaDaCozinha";
import { TodaCozinha } from "./TodaCozinha";

describe("a cozinha no axe", () => {
  it("a tela inteira, e com as receitas de um item abertas", async () => {
    const { container } = render(
      <ProvedorDeToasts>
        <TelaDaCozinha perfil={contrato<PerfilDaCozinha>("perfil.json")} />
      </ProvedorDeToasts>,
    );
    expect(await axe(container)).toHaveNoViolations();
    fireEvent.click(screen.getAllByRole("button", { name: /Muda o que dá para fazer/ })[0] as HTMLElement);
    expect(await axe(container)).toHaveNoViolations();
    // São 63 itens com três rádios cada: o axe no jsdom leva alguns segundos.
  }, 60_000);

  it("o que toda cozinha tem, com tudo confirmado", async () => {
    const bloco = contrato<PerfilDaCozinha>("perfil.json").toda_cozinha;
    const { container } = render(
      <ProvedorDeToasts>
        <TodaCozinha bloco={{ ...bloco, tudo_confirmado: true, a_confirmar: 0 }} />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByText("Ver os itens"));
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a miniatura com foto e a sem foto", async () => {
    const perfil = contrato<PerfilDaCozinha>("perfil.json");
    const itens = [...perfil.equipamentos, ...perfil.tecnicas].filter((i) => i.id === "forno" || i.id === "reducao");
    const { container } = render(
      <ul>
        {itens.map((item) => (
          <li key={item.id}>
            <MiniaturaDoItem item={item} />
            <p>{item.nome}</p>
          </li>
        ))}
      </ul>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
