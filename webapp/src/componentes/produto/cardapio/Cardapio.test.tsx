/**
 * O cardápio: os pratos com a conta de agora, "Mudar preço" pela conversa,
 * "Tirar do cardápio" com a confirmação e o "Desfazer" no aviso, o resumo com
 * a linha dos R$ 80,00, os pratos que ela não quer e o histórico em frases.
 */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/cardapio", () => ({
  tirarDoCardapio: vi.fn(async (prato: string) => ({ ok: true, dados: { texto: `A senhora tirou o ${prato.toLowerCase()} do cardápio.` } })),
  desfazerNoCardapio: vi.fn(async (prato: string) => ({
    ok: true,
    dados: { texto: `A senhora voltou atrás: o ${prato.toLowerCase()} está de novo no cardápio.` },
  })),
}));

import { desfazerNoCardapio, tirarDoCardapio } from "@/lib/acoes/cardapio";
import type { CardapioCompleto, DecisaoNoHistorico } from "@/lib/api/cardapio";
import { contrato } from "@/teste/fixturas";
import { montar } from "@/teste/receitas";

import { TelaDoCardapio } from "./TelaDoCardapio";

const CARDAPIO = contrato<CardapioCompleto>("cardapio.json");
const [ARROZ, MILHO] = CARDAPIO.pratos;

function cardapio(extras: Partial<CardapioCompleto> = {}): CardapioCompleto {
  return { ...structuredClone(CARDAPIO), ...extras };
}

afterEach(() => {
  vi.clearAllMocks();
});

function cartao(nome: string): HTMLElement {
  const link = screen.getByRole("link", { name: nome });
  return link.closest("article") as HTMLElement;
}

