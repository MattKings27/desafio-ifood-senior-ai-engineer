/**
 * Cada card da conversa com o exemplo publicado em `contratos/web/cartoes/`:
 * mostra o que importa daquele card, os botões mandam a ação do contrato (ou
 * só preenchem a caixa), nenhum jargão chega à tela e o axe não acha problema.
 * Depois, cada card com os dados no mínimo, que o backend manda enquanto a
 * rota dele não existe.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversa",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import type { CartaoDaConversa as CartaoDaApi } from "@/lib/api/conversa";
import type { TipoDeCartao } from "@/lib/conversa/cartoes";
import { TIPOS_DE_CARTAO } from "@/lib/conversa/cartoes";
import { cartaoNaTela } from "@/lib/conversa/estado";
import { encontrarJargao } from "@/lib/formato";
import { esperarPromessas, lojaDeTeste } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";
import { contrato } from "@/teste/fixturas";

import { ProvedorDaConversa } from "../ProvedorDaConversa";
import { CartaoDaConversa } from "./registro";

function exemplo(tipo: TipoDeCartao) {
  const bruto = contrato<CartaoDaApi>(`cartoes/${tipo}.json`);
  const cartao = cartaoNaTela(bruto, true);
  if (!cartao) throw new Error(`exemplo inválido: ${tipo}`);
  return cartao;
}

let rede: ReturnType<typeof vi.fn>;

beforeEach(() => {
  rede = vi.fn();
  vi.stubGlobal("fetch", rede);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function montar(tipo: TipoDeCartao, extras: { dados?: unknown; historico?: boolean; parametros?: Record<string, unknown> } = {}, t: LojaDeTeste = lojaDeTeste()) {
  await t.loja.abrirConversa("cv-1");
  const base = exemplo(tipo);
  const cartao = {
    ...base,
    ...(extras.dados === undefined ? {} : { dados: extras.dados }),
    ...(extras.parametros ? { ref: { ...base.ref, parametros: extras.parametros } } : {}),
  };
  const resultado = render(
    <ProvedorDaConversa loja={t.loja}>
      <CartaoDaConversa cartao={cartao} historico={extras.historico ?? false} />
    </ProvedorDaConversa>,
  );
  return { ...resultado, ...t };
}

const envelope = (dados: unknown) => new Response(JSON.stringify({ ok: true, dados, erro: null, categoria: null, pergunta: null }));

describe("todo exemplo publicado vira um card, sem jargão e sem problema de acessibilidade", () => {
  it.each(TIPOS_DE_CARTAO)("%s", async (tipo) => {
    const { container } = await montar(tipo);
    expect(container.querySelector("article")).not.toBeNull();
    const texto = [container.textContent ?? "", ...[...container.querySelectorAll("[aria-label], [title], [alt]")].map((e) => e.getAttribute("aria-label") ?? e.getAttribute("title") ?? e.getAttribute("alt") ?? "")].join("\n");
    expect(encontrarJargao(texto)).toEqual([]);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("receita e viabilidade", () => {
  it("a receita: foto, fonte com link de fora, tempo, nota, e 'Dá pra eu fazer?' manda com o contexto", async () => {
    const t = await montar("receita");
    const card = screen.getByRole("article", { name: "Carne moída com arroz na panela de pressão" });
    expect(within(card).getByText("Receita de TudoGostoso")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Abrir no TudoGostoso/ })).toHaveAttribute("target", "_blank");
    expect(within(card).getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", "/receitas/f8fc24c7f065125e");
    expect(within(card).getByText("nota 87,8")).toBeInTheDocument();
    expect(within(card).getByText("Receita de Leuda M. V. Xavier")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "Dá pra eu fazer?" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({
      texto: "Dá pra eu fazer Carne moída com arroz na panela de pressão?",
      contexto: { tela: "receitas", tipo: "receita", id: "f8fc24c7f065125e", rotulo: "Carne moída com arroz na panela de pressão" },
    }));
  });

  it("a receita com o mínimo: sem foto, sem fonte, sem nota", async () => {
    await montar("receita", { dados: { nome: "Bolo", slug: "bolo" }, parametros: {} });
    const card = screen.getByRole("article", { name: "Bolo" });
    expect(within(card).getByText("Receita")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", "/receitas/bolo");
    await montar("receita", { dados: null, parametros: {} });
    expect(screen.getAllByRole("article").at(-1)).toHaveAccessibleName("Receita");
  });

  it("a viabilidade: o que tem, o que falta com o custo, os avisos e a pergunta que abre a caixa", async () => {
    const t = await montar("viabilidade");
    const card = screen.getByRole("article", { name: "Carne moída com arroz na panela de pressão" });
    expect(within(card).getByText("Falta saber")).toBeInTheDocument();
    expect(within(card).getByText("A senhora tem")).toBeInTheDocument();
    expect(within(card).getByText("tem 1,5 kg, sobram 1 kg")).toBeInTheDocument();
    expect(within(card).getByText("1 lata, R$ 6,00")).toBeInTheDocument();
    expect(within(card).getByText(/cabe nos R\$ 80,00 que restam/)).toBeInTheDocument();
    expect(within(card).getByText(/outra panela no fogo ao mesmo tempo/)).toBeInTheDocument();
    expect(within(card).getByText("Vai a gosto:").parentElement).toHaveTextContent("Vai a gosto: Sal.");
    expect(within(card).getByText("Opcional:").parentElement).toHaveTextContent("Opcional: Salsinha (cheiro-verde).");
    expect(within(card).getByText("Não consegui ler:").parentElement).toHaveTextContent("temperos de sua preferência.");
    fireEvent.click(within(card).getByRole("button", { name: "Responder" }));
    expect(t.loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "receita", id: "f8fc24c7f065125e", rotulo: "Carne moída com arroz na panela de pressão" });
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });

  it("a salsinha e a cebolinha do mesmo cheiro-verde não brigam pela mesma chave", async () => {
    // O caso real: "Frango com alcaparras" pedia as duas, e as duas saem do
    // mesmo item dela. A chave repetida virava aviso do React na conversa.
    const erro = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await montar("viabilidade", {
      dados: {
        nome: "Frango com alcaparras",
        veredito: "FALTA INFO",
        ingredientes: [
          { nome: "Salsinha (cheiro-verde)", item_id: "salsinha-cheiro-verde", situacao: "tem", precisa: { texto: "2 colheres de sopa" } },
          { nome: "Salsinha (cheiro-verde)", item_id: "salsinha-cheiro-verde", situacao: "tem", precisa: { texto: "2 colheres de sopa" } },
        ],
        avisos: [{ tipo: "bocas", texto: "Uma boca só." }, { tipo: "bocas", texto: "Uma boca só." }],
        perguntas: [
          { tipo: "ingrediente", campo: "alcaparras", texto: "Não sei quanto pesa uma colher de sopa de alcaparras." },
          { tipo: "ingrediente", campo: "alcaparras", texto: "De novo?" },
        ],
      },
    });
    const card = screen.getByRole("article", { name: "Frango com alcaparras" });
    expect(within(card).getAllByText("Salsinha (cheiro-verde)")).toHaveLength(2);
    expect(erro.mock.calls.filter(([mensagem]) => String(mensagem).includes("same key"))).toEqual([]);
    erro.mockRestore();
  });

  it("a viabilidade com pergunta de sim e não manda a resposta como ação; o que falta sem caber fica em perigo", async () => {
    const t = await montar("viabilidade", {
      dados: {
        nome: "Bolo de fubá",
        veredito: "BLOQUEADO",
        ingredientes: [{ nome: "Fubá", situacao: "falta", precisa: { texto: "2 xícaras" } }, { situacao: "tem" }],
        falta_comprar: { texto: "não cabe nos R$ 80,00", cabe_no_orcamento: false },
        perguntas: [
          { tipo: "equipamento", campo: "forno", texto: "A senhora tem forno?", opcoes: [{ rotulo: "Tenho", resposta: "sim" }, { rotulo: "Não sei", resposta: "nao_sei" }, { resposta: "x" }] },
          { tipo: "equipamento", campo: "forno" },
        ],
      },
      parametros: { slug: "bolo-de-fuba" },
    });
    const card = screen.getByRole("article", { name: "Bolo de fubá" });
    expect(within(card).getByText("Não dá")).toBeInTheDocument();
    expect(within(card).getByText("2 xícaras")).toBeInTheDocument();
    expect(within(card).getByText("não cabe nos R$ 80,00").className).toContain("text-perigo");
    expect(within(card).getByText("Ingrediente")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "Tenho" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({
      texto: "Tenho.",
      acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
    }));
    expect(within(card).getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", "/receitas/bolo-de-fuba");
  });

  it("o item parecido da despensa responde pela receita: a ação leva o receita_id", async () => {
    const t = await montar("viabilidade", {
      dados: {
        nome: "Alcatra com molho de queijo",
        slug: "alcatra-com-molho",
        veredito: "FALTA INFO",
        ingredientes: [{ nome: "bifes de alcatra", situacao: "confirmar", precisa: { texto: "500 g" } }],
        perguntas: [
          {
            tipo: "ingrediente",
            assunto: "mesmo_ingrediente",
            campo: "6 bifes de alcatra",
            texto: "A receita pede alcatra. É o seu miolo de alcatra?",
            opcoes: [
              { rotulo: "É, sim", resposta: "sim" },
              { rotulo: "Não é", resposta: "nao" },
            ],
          },
        ],
      },
    });
    const card = screen.getByRole("article", { name: "Alcatra com molho de queijo" });
    expect(within(card).getByText("Falta a senhora confirmar:").parentElement).toHaveTextContent("bifes de alcatra.");
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "É, sim" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({
      acao: { tipo: "responder", tipo_pergunta: "ingrediente", campo: "6 bifes de alcatra", resposta: "sim", receita_id: "alcatra-com-molho" },
    }));
  });
});

describe("comparação e avaliação", () => {
  it("a comparação: cada receita com o selo, o que usa e o que falta, e o caminho para todas", async () => {
    await montar("comparacao");
    const card = screen.getByRole("article", { name: "2 receitas para a senhora" });
    expect(within(card).getByRole("link", { name: "Frango com milho verde" })).toHaveAttribute("href", "/receitas/8747bf504b200286");
    expect(within(card).getByText("Com o que a senhora tem")).toBeInTheDocument();
    expect(within(card).getByText("Comprando R$ 6,00, cabe nos R$ 80,00")).toBeInTheDocument();
    expect(within(card).getByText("nota 86,9")).toBeInTheDocument();
    expect(within(card).getByText(/Trouxe 2 receitas da internet/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver as receitas" })).toHaveAttribute("href", "/receitas");
  });

  it("a comparação antiga (receitas com veredito), com mais do que cabe, e vazia", async () => {
    const receitas = Array.from({ length: 5 }, (_, i) => ({ nome: `R${i}`, veredito: "APTO", veredito_rotulo: "Dá pra fazer", nota: { texto: "70" } }));
    await montar("comparacao", { dados: { receitas: [...receitas, { selo: { codigo: "outro", texto: "Outro" } }], orcamento_restante: { valor: 80, texto: "R$ 80,00" } } });
    const card = screen.getByRole("article", { name: "6 receitas para a senhora" });
    expect(within(card).getAllByRole("listitem")).toHaveLength(4);
    expect(within(card).getAllByText("Dá pra fazer")).toHaveLength(4);
    expect(within(card).getByRole("link", { name: "Ver todas as receitas" })).toBeInTheDocument();
    expect(within(card).getByText("R$ 80,00")).toBeInTheDocument();

    await montar("comparacao", { dados: { itens: [{ nome: "Só uma" }] } });
    expect(screen.getByRole("article", { name: "1 receita para a senhora" })).toBeInTheDocument();
    await montar("comparacao", { dados: {} });
    expect(screen.getByText("Nenhuma receita dá para fazer agora.")).toBeInTheDocument();
  });

  it("a comparação vazia com receitas esperando resposta diz que ainda não confirmou, não que nada dá", async () => {
    const texto = "7 receitas usam só o que a senhora tem; falta só a senhora me dizer quanto tempo consegue ficar cozinhando de uma vez.";
    await montar("comparacao", { dados: { itens: [], esperando_resposta: { texto } } });
    expect(screen.getByText("Nenhuma receita confirmada ainda.")).toBeInTheDocument();
    expect(screen.getByText(texto)).toBeInTheDocument();
    expect(screen.queryByText("Nenhuma receita dá para fazer agora.")).not.toBeInTheDocument();
  });

  it("a avaliação: gosta, as estrelas, a pontuação com a conta, a posição e a anotação", async () => {
    await montar("avaliacao_da_receita");
    const card = screen.getByRole("article", { name: "Frango com milho verde" });
    expect(within(card).getByText("Gosta de fazer")).toBeInTheDocument();
    expect(within(card).getByRole("img", { name: "Sabor: 4 de 5 estrelas" })).toBeInTheDocument();
    expect(within(card).getByRole("img", { name: "Aguenta a entrega: 5 de 5 estrelas" })).toBeInTheDocument();
    expect(within(card).getByText("88,8")).toBeInTheDocument();
    expect(within(card).getByText(/pontuação = 100/)).toBeInTheDocument();
    expect(within(card).getByText("1º lugar no ranking da senhora")).toBeInTheDocument();
    expect(within(card).getByText("Servir com arroz branco.")).toBeInTheDocument();
  });

  it("a avaliação sem nota: não disse se gosta, ou não quer", async () => {
    await montar("avaliacao_da_receita", { dados: { nome: "Bolo", avaliacao: { gosta: null, estrelas: { sabor: null } } }, parametros: {} });
    expect(screen.getByText("Ainda não disse se gosta")).toBeInTheDocument();
    expect(screen.getAllByText("sem nota")).toHaveLength(5);
    await montar("avaliacao_da_receita", { dados: { avaliacao: { gosta: false, pontuacao: { texto: "40" } } }, parametros: { prato: "Pudim" } });
    expect(screen.getByText("Não quer fazer")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Pudim" })).toBeInTheDocument();
  });
});

describe("cozinha", () => {
  it("a pergunta: os botões mandam a ação; 'Não sei' vai só como texto", async () => {
    const t = await montar("pergunta");
    const card = screen.getByRole("article", { name: "A senhora tem forno? Pode ser o do fogão mesmo, ou elétrico." });
    expect(within(card).getByText("Vale para: Bolo de fubá.")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "Tenho" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", {
      texto: "Tenho forno.",
      acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
      id_cliente: "u-1",
    });
    // Respondendo, os botões esperam.
    fireEvent.click(within(card).getByRole("button", { name: "Não sei" }));
    expect(t.transporte.enviar).toHaveBeenCalledTimes(1);
  });

  it("'Não sei' sem ação, a pergunta sem opções, e sem pergunta nenhuma", async () => {
    const t = await montar("pergunta");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Não sei" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", { texto: "Não sei se tenho forno.", id_cliente: "u-1" });

    const aberta = await montar("pergunta", { dados: { pergunta: "Quanto tempo a senhora tem por dia?", tipo: "restricao", campo: "tempo", por_que_esta: "muda o que dá tempo de fazer" } });
    expect(screen.getByText("Muda o que dá tempo de fazer.")).toBeInTheDocument();
    fireEvent.click(within(aberta.container).getByRole("button", { name: "Responder" }));
    expect(aberta.loja.ler().caixa.contexto).toEqual({ tela: "cozinha", tipo: "restricao", id: "tempo" });
    const tecnica = await montar("pergunta", { dados: { pergunta: "Sabe fazer béchamel?", tipo: "tecnica" } });
    fireEvent.click(within(tecnica.container).getByRole("button", { name: "Responder" }));
    expect(tecnica.loja.ler().caixa.contexto).toEqual({ tela: "cozinha", tipo: "tecnica" });
    const equipamento = await montar("pergunta", { dados: { pergunta: "Tem liquidificador?" } });
    fireEvent.click(within(equipamento.container).getByRole("button", { name: "Responder" }));
    expect(equipamento.loja.ler().caixa.contexto).toEqual({ tela: "cozinha", tipo: "equipamento" });

    await montar("pergunta", { dados: { ha_pergunta: false } });
    expect(screen.getByRole("article", { name: "Nada a perguntar agora" })).toBeInTheDocument();
  });

  it("a cozinha atualizada: o item que mudou, quem mudou, quantas receitas, e o resumo em linhas", async () => {
    await montar("cozinha_atualizada");
    const card = screen.getByRole("article", { name: "Forno" });
    expect(within(card).getByText("Não tem")).toBeInTheDocument();
    expect(within(card).getByText("Anotado pela conversa, hoje, 09:12.")).toBeInTheDocument();
    expect(within(card).getByText("Isso muda 2 receitas.")).toBeInTheDocument();
    expect(within(card).getByRole("meter", { name: "Quanto da cozinha a senhora já respondeu" })).toBeInTheDocument();
    expect(within(card).getByText("17 supostos")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver a cozinha" })).toHaveAttribute("href", "/cozinha");
  });

  it("a técnica que mudou, uma receita só, e sem o item: a lista do que a conversa anotou", async () => {
    await montar("cozinha_atualizada", {
      dados: { tecnicas: [{ id: "refogar", nome: "Refogar", estado: "tem", receitas_afetadas: 1 }] },
      parametros: { tipo: "tecnica", campo: "refogar" },
    });
    expect(screen.getByText("Sabe fazer")).toBeInTheDocument();
    expect(screen.getByText("Isso muda 1 receita.")).toBeInTheDocument();

    await montar("cozinha_atualizada", {
      dados: { tecnicas: [{ id: "fritar", nome: "Fritar", estado: "desconhecido" }] },
      parametros: { campo: "fritar" },
    });
    expect(screen.getByText("Não sei ainda")).toBeInTheDocument();

    await montar("cozinha_atualizada", { parametros: {} });
    const geral = screen.getAllByRole("article").at(-1) as HTMLElement;
    expect(within(geral).getByText("Cozinha atualizada")).toBeInTheDocument();
    expect(within(geral).getByText("Forno")).toBeInTheDocument();

    await montar("cozinha_atualizada", { dados: null, parametros: { campo: "nada" } });
    expect(screen.getAllByRole("article").at(-1)).toHaveAccessibleName("Cozinha atualizada");
  });
});

describe("preço", () => {
  const ponto = {
    preco: { valor: 7.5, texto: "R$ 7,50" },
    taxa: { valor: 0.75, texto: "R$ 0,75" },
    recebe: { valor: 6.75, texto: "R$ 6,75" },
    lucro: { valor: 3.75, texto: "R$ 3,75" },
    food_cost: 0.4,
    margem: 0.5,
    da_prejuizo: false,
    explicacao: "a conta",
  };

  it("o custo de uma porção: o total, cada ingrediente com a conta e o peso, e o que vai a gosto", async () => {
    await montar("custo_porcao");
    const card = screen.getByRole("article", { name: "Arroz com frango" });
    expect(within(card).getByText("R$ 2,37", { selector: "span.text-3xl" })).toBeInTheDocument();
    expect(within(card).getByText(/500 g × R\$ 14,00\/kg/)).toBeInTheDocument();
    expect(within(card).getByRole("meter", { name: "Peito de frango no custo da porção" })).toBeInTheDocument();
    expect(within(card).getByText("Fica de fora da conta, porque vai a gosto: sal.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", "/receitas/arroz-com-frango");
  });

  it("o custo em faixa, e com o mínimo", async () => {
    await montar("custo_porcao", {
      dados: { e_faixa: true, total: { valor: 2, texto: "R$ 2,00" }, minimo: { valor: 1, texto: "R$ 1,00" }, maximo: { valor: 3, texto: "R$ 3,00" }, linhas: [{ custo: null }] },
      parametros: {},
    });
    expect(screen.getByText("de ingrediente por porção, entre R$ 1,00 e R$ 3,00")).toBeInTheDocument();
    expect(screen.getByText("Ingrediente")).toBeInTheDocument();
  });

  it("os caminhos de preço: nenhum em destaque, e 'Vou cobrar este' confere a conta antes de mandar a decisão", async () => {
    rede.mockResolvedValue(envelope(ponto));
    const t = await montar("cenarios");
    const card = screen.getByRole("article", { name: "Arroz com frango" });
    const caminhos = within(card).getAllByRole("button", { name: "Vou cobrar este" });
    expect(caminhos).toHaveLength(3);
    expect(within(card).getByText(/Se o ingrediente subir 20%/)).toHaveTextContent("Ainda dá lucro.");
    expect(within(card).queryByText(/CMV/)).toBeNull();
    await act(async () => {
      fireEvent.click(caminhos[0]!);
      await esperarPromessas(10);
    });
    const dialogo = await screen.findByRole("dialog", { name: "Cobrar R$ 7,50 por porção?" });
    expect(rede.mock.calls[0]?.[0]).toBe("/motor/preco-em?prato=Arroz%20com%20frango&preco=7.5");
    await act(async () => {
      fireEvent.click(within(dialogo).getByRole("button", { name: "Vou cobrar este" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", {
      texto: "Vou cobrar R$ 7,50 por porção de arroz com frango.",
      acao: { tipo: "decidir", prato: "Arroz com frango", decisao: "aceito", preco: 7.5 },
      id_cliente: "u-1",
    });
  });

  it("caminhos sem prato não oferecem cobrar; a alta que dá prejuízo avisa; respondendo, o botão espera", async () => {
    await montar("cenarios", {
      dados: { cenarios: [{ preco: { valor: 1, texto: "R$ 1,00" } }], sensibilidade: { variacao_testada: 0.2, cmv_original: { texto: "R$ 1" }, cmv_com_alta: { texto: "R$ 2" }, lucro_original: { texto: "R$ 1" }, lucro_com_alta: { texto: "R$ 0" }, ainda_lucrativo: false } },
      parametros: {},
    });
    expect(screen.getByRole("article", { name: "Caminhos de preço" })).toBeInTheDocument();
    expect(screen.getByText("Caminho 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vou cobrar este" })).toBeNull();
    expect(screen.getByText(/Aí passa a dar prejuízo/)).toBeInTheDocument();

    await montar("cenarios", { dados: { cenarios: [], sensibilidade: { variacao_testada: 0.2 } } });
    await montar("cenarios", { dados: { prato: "X", cenarios: [], sensibilidade: { variacao_testada: 0.1, cmv_original: { texto: "a" }, cmv_com_alta: { texto: "b" }, lucro_original: { texto: "c" }, lucro_com_alta: { texto: "d" } } } });
    expect(screen.getByText(/Se o ingrediente subir 10%/).textContent).not.toMatch(/lucro\.|prejuízo/);

    const t = lojaDeTeste({ enviar: () => new Promise(() => {}) });
    await montar("ponto_de_preco", {}, t);
    await act(async () => {
      void t.loja.enviar("Oi");
      await esperarPromessas();
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Vou cobrar este" }).at(-1)!);
    expect(screen.queryByRole("dialog", { name: /Cobrar/ })).toBeNull();
  });

  it("a conta de um preço: o que fica com a plataforma, o que chega, a sobra; prejuízo em destaque", async () => {
    rede.mockResolvedValue(envelope(exemplo("ponto_de_preco").dados));
    await montar("ponto_de_preco");
    const card = screen.getByRole("article", { name: "Arroz com frango" });
    expect(within(card).getByText("R$ 1,20")).toBeInTheDocument();
    expect(within(card).getByText("R$ 10,80")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "Vou cobrar este" }));
      await esperarPromessas(10);
    });
    expect(await screen.findByRole("dialog", { name: "Cobrar R$ 12,00 por porção?" })).toBeInTheDocument();

    await montar("ponto_de_preco", { dados: { ...ponto, da_prejuizo: true, aviso: "Perde R$ 1,00 por porção.", lucro: { valor: -1, texto: "−R$ 1,00" } }, parametros: {} });
    expect(screen.getByText("Dá prejuízo")).toBeInTheDocument();
    expect(screen.getByText("Perde R$ 1,00 por porção.")).toBeInTheDocument();
    expect(screen.getAllByRole("article").at(-1)).toHaveAccessibleName("Preço");
  });

  it("o preço preliminar: sempre rotulado, a linha sem valor, a conta de cada preço e o que falta ela dizer", async () => {
    await montar("preco_preliminar");
    const card = screen.getByRole("article", { name: "Arroz com frango" });
    expect(within(card).getByText("Preço preliminar")).toBeInTheDocument();
    expect(within(card).getByText("falta saber")).toBeInTheDocument();
    expect(within(card).getByText(/R\$ 5,27 ÷ 0,90/)).toBeInTheDocument();
    expect(within(card).getAllByText("Chega para a senhora")).toHaveLength(3);
    expect(within(card).getByText("Falta a senhora me dizer: embalagem por porção.")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Vou cobrar este" })).toBeNull();
    expect(within(card).getByText(/Ainda não tenho preço de mercado/)).toBeInTheDocument();
  });

  it("o preço preliminar com o mínimo, e com o que falta achado pela linha", async () => {
    await montar("preco_preliminar", {
      dados: { linhas: [{ id: "gas", premissas: ["gas_por_minuto"], rotulo: "Gás" }, { valor: null }], sinais: { faltam_parametros: ["gas_por_minuto", "outro"] }, pontos: [{ preco: { texto: "R$ 1" } }] },
      parametros: {},
    });
    expect(screen.getByRole("article", { name: "Prato" })).toBeInTheDocument();
    expect(screen.getByText("Falta a senhora me dizer: gás.")).toBeInTheDocument();
    expect(screen.getByText("Preço 1")).toBeInTheDocument();
    expect(screen.getByText("Custo")).toBeInTheDocument();
  });

  it("a decisão: o prato no cardápio, o que ela fez, e 'Mudar preço' só preenche a caixa", async () => {
    const t = await montar("decisao");
    const card = screen.getByRole("article", { name: "Arroz com frango" });
    expect(within(card).getByText("Aceitou")).toBeInTheDocument();
    expect(within(card).getByText("A senhora aceitou o arroz com frango a R$ 18,00.")).toBeInTheDocument();
    expect(within(card).getByText("R$ 13,73")).toBeInTheDocument();
    expect(within(card).getByText(/1 prato no cardápio\. 76% de sobra/)).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Mudar preço" }));
    expect(t.loja.ler().caixa.texto).toBe("Quero mudar o preço de arroz com frango para ");
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });

  it("a decisão com o mínimo", async () => {
    await montar("decisao", { dados: {}, parametros: {} });
    expect(screen.getByRole("article", { name: "Cardápio" })).toBeInTheDocument();
  });
});

describe("fontes", () => {
  it("De onde eu tirei isso: chip com link para a tela, e chip sem link", async () => {
    await montar("fontes");
    const card = screen.getByRole("article", { name: "De onde eu tirei isso" });
    expect(within(card).getByRole("link", { name: "Óleo de soja, na sua despensa" })).toHaveAttribute("href", "/despensa/oleo-de-soja");
    expect(within(card).getByText("Anvisa, Resolução RDC nº 216/2004 (AnvisaLegis)").closest("a")).toBeNull();
  });

  it("sem chip nenhum, o card não aparece", async () => {
    const { container } = await montar("fontes", { dados: { chips: [{ rotulo: " " }] } });
    expect(container.querySelector("article")).toBeNull();
    await montar("fontes", { dados: { chips: [{ rotulo: "Base de culinária" }] } });
    expect(screen.getByRole("article", { name: "De onde eu tirei isso" })).toBeInTheDocument();
  });
});
