/**
 * Escolhas: segmentado, abas, estrelas e filtros. Todos sobre controles
 * nativos (rádio, caixa de marcar, seleção), então o teclado já funciona; o
 * que se testa é que a escolha chega a quem usa e o estado aparece.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Abas, AbasDeNavegacao } from "./Abas";
import { Estrelas } from "./Estrelas";
import { BotaoFiltros, ChipsAtivos, FiltroChips, Ordenacao } from "./Filtros";
import { Segmentado } from "./Segmentado";

const POSSE = [
  { valor: "tem", rotulo: "Tenho" },
  { valor: "nao_tem", rotulo: "Não tenho" },
  { valor: "nao_sei", rotulo: "Não sei", icone: <svg data-testid="icone" /> },
] as const;

describe("Segmentado", () => {
  it("é um grupo de rádios com legenda, e a escolha chega a quem usa", () => {
    const aoMudar = vi.fn();
    render(<Segmentado legenda="Forno" opcoes={POSSE} valor="tem" aoMudar={aoMudar} />);
    const grupo = screen.getByRole("group", { name: "Forno" });
    expect(grupo.tagName).toBe("FIELDSET");
    expect(screen.getByRole("radio", { name: "Tenho" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Não sei" }));
    expect(aoMudar).toHaveBeenCalledWith("nao_sei");
    expect(screen.getByTestId("icone").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("sem resposta, nada marcado; os rádios dividem o mesmo nome", () => {
    render(<Segmentado legenda="Forno" opcoes={POSSE} valor={null} aoMudar={() => {}} nome="forno" />);
    const radios = screen.getAllByRole("radio");
    expect(radios.every((r) => !(r as HTMLInputElement).checked)).toBe(true);
    expect(radios.every((r) => r.getAttribute("name") === "forno")).toBe(true);
  });

  it("vertical: uma opção por linha, alinhada à esquerda", () => {
    render(<Segmentado legenda="Aparência" orientacao="vertical" opcoes={POSSE} valor="tem" aoMudar={() => {}} />);
    const opcao = screen.getByRole("radio", { name: "Tenho" }).nextElementSibling as HTMLElement;
    expect(opcao.className).toContain("justify-start");
    expect(opcao.parentElement?.parentElement?.className).toContain("grid-cols-1");
  });

  it("legenda escondida, largura natural e desabilitado", () => {
    render(
      <Segmentado
        legenda="Tema"
        legendaVisivel={false}
        larguraTotal={false}
        desabilitado
        opcoes={POSSE}
        valor="tem"
        aoMudar={() => {}}
      />,
    );
    expect(screen.getByText("Tema")).toHaveClass("sr-only");
    expect(screen.getByRole("radio", { name: "Tenho" })).toBeDisabled();
  });
});

const ABAS = [
  { id: "todas", rotulo: "Todas", contagem: 12, conteudo: <p>a grade</p> },
  { id: "avaliacao", rotulo: "Em avaliação", conteudo: <p>as avaliadas</p> },
  { id: "ranking", rotulo: "Ranking", conteudo: <p>o ranking</p> },
];

describe("Abas", () => {
  it("mostra o painel da aba escolhida, ligado a ela", () => {
    render(<Abas rotulo="Receitas" abas={ABAS} />);
    expect(screen.getByRole("tablist", { name: "Receitas" })).toBeInTheDocument();
    const todas = screen.getByRole("tab", { name: "Todas 12" });
    expect(todas).toHaveAttribute("aria-selected", "true");
    expect(todas).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Ranking" })).toHaveAttribute("tabindex", "-1");
    const painel = screen.getByRole("tabpanel");
    expect(painel).toHaveAccessibleName("Todas 12");
    expect(painel).toHaveTextContent("a grade");

    fireEvent.click(screen.getByRole("tab", { name: "Ranking" }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("o ranking");
  });

  it("setas, Home e End trocam de aba e levam o foco", () => {
    render(<Abas rotulo="Receitas" abas={ABAS} inicial="avaliacao" />);
    const avaliacao = screen.getByRole("tab", { name: "Em avaliação" });
    fireEvent.keyDown(avaliacao, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Ranking" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Ranking" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Todas 12" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Todas 12" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Ranking" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Ranking" }), { key: "Home" });
    expect(screen.getByRole("tab", { name: "Todas 12" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Todas 12" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Ranking" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Ranking" }), { key: "a" });
    expect(screen.getByRole("tab", { name: "Ranking" })).toHaveAttribute("aria-selected", "true");
  });

  it("controlado: a aba vem de fora e a troca é avisada", () => {
    const aoTrocar = vi.fn();
    render(<Abas rotulo="Receitas" abas={ABAS} ativa="ranking" aoTrocar={aoTrocar} />);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("o ranking");
    fireEvent.click(screen.getByRole("tab", { name: "Todas 12" }));
    expect(aoTrocar).toHaveBeenCalledWith("todas");
    // Quem controla ainda não trocou: continua no ranking.
    expect(screen.getByRole("tabpanel")).toHaveTextContent("o ranking");
  });

  it("sem abas, não quebra", () => {
    render(<Abas rotulo="Vazio" abas={[]} />);
    expect(screen.getByRole("tablist")).toBeEmptyDOMElement();
  });
});

describe("AbasDeNavegacao", () => {
  it("são links, com a atual marcada", () => {
    render(
      <AbasDeNavegacao
        rotulo="Receitas"
        abas={[
          { href: "/receitas?aba=todas", rotulo: "Todas", contagem: 12, ativa: false },
          { href: "/receitas?aba=ranking", rotulo: "Ranking", ativa: true },
        ]}
      />,
    );
    expect(screen.getByRole("navigation", { name: "Receitas" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ranking" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Todas 12" })).not.toHaveAttribute("aria-current");
  });
});

function Nota({ inicial = null, aoMudar }: { inicial?: number | null; aoMudar?: (n: number | null) => void }) {
  const [valor, setValor] = useState<number | null>(inicial);
  return (
    <Estrelas
      legenda="Sabor"
      valor={valor}
      aoMudar={(n) => {
        setValor(n);
        aoMudar?.(n);
      }}
    />
  );
}

const acesas = (container: HTMLElement) => container.querySelectorAll("svg.text-atencao").length;

describe("Estrelas", () => {
  it("dar nota é escolher um rádio: '4 estrelas'", () => {
    const aoMudar = vi.fn();
    render(<Nota aoMudar={aoMudar} />);
    expect(screen.getByRole("group", { name: "Sabor" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "4 estrelas" }));
    expect(aoMudar).toHaveBeenCalledWith(4);
    expect(screen.getByRole("radio", { name: "4 estrelas" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "1 estrela" })).not.toBeChecked();
  });

  it("'Tirar nota' volta ao sem nota, que é diferente de uma estrela", () => {
    const aoMudar = vi.fn();
    render(<Nota inicial={3} aoMudar={aoMudar} />);
    fireEvent.click(screen.getByRole("button", { name: "Tirar nota" }));
    expect(aoMudar).toHaveBeenCalledWith(null);
    expect(screen.queryByRole("button", { name: "Tirar nota" })).not.toBeInTheDocument();
  });

  it("passar o ponteiro acende a prévia, e sair volta à nota", () => {
    const { container } = render(<Nota inicial={2} />);
    expect(acesas(container)).toBe(2);
    const cinco = screen.getByRole("radio", { name: "5 estrelas" }).closest("label") as HTMLElement;
    fireEvent.mouseEnter(cinco);
    expect(acesas(container)).toBe(5);
    fireEvent.mouseLeave(cinco.parentElement as HTMLElement);
    expect(acesas(container)).toBe(2);
  });

  it("sem limpar e com legenda escondida", () => {
    render(<Estrelas legenda="Tempo" valor={2} aoMudar={() => {}} permiteLimpar={false} legendaVisivel={false} tamanho="sm" nome="tempo" />);
    expect(screen.queryByRole("button", { name: "Tirar nota" })).not.toBeInTheDocument();
    expect(screen.getByText("Tempo")).toHaveClass("sr-only");
    expect(screen.getAllByRole("radio").every((r) => r.getAttribute("name") === "tempo")).toBe(true);
  });

  it("só para ver: uma imagem com a nota dita", () => {
    const { container, rerender } = render(<Estrelas legenda="Sabor" valor={4} somenteLeitura />);
    expect(screen.getByRole("img", { name: "Sabor: 4 de 5 estrelas" })).toBeInTheDocument();
    expect(acesas(container)).toBe(4);
    rerender(<Estrelas legenda="Sabor" valor={null} />);
    expect(screen.getByRole("img", { name: "Sabor: sem nota" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
});

const CATEGORIAS = [
  { valor: "graos", rotulo: "Grãos", contagem: 7 },
  { valor: "laticinios", rotulo: "Laticínios" },
] as const;

describe("FiltroChips", () => {
  it("múltiplo: caixas de marcar que ligam e desligam", () => {
    const aoMudar = vi.fn();
    const { rerender } = render(
      <FiltroChips legenda="Categoria" opcoes={CATEGORIAS} selecionados={[]} aoMudar={aoMudar} />,
    );
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Grãos 7" }));
    expect(aoMudar).toHaveBeenLastCalledWith(["graos"]);

    rerender(<FiltroChips legenda="Categoria" opcoes={CATEGORIAS} selecionados={["graos"]} aoMudar={aoMudar} />);
    expect(screen.getByRole("checkbox", { name: "Grãos 7" })).toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: "Laticínios" }));
    expect(aoMudar).toHaveBeenLastCalledWith(["graos", "laticinios"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Grãos 7" }));
    expect(aoMudar).toHaveBeenLastCalledWith([]);
  });

  it("escolha única: rádios, a legenda pode aparecer", () => {
    const aoMudar = vi.fn();
    render(
      <FiltroChips
        legenda="Quem fez"
        legendaVisivel
        multiplo={false}
        nome="quem"
        opcoes={[
          { valor: "consultora", rotulo: "O agente" },
          { valor: "senhora", rotulo: "A senhora" },
        ]}
        selecionados={["consultora"]}
        aoMudar={aoMudar}
      />,
    );
    expect(screen.getByText("Quem fez")).not.toHaveClass("sr-only");
    fireEvent.click(screen.getByRole("radio", { name: "A senhora" }));
    expect(aoMudar).toHaveBeenCalledWith(["senhora"]);
  });
});

describe("ChipsAtivos", () => {
  it("cada filtro tem o seu ✕; 'Limpar filtros' só com mais de um", () => {
    const tirarA = vi.fn();
    const limpar = vi.fn();
    const { rerender } = render(
      <ChipsAtivos
        resumo="3 de 37 ingredientes"
        aoLimparTudo={limpar}
        filtros={[
          { id: "a", rotulo: "Grãos", aoRemover: tirarA },
          { id: "b", rotulo: "Até R$ 20,00", aoRemover: () => {} },
        ]}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("3 de 37 ingredientes");
    fireEvent.click(screen.getByRole("button", { name: "Grãos: tirar este filtro" }));
    expect(tirarA).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(limpar).toHaveBeenCalledOnce();

    rerender(<ChipsAtivos aoLimparTudo={limpar} filtros={[{ id: "a", rotulo: "Grãos", aoRemover: tirarA }]} />);
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("sem filtros, sem lista", () => {
    render(<ChipsAtivos filtros={[]} resumo="37 ingredientes" />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});

describe("BotaoFiltros e Ordenacao", () => {
  it("o botão diz quantos filtros estão ativos e abre a folha", () => {
    const abrir = vi.fn();
    const { rerender } = render(<BotaoFiltros quantidade={2} aoAbrir={abrir} aberto />);
    const botao = screen.getByRole("button", { name: "Filtros 2 ativos" });
    expect(botao).toHaveAttribute("aria-haspopup", "dialog");
    expect(botao).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(botao);
    expect(abrir).toHaveBeenCalledOnce();
    rerender(<BotaoFiltros quantidade={0} aoAbrir={abrir} />);
    expect(screen.getByRole("button", { name: "Filtros" })).toHaveAttribute("aria-expanded", "false");
  });

  it("a ordenação é uma seleção com rótulo", () => {
    const aoMudar = vi.fn();
    render(
      <Ordenacao
        valor="nota"
        aoMudar={aoMudar}
        opcoes={[
          { valor: "nota", rotulo: "Nota" },
          { valor: "custo", rotulo: "Custo" },
        ]}
      />,
    );
    const selecao = screen.getByRole("combobox", { name: "Ordenar por" });
    expect(selecao).toHaveValue("nota");
    fireEvent.change(selecao, { target: { value: "custo" } });
    expect(aoMudar).toHaveBeenCalledWith("custo");
  });
});
