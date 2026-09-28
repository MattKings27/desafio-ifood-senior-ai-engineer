/**
 * Cartões: o cartão clicável inteiro tem um link só (o do título), e o que
 * fica por cima continua clicável sozinho. A classe de quem usa vence a padrão.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AcimaDoLink, Card, CardLink, LinkEsticado } from "./Card";
import { unirClasses } from "./classes";

describe("Card", () => {
  it("é uma seção por padrão, e pode ser outro elemento", () => {
    const { container, rerender } = render(<Card>conteúdo</Card>);
    expect(container.firstChild?.nodeName).toBe("SECTION");
    rerender(<Card como="article">conteúdo</Card>);
    expect(container.firstChild?.nodeName).toBe("ARTICLE");
  });

  it.each([
    ["padrao", "bg-superficie"],
    ["plano", "bg-superficie"],
    ["creme", "bg-creme"],
    ["secao", "bg-secao"],
    ["alerta", "bg-tinta-clara"],
  ] as const)("tom %s", (tom, classe) => {
    const { container } = render(<Card tom={tom}>x</Card>);
    expect((container.firstChild as HTMLElement).className).toContain(classe);
  });

  it.each([
    ["normal", "p-4"],
    ["compacta", "p-3"],
    ["nenhuma", "p-0"],
  ] as const)("densidade %s", (densidade, classe) => {
    const { container } = render(<Card densidade={densidade}>x</Card>);
    expect((container.firstChild as HTMLElement).className).toContain(classe);
  });

  it("o fundo de quem usa vence o padrão (o bg-info/5 das telas antigas)", () => {
    const { container } = render(<Card className="border-info/30 bg-info/5">x</Card>);
    const classes = (container.firstChild as HTMLElement).className.split(" ");
    expect(classes).toContain("bg-info/5");
    expect(classes).not.toContain("bg-superficie");
    expect(classes).toContain("border-info/30");
    expect(classes).not.toContain("border-borda");
    // A largura da borda continua: só a cor foi trocada.
    expect(classes).toContain("border");
  });
});

describe("CardLink", () => {
  it("o link é o título, e cobre o cartão inteiro", () => {
    const { container } = render(
      <CardLink href="/despensa/alcaparras" titulo="Alcaparras" midia={<div data-testid="foto" />}>
        <p>R$ 82,00</p>
      </CardLink>,
    );
    const link = screen.getByRole("link", { name: "Alcaparras" });
    expect(link).toHaveAttribute("href", "/despensa/alcaparras");
    expect(link.closest("h3")).not.toBeNull();
    expect(link).toHaveAttribute("data-link-esticado");
    expect(link.className).toContain("after:inset-0");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    const cartao = container.firstChild as HTMLElement;
    expect(cartao.nodeName).toBe("ARTICLE");
    expect(cartao).toHaveAttribute("data-cartao-link");
    expect(cartao.className).toContain("relative");
    expect(screen.getByTestId("foto")).toBeInTheDocument();
  });

  it("nível do título e classe do título", () => {
    render(<CardLink href="/x" titulo="Receitas" nivelTitulo={2} classeDoTitulo="text-lg" />);
    const titulo = screen.getByRole("heading", { level: 2, name: "Receitas" });
    expect(titulo.className).toContain("text-lg");
  });

  it("o que vai por cima do link continua clicável sozinho", () => {
    const perguntar = vi.fn();
    render(
      <CardLink href="/receitas/arroz" titulo="Arroz com frango">
        <AcimaDoLink>
          <button type="button" onClick={perguntar}>
            Perguntar
          </button>
        </AcimaDoLink>
      </CardLink>,
    );
    const botao = screen.getByRole("button", { name: "Perguntar" });
    expect(botao.parentElement?.className).toContain("z-10");
    fireEvent.click(botao);
    expect(perguntar).toHaveBeenCalledOnce();
  });

  it("AcimaDoLink pode ser outro elemento", () => {
    const { container } = render(
      <AcimaDoLink como="span" className="ml-2">
        x
      </AcimaDoLink>,
    );
    expect(container.firstChild?.nodeName).toBe("SPAN");
    expect((container.firstChild as HTMLElement).className).toBe("relative z-10 ml-2");
  });
});

describe("LinkEsticado", () => {
  it("externo abre em outra aba e avisa", () => {
    render(
      <LinkEsticado href="https://www.tudogostoso.com.br/receita/1" externo>
        Carne moída com arroz
      </LinkEsticado>,
    );
    const link = screen.getByRole("link", { name: "Carne moída com arroz (abre em outra aba)" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("data-link-esticado");
  });
});

describe("unirClasses", () => {
  it("sem classes de quem usa, fica o padrão", () => {
    expect(unirClasses("p-4 bg-superficie")).toBe("p-4 bg-superficie");
  });

  it("troca só o grupo que quem usa passou, respeitando as variantes", () => {
    expect(unirClasses("bg-superficie hover:bg-secao p-4 shadow-cartao", "bg-creme")).toBe(
      "hover:bg-secao p-4 shadow-cartao bg-creme",
    );
    expect(unirClasses("bg-superficie hover:bg-secao", "hover:bg-marca/10")).toBe("bg-superficie hover:bg-marca/10");
    expect(unirClasses("shadow-cartao p-4", "shadow-none p-0")).toBe("shadow-none p-0");
  });

  it("borda: a cor é trocada, a largura e o estilo ficam", () => {
    expect(unirClasses("border border-borda border-dashed", "border-perigo/20")).toBe(
      "border border-dashed border-perigo/20",
    );
    expect(unirClasses("border-borda", "border-2")).toBe("border-borda border-2");
    expect(unirClasses("border-borda", "border-t")).toBe("border-borda border-t");
  });

  it("utilitárias de fundo que não são cor não conflitam", () => {
    expect(unirClasses("bg-superficie", "bg-gradient-to-br bg-cover")).toBe(
      "bg-superficie bg-gradient-to-br bg-cover",
    );
  });

  it("aceita o ! de importante e objetos do clsx", () => {
    expect(unirClasses("bg-superficie", "!bg-creme")).toBe("!bg-creme");
    expect(unirClasses(["p-4", { "bg-superficie": true }], { "p-2": true })).toBe("bg-superficie p-2");
  });
});
