/**
 * Testes da navegação do computador.
 *
 * Dois riscos reais aqui. O primeiro é a seção ativa errada: `startsWith`
 * marca `/` como ativa em toda rota se ninguém tratar o caso, e a pessoa perde
 * a referência de onde está. O segundo é a navegação não ser anunciada, o que
 * deixa quem usa leitor de tela sem o mapa do produto.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const caminhoAtual = vi.fn(() => "/");
vi.mock("next/navigation", () => ({ usePathname: () => caminhoAtual() }));

import { DESTINOS, estaAtivo } from "./destinos";
import { Navegacao } from "./Navegacao";

describe("Navegacao", () => {
  it("anuncia-se como navegação nomeada", () => {
    render(<Navegacao />);
    expect(screen.getByRole("navigation", { name: "Seções" })).toBeInTheDocument();
  });

  it("leva a todas as seções do produto, com os nomes que ela entende", () => {
    render(<Navegacao />);
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/",
      "/despensa",
      "/receitas",
      "/cozinha",
      "/precificar",
      "/cardapio",
      "/trilha",
    ]);
    expect(links.map((a) => a.textContent)).toEqual([
      "Início",
      "Despensa",
      "Receitas",
      "Cozinha",
      "Pôr preço",
      "Cardápio",
      "Histórico",
    ]);
  });

  it("marca exatamente uma seção como atual, sem usar o vermelho da marca", () => {
    caminhoAtual.mockReturnValue("/despensa");
    render(<Navegacao />);
    const atuais = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current"));
    expect(atuais).toHaveLength(1);
    expect(atuais[0]).toHaveAttribute("href", "/despensa");
    expect(atuais[0]?.className).not.toMatch(/text-marca|bg-marca/);
  });

  it("a raiz só é atual na própria raiz", () => {
    // `startsWith("/")` casaria com tudo: duas seções ficariam acesas ao mesmo tempo.
    caminhoAtual.mockReturnValue("/cozinha");
    render(<Navegacao />);
    const raiz = screen.getAllByRole("link").find((a) => a.getAttribute("href") === "/");
    expect(raiz).not.toHaveAttribute("aria-current");
  });

  it("uma sub-rota mantém a seção acesa", () => {
    caminhoAtual.mockReturnValue("/receitas/arroz-com-frango");
    render(<Navegacao />);
    const atual = screen.getAllByRole("link").find((a) => a.getAttribute("aria-current"));
    expect(atual).toHaveAttribute("href", "/receitas");
  });
});

describe("estaAtivo", () => {
  it.each([
    ["/", "/", true],
    ["/", "/despensa", false],
    ["/despensa", "/despensa", true],
    ["/despensa", "/despensa/alcaparras", true],
    ["/receitas", "/receitas-antigas", false],
  ])("%s em %s: %s", (href, caminho, esperado) => {
    expect(estaAtivo(href, caminho)).toBe(esperado);
  });

  it("a barra de baixo tem quatro seções (o Conversar entra no meio); o resto vai para Mais", () => {
    expect(DESTINOS.filter((d) => d.naBarra).map((d) => d.rotulo)).toEqual([
      "Início",
      "Despensa",
      "Receitas",
      "Cardápio",
    ]);
    const mais = DESTINOS.filter((d) => !d.naBarra);
    expect(mais.map((d) => d.rotulo)).toEqual(["Cozinha", "Pôr preço", "Histórico"]);
    expect(mais.every((d) => Boolean(d.descricao))).toBe(true);
  });
});
