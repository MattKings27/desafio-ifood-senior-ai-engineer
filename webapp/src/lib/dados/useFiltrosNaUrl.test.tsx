/**
 * O hook dos filtros da página: lê da URL e escreve com replaceState, sem ida
 * ao servidor. O `useSearchParams` do Next é trocado por um que acompanha o
 * `history`, como o Next faz no navegador.
 */

import { act, render, screen } from "@testing-library/react";
import { useSyncExternalStore } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const ouvintes = new Set<() => void>();
function avisarMudanca() {
  for (const ouvinte of ouvintes) ouvinte();
}
const trocaOriginal = window.history.replaceState.bind(window.history);

vi.mock("next/navigation", () => ({
  useSearchParams: () => {
    const busca = useSyncExternalStore(
      (ouvinte) => {
        ouvintes.add(ouvinte);
        return () => ouvintes.delete(ouvinte);
      },
      () => window.location.search,
    );
    return new URLSearchParams(busca);
  },
}));

import { estadoSemAsMarcasDoNext, useFiltrosNaUrl } from "./useFiltrosNaUrl";

const ESQUEMA = {
  q: { tipo: "texto" },
  categoria: { tipo: "lista" },
  ordem: { tipo: "opcao", opcoes: ["pago", "nome"], padrao: "pago" },
} as const;

let ultimo: ReturnType<typeof useFiltrosNaUrl<typeof ESQUEMA>>;

function Tela() {
  ultimo = useFiltrosNaUrl(ESQUEMA);
  return (
    <p>
      <span data-testid="q">{ultimo.filtros.q}</span>
      <span data-testid="categoria">{ultimo.filtros.categoria.join(",")}</span>
      <span data-testid="ordem">{ultimo.filtros.ordem}</span>
      <span data-testid="ativos">{ultimo.ativos}</span>
    </p>
  );
}

function irPara(busca: string) {
  trocaOriginal(null, "", `/despensa${busca}`);
}

window.history.replaceState = (...args: Parameters<History["replaceState"]>) => {
  trocaOriginal(...args);
  avisarMudanca();
};

afterEach(() => {
  irPara("");
});

describe("useFiltrosNaUrl", () => {
  it("lê os filtros da URL da página", () => {
    irPara("?q=choco&categoria=confeitaria&ordem=nome&aba=x");
    render(<Tela />);
    expect(screen.getByTestId("q")).toHaveTextContent("choco");
    expect(screen.getByTestId("categoria")).toHaveTextContent("confeitaria");
    expect(screen.getByTestId("ordem")).toHaveTextContent("nome");
    expect(screen.getByTestId("ativos")).toHaveTextContent("3");
  });

  it("definir troca a URL sem apagar o que não é filtro, e a tela acompanha", () => {
    irPara("?aba=ranking");
    render(<Tela />);
    act(() => ultimo.definir({ q: "alho", categoria: ["temperos", "hortifruti"] }));
    expect(window.location.search).toBe("?aba=ranking&q=alho&categoria=temperos&categoria=hortifruti");
    expect(screen.getByTestId("q")).toHaveTextContent("alho");
    expect(screen.getByTestId("ativos")).toHaveTextContent("2");
    expect(window.location.pathname).toBe("/despensa");
  });

  it("a troca vai sem as marcas do Next (senão ele não acompanha), e o resto do estado fica", () => {
    trocaOriginal({ __NA: true, __PRIVATE_NEXTJS_INTERNALS_TREE: ["x"], __painelDaConversa: true }, "", "/receitas");
    render(<Tela />);
    act(() => ultimo.definir({ q: "bolo" }));
    expect(window.history.state).toEqual({ __painelDaConversa: true });
    expect(window.location.search).toBe("?q=bolo");
  });

  it("estado que não é objeto vira nulo", () => {
    expect(estadoSemAsMarcasDoNext(null)).toBeNull();
    expect(estadoSemAsMarcasDoNext("x")).toBeNull();
    expect(estadoSemAsMarcasDoNext({ _N: 1, outra: 2 })).toEqual({ outra: 2 });
  });

  it("limpar tira os filtros (todos, ou só os pedidos)", () => {
    irPara("?aba=ranking&q=alho&ordem=nome");
    render(<Tela />);
    act(() => ultimo.limpar(["q"]));
    expect(window.location.search).toBe("?aba=ranking&ordem=nome");
    act(() => ultimo.limpar());
    expect(window.location.search).toBe("?aba=ranking");
    expect(screen.getByTestId("ativos")).toHaveTextContent("0");
  });
});