describe("os pratos", () => {
  it("cada prato tem o preço dela, o que chega, o custo, o lucro e a conta escrita", () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    expect(screen.getByRole("heading", { level: 1, name: "O cardápio" })).toBeInTheDocument();
    const arroz = cartao(ARROZ?.prato ?? "");
    expect(within(arroz).getByRole("link", { name: ARROZ?.prato })).toHaveAttribute("href", ARROZ?.rota);
    for (const valor of [ARROZ?.preco, ARROZ?.recebe, ARROZ?.custo_porcao, ARROZ?.lucro_porcao]) {
      expect(within(arroz).getByText(valor?.texto ?? "")).toBeInTheDocument();
    }
    expect(within(arroz).getByText(ARROZ?.derivacao ?? "")).toBeInTheDocument();
    expect(within(arroz).getByText(`“${ARROZ?.notas}”`)).toBeInTheDocument();
    expect(within(arroz).getByText(ARROZ?.nota?.texto ?? "")).toBeInTheDocument();
    const milho = cartao(MILHO?.prato ?? "");
    expect(within(milho).getByText(MILHO?.aviso ?? "")).toBeInTheDocument();
  });

  it("o resumo vem do servidor, com a linha dos complementos levando ao orçamento", () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    const resumo = screen.getByRole("region", { name: "O resumo do cardápio" });
    expect(within(resumo).getByText(CARDAPIO.resumo.texto)).toBeInTheDocument();
    expect(within(resumo).getByText(CARDAPIO.resumo.preco_medio?.texto ?? "")).toBeInTheDocument();
    expect(within(resumo).getByText(CARDAPIO.resumo.margem_media_texto)).toBeInTheDocument();
    expect(within(resumo).getByText(CARDAPIO.resumo.orcamento_texto)).toBeInTheDocument();
    expect(within(resumo).getByRole("link", { name: /Ver os complementos/ })).toHaveAttribute("href", "/despensa#orcamento");
  });

  it("Mudar preço abre a conversa com o pedido escrito e o prato junto", () => {
    const { loja } = montar(<TelaDoCardapio cardapio={cardapio()} />);
    fireEvent.click(within(cartao(ARROZ?.prato ?? "")).getByRole("button", { name: "Mudar preço" }));
    expect(loja.ler().caixa.texto).toBe("Quero mudar o preço de arroz com frango para ");
    expect(loja.ler().caixa.contexto).toEqual({ tela: "cardapio", tipo: "prato", id: ARROZ?.slug, rotulo: ARROZ?.prato });
  });

  it("Tirar do cardápio pede confirmação, e o aviso traz o Desfazer", async () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    fireEvent.click(within(cartao(ARROZ?.prato ?? "")).getByRole("button", { name: "Tirar do cardápio" }));
    const dialogo = screen.getByRole("alertdialog", { name: `Tirar ${ARROZ?.prato} do cardápio?` });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Tirar do cardápio" }));
    await waitFor(() => expect(tirarDoCardapio).toHaveBeenCalledWith(ARROZ?.prato, expect.any(String)));
    // O aviso tem o "Desfazer" sozinho; o do histórico diz também a decisão.
    fireEvent.click(await screen.findByRole("button", { name: "Desfazer" }));
    await waitFor(() => expect(desfazerNoCardapio).toHaveBeenCalledWith(ARROZ?.prato, expect.any(String)));
    expect(await screen.findByText("A senhora voltou atrás: o arroz com frango está de novo no cardápio.")).toBeInTheDocument();
  });

  it("cancelar a confirmação não tira nada", () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    fireEvent.click(within(cartao(ARROZ?.prato ?? "")).getByRole("button", { name: "Tirar do cardápio" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(tirarDoCardapio).not.toHaveBeenCalled();
  });

  it("se a API recusa, o aviso diz o porquê e não há Desfazer", async () => {
    vi.mocked(tirarDoCardapio).mockResolvedValueOnce({ ok: false, erro: { categoria: "regra", mensagem: "Não deu para tirar agora." } });
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    fireEvent.click(within(cartao(ARROZ?.prato ?? "")).getByRole("button", { name: "Tirar do cardápio" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Tirar do cardápio" }));
    expect(await screen.findByText("Não deu para tirar agora.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Desfazer" })).not.toBeInTheDocument();
  });

  it("sem prato no cardápio, leva às receitas", () => {
    montar(<TelaDoCardapio cardapio={cardapio({ pratos: [], nao_quer: [], historico: [] })} />);
    expect(screen.getByText("Nenhum prato no cardápio ainda")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver as receitas" })).toHaveAttribute("href", "/receitas");
    expect(screen.getByText(/Nenhuma decisão ainda/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Pratos que a senhora não quer" })).not.toBeInTheDocument();
  });
});

describe("os que ela não quer e o histórico", () => {
  it("os pratos que ela não quer levam à receita, com o motivo", () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    const secao = screen.getByRole("region", { name: "Pratos que a senhora não quer" });
    const [assado] = CARDAPIO.nao_quer;
    expect(within(secao).getByRole("link", { name: assado?.prato })).toHaveAttribute("href", assado?.rota);
    expect(within(secao).getByText(assado?.motivo_texto ?? "")).toBeInTheDocument();
  });

  it("o histórico diz cada decisão em frases, com o desfazer só na que vale hoje", async () => {
    montar(<TelaDoCardapio cardapio={cardapio()} />);
    const secao = screen.getByRole("region", { name: "O que a senhora decidiu" });
    for (const decisao of CARDAPIO.historico) expect(within(secao).getByText(decisao.texto_humano)).toBeInTheDocument();
    expect(within(secao).getAllByText(/pela conversa/).length).toBeGreaterThan(0);
    const desfazer = within(secao).getAllByRole("button", { name: /^Desfazer/ });
    expect(desfazer).toHaveLength(CARDAPIO.historico.filter((d) => d.pode_desfazer).length);
    fireEvent.click(desfazer[0] as HTMLElement);
    await waitFor(() => expect(desfazerNoCardapio).toHaveBeenCalledWith(CARDAPIO.historico[0]?.prato, expect.any(String)));
    expect(within(secao).getAllByRole("link", { name: /^Ver a receita/ }).length).toBeGreaterThan(0);
    expect(within(secao).getByRole("link", { name: "Ver no histórico: O que a senhora decidiu" })).toHaveAttribute(
      "href",
      "/trilha?categoria=cardapio",
    );
  });

  it("um histórico longo mostra seis e abre o resto; tipo desconhecido tem o marcador neutro", () => {
    const extra: DecisaoNoHistorico = { ...(CARDAPIO.historico[0] as DecisaoNoHistorico), id: 99, tipo: "outro", canal: "whatever", pode_desfazer: false };
    const historico = [...CARDAPIO.historico, extra, { ...extra, id: 100 }];
    montar(<TelaDoCardapio cardapio={cardapio({ historico })} />);
    const secao = screen.getByRole("region", { name: "O que a senhora decidiu" });
    expect(within(secao).getAllByRole("listitem")).toHaveLength(6);
    fireEvent.click(within(secao).getByRole("button", { name: /Ver mais/ }));
    expect(within(secao).getAllByRole("listitem")).toHaveLength(historico.length);
  });
});

describe("acessibilidade", () => {
  it("a tela inteira não tem violação do axe", async () => {
    const { container } = montar(<TelaDoCardapio cardapio={cardapio()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
