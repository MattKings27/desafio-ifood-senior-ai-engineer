/**
 * A tela inicial: o próximo passo, os cinco números clicáveis, as perguntas com
 * o botão Chat, o dinheiro parado com o "Ver mais", as receitas e a prévia do
 * cardápio. Os dados são os do contrato (`visao-geral.json`).
 */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/despensa", () => ({ corrigirItem: vi.fn(), desfazerMudanca: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({
  responderSobreAReceita: vi.fn(),
  responderSobreACozinha: vi.fn(async () => ({ ok: true, dados: { texto: "Anotei que a senhora tem forno." } })),
  responderLimiteDaCozinha: vi.fn(),
  informarPrecoDoQueFalta: vi.fn(),
}));

import { responderSobreACozinha } from "@/lib/acoes/receitas";
import type { VisaoGeral } from "@/lib/api/visao-geral";
import { contrato } from "@/teste/fixturas";
import { PERGUNTAS_QUE_NAO_SAO_DELA, TEXTOS_QUE_NUNCA_APARECEM, montar } from "@/teste/receitas";

import { indicadoresDe } from "./Indicadores";
import { TelaInicial } from "./TelaInicial";

const VISAO = contrato<VisaoGeral>("visao-geral.json");

function visao(extras: Partial<VisaoGeral> = {}): VisaoGeral {
  return { ...structuredClone(VISAO), ...extras };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("o topo da tela inicial", () => {
  it("diz o próximo passo com o link que ele pede", () => {
    montar(<TelaInicial visao={visao()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    const passo = screen.getByRole("region", { name: "O próximo passo" });
    expect(within(passo).getByText(VISAO.proximo_passo.texto)).toBeInTheDocument();
    expect(within(passo).getByRole("link", { name: "Responder agora" })).toHaveAttribute("href", "/conversa?comecar=cozinha");
  });

  it("o passo que aponta para as perguntas some quando não há pergunta da cozinha para ela responder aqui", () => {
    montar(
      <TelaInicial
        visao={visao({ perguntas_da_cozinha: [], proximo_passo: { texto: "Responda a pergunta.", acao: { tipo: "link", rota: "/#perguntas" } } })}
      />,
    );
    expect(screen.queryByRole("region", { name: "O próximo passo" })).not.toBeInTheDocument();
  });

  it("o passo que é conversa abre o chat com o pedido escrito, sem mandar", () => {
    const { loja } = montar(
      <TelaInicial
        visao={visao({ proximo_passo: { texto: "Peça receitas.", acao: { tipo: "perguntar", rascunho: "Que receitas eu faço?" } } })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Pedir ao agente" }));
    expect(loja.ler().caixa.texto).toBe("Que receitas eu faço?");
  });

  it("um passo sem destino conhecido ainda tem o link, e sem rota não tem botão", () => {
    const { refazer } = montar(<TelaInicial visao={visao({ proximo_passo: { texto: "Veja.", acao: { tipo: "link", rota: "/cozinha" } } })} />);
    expect(screen.getByRole("link", { name: "Ir agora" })).toHaveAttribute("href", "/cozinha");
    refazer(<TelaInicial visao={visao({ proximo_passo: { texto: "Nada a fazer.", acao: { tipo: "link" } } })} />);
    expect(within(screen.getByRole("region", { name: "O próximo passo" })).queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("os cinco números", () => {
  it("cada cartão é um link para a tela dele, com o texto da API", () => {
    montar(<TelaInicial visao={visao()} />);
    const numeros = screen.getByRole("region", { name: "Os números de agora" });
    const links = within(numeros).getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Despensa", "/despensa"],
      ["Orçamento", "/despensa#orcamento"],
      ["Receitas", "/receitas"],
      ["Cardápio", "/cardapio"],
      ["Cozinha", "/cozinha"],
    ]);
    expect(within(numeros).getByText(VISAO.kpis.despensa.total.texto)).toBeInTheDocument();
    expect(within(numeros).getByText(`restam dos ${VISAO.kpis.orcamento.inicial.texto}; ${VISAO.kpis.orcamento.texto}`)).toBeInTheDocument();
    expect(within(numeros).getByText(VISAO.kpis.cozinha.texto)).toBeInTheDocument();
    expect(within(numeros).getByRole("meter", { name: "Cozinha respondida pela senhora" })).toBeInTheDocument();
  });

  it("a lista de números sai dos indicadores da API, na ordem da tela", () => {
    expect(indicadoresDe(VISAO.kpis).map((indicador) => indicador.chave)).toEqual([
      "despensa",
      "orcamento",
      "receitas",
      "cardapio",
      "cozinha",
    ]);
  });
});

describe("as perguntas", () => {
  it("a da cozinha tem o botão Chat, que abre a conversa com a pergunta; a da despensa não é pergunta", () => {
    const { loja, container } = montar(<TelaInicial visao={visao()} />);
    const perguntas = screen.getByRole("region", { name: "Preciso perguntar uma coisa" });
    const chats = within(perguntas).getAllByRole("button", { name: "Chat" });
    expect(chats).toHaveLength(1);
    const [cozinha] = VISAO.perguntas_da_cozinha;
    fireEvent.click(chats[0] as HTMLElement);
    expect(loja.ler().caixa.texto).toBe(cozinha?.rascunho_chat);
    expect(loja.ler().caixa.contexto?.rotulo).toBe(cozinha?.pergunta.texto);
    expect(chats[0]).toHaveAccessibleDescription(cozinha?.pergunta.texto ?? "");
    // O peso da embalagem e o preço pago nunca são pergunta: nem o texto, nem o campo.
    const [pendencia] = VISAO.pendencias;
    expect(container.textContent).not.toContain(pendencia?.pergunta ?? "");
    expect(within(perguntas).queryByRole("button", { name: "Responder no chat" })).not.toBeInTheDocument();
    for (const texto of TEXTOS_QUE_NUNCA_APARECEM) expect(container.textContent).not.toMatch(texto);
    expect(within(perguntas).getByRole("link", { name: "Ver as receitas que esperam" })).toHaveAttribute(
      "href",
      "/receitas?aba=falta_resposta",
    );
  });

  it("a pergunta de outro assunto que ainda chegar da API não aparece", () => {
    const [cozinha] = VISAO.perguntas_da_cozinha;
    const [peso] = PERGUNTAS_QUE_NAO_SAO_DELA;
    const deOutroAssunto = { ...cozinha!, id: "medida:alcaparras", pergunta: peso! };
    montar(<TelaInicial visao={visao({ perguntas_da_cozinha: [deOutroAssunto] })} />);
    expect(screen.queryByRole("region", { name: /Preciso perguntar/ })).not.toBeInTheDocument();
  });

  it("a pergunta da cozinha se responde ali mesmo, no perfil da cozinha", async () => {
    montar(<TelaInicial visao={visao()} />);
    fireEvent.click(screen.getByRole("radio", { name: "Tenho" }));
    await waitFor(() => expect(responderSobreACozinha).toHaveBeenCalledWith("equipamentos", "forno", "tem"));
  });

  it("duas perguntas falam no plural, e sem pergunta a seção some", () => {
    const [cozinha] = VISAO.perguntas_da_cozinha;
    const duas = [cozinha!, { ...cozinha!, id: "equipamento:batedeira" }];
    const { refazer } = montar(<TelaInicial visao={visao({ perguntas_da_cozinha: duas })} />);
    expect(screen.getByRole("region", { name: "Preciso perguntar algumas coisas" })).toBeInTheDocument();
    refazer(<TelaInicial visao={visao({ perguntas_da_cozinha: [], pendencias: [] })} />);
    expect(screen.queryByRole("region", { name: /Preciso perguntar/ })).not.toBeInTheDocument();
  });
});

describe("onde o dinheiro está parado", () => {
  it("mostra cinco, e o Ver mais abre até o último, cada um levando ao ingrediente", () => {
    montar(<TelaInicial visao={visao()} />);
    const secao = screen.getByRole("region", { name: "Onde o dinheiro está parado" });
    expect(within(secao).getAllByRole("article")).toHaveLength(5);
    const verMais = within(secao).getByRole("button", { name: /Ver mais/ });
    expect(verMais).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(verMais);
    const todos = within(secao).getAllByRole("article");
    expect(todos).toHaveLength(VISAO.dinheiro_parado.itens.length);
    const [primeiro] = VISAO.dinheiro_parado.itens;
    expect(within(secao).getByRole("link", { name: primeiro?.nome })).toHaveAttribute("href", primeiro?.rota);
    expect(within(secao).getByText(VISAO.dinheiro_parado.dois_maiores.texto)).toBeInTheDocument();
    expect(within(secao).getAllByText("nenhuma receita usa ainda").length).toBeGreaterThan(0);
  });
});

describe("as receitas e o cardápio", () => {
  it("as receitas que dão pra fazer vêm nos cards da grade", () => {
    montar(<TelaInicial visao={visao()} />);
    const secao = screen.getByRole("region", { name: "Receitas que dão pra fazer" });
    const [primeira] = VISAO.receitas_recomendadas;
    expect(within(secao).getByRole("link", { name: primeira?.nome })).toHaveAttribute("href", primeira?.rota);
    expect(within(secao).getByRole("link", { name: /Ver todas/ })).toHaveAttribute("href", "/receitas");
  });

  it("sem receita, convida a pedir ao agente", () => {
    const { loja } = montar(<TelaInicial visao={visao({ receitas_recomendadas: [] })} />);
    expect(screen.getByText("Nenhuma receita dá pra fazer ainda")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pedir receitas" }));
    expect(loja.ler().caixa.texto).toMatch(/^Que receitas eu consigo fazer/);
  });

  it("a prévia do cardápio traz o preço e o lucro de cada prato, com o aviso da conta", () => {
    montar(<TelaInicial visao={visao()} />);
    const secao = screen.getByRole("region", { name: "O cardápio" });
    const [arroz, milho] = VISAO.cardapio_previa;
    expect(within(secao).getByRole("link", { name: arroz?.prato })).toHaveAttribute("href", arroz?.rota);
    expect(within(secao).getByText(arroz?.lucro_porcao?.texto ?? "")).toBeInTheDocument();
    expect(within(secao).getByText(milho?.aviso ?? "")).toBeInTheDocument();
  });

  it("sem prato no cardápio, leva às receitas", () => {
    montar(<TelaInicial visao={visao({ cardapio_previa: [] })} />);
    expect(screen.getByText("Nenhum prato no cardápio ainda")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Escolher nas receitas" })).toHaveAttribute("href", "/receitas");
  });
});

describe("acessibilidade", () => {
  it("a tela inteira não tem violação do axe", async () => {
    const { container } = montar(<TelaInicial visao={visao()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
