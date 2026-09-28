/**
 * Campos: o rótulo, a dica e o erro ligados ao controle sem quem usa lembrar;
 * número com vírgula; área que cresce; busca que o Esc limpa.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AreaDeTexto, Busca, Campo, Entrada, EntradaNumero, Selecao } from "./Campos";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Campo", () => {
  it("liga o rótulo, a dica e o erro ao controle de dentro", () => {
    render(
      <Campo rotulo="Quanto pagou" dica="o total da nota" erro="Escreva só o número." obrigatorio>
        <Entrada />
      </Campo>,
    );
    const entrada = screen.getByLabelText("Quanto pagou");
    expect(entrada).toHaveAccessibleDescription("Escreva só o número. o total da nota");
    expect(entrada).toHaveAttribute("aria-invalid", "true");
    expect(entrada).toBeRequired();
  });

  it("sem erro, não está inválido; rótulo pode ficar só para o leitor de tela", () => {
    render(
      <Campo rotulo="Nome" rotuloVisivel={false} opcional id="nome-do-item">
        <Entrada />
      </Campo>,
    );
    const entrada = screen.getByLabelText("Nome (opcional)");
    expect(entrada).toHaveAttribute("id", "nome-do-item");
    expect(entrada).not.toHaveAttribute("aria-invalid");
    expect(entrada).not.toHaveAttribute("aria-describedby");
    expect(screen.getByText("Nome").closest("label")).toHaveClass("sr-only");
  });

  it("o controle soma a própria descrição à do campo", () => {
    render(
      <>
        <p id="extra">em quilos</p>
        <Campo rotulo="Peso" dica="da embalagem">
          <Entrada aria-describedby="extra" />
        </Campo>
      </>,
    );
    expect(screen.getByLabelText("Peso")).toHaveAccessibleDescription("da embalagem em quilos");
  });
});

describe("Entrada", () => {
  it("fora de um Campo, usa o que recebe", () => {
    render(<Entrada aria-label="Endereço" invalido required id="e1" className="w-40" />);
    const entrada = screen.getByRole("textbox", { name: "Endereço" });
    expect(entrada).toHaveAttribute("aria-invalid", "true");
    expect(entrada).toBeRequired();
    expect(entrada.className).toContain("w-40");
    expect(entrada.className).toContain("text-base");
  });
});

function Numero(props: Partial<React.ComponentProps<typeof EntradaNumero>> & { inicial?: number | null }) {
  const { inicial = null, aoMudar, ...resto } = props;
  const [valor, setValor] = useState<number | null>(inicial);
  return (
    <Campo rotulo="Quantidade">
      <EntradaNumero
        valor={valor}
        aoMudar={(v) => {
          setValor(v);
          aoMudar?.(v);
        }}
        {...resto}
      />
    </Campo>
  );
}

describe("EntradaNumero", () => {
  it("lê a vírgula dela e avisa o número", () => {
    const aoMudar = vi.fn();
    render(<Numero aoMudar={aoMudar} />);
    const entrada = screen.getByLabelText("Quantidade");
    fireEvent.change(entrada, { target: { value: "1,5" } });
    expect(aoMudar).toHaveBeenLastCalledWith(1.5);
    expect(entrada).toHaveValue("1,5");
    expect(entrada).toHaveAttribute("inputmode", "decimal");
  });

  it("enquanto ela digita, '1,' fica como está; ao sair, volta ao último número", () => {
    const aoMudar = vi.fn();
    render(<Numero aoMudar={aoMudar} />);
    const entrada = screen.getByLabelText("Quantidade");
    fireEvent.change(entrada, { target: { value: "2" } });
    fireEvent.change(entrada, { target: { value: "2," } });
    expect(entrada).toHaveValue("2,");
    expect(aoMudar).toHaveBeenLastCalledWith(2);
    fireEvent.blur(entrada);
    expect(entrada).toHaveValue("2");
  });

  it("campo vazio é null, nunca zero", () => {
    const aoMudar = vi.fn();
    render(<Numero inicial={3} aoMudar={aoMudar} />);
    const entrada = screen.getByLabelText("Quantidade");
    expect(entrada).toHaveValue("3");
    fireEvent.change(entrada, { target: { value: "" } });
    expect(aoMudar).toHaveBeenLastCalledWith(null);
    fireEvent.blur(entrada);
    expect(entrada).toHaveValue("");
  });

  it("ao sair, prende nos limites e arruma o texto", () => {
    const aoMudar = vi.fn();
    const aoSair = vi.fn();
    render(<Numero aoMudar={aoMudar} min={1} max={8} casas={0} onBlur={aoSair} />);
    const entrada = screen.getByLabelText("Quantidade");
    expect(entrada).toHaveAttribute("inputmode", "numeric");
    fireEvent.change(entrada, { target: { value: "12" } });
    fireEvent.blur(entrada);
    expect(aoMudar).toHaveBeenLastCalledWith(8);
    expect(entrada).toHaveValue("8");
    expect(aoSair).toHaveBeenCalledOnce();

    fireEvent.change(entrada, { target: { value: "0" } });
    fireEvent.blur(entrada);
    expect(aoMudar).toHaveBeenLastCalledWith(1);
  });

  it("ao sair com o mesmo número, não avisa de novo", () => {
    const aoMudar = vi.fn();
    render(<Numero inicial={2} aoMudar={aoMudar} />);
    fireEvent.blur(screen.getByLabelText("Quantidade"));
    expect(aoMudar).not.toHaveBeenCalled();
  });

  it("botões − e + mudam pelo passo e param nos limites", () => {
    const aoMudar = vi.fn();
    render(
      <Numero
        inicial={null}
        aoMudar={aoMudar}
        comBotoes
        min={1}
        max={3}
        casas={0}
        rotulos={{ menos: "Uma boca a menos", mais: "Uma boca a mais" }}
      />,
    );
    const mais = screen.getByRole("button", { name: "Uma boca a mais" });
    const menos = screen.getByRole("button", { name: "Uma boca a menos" });
    fireEvent.click(mais);
    expect(aoMudar).toHaveBeenLastCalledWith(2);
    expect(screen.getByLabelText("Quantidade")).toHaveValue("2");
    fireEvent.click(mais);
    expect(mais).toBeDisabled();
    fireEvent.click(menos);
    fireEvent.click(menos);
    expect(aoMudar).toHaveBeenLastCalledWith(1);
    expect(menos).toBeDisabled();
  });

  it("sem mínimo, o − parte do zero; decimal não acumula erro de ponto flutuante", () => {
    const aoMudar = vi.fn();
    render(<Numero inicial={0.1} aoMudar={aoMudar} comBotoes passo={0.2} casas={1} />);
    fireEvent.click(screen.getByRole("button", { name: "Aumentar" }));
    expect(aoMudar).toHaveBeenLastCalledWith(0.3);
  });

  it("valor que muda por fora aparece no campo", () => {
    const { rerender } = render(<EntradaNumero aria-label="Preço" valor={1} aoMudar={() => {}} />);
    rerender(<EntradaNumero aria-label="Preço" valor={12.5} aoMudar={() => {}} />);
    expect(screen.getByRole("textbox", { name: "Preço" })).toHaveValue("12,5");
  });

  it("prefixo e unidade aparecem, sem entrar no nome do campo", () => {
    render(
      <Campo rotulo="Preço">
        <EntradaNumero valor={9} aoMudar={() => {}} prefixo="R$" unidade="por kg" />
      </Campo>,
    );
    expect(screen.getByLabelText("Preço")).toHaveClass("pl-10", "pr-16");
    expect(screen.getByText("R$")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("por kg")).toHaveAttribute("aria-hidden", "true");
  });

  it("desabilitado desabilita os botões também", () => {
    render(<EntradaNumero aria-label="Preço" valor={1} aoMudar={() => {}} comBotoes disabled />);
    expect(screen.getByRole("textbox", { name: "Preço" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Aumentar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Diminuir" })).toBeDisabled();
  });

  it("inválido marca o campo", () => {
    render(<EntradaNumero aria-label="Preço" valor={null} aoMudar={() => {}} invalido />);
    expect(screen.getByRole("textbox", { name: "Preço" })).toHaveAttribute("aria-invalid", "true");
  });
});

describe("AreaDeTexto", () => {
  it("cresce com o texto, e avisa a mudança", () => {
    const aoMudar = vi.fn();
    const original = window.getComputedStyle.bind(window);
    vi.spyOn(window, "getComputedStyle").mockImplementation((elemento, pseudo) =>
      elemento instanceof HTMLTextAreaElement
        ? ({ lineHeight: "24px", paddingTop: "10px", paddingBottom: "10px" } as CSSStyleDeclaration)
        : original(elemento, pseudo),
    );
    render(
      <Campo rotulo="Notas">
        <AreaDeTexto value="" onChange={aoMudar} maxLinhas={3} />
      </Campo>,
    );
    const area = screen.getByLabelText("Notas") as HTMLTextAreaElement;
    Object.defineProperty(area, "scrollHeight", { configurable: true, value: 60 });
    fireEvent.change(area, { target: { value: "uma linha" } });
    expect(aoMudar).toHaveBeenCalledOnce();
    expect(area.style.height).toBe("60px");
    expect(area.style.overflowY).toBe("hidden");

    // Passou de 3 linhas: para de crescer e rola por dentro.
    Object.defineProperty(area, "scrollHeight", { configurable: true, value: 400 });
    fireEvent.change(area, { target: { value: "muitas linhas" } });
    expect(area.style.height).toBe(`${24 * 3 + 20}px`);
    expect(area.style.overflowY).toBe("auto");
  });

  it("aceita ref de função e de objeto, e estilo sem medidas (usa 24 px por linha)", () => {
    const refFuncao = vi.fn();
    const refObjeto = { current: null as HTMLTextAreaElement | null };
    const { rerender } = render(<AreaDeTexto aria-label="A" ref={refFuncao} readOnly value="x" />);
    expect(refFuncao).toHaveBeenCalledWith(expect.any(HTMLTextAreaElement));
    rerender(<AreaDeTexto aria-label="A" ref={refObjeto} readOnly value="x" invalido />);
    expect(refObjeto.current).toBeInstanceOf(HTMLTextAreaElement);
    expect(screen.getByRole("textbox", { name: "A" })).toHaveAttribute("aria-invalid", "true");
  });
});

describe("Selecao", () => {
  it("é a seleção nativa, com as opções e o que vier de filho", () => {
    const aoMudar = vi.fn();
    render(
      <Campo rotulo="Unidade">
        <Selecao
          value="kg"
          onChange={(e) => aoMudar(e.target.value)}
          opcoes={[
            { valor: "kg", rotulo: "quilo" },
            { valor: "g", rotulo: "grama" },
            { valor: "l", rotulo: "litro", desabilitada: true },
          ]}
        >
          <option value="un">unidade</option>
        </Selecao>
      </Campo>,
    );
    const selecao = screen.getByLabelText("Unidade");
    expect(screen.getAllByRole("option")).toHaveLength(4);
    expect(screen.getByRole("option", { name: "litro" })).toBeDisabled();
    fireEvent.change(selecao, { target: { value: "g" } });
    expect(aoMudar).toHaveBeenCalledWith("g");
  });

  it("fora de um Campo, marca inválido pelo que recebe", () => {
    render(<Selecao aria-label="Ordem" invalido opcoes={[{ valor: "a", rotulo: "A" }]} />);
    expect(screen.getByRole("combobox", { name: "Ordem" })).toHaveAttribute("aria-invalid", "true");
  });
});

function BuscaControlada({ inicial = "" }: { inicial?: string }) {
  const [valor, setValor] = useState(inicial);
  return <Busca valor={valor} aoMudar={setValor} rotulo="Buscar ingrediente" placeholder="Buscar" />;
}

describe("Busca", () => {
  it("tem nome mesmo sem Campo em volta, e digita", () => {
    render(<BuscaControlada />);
    const busca = screen.getByRole("searchbox", { name: "Buscar ingrediente" });
    fireEvent.change(busca, { target: { value: "alho" } });
    expect(busca).toHaveValue("alho");
  });

  it("o ✕ limpa e devolve o foco à busca", () => {
    render(<BuscaControlada inicial="alho" />);
    fireEvent.click(screen.getByRole("button", { name: "Limpar a busca" }));
    const busca = screen.getByRole("searchbox", { name: "Buscar ingrediente" });
    expect(busca).toHaveValue("");
    expect(busca).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Limpar a busca" })).not.toBeInTheDocument();
  });

  it("Esc limpa quando há texto; vazio, deixa o Esc seguir (fecha a folha)", () => {
    const aoTeclar = vi.fn();
    const aoMudar = vi.fn();
    const { rerender } = render(<Busca valor="alho" aoMudar={aoMudar} onKeyDown={aoTeclar} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Escape" });
    expect(aoMudar).toHaveBeenCalledWith("");
    expect(aoTeclar).toHaveBeenCalledOnce();

    aoMudar.mockClear();
    rerender(<Busca valor="" aoMudar={aoMudar} onKeyDown={aoTeclar} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Escape" });
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "a" });
    expect(aoMudar).not.toHaveBeenCalled();
  });

  it("dentro de um Campo, usa o rótulo do Campo", () => {
    render(
      <Campo rotulo="Procurar na despensa">
        <Busca valor="" aoMudar={() => {}} />
      </Campo>,
    );
    expect(screen.getByRole("searchbox", { name: "Procurar na despensa" })).toBeInTheDocument();
    expect(screen.getAllByText(/Procurar|Buscar/)).toHaveLength(1);
  });
});
