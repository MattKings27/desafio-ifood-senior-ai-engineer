/**
 * O que só mostra: listas, linha do tempo, salvamento, vazio, esqueletos,
 * fotos, movimento, títulos, valores, barras e chips.
 *
 * As regras que importam: valor ausente nunca vira R$ 0,00; foto só da API;
 * toda amostra tem o caminho para o resto; nada que mude sozinho rouba o foco.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Barra } from "./Barra";
import { Chip, SeloVeredito } from "./Chip";
import {
  Esqueleto,
  EsqueletoCartao,
  EsqueletoDaPagina,
  EsqueletoGrade,
  EsqueletoLista,
  EsqueletoTexto,
} from "./Esqueleto";
import { EstadoVazio, Vazio } from "./EstadoVazio";
import { ImagemComFallback } from "./ImagemComFallback";
import { IndicadorDeSalvamento } from "./IndicadorDeSalvamento";
import { ListaDoTempo } from "./ListaDoTempo";
import { ListaExpansivel } from "./ListaExpansivel";
import { ProvedorDeMovimento, Revelar, Surgir } from "./Movimento";
import { CabecalhoDaPagina, TituloSecao } from "./Titulos";
import { Derivacao, Valor } from "./Valor";

afterEach(() => {
  vi.restoreAllMocks();
});

const ITENS = Array.from({ length: 37 }, (_, i) => `Item ${i + 1}`);

describe("ListaExpansivel", () => {
  it("mostra os primeiros e diz quantos faltam", () => {
    render(
      <ListaExpansivel
        itens={ITENS}
        visiveis={5}
        chave={(item) => item}
        renderizar={(item) => <span>{item}</span>}
        descricaoDoResto="ingredientes"
        classeDoItem="py-2"
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    const botao = screen.getByRole("button", { name: "Ver mais 32 ingredientes" });
    expect(botao).toHaveAttribute("aria-expanded", "false");
    const lista = screen.getByRole("list");
    expect(botao).toHaveAttribute("aria-controls", lista.id);
    expect(screen.getAllByRole("listitem")[0]).toHaveClass("py-2");
  });

  it("a seta abre a lista inteira e fecha de novo", () => {
    render(
      <ListaExpansivel
        itens={ITENS}
        chave={(item) => item}
        renderizar={(item) => <span>{item}</span>}
        rotuloVerMais="Ver os 37"
        rotuloVerMenos="Mostrar menos"
        como="ol"
        id="parados"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Ver os 37/ }));
    expect(screen.getAllByRole("listitem")).toHaveLength(37);
    expect(screen.getByText("Item 37")).toBeInTheDocument();
    const fechar = screen.getByRole("button", { name: "Mostrar menos" });
    expect(fechar).toHaveAttribute("aria-expanded", "true");
    expect(fechar).toHaveAttribute("aria-controls", "parados");
    expect(screen.getByRole("list").tagName).toBe("OL");
    fireEvent.click(fechar);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("cabe tudo: sem botão", () => {
    render(<ListaExpansivel itens={["a", "b"]} chave={(i) => i} renderizar={(i) => i} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("vazia: o vazio de quem usa, ou nada", () => {
    const { container, rerender } = render(
      <ListaExpansivel itens={[]} chave={(i: string) => i} renderizar={(i) => i} vazio={<p>Nada parado.</p>} />,
    );
    expect(screen.getByText("Nada parado.")).toBeInTheDocument();
    rerender(<ListaExpansivel itens={[]} chave={(i: string) => i} renderizar={(i) => i} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ListaDoTempo", () => {
  it("agrupa por dia, com link, ação e detalhe", () => {
    const desfazer = vi.fn();
    render(
      <ListaDoTempo
        grupos={[
          {
            id: "hoje",
            titulo: "Hoje",
            itens: [
              {
                id: "a",
                texto: "A senhora informou que a embalagem tem 1 kg.",
                quandoTexto: "hoje, 09:58",
                tom: "sucesso",
                icone: <svg data-testid="icone" />,
                link: { href: "/despensa/cobertura-de-chocolate", rotulo: "Ver o item" },
                acao: (
                  <button type="button" onClick={desfazer}>
                    Desfazer
                  </button>
                ),
                detalhe: "Cobertura de chocolate",
              },
              { id: "b", texto: "Pesquisei receitas.", quandoTexto: "hoje, 10:02" },
            ],
          },
          { id: "ontem", titulo: "Ontem", itens: [] },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Hoje" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ontem" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver o item" })).toHaveAttribute("href", "/despensa/cobertura-de-chocolate");
    fireEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(desfazer).toHaveBeenCalledOnce();
    expect(screen.getByText("Cobertura de chocolate")).toBeInTheDocument();
    expect(screen.getByTestId("icone")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("itens soltos, sem grupos", () => {
    render(<ListaDoTempo itens={[{ id: "a", texto: "Veio da planilha.", quandoTexto: "24 de setembro" }]} />);
    expect(screen.getByText("Veio da planilha.")).toBeInTheDocument();
    expect(screen.getByText("24 de setembro")).toBeInTheDocument();
  });

  it("vazia: o vazio de quem usa, ou nada", () => {
    const { container, rerender } = render(
      <ListaDoTempo grupos={[{ id: "x", titulo: "X", itens: [] }]} vazio={<p>Nenhuma decisão ainda.</p>} />,
    );
    expect(screen.getByText("Nenhuma decisão ainda.")).toBeInTheDocument();
    rerender(<ListaDoTempo itens={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("IndicadorDeSalvamento", () => {
  it("salvando aparece, mas não é anunciado", () => {
    render(<IndicadorDeSalvamento estado="salvando" />);
    expect(screen.getByText("Salvando…")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(screen.getByRole("alert")).toBeEmptyDOMElement();
  });

  it("salvo é anunciado, com o quando da API", () => {
    const { rerender } = render(<IndicadorDeSalvamento estado="salvo" quandoTexto="hoje, 14:31" />);
    expect(screen.getByRole("status")).toHaveTextContent("Salvo hoje, 14:31");
    rerender(<IndicadorDeSalvamento estado="salvo" />);
    expect(screen.getByRole("status")).toHaveTextContent(/^Salvo$/);
  });

  it("erro é alerta, com tentar de novo", () => {
    const tentar = vi.fn();
    const { rerender } = render(<IndicadorDeSalvamento estado="erro" aoTentarDeNovo={tentar} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Não salvou.");
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(tentar).toHaveBeenCalledOnce();
    rerender(<IndicadorDeSalvamento estado="erro" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<IndicadorDeSalvamento estado="ocioso" />);
    expect(screen.getByRole("alert")).toBeEmptyDOMElement();
  });
});

describe("EstadoVazio", () => {
  it("explica o vazio e oferece a saída", () => {
    render(
      <EstadoVazio
        titulo="Nenhum prato no cardápio"
        descricao="Confira uma receita e a decisão da senhora aparece aqui."
        acao={<a href="/receitas">Ver receitas</a>}
        icone={<svg data-testid="icone" />}
      />,
    );
    expect(screen.getByText("Nenhum prato no cardápio")).toBeInTheDocument();
    expect(screen.getByText(/Confira uma receita/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver receitas" })).toBeInTheDocument();
    expect(screen.getByTestId("icone").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("compacto, com o ícone padrão; Vazio é o nome antigo", () => {
    const { container } = render(<Vazio titulo="Nada ainda" compacto />);
    expect(Vazio).toBe(EstadoVazio);
    expect((container.firstChild as HTMLElement).className).toContain("p-5");
    expect(container.querySelector("svg")).not.toBeNull();
  });
});

describe("Esqueletos", () => {
  it("peças decorativas, com formas e alturas", () => {
    const { container } = render(
      <>
        <Esqueleto />
        <Esqueleto forma="linha" />
        <Esqueleto forma="linha" className="h-6" />
        <Esqueleto forma="circulo" className="size-10" />
      </>,
    );
    const pecas = Array.from(container.children) as HTMLElement[];
    expect(pecas.every((p) => p.getAttribute("aria-hidden") === "true")).toBe(true);
    expect(pecas[1]?.className).toContain("h-4");
    expect(pecas[2]?.className).not.toContain("h-4");
    expect(pecas[3]?.className).toContain("rounded-full");
  });

  it("presets de texto, cartão, grade e lista", () => {
    const { container } = render(
      <>
        <EsqueletoTexto linhas={4} />
        <EsqueletoCartao comImagem />
        <EsqueletoGrade quantidade={3} comImagem={false} />
        <EsqueletoLista linhas={2} />
      </>,
    );
    expect(container.querySelectorAll(".aspect-square")).toHaveLength(1);
    expect(container.querySelectorAll(".esqueleto").length).toBeGreaterThan(10);
  });

  it.each(["grade", "lista", "detalhe", "painel"] as const)(
    "a página %s carregando é anunciada uma vez",
    (variante) => {
      render(<EsqueletoDaPagina variante={variante} rotulo="Carregando a despensa…" />);
      expect(screen.getByRole("status")).toHaveTextContent("Carregando a despensa…");
    },
  );

  it("o padrão é o painel, com o rótulo padrão", () => {
    render(<EsqueletoDaPagina />);
    expect(screen.getByRole("status")).toHaveTextContent("Carregando…");
  });
});

describe("ImagemComFallback", () => {
  const FOTO = "/motor/imagens/9b1e22c4a0f35d7e";

  it("só carrega foto da API, preguiçosa, com o alt de quem usa", () => {
    render(<ImagemComFallback src={FOTO} alt="Peito de frango" proporcao="1/1" />);
    const img = screen.getByRole("img", { name: "Peito de frango" });
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("src", FOTO);
  });

  it.each(["https://www.tudogostoso.com.br/foto.jpg", "/motor/imagens/../segredo", "/outra/rota/abc12345", ""])(
    "%j não é foto da API: cai no plano B",
    (src) => {
      const { container } = render(<ImagemComFallback src={src} alt="Carne moída" tipo="prato" />);
      expect(container.querySelector("img")).toBeNull();
      expect(screen.getByRole("img", { name: "Carne moída" }).tagName).toBe("DIV");
    },
  );

  it("sem foto e decorativa: nada para o leitor de tela", () => {
    const { container } = render(<ImagemComFallback src={null} alt="" tipo="ingrediente" proporcao="16/9" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(container.querySelector("[aria-hidden='true'] svg")).not.toBeNull();
  });

  it("brilha enquanto carrega, aparece ao carregar, e cai no plano B se falhar", () => {
    const { container } = render(<ImagemComFallback src={FOTO} alt="" proporcao="3/2" />);
    const img = container.querySelector("img") as HTMLImageElement;
    expect(container.querySelector(".esqueleto")).not.toBeNull();
    fireEvent.load(img);
    expect(img.className).toContain("opacity-100");
    expect(container.querySelector(".esqueleto")).toBeNull();
    fireEvent.error(img);
    expect(container.querySelector("img")).toBeNull();
  });

  it("foto que já tinha carregado antes do React é reconhecida", () => {
    vi.spyOn(HTMLImageElement.prototype, "complete", "get").mockReturnValue(true);
    vi.spyOn(HTMLImageElement.prototype, "naturalWidth", "get").mockReturnValue(640);
    const { container } = render(<ImagemComFallback src={FOTO} alt="" />);
    expect((container.querySelector("img") as HTMLImageElement).className).toContain("opacity-100");
  });

  it("foto que já tinha falhado antes do React cai no plano B", () => {
    vi.spyOn(HTMLImageElement.prototype, "complete", "get").mockReturnValue(true);
    vi.spyOn(HTMLImageElement.prototype, "naturalWidth", "get").mockReturnValue(0);
    const { container } = render(<ImagemComFallback src={FOTO} alt="" />);
    expect(container.querySelector("img")).toBeNull();
  });

  it("trocar para um endereço que não é da API volta ao plano B", () => {
    const { container, rerender } = render(<ImagemComFallback src={FOTO} alt="" />);
    rerender(<ImagemComFallback src="https://fora.com/x.jpg" alt="" />);
    expect(container.querySelector("img")).toBeNull();
    rerender(<ImagemComFallback src={FOTO} alt="" />);
    expect(container.querySelector("img")).not.toBeNull();
  });

  it("no detalhe: prioridade e o crédito embaixo", () => {
    render(
      <ImagemComFallback
        src={FOTO}
        alt="Peito de frango cru"
        mostrarCredito
        credito="Foto: Wikimedia Commons (CC BY-SA 4.0)"
        prioridade
        className="rounded-lg"
      />,
    );
    const img = screen.getByRole("img", { name: "Peito de frango cru" });
    expect(img).toHaveAttribute("loading", "eager");
    expect(img).toHaveAttribute("fetchpriority", "high");
    const figura = screen.getByRole("figure");
    expect(figura).toHaveClass("rounded-lg");
    expect(screen.getByText("Foto: Wikimedia Commons (CC BY-SA 4.0)").tagName).toBe("FIGCAPTION");
  });

  it("no detalhe sem crédito, só a figura", () => {
    render(<ImagemComFallback src={null} alt="Sem foto" mostrarCredito />);
    expect(screen.getByRole("figure")).toBeInTheDocument();
  });
});

describe("Movimento", () => {
  it("o provedor e as peças mostram o conteúdo", () => {
    const { rerender } = render(
      <ProvedorDeMovimento>
        <Surgir atraso={0.1} className="bloco">
          <p>chegou</p>
        </Surgir>
        <Revelar chave="rascunho">R$ ···</Revelar>
      </ProvedorDeMovimento>,
    );
    expect(screen.getByText("chegou")).toBeInTheDocument();
    expect(screen.getByText("R$ ···")).toBeInTheDocument();
    rerender(
      <ProvedorDeMovimento>
        <Revelar chave="conferido" className="numero">
          R$ 2,47
        </Revelar>
      </ProvedorDeMovimento>,
    );
    expect(screen.getByText("R$ 2,47")).toBeInTheDocument();
  });
});

describe("Títulos", () => {
  it("TituloSecao com 'Ver tudo' que diz de qual seção é", () => {
    render(
      <TituloSecao
        titulo="Receitas recomendadas"
        apoio="as que mais usam a despensa"
        verMais={{ href: "/receitas" }}
        acao={<span>12</span>}
        id="recomendadas"
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Receitas recomendadas" })).toHaveAttribute(
      "id",
      "recomendadas",
    );
    expect(screen.getByRole("link", { name: "Ver tudo: Receitas recomendadas" })).toHaveAttribute("href", "/receitas");
    expect(screen.getByText("as que mais usam a despensa")).toBeInTheDocument();
  });

  it("TituloSecao de nível 3, com rótulo próprio e sem ações", () => {
    const { rerender } = render(
      <TituloSecao titulo="Compras" nivel={3} verMais={{ href: "/despensa#orcamento", rotulo: "Ver as compras" }} />,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Compras" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver as compras: Compras" })).toBeInTheDocument();
    rerender(<TituloSecao titulo="Compras" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("CabecalhoDaPagina: o único h1, com voltar, ações e o que vier embaixo", () => {
    render(
      <CabecalhoDaPagina
        titulo="Peito de frango"
        descricao="2 kg na despensa"
        voltar={{ href: "/despensa", rotulo: "Despensa" }}
        acoes={<button type="button">Editar</button>}
      >
        <p>entra em 3 receitas</p>
      </CabecalhoDaPagina>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Peito de frango" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Despensa" })).toHaveAttribute("href", "/despensa");
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
    expect(screen.getByText("entra em 3 receitas")).toBeInTheDocument();
  });

  it("CabecalhoDaPagina só com o título", () => {
    render(<CabecalhoDaPagina titulo="Histórico" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Histórico");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("Valor e Derivacao", () => {
  it("valor ausente é um traço, nunca R$ 0,00, e é dito como desconhecido", () => {
    const { rerender } = render(<Valor dinheiro={null} />);
    expect(screen.getByText("—")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("valor ainda desconhecido")).toHaveClass("sr-only");
    rerender(<Valor dinheiro={{ valor: 0, texto: "  " }} semValor="a conferir" />);
    expect(screen.getByText("a conferir")).toBeInTheDocument();
    rerender(<Valor />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("sem `valor`, não infere o sinal; com tom, usa o tom", () => {
    const { container, rerender } = render(<Valor dinheiro={{ texto: "R$ 9,00" }} tamanho="destaque" />);
    expect(container.querySelector(".text-tinta")).not.toBeNull();
    expect(container.querySelector(".font-titulo")).not.toBeNull();
    rerender(<Valor dinheiro={{ valor: 1, texto: "R$ 1,00" }} tom="positivo" tamanho="lg" />);
    expect(container.querySelector(".text-sucesso")).not.toBeNull();
    rerender(<Valor dinheiro={{ valor: 1, texto: "R$ 1,00" }} tom="apagado" tamanho="sm" />);
    expect(container.querySelector(".text-apagado")).not.toBeNull();
  });

  it("a derivação é texto tabular, não fonte de código", () => {
    const { container } = render(<Derivacao como="span" className="mt-0">R$ 82,00 ÷ 2 kg</Derivacao>);
    const elemento = container.firstChild as HTMLElement;
    expect(elemento.tagName).toBe("SPAN");
    expect(elemento.className).toContain("numero");
    expect(elemento.className).not.toContain("font-mono");
  });
});

describe("Barra", () => {
  it("fração inválida não quebra: vira zero", () => {
    render(<Barra fracao={Number.NaN} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
  });

  it.each(["marca", "sucesso", "atencao", "perigo", "info", "neutro"] as const)("tom %s", (tom) => {
    const { container } = render(<Barra fracao={0.5} tom={tom} espessura="lg" valorTexto="metade" />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuetext", "metade");
    expect(container.querySelector(".h-3")).not.toBeNull();
  });

  it("espessura fina", () => {
    const { container } = render(<Barra fracao={0.1} espessura="sm" className="mt-2" />);
    expect(container.querySelector(".h-1\\.5.mt-2")).not.toBeNull();
  });
});

describe("Chip e SeloVeredito", () => {
  it.each(["neutro", "marca", "sucesso", "atencao", "perigo", "info"] as const)("tom %s", (tom) => {
    render(<Chip tom={tom}>rótulo</Chip>);
    expect(screen.getByText("rótulo")).toBeInTheDocument();
  });

  it("o selo usa o rótulo que a API mandou, com ícone decorativo", () => {
    const { container } = render(<SeloVeredito veredito="APTO COM COMPRA" rotulo="Dá, comprando 1 item" />);
    expect(screen.getByText("Dá, comprando 1 item")).toBeInTheDocument();
    expect(container.querySelector("[aria-hidden='true'] svg")).not.toBeNull();
    expect(container.querySelector(".text-info")).not.toBeNull();
  });
});
