/**
 * Acessibilidade da despensa, pelo axe: a tela inteira, a folha de filtros e o
 * formulário abertos, e a página de um item com a pergunta. O contraste fica
 * com o axe do Playwright, na tela pintada de verdade.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("@/lib/acoes/despensa", () => ({
  adicionarItem: vi.fn(),
  corrigirItem: vi.fn(),
  removerItem: vi.fn(),
  desfazerMudanca: vi.fn(),
  devolverCompra: vi.fn(),
}));
vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import type { DetalheDoItem, ListaDaDespensa } from "@/lib/api/despensa";
import { contrato } from "@/teste/fixturas";
import { irPara } from "@/teste/navegacao";

import { DetalheDoIngrediente } from "./DetalheDoIngrediente";
import { TelaDaDespensa } from "./TelaDaDespensa";

const LISTA = contrato<ListaDaDespensa>("despensa.json");

afterEach(() => {
  irPara("/despensa");
});

describe("a despensa no axe", () => {
  it("a tela inteira: orçamento, perguntas, filtros e a grade", async () => {
    const { container } = render(
      <ProvedorDeToasts>
        <TelaDaDespensa lista={LISTA} />
      </ProvedorDeToasts>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a folha de filtros e o formulário abertos", async () => {
    const { baseElement } = render(
      <ProvedorDeToasts>
        <TelaDaDespensa lista={LISTA} />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Filtros/ }));
    expect(await axe(baseElement)).toHaveNoViolations();
    fireEvent.click(screen.getByRole("button", { name: "Registrar compra" }));
    fireEvent.change(screen.getByLabelText("Como a senhora mede"), { target: { value: "embalagem" } });
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("a página de um item, com a pergunta, as receitas e o histórico", async () => {
    const detalhe = {
      ...contrato<DetalheDoItem>("despensa-item-comprado.json"),
      pendencia: LISTA.pendencias.find((p) => p.tipo === "preco_pago") ?? null,
    };
    const { container } = render(
      <ProvedorDeToasts>
        <DetalheDoIngrediente
          detalhe={detalhe}
          receitas={[
            {
              slug: "arroz-com-frango",
              nome: "Arroz com frango",
              imagem: null,
              rota: "/receitas/arroz-com-frango",
              usa_texto: "usa 200 g",
              selo: { texto: "Com o que a senhora tem", codigo: "com_o_que_tem" },
            },
          ]}
          categorias={LISTA.categorias_para_escolher}
          orcamento={LISTA.orcamento}
        />
      </ProvedorDeToasts>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
