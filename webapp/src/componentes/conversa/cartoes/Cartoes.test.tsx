/**
 * Os cards da conversa: o registro (tipo desconhecido é ignorado), a moldura
 * com "Refazer a conta" e a fronteira de erro, os cards da despensa com os
 * dados completos e com o mínimo, as leituras seguras e a confirmação de
 * preço antes de gravar a decisão.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/despensa",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import type { CartaoNaTela } from "@/lib/conversa/estado";
import { contrato } from "@/teste/fixturas";
import { esperarPromessas, lojaDeTeste } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import { ProvedorDaConversa } from "../ProvedorDaConversa";
import { ConfirmarPreco } from "./ConfirmarPreco";
import { bool, dinheiro, imagem, lista, num, obj, objetos, parametro, rotaInterna, str, urlExterna, veredito } from "./leitura";
import { LimiteDoCartao, LinhaDoCartao, MolduraDoCartao, ROTULO_REFEITA } from "./Moldura";
import { CartaoDaConversa, CartoesDaResposta, componenteDoCartao } from "./registro";

const VISAO = contrato<Record<string, unknown>>("visao-geral.json");
const ITEM = contrato<Record<string, unknown>>("despensa-item.json");
const ORCAMENTO = contrato<{ orcamento: Record<string, unknown> }>("despensa.json").orcamento;

function cartao(tipo: CartaoNaTela["tipo"], dados: unknown, extras: Partial<CartaoNaTela> = {}): CartaoNaTela {
  return { id: `k-${tipo}`, tipo, dados, ref: { rota: null }, geradoTexto: "conta de hoje, 14:32", aoVivo: true, ...extras };
}

let rede: ReturnType<typeof vi.fn>;

beforeEach(() => {
  rede = vi.fn();
  vi.stubGlobal("fetch", rede);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function comLoja(ui: React.ReactElement, t: LojaDeTeste = lojaDeTeste()) {
  return { ...render(<ProvedorDaConversa loja={t.loja}>{ui}</ProvedorDaConversa>), ...t };
}

const envelope = (dados: unknown) => new Response(JSON.stringify({ ok: true, dados, erro: null, categoria: null, pergunta: null }));

describe("o registro", () => {
  it("tem um componente para cada tipo do contrato e ignora o resto", () => {
    expect(componenteDoCartao("despensa_resumo")).not.toBeNull();
    expect(componenteDoCartao("fontes")).not.toBeNull();
    expect(componenteDoCartao("inventado")).toBeNull();
    const { container } = comLoja(<CartaoDaConversa cartao={{ ...cartao("orcamento", {}), tipo: "inventado" as never }} historico={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("empilha só os que sabe mostrar; sem nenhum, nada", () => {
    const { container, rerender } = comLoja(
      <CartoesDaResposta
        cartoes={[cartao("orcamento", ORCAMENTO), { ...cartao("orcamento", {}), tipo: "inventado" as never }, cartao("ingrediente", ITEM, { aoVivo: false })]}
      />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
    rerender(
      <ProvedorDaConversa loja={lojaDeTeste().loja}>
        <CartoesDaResposta cartoes={[{ ...cartao("orcamento", {}), tipo: "inventado" as never }]} />
      </ProvedorDaConversa>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("muitos cards numa resposta", () => {
  const INGREDIENTE = (n: number, extras: Partial<CartaoNaTela> = {}) =>
    cartao("ingrediente", { ...ITEM, nome: `Item ${n}` }, { id: `k-${n}`, ref: { rota: `/api/despensa/itens/item-${n}` }, ...extras });

  it("o mesmo card repetido no turno fica só no último, com os dados de depois", () => {
    comLoja(
      <CartoesDaResposta
        cartoes={[
          cartao("orcamento", ORCAMENTO, { id: "k-a", ref: { rota: "/api/orcamento" } }),
          cartao("ingrediente", ITEM, { id: "k-b", ref: { rota: "/api/despensa/itens/alcaparras" } }),
          cartao("orcamento", ORCAMENTO, { id: "k-c", ref: { rota: "/api/orcamento" } }),
        ]}
      />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("três ou mais do mesmo tipo viram um grupo: dois à mostra e Ver mais com quantos faltam", async () => {
    const { container } = comLoja(
      <CartoesDaResposta
        cartoes={[
          INGREDIENTE(1),
          cartao("orcamento", ORCAMENTO, { ref: { rota: "/api/orcamento" } }),
          INGREDIENTE(2),
          INGREDIENTE(3),
          INGREDIENTE(4, { aoVivo: false }),
        ]}
      />,
    );
    const grupo = screen.getByRole("region", { name: "4 ingredientes" });
    expect(within(grupo).getAllByRole("article")).toHaveLength(2);
    const verMais = within(grupo).getByRole("button", { name: /Ver mais/ });
    expect(verMais).toHaveTextContent("Ver mais 2 ingredientes");
    expect(verMais).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    fireEvent.click(verMais);
    expect(within(grupo).getAllByRole("article")).toHaveLength(4);
    expect(within(grupo).getByRole("button", { name: "Ver menos" })).toHaveAttribute("aria-expanded", "true");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("dois do mesmo tipo continuam soltos", () => {
    comLoja(<CartoesDaResposta cartoes={[INGREDIENTE(1), INGREDIENTE(2)]} />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });
});

describe("os cards da despensa", () => {
  it("o resumo: quanto pagou, os três mais parados, e a pendência que só preenche a caixa", async () => {
    const t = lojaDeTeste();
    const { container } = comLoja(<CartaoDaConversa cartao={cartao("despensa_resumo", VISAO)} historico={false} />, t);
    const card = screen.getByRole("article", { name: "O que a senhora tem" });
    expect(within(card).getByText("R$ 663,39")).toBeInTheDocument();
    expect(within(card).getByText("pagos em 37 ingredientes")).toBeInTheDocument();
    expect(within(card).getAllByRole("listitem").length).toBeLessThanOrEqual(3);
    expect(within(card).getByRole("link", { name: "Alcaparras" })).toHaveAttribute("href", "/despensa/alcaparras");
    expect(within(card).getByRole("link", { name: "Ver a despensa" })).toHaveAttribute("href", "/despensa");
    fireEvent.click(within(card).getByRole("button", { name: "Responder" }));
    expect(t.loja.ler().caixa).toMatchObject({
      texto: "A embalagem da cobertura de chocolate tem ",
      contexto: { tela: "conversa", tipo: "pendencia", id: "cobertura-de-chocolate", rotulo: "Cobertura de chocolate" },
    });
    await esperarPromessas();
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("o resumo com o mínimo: sem total, sem itens, pendência sem rascunho do backend", () => {
    comLoja(
      <CartaoDaConversa
        cartao={cartao("despensa_resumo", { pendencias: [{ pergunta: "Quanto pesa?", ingrediente: "Farinha" }], dinheiro_parado: { itens: [{ nome: "Sal", pago: null }] } })}
        historico={false}
      />,
    );
    expect(screen.getByText("pagos na despensa")).toBeInTheDocument();
    expect(screen.getByText("Sal")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    const semNada = comLoja(<CartaoDaConversa cartao={cartao("despensa_resumo", "quebrado")} historico={false} />);
    expect(within(semNada.container).queryByRole("button", { name: "Responder" })).toBeNull();
    expect(within(semNada.container).getByRole("link", { name: "Ver a despensa" })).toHaveAttribute("href", "/despensa");
  });

  it("o ingrediente: foto da API, quanto pagou, custo por unidade com a conta", () => {
    comLoja(<CartaoDaConversa cartao={cartao("ingrediente", ITEM)} historico={false} />);
    const card = screen.getByRole("article", { name: String(ITEM.nome) });
    expect(within(card).getByText(String((ITEM.pago as { texto: string }).texto))).toBeInTheDocument();
    expect(within(card).getByText(String(ITEM.derivacao))).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver na despensa" })).toHaveAttribute("href", String(ITEM.rota));
  });

  it("o ingrediente sem preço (cobertura sem o peso): o custo fica desconhecido, nunca zero", () => {
    comLoja(<CartaoDaConversa cartao={cartao("ingrediente", { nome: "Cobertura de chocolate", pago: null, custo_unitario: null, unidade: "kg" })} historico={false} />);
    expect(screen.getByText("Custo por kg")).toBeInTheDocument();
    expect(screen.getAllByText("valor ainda desconhecido")).toHaveLength(2);
    comLoja(<CartaoDaConversa cartao={cartao("ingrediente", null)} historico={false} />);
    expect(screen.getByRole("article", { name: "Ingrediente" })).toHaveTextContent("Custo por unidade");
  });

  it("o orçamento: quanto sobra, a barra, as últimas compras e se cabe", () => {
    const comCompras = {
      ...ORCAMENTO,
      fracao_gasta: 0.25,
      cabe: true,
      compras: [
        { id: 1, descricao: "Creme de leite", valor: { valor: 9, texto: "R$ 9,00" }, quando_texto: "hoje, 10:00" },
        { id: 2, descricao: "Milho", valor: { valor: 11, texto: "R$ 11,00" }, quando: "ontem" },
        { descricao: null, valor: null },
      ],
    };
    comLoja(<CartaoDaConversa cartao={cartao("orcamento", comCompras)} historico={false} />);
    const card = screen.getByRole("article", { name: "Quanto ainda sobra" });
    expect(within(card).getByText("Cabe no orçamento")).toBeInTheDocument();
    expect(within(card).getByRole("meter", { name: "Orçamento já usado" })).toBeInTheDocument();
    expect(within(card).getByText("Creme de leite")).toBeInTheDocument();
    expect(within(card).getByText("ontem")).toBeInTheDocument();
    expect(within(card).getByText("Compra")).toBeInTheDocument();
    expect(within(card).getByText("de R$ 80,00 para as compras")).toBeInTheDocument();

    comLoja(<CartaoDaConversa cartao={cartao("orcamento", { cabe_no_orcamento: false, fracao_usada: 1 })} historico={false} />);
    expect(screen.getByText("Não cabe no orçamento")).toBeInTheDocument();
  });
});

describe("a moldura", () => {
  it("no histórico, um card com dinheiro refaz a conta pela rota dele", async () => {
    rede.mockResolvedValueOnce(envelope({ ...ORCAMENTO, restante: { valor: 71, texto: "R$ 71,00" } }));
    comLoja(
      <CartaoDaConversa cartao={cartao("orcamento", ORCAMENTO, { ref: { rota: "/api/orcamento" }, aoVivo: false })} historico />,
    );
    expect(screen.getByText("conta de hoje, 14:32")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Refazer a conta" }));
      await esperarPromessas();
    });
    expect(rede.mock.calls[0]?.[0]).toBe("/motor/orcamento");
    await waitFor(() => expect(screen.getByText("R$ 71,00")).toBeInTheDocument());
    expect(screen.getByText(ROTULO_REFEITA)).toBeInTheDocument();
  });

  it("refazer que falha avisa; enquanto refaz, não repete; ao vivo não oferece", async () => {
    let soltar: (resposta: Response) => void = () => {};
    rede.mockImplementationOnce(() => new Promise((resolver) => (soltar = resolver)));
    comLoja(
      <CartaoDaConversa cartao={cartao("orcamento", ORCAMENTO, { ref: { rota: "/api/orcamento" }, aoVivo: false })} historico />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Refazer a conta" }));
    const refazendo = screen.getByRole("button", { name: "Refazendo a conta…" });
    fireEvent.click(refazendo);
    expect(rede).toHaveBeenCalledTimes(1);
    await act(async () => {
      soltar(new Response("x", { status: 500 }));
      await esperarPromessas(10);
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Não consegui refazer a conta agora");

    comLoja(<CartaoDaConversa cartao={cartao("orcamento", ORCAMENTO, { ref: { rota: "/api/orcamento" } })} historico={false} />);
    expect(screen.getAllByRole("button", { name: /Refazer/ })).toHaveLength(1);
  });

  it("peças soltas da moldura: selo, mídia, rodapé e a linha de recibo", () => {
    render(
      <MolduraDoCartao sobretitulo="Teste" titulo="Título" selo={<span>selo</span>} midia={<img alt="" src="" />} rodape={<a href="/x">link</a>}>
        <LinhaDoCartao rotulo="Pagou" valor="R$ 1,00" detalhe="a conta" className="extra" />
      </MolduraDoCartao>,
    );
    expect(screen.getByText("selo")).toBeInTheDocument();
    expect(screen.getByText("a conta")).toBeInTheDocument();
    render(<MolduraDoCartao sobretitulo="Sem nada" titulo="Vazio" />);
    expect(screen.getByRole("article", { name: "Vazio" })).toBeInTheDocument();
  });

  it("um card que quebra vira uma linha, e tentar de novo remonta", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let quebra = true;
    function Quebradico() {
      if (quebra) throw new Error("dados estranhos");
      return <p>voltou</p>;
    }
    render(
      <LimiteDoCartao>
        <Quebradico />
      </LimiteDoCartao>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Não consegui mostrar este cartão.");
    quebra = false;
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(screen.getByText("voltou")).toBeInTheDocument();
  });
});

describe("as leituras seguras", () => {
  it("cada leitura devolve o valor certo ou nulo", () => {
    expect(obj([1])).toBeNull();
    expect(lista("x")).toEqual([]);
    expect(objetos([{ a: 1 }, 2, null])).toEqual([{ a: 1 }]);
    expect(str("  ")).toBeNull();
    expect(num(Number.NaN)).toBeNull();
    expect(bool("sim")).toBeNull();
    expect(bool(false)).toBe(false);
    expect(dinheiro({ texto: "R$ 1,00" })?.texto).toBe("R$ 1,00");
    expect(Number.isNaN(dinheiro({ texto: "R$ 1,00" })?.valor)).toBe(true);
    expect(dinheiro({ valor: 1 })).toBeNull();
    expect(imagem({ url: "/motor/imagens/3f2a9c0d1b7e4a55" })).toEqual({ url: "/motor/imagens/3f2a9c0d1b7e4a55", credito: "" });
    expect(imagem({ url: "https://fora.com/foto.jpg" })).toBeNull();
    expect(rotaInterna("/receitas/arroz?aba=x#y")).toBe("/receitas/arroz?aba=x#y");
    expect(rotaInterna("//fora.com")).toBeNull();
    expect(rotaInterna("/\\fora")).toBeNull();
    expect(rotaInterna("/api/receitas")).toBeNull();
    expect(rotaInterna("/motor/x")).toBeNull();
    expect(rotaInterna("/com espaço")).toBeNull();
    expect(rotaInterna("receitas")).toBeNull();
    expect(urlExterna("https://tudogostoso.com.br")).toBe("https://tudogostoso.com.br/");
    expect(urlExterna(null)).toBeNull();
    expect(veredito("APTO")).toBe("APTO");
    expect(veredito("TALVEZ")).toBeNull();
    expect(parametro({ ref: { parametros: { prato: "Arroz" } } }, "prato")).toBe("Arroz");
    expect(parametro({ ref: {} }, "prato")).toBeUndefined();
  });
});

describe("ConfirmarPreco", () => {
  const ponto = {
    preco: { valor: 18, texto: "R$ 18,00" },
    taxa: { valor: 1.8, texto: "R$ 1,80" },
    recebe: { valor: 16.2, texto: "R$ 16,20" },
    lucro: { valor: 13.73, texto: "R$ 13,73" },
    food_cost: 0.14,
    margem: 0.76,
    da_prejuizo: false,
    explicacao: "0,90 × R$ 18,00 − R$ 2,47 = R$ 13,73",
  };

  it("busca a conta de novo, mostra, e só então manda a decisão com o mesmo preço", async () => {
    rede.mockResolvedValueOnce(envelope(ponto));
    const aoFechar = vi.fn();
    const t = lojaDeTeste();
    await t.loja.abrirConversa("cv-1");
    comLoja(<ConfirmarPreco pedido={{ prato: "Arroz com frango", valor: 18, texto: "R$ 18,00" }} aoFechar={aoFechar} />, t);
    expect(screen.getByRole("status")).toHaveTextContent("Conferindo a conta com esse preço…");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Vou cobrar este" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    expect(await screen.findByText("R$ 16,20")).toBeInTheDocument();
    expect(rede.mock.calls[0]?.[0]).toBe("/motor/preco-em?prato=Arroz%20com%20frango&preco=18");
    expect(screen.getByRole("dialog", { name: "Cobrar R$ 18,00 por porção?" })).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Vou cobrar este" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", {
      texto: "Vou cobrar R$ 18,00 por porção de arroz com frango.",
      acao: { tipo: "decidir", prato: "Arroz com frango", decisao: "aceito", preco: 18 },
      id_cliente: "u-1",
    });
    expect(aoFechar).toHaveBeenCalled();
  });

  it("prejuízo avisa; a conta que falha deixa conferir de novo; sem pedido, fechado", async () => {
    rede.mockRejectedValueOnce(new TypeError("fetch failed")).mockResolvedValueOnce(envelope({ ...ponto, da_prejuizo: true, preco: null }));
    const aoFechar = vi.fn();
    comLoja(<ConfirmarPreco pedido={{ prato: "Arroz", valor: 2, texto: null }} aoFechar={aoFechar} />);
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não consegui");
    await act(async () => {
      fireEvent.click(within(alerta).getByRole("button", { name: "Conferir de novo" }));
      await esperarPromessas();
    });
    expect(await screen.findByText(/a senhora perde dinheiro em cada porção/)).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Cobrar este preço por porção?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Agora não" }));
    expect(aoFechar).toHaveBeenCalled();

    const fechado = comLoja(<ConfirmarPreco pedido={null} aoFechar={() => {}} />);
    expect(fechado.container.querySelector("dialog")).not.toHaveAttribute("open");
  });

  it("uma resposta que chega depois de fechar é ignorada", async () => {
    let soltar: (resposta: Response) => void = () => {};
    rede.mockImplementationOnce(() => new Promise((resolver) => (soltar = resolver)));
    const { unmount } = comLoja(<ConfirmarPreco pedido={{ prato: "Arroz", valor: 18 }} aoFechar={() => {}} />);
    unmount();
    await act(async () => {
      soltar(envelope(ponto));
      await esperarPromessas();
    });
    let rejeitar: (erro: unknown) => void = () => {};
    rede.mockImplementationOnce(() => new Promise((_ok, erro) => (rejeitar = erro)));
    const outro = comLoja(<ConfirmarPreco pedido={{ prato: "Arroz", valor: 18 }} aoFechar={() => {}} />);
    outro.unmount();
    await act(async () => {
      rejeitar(new Error("x"));
      await esperarPromessas();
    });
  });
});
