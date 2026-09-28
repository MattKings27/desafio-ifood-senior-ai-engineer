/**
 * A tela da despensa com os dados do contrato: o cartão de cada ingrediente, a
 * pergunta com a resposta ali mesmo, o orçamento com a devolução, os filtros na
 * URL, o formulário de acrescentar e corrigir, e a página de um item.
 *
 * As Server Actions são espiões que devolvem `Resultado`; o que se confere é o
 * pedido que a tela monta e o que ela diz depois (a frase da API, o
 * "Desfazer"), nunca uma conta feita aqui.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const acoes = vi.hoisted(() => ({
  adicionarItem: vi.fn(),
  corrigirItem: vi.fn(),
  removerItem: vi.fn(),
  desfazerMudanca: vi.fn(),
  devolverCompra: vi.fn(),
}));
vi.mock("@/lib/acoes/despensa", () => acoes);
vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import type {
  DetalheDoItem,
  ItemDaDespensa,
  ListaDaDespensa,
  PendenciaDaDespensa,
  RespostaDaEscrita,
} from "@/lib/api/despensa";
import { contrato } from "@/teste/fixturas";
import { irPara, roteador } from "@/teste/navegacao";

import { semLancar } from "./avisos";
import { CartaoIngrediente } from "./CartaoIngrediente";
import { DetalheDoIngrediente, HistoricoDoItem } from "./DetalheDoIngrediente";
import { FormularioDoItem, campoDoErro, medidaDoRotulo, unidadeDaMedida } from "./FormularioDoItem";
import { FotoDoIngrediente, desenhoDaCategoria } from "./FotoDoIngrediente";
import { PainelDoOrcamento } from "./PainelDoOrcamento";
import { TelaDaDespensa } from "./TelaDaDespensa";
import { comMaiuscula, semQuebrarNumero } from "./texto";

const LISTA = contrato<ListaDaDespensa>("despensa.json");
const PECA = contrato<DetalheDoItem>("despensa-item.json");
const COMPRADO = contrato<DetalheDoItem>("despensa-item-comprado.json");
const ESCRITA = contrato<Record<string, { resposta: RespostaDaEscrita }>>("despensa-escrita.json");
const item = (id: string) => LISTA.itens.find((i) => i.id === id) as ItemDaDespensa;
const pendencia = (tipo: string) => LISTA.pendencias.find((p) => p.tipo === tipo) as PendenciaDaDespensa;

const deu = <T,>(dados: T) => ({ ok: true as const, dados });
const recusou = (mensagem: string, categoria = "uso", pergunta?: string) => ({
  ok: false as const,
  erro: { categoria, mensagem, ...(pergunta ? { pergunta } : {}) },
});

function montar(elemento: ReactElement) {
  return render(<ProvedorDeToasts>{elemento}</ProvedorDeToasts>);
}

/** Espera as transições da ação terminarem. */
async function esperar() {
  await act(async () => {
    await new Promise((resolver) => setTimeout(resolver, 0));
  });
}

beforeEach(() => {
  irPara("/despensa");
});

afterEach(() => {
  vi.clearAllMocks();
});

/* -------------------------------------------------------------------------- */

describe("o texto da API na tela", () => {
  it("primeira letra maiúscula e número que não quebra longe da unidade", () => {
    expect(comMaiuscula("a senhora já tinha")).toBe("A senhora já tinha");
    expect(semQuebrarNumero("R$ 9,00 ÷ 0,4 kg = R$ 22,50/kg; 2 embalagens")).toBe(
      "R$\u00a09,00 ÷ 0,4\u00a0kg = R$\u00a022,50/kg; 2\u00a0embalagens",
    );
  });
});

describe("FotoDoIngrediente", () => {
  it("com foto, a da API com o crédito; sem foto, o desenho da categoria", () => {
    const { container, rerender } = render(
      <FotoDoIngrediente imagem={item("alcaparras").imagem} categoria="conservas" mostrarCredito />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", item("alcaparras").imagem?.url);
    // O crédito é o do contrato: autor, licença e "Wikimedia Commons".
    expect(screen.getByText(item("alcaparras").imagem?.credito ?? "")).toBeInTheDocument();
    rerender(<FotoDoIngrediente imagem={null} categoria="laticinios" grande />);
    expect(container.querySelector("[data-sem-foto]")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("img")).toBeNull();
    expect(desenhoDaCategoria("confeitaria").cor).toBe("text-marca");
    expect(desenhoDaCategoria("joias").cor).toBe("text-apagado");
  });
});

describe("CartaoIngrediente", () => {
  it("o cartão inteiro leva ao item, com a conta e os selos", () => {
    render(<CartaoIngrediente item={item("alcaparras")} />);
    expect(screen.getByRole("link", { name: "Alcaparras" })).toHaveAttribute("href", "/despensa/alcaparras");
    expect(screen.getByText("2 kg (1 balde de 2 kg)")).toBeInTheDocument();
    expect(screen.getByText("R$ 82,00")).toBeInTheDocument();
    expect(screen.getByText("R$ 41,00/kg")).toBeInTheDocument();
    expect(screen.getByText(/1 × 2 kg = 2 kg/).textContent).toContain("2\u00a0kg = 2\u00a0kg");
    expect(screen.getByText("Ainda sem receita")).toBeInTheDocument();
    expect(screen.queryByText("Falta uma resposta")).not.toBeInTheDocument();
  });

  it("sem preço e sem conta, diz o que falta; a origem aparece quando não é a planilha", () => {
    const { rerender } = render(<CartaoIngrediente item={item("item-7b2d9e10")} nivelTitulo={2} />);
    expect(screen.getByRole("heading", { level: 2, name: "Farinha de rosca" })).toBeInTheDocument();
    expect(screen.getByText("Ainda sem o preço")).toBeInTheDocument();
    expect(screen.getByText("Custo ainda desconhecido")).toBeInTheDocument();
    expect(screen.getByText("Falta uma resposta")).toBeInTheDocument();
    expect(screen.getByText("A senhora já tinha")).toBeInTheDocument();
    rerender(<CartaoIngrediente item={item("item-4f7a1c2e")} />);
    expect(screen.getByText("Comprado com os complementos")).toBeInTheDocument();
    expect(screen.getByText("Entra em 1 receita")).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */

describe("o que a planilha não diz não vira pergunta", () => {
  it("nem o peso da embalagem nem o preço pago aparecem como pergunta, na lista e no item", () => {
    const [embalagem, preco] = [pendencia("conteudo_embalagem"), pendencia("preco_pago")];
    const { container, unmount } = montar(<TelaDaDespensa lista={LISTA} />);
    expect(container.textContent).not.toContain(embalagem.pergunta);
    expect(container.textContent).not.toContain(preco.pergunta);
    expect(screen.queryByRole("region", { name: "Preciso saber" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Quanto vem na embalagem?")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Quanto a senhora pagou?")).not.toBeInTheDocument();
    unmount();
    const comPergunta = { ...PECA, pendencia: embalagem };
    const detalhe = montar(
      <DetalheDoIngrediente detalhe={comPergunta} receitas={[]} categorias={LISTA.categorias_para_escolher} orcamento={LISTA.orcamento} />,
    );
    expect(detalhe.container.textContent).not.toContain(embalagem.pergunta);
    expect(screen.queryByRole("button", { name: "Responder" })).not.toBeInTheDocument();
    // O caminho para corrigir continua: o Editar do item.
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */

describe("PainelDoOrcamento", () => {
  it("quanto resta, a conta da API, e devolver uma compra com confirmação", async () => {
    acoes.devolverCompra.mockResolvedValue(deu({ texto: "Devolvi R$ 9,00 aos complementos; restam R$ 80,00." }));
    const aoRegistrar = vi.fn();
    montar(<PainelDoOrcamento orcamento={LISTA.orcamento} aoRegistrarCompra={aoRegistrar} />);
    const painel = screen.getByRole("region", { name: "Orçamento dos complementos" });
    expect(painel).toHaveAttribute("id", "orcamento");
    expect(within(painel).getByText("R$ 71,00")).toBeInTheDocument();
    expect(within(painel).getByRole("meter", { name: "Parte do orçamento já gasta" })).toHaveAttribute(
      "aria-valuetext",
      "Saíram R$ 9,00 dos complementos; restam R$ 71,00.",
    );
    fireEvent.click(within(painel).getByRole("button", { name: "Registrar compra" }));
    expect(aoRegistrar).toHaveBeenCalledOnce();

    const compra = within(painel).getByRole("listitem");
    expect(within(compra).getByRole("link", { name: "Creme de leite (despensa, para Arroz com frango)" })).toHaveAttribute(
      "href",
      "/despensa/item-4f7a1c2e",
    );
    fireEvent.click(within(compra).getByRole("button", { name: "Devolver ao orçamento" }));
    const confirmar = screen.getByRole("alertdialog", { name: "Devolver ao orçamento?" });
    expect(confirmar).toHaveTextContent("R$ 9,00 voltam para os complementos");
    fireEvent.click(within(confirmar).getByRole("button", { name: "Devolver" }));
    await esperar();
    expect(acoes.devolverCompra).toHaveBeenCalledWith(1, expect.any(String));
    expect(screen.getByText("Devolvi R$ 9,00 aos complementos; restam R$ 80,00.")).toBeInTheDocument();
  });

  it("cancelar não devolve; sem compra nenhuma, o vazio explica", () => {
    const { rerender } = montar(<PainelDoOrcamento orcamento={LISTA.orcamento} aoRegistrarCompra={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Devolver ao orçamento" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(acoes.devolverCompra).not.toHaveBeenCalled();
    rerender(
      <ProvedorDeToasts>
        <PainelDoOrcamento orcamento={{ ...LISTA.orcamento, compras: [] }} aoRegistrarCompra={() => {}} />
      </ProvedorDeToasts>,
    );
    expect(screen.getByText("Nenhuma compra ainda")).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */

describe("TelaDaDespensa", () => {
  const grade = () => screen.getByRole("region", { name: "Ingredientes" });
  const cartoes = () => within(grade()).queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

  it("o cabeçalho, o orçamento e a grade inteira, sem pergunta de peso ou preço", () => {
    const { container } = montar(<TelaDaDespensa lista={LISTA} />);
    expect(screen.getByRole("heading", { level: 1, name: "Despensa" })).toBeInTheDocument();
    expect(screen.getByText(/pagos em 39 ingredientes/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Preciso saber" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Responder no chat" })).not.toBeInTheDocument();
    expect(container.querySelector("#orcamento")).toHaveClass("lg:col-span-5");
    expect(cartoes()).toHaveLength(39);
    expect(screen.getByText("39 ingredientes")).toBeInTheDocument();
  });

  it("a busca, a categoria e a ordem mudam a URL e a lista", () => {
    montar(<TelaDaDespensa lista={LISTA} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar ingrediente" }), { target: { value: "feijao" } });
    expect(window.location.search).toBe("?q=feijao");
    expect(cartoes()).toEqual(["Feijão carioquinha", "Feijão preto"]);
    expect(screen.getByText("2 encontrados")).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("group", { name: "Categorias" })).getByRole("checkbox", { name: /Hortifrúti/ }));
    expect(window.location.search).toBe("?q=feijao&categoria=hortifruti");
    expect(screen.getByText("Nenhum ingrediente com esses filtros")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Limpar filtros" }).at(-1) as HTMLElement);
    expect(window.location.search).toBe("");

    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "nome" } });
    expect(window.location.search).toBe("?ordem=nome");
    expect(cartoes()[0]).toBe("Açafrão em pó (cúrcuma)");
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "custo" } });
    expect(cartoes()[0]).toBe("Azeite de oliva extra virgem");
  });

  it("a folha de filtros: confiança, origem e só o que tem pergunta, com o número no botão", () => {
    montar(<TelaDaDespensa lista={LISTA} />);
    fireEvent.click(screen.getByRole("button", { name: /^Filtros/ }));
    const folha = screen.getByRole("dialog", { name: "Filtros" });
    fireEvent.click(within(folha).getByRole("checkbox", { name: "Com pergunta em aberto" }));
    expect(window.location.search).toBe("?pendentes=true");
    expect(cartoes()).toEqual(["Cobertura de chocolate", "Farinha de rosca"]);
    fireEvent.click(within(folha).getByRole("checkbox", { name: "Falta um dado" }));
    fireEvent.click(within(folha).getByRole("checkbox", { name: "Já tinha" }));
    fireEvent.click(within(folha).getByRole("checkbox", { name: "Sem receita ainda" }));
    expect(cartoes()).toEqual(["Farinha de rosca"]);
    expect(within(folha).getByRole("button", { name: "Ver 1 ingrediente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Filtros 4/ })).toBeInTheDocument();

    const ativos = screen.getByRole("list", { name: "Filtros ativos" });
    fireEvent.click(within(ativos).getByRole("button", { name: "Já tinha: tirar este filtro" }));
    fireEvent.click(within(ativos).getByRole("button", { name: "Falta um dado: tirar este filtro" }));
    fireEvent.click(within(ativos).getByRole("button", { name: "Sem receita ainda: tirar este filtro" }));
    fireEvent.click(within(ativos).getByRole("button", { name: "Com pergunta em aberto: tirar este filtro" }));
    expect(window.location.search).toBe("");

    fireEvent.click(within(folha).getByRole("checkbox", { name: "Da planilha" }));
    fireEvent.click(within(folha).getByRole("button", { name: "Limpar estes filtros" }));
    expect(window.location.search).toBe("");
    fireEvent.click(within(folha).getByRole("button", { name: "Ver todos" }));
  });

  it("os chips ativos da busca e da categoria saem um a um", () => {
    irPara("/despensa?q=arroz&categoria=graos");
    montar(<TelaDaDespensa lista={LISTA} />);
    const ativos = screen.getByRole("list", { name: "Filtros ativos" });
    fireEvent.click(within(ativos).getByRole("button", { name: "Grãos, farinhas e massas: tirar este filtro" }));
    expect(window.location.search).toBe("?q=arroz");
    fireEvent.click(within(screen.getByRole("list", { name: "Filtros ativos" })).getByRole("button", { name: "Busca: arroz: tirar este filtro" }));
    expect(window.location.search).toBe("");
  });

  it("o orçamento ocupa a linha; despensa vazia chama para acrescentar", () => {
    const { container } = montar(<TelaDaDespensa lista={{ ...LISTA, pendencias: [], itens: [], total_itens: 0 }} />);
    expect(screen.queryByRole("region", { name: "Preciso saber" })).not.toBeInTheDocument();
    expect(container.querySelector("#orcamento")).toHaveClass("lg:col-span-5");
    expect(screen.getByText("A despensa está vazia")).toBeInTheDocument();
    fireEvent.click(within(screen.getByText("A despensa está vazia").closest("div")?.parentElement as HTMLElement).getByRole("button", { name: "Adicionar ingrediente" }));
    expect(screen.getByRole("dialog", { name: "Adicionar ingrediente" })).toBeInTheDocument();
  });

  it("os dois caminhos do formulário: acrescentar e registrar compra", () => {
    montar(<TelaDaDespensa lista={LISTA} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Adicionar ingrediente" })[0] as HTMLElement);
    expect(screen.getByRole("radio", { name: "Já tinha" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(screen.getByRole("button", { name: "Registrar compra" }));
    expect(screen.getByRole("dialog", { name: "Registrar compra" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Comprei com os R$ 80,00" })).toBeChecked();
    expect(screen.getByText("Restam R$ 71,00 para complementos.")).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */

describe("o formulário, peça por peça", () => {
  it("a medida como a API guarda, lida e escrita de volta", () => {
    expect(medidaDoRotulo("kg")).toEqual({ medida: "kg", conteudo: null, unidadeDoConteudo: "g" });
    expect(medidaDoRotulo(" L ")).toEqual({ medida: "L", conteudo: null, unidadeDoConteudo: "g" });
    expect(medidaDoRotulo("un 200g")).toEqual({ medida: "embalagem", conteudo: 200, unidadeDoConteudo: "g" });
    expect(medidaDoRotulo("balde 2kg")).toEqual({ medida: "embalagem", conteudo: 2, unidadeDoConteudo: "kg" });
    expect(medidaDoRotulo("garrafa 1,5 l")).toEqual({ medida: "embalagem", conteudo: 1.5, unidadeDoConteudo: "L" });
    expect(medidaDoRotulo("und")).toEqual({ medida: "un", conteudo: null, unidadeDoConteudo: "g" });
    expect(unidadeDaMedida({ medida: "embalagem", conteudo: 1.5, unidadeDoConteudo: "kg" })).toBe("un 1,5kg");
    expect(unidadeDaMedida({ medida: "embalagem", conteudo: null, unidadeDoConteudo: "g" })).toBe("un 0g");
    expect(unidadeDaMedida({ medida: "ml", conteudo: null, unidadeDoConteudo: "g" })).toBe("ml");
  });

  it.each([
    [{ categoria: "regra", mensagem: "a compra exige R$ 90,00" }, "preco"],
    [{ categoria: "uso", mensagem: "para comprar com os complementos, diga quanto a senhora pagou" }, "preco"],
    [{ categoria: "uso", mensagem: "Creme de leite já está na despensa; corrija o item" }, "nome"],
    [{ categoria: "uso", mensagem: "não entendi a unidade 'punhado'" }, "medida"],
    [{ categoria: "uso", mensagem: "a quantidade comprada precisa ser maior que zero" }, "quantidade"],
    [{ categoria: "uso", mensagem: "o estoque precisa ser um número" }, "estoque"],
    [{ categoria: "rede", mensagem: "Não consegui falar com o sistema" }, null],
  ] as const)("o erro %j vai para %s", (erro, campo) => {
    expect(campoDoErro(erro)).toBe(campo);
  });
});

describe("FormularioDoItem", () => {
  const categorias = LISTA.categorias_para_escolher;

  function abrirNovo(origem: "ja_tinha" | "orcamento" = "ja_tinha") {
    const aoFechar = vi.fn();
    const tela = montar(
      <FormularioDoItem pedido={{ modo: "novo", origem }} aoFechar={aoFechar} categorias={categorias} orcamento={LISTA.orcamento} />,
    );
    return { ...tela, aoFechar, folha: screen.getByRole("dialog") };
  }

  it("acrescentar: confere antes de enviar, e o pedido sai na unidade que a API lê", async () => {
    acoes.adicionarItem.mockResolvedValue(deu(ESCRITA.adicionar?.resposta));
    const { folha, aoFechar } = abrirNovo("orcamento");
    fireEvent.change(within(folha).getByLabelText("Como a senhora mede"), { target: { value: "embalagem" } });
    fireEvent.click(within(folha).getByRole("button", { name: "Anotar na despensa" }));
    expect(await within(folha).findByText("Escreva o nome do ingrediente.")).toBeInTheDocument();
    expect(within(folha).getByText("Diga quanto vem em cada embalagem, como está no rótulo.")).toBeInTheDocument();
    expect(within(folha).getByText("Diga quanto a senhora tem agora. Se acabou, pode pôr 0.")).toBeInTheDocument();
    expect(within(folha).getByText("Para comprar com os complementos, diga quanto a senhora pagou.")).toBeInTheDocument();
    expect(acoes.adicionarItem).not.toHaveBeenCalled();

    fireEvent.change(within(folha).getByLabelText("Nome do ingrediente"), { target: { value: "  Creme de leite " } });
    fireEvent.change(within(folha).getByLabelText("Categoria"), { target: { value: "laticinios" } });
    fireEvent.change(within(folha).getByLabelText("Quanto vem em cada embalagem"), { target: { value: "200" } });
    fireEvent.change(within(folha).getByLabelText("Unidade do que vem na embalagem"), { target: { value: "g" } });
    fireEvent.change(within(folha).getByLabelText("Quantas embalagens tem agora"), { target: { value: "2" } });
    fireEvent.change(within(folha).getByLabelText(/Quantas embalagens comprou/), { target: { value: "2" } });
    fireEvent.change(within(folha).getByLabelText(/Quanto pagou/), { target: { value: "9,00" } });
    fireEvent.change(within(folha).getByLabelText(/Para qual prato comprou/), { target: { value: " Arroz com frango " } });
    fireEvent.click(within(folha).getByRole("button", { name: "Anotar na despensa" }));
    await esperar();
    expect(acoes.adicionarItem).toHaveBeenCalledWith({
      nome: "Creme de leite",
      estoque: 2,
      unidade: "un 200g",
      origem: "orcamento",
      id_cliente: expect.any(String),
      categoria: "laticinios",
      quantidade_comprada: 2,
      preco_pago: 9,
      receita: "Arroz com frango",
    });
    expect(screen.getByText(ESCRITA.adicionar?.resposta.texto as string)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desfazer" })).toBeInTheDocument();
    expect(aoFechar).toHaveBeenCalledOnce();
  });

  it("já tinha, sem preço: pode; a recusa da API volta no campo, ou num aviso", async () => {
    const { folha } = abrirNovo();
    expect(within(folha).getByText("Sem o preço, eu pergunto depois.")).toBeInTheDocument();
    fireEvent.change(within(folha).getByLabelText("Nome do ingrediente"), { target: { value: "Farinha de rosca" } });
    fireEvent.change(within(folha).getByLabelText("Quanto tem agora"), { target: { value: "0,5" } });

    acoes.adicionarItem.mockResolvedValueOnce(recusou("Farinha de rosca já está na despensa; corrija o item em vez de acrescentar outro"));
    fireEvent.click(within(folha).getByRole("button", { name: "Anotar na despensa" }));
    await esperar();
    expect(acoes.adicionarItem).toHaveBeenLastCalledWith({
      nome: "Farinha de rosca",
      estoque: 0.5,
      unidade: "kg",
      origem: "ja_tinha",
      id_cliente: expect.any(String),
    });
    expect(within(folha).getByText(/já está na despensa/)).toBeInTheDocument();

    acoes.adicionarItem.mockResolvedValueOnce(recusou("Não consegui falar com o sistema agora.", "rede"));
    fireEvent.click(within(folha).getByRole("button", { name: "Anotar na despensa" }));
    await esperar();
    expect(screen.getByText("Não consegui falar com o sistema agora.")).toBeInTheDocument();
    // A mesma chave nas duas tentativas: o mesmo clique nunca anota duas vezes.
    const [primeira, segunda] = acoes.adicionarItem.mock.calls.map((chamada) => (chamada[0] as { id_cliente: string }).id_cliente);
    expect(primeira).toBe(segunda);
  });

  it("corrigir: o nome fica só para leitura, e só vai o que mudou", async () => {
    acoes.corrigirItem.mockResolvedValue(deu(ESCRITA.corrigir_preco?.resposta));
    const aoFechar = vi.fn();
    montar(<FormularioDoItem pedido={{ modo: "editar", item: PECA }} aoFechar={aoFechar} categorias={categorias} />);
    const folha = screen.getByRole("dialog", { name: "Corrigir Peito de frango" });
    expect(within(folha).getByLabelText("Nome do ingrediente")).toHaveAttribute("readonly");
    expect(within(folha).getByText("Para trocar o nome, tire o item e acrescente de novo.")).toBeInTheDocument();
    expect(within(folha).getByText("Hoje: 2 kg. Em branco, continua assim.")).toBeInTheDocument();
    expect(within(folha).getByText("De onde veio:")).toBeInTheDocument();

    fireEvent.click(within(folha).getByRole("button", { name: "Salvar" }));
    expect(await within(folha).findByRole("alert")).toHaveTextContent("Nada mudou.");
    expect(acoes.corrigirItem).not.toHaveBeenCalled();

    fireEvent.change(within(folha).getByLabelText(/Quanto pagou/), { target: { value: "30" } });
    fireEvent.change(within(folha).getByLabelText("Categoria"), { target: { value: "outros" } });
    fireEvent.click(within(folha).getByRole("button", { name: "Salvar" }));
    await esperar();
    expect(acoes.corrigirItem).toHaveBeenCalledWith("peito-de-frango", {
      categoria: "outros",
      preco_pago: 30,
      id_cliente: expect.any(String),
    });
    expect(aoFechar).toHaveBeenCalledOnce();
  });

  it("corrigir a medida pede o estoque e a quantidade nela; sem mudar, o rótulo dela volta como estava", async () => {
    acoes.corrigirItem.mockResolvedValue(deu(ESCRITA.acabou?.resposta));
    const balde = { ...PECA, unidade_compra_rotulo: "balde 2kg" };
    montar(<FormularioDoItem pedido={{ modo: "editar", item: balde }} aoFechar={() => {}} categorias={categorias} />);
    const folha = screen.getByRole("dialog");
    expect(within(folha).getByLabelText("Como a senhora mede")).toHaveValue("embalagem");
    fireEvent.change(within(folha).getByLabelText("Quantas embalagens tem agora"), { target: { value: "3" } });
    fireEvent.click(within(folha).getByRole("button", { name: "Salvar" }));
    await esperar();
    expect(acoes.corrigirItem).toHaveBeenLastCalledWith("peito-de-frango", {
      estoque: 3,
      unidade: "balde 2kg",
      id_cliente: expect.any(String),
    });

    fireEvent.change(within(folha).getByLabelText("Como a senhora mede"), { target: { value: "g" } });
    fireEvent.change(within(folha).getByLabelText("Quanto tem agora"), { target: { value: "" } });
    fireEvent.click(within(folha).getByRole("button", { name: "Salvar" }));
    expect(await within(folha).findByText("Com a medida nova, diga quanto comprou nela.")).toBeInTheDocument();
    expect(acoes.corrigirItem).toHaveBeenCalledTimes(1);
  });

  it("fechado, não mostra nada; abrir de novo começa do zero", () => {
    const { rerender } = montar(
      <FormularioDoItem pedido={null} aoFechar={() => {}} categorias={categorias} orcamento={null} />,
    );
    expect(screen.queryByLabelText("Nome do ingrediente")).not.toBeInTheDocument();
    const abrirCom = (origem: "ja_tinha" | "orcamento") =>
      rerender(
        <ProvedorDeToasts>
          <FormularioDoItem pedido={{ modo: "novo", origem }} aoFechar={() => {}} categorias={categorias} orcamento={null} />
        </ProvedorDeToasts>,
      );
    abrirCom("orcamento");
    expect(screen.getByRole("radio", { name: "Comprei com o orçamento" })).toBeChecked();
  });
});

/* -------------------------------------------------------------------------- */

describe("DetalheDoIngrediente", () => {
  function montarDetalhe(detalhe: DetalheDoItem = COMPRADO, receitas = [] as Parameters<typeof DetalheDoIngrediente>[0]["receitas"]) {
    return montar(
      <DetalheDoIngrediente detalhe={detalhe} receitas={receitas} categorias={LISTA.categorias_para_escolher} orcamento={LISTA.orcamento} />,
    );
  }

  it("a conta inteira, com a derivação à vista e a confiança", () => {
    montarDetalhe();
    expect(screen.getByRole("heading", { level: 1, name: "Creme de leite" })).toBeInTheDocument();
    expect(screen.getByText("Laticínios · Comprado com os complementos")).toBeInTheDocument();
    const conta = screen.getByRole("region", { name: "A conta" });
    expect(within(conta).getByText("400 g (2 embalagens de 200 g)")).toBeInTheDocument();
    expect(within(conta).getByText("2 embalagens de 200 g por R$ 9,00")).toBeInTheDocument();
    expect(within(conta).getByText("Custo por quilo")).toBeInTheDocument();
    expect(within(conta).getByText("R$ 22,50/kg")).toBeInTheDocument();
    expect(within(conta).getByText(/R\$ 9,00 ÷ 0,4 kg/)).toBeInTheDocument();
    expect(within(conta).getByText("Conta com conversão de embalagem")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Compras com os complementos" })).toBeInTheDocument();
  });

  it("sem receita, chama para procurar; com receitas, cada uma com o selo dela", () => {
    const { unmount } = montarDetalhe(PECA);
    expect(screen.getByText("Nenhuma receita usa isso ainda")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Procurar receitas" })).toHaveAttribute(
      "href",
      "/receitas?usa=peito-de-frango",
    );
    expect(screen.queryByRole("region", { name: "Compras com os complementos" })).not.toBeInTheDocument();
    unmount();
    montarDetalhe(PECA, [
      { slug: "a", nome: "Arroz com frango", imagem: null, rota: "/receitas/a", usa_texto: "usa 500 g", selo: { texto: "Com o que a senhora tem", codigo: "com_o_que_tem" } },
      { slug: "b", nome: "Frango com milho", imagem: null, rota: "/receitas/b", usa_texto: "usa 300 g", selo: { texto: "Comprando R$ 6,00, cabe nos R$ 80,00", codigo: "comprando" } },
      { slug: "c", nome: "Frango assado", imagem: null, rota: "/receitas/c", usa_texto: "usa 1 kg", selo: { texto: "Falta saber", veredito: "FALTA INFO" } },
      { slug: "d", nome: "Canja", imagem: null, rota: "/receitas/d", usa_texto: "usa 200 g", selo: { texto: "Sem código" } },
    ]);
    expect(screen.getByRole("link", { name: "Arroz com frango" })).toHaveAttribute("href", "/receitas/a");
    expect(screen.getByText("Comprando R$ 6,00, cabe nos R$ 80,00")).toHaveClass("text-info");
    expect(screen.getByText("Sem código")).toHaveClass("text-sucesso");
    expect(screen.getByText("Falta saber")).toBeInTheDocument();
  });

  it("Acabou zera o estoque, com o aviso e o Desfazer", async () => {
    acoes.corrigirItem.mockResolvedValue(deu(ESCRITA.acabou?.resposta));
    montarDetalhe();
    fireEvent.click(screen.getByRole("button", { name: "Acabou" }));
    await esperar();
    expect(acoes.corrigirItem).toHaveBeenCalledWith("item-4f7a1c2e", { estoque: 0, id_cliente: expect.any(String) });
    const aviso = screen.getByText("Anotei que o arroz branco tipo 1 acabou.").parentElement as HTMLElement;
    expect(within(aviso).getByRole("button", { name: "Desfazer" })).toBeInTheDocument();
  });

  it("tirar da despensa confirma, volta para a lista e oferece desfazer", async () => {
    acoes.removerItem.mockResolvedValue(deu(ESCRITA.remover?.resposta));
    montarDetalhe();
    fireEvent.click(screen.getByRole("button", { name: "Tirar da despensa" }));
    const confirmar = screen.getByRole("alertdialog", { name: "Tirar creme de leite da despensa?" });
    expect(confirmar).toHaveTextContent("O que a senhora pagou volta para os complementos.");
    fireEvent.click(within(confirmar).getByRole("button", { name: "Tirar da despensa" }));
    await esperar();
    expect(acoes.removerItem).toHaveBeenCalledWith("item-4f7a1c2e", expect.any(String), { atualizar: false });
    expect(roteador.push).toHaveBeenCalledWith("/despensa");
    expect(screen.getByText(ESCRITA.remover?.resposta.texto as string)).toBeInTheDocument();
  });

  it("o item da planilha: confirmação sem devolução; o item que acabou não tem Acabou; e editar abre a folha", () => {
    montarDetalhe({ ...PECA, estoque: 0, estoque_texto: "acabou", pendencia: LISTA.pendencias[0] ?? null });
    expect(screen.queryByRole("button", { name: "Acabou" })).not.toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /quanto vem na embalagem/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tirar da despensa" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Dá para desfazer logo depois, no aviso ou no histórico.");
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByRole("dialog", { name: "Corrigir Peito de frango" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Cancelar" }).at(-1) as HTMLElement);
  });

  it("sem preço nem custo, diz o que falta; outra unidade tem o seu custo", () => {
    montarDetalhe({ ...PECA, pago: null, custo_unitario: null, unidade: "L" });
    expect(screen.getByText("A senhora ainda não disse")).toBeInTheDocument();
    expect(screen.getByText("Ainda não dá para saber")).toBeInTheDocument();
    expect(screen.getByText("Custo por litro")).toBeInTheDocument();
  });
});

describe("HistoricoDoItem", () => {
  it("do mais novo para o mais antigo, com o canal, o motivo e o Desfazer na última mudança", async () => {
    acoes.desfazerMudanca.mockResolvedValue(recusou("só a última mudança de um item dá para desfazer"));
    const historico = [
      ...(PECA.historico ?? []),
      { ...(COMPRADO.historico[0] as DetalheDoItem["historico"][number]), id: "ev-0009", tipo: "corrigir", canal: "conversa", motivo: "achei mais", pode_desfazer: true },
      { ...(COMPRADO.historico[0] as DetalheDoItem["historico"][number]), id: "ev-0010", tipo: "outro", canal: "zap", pode_desfazer: false },
    ];
    montar(<HistoricoDoItem historico={historico} />);
    const itens = screen.getAllByRole("listitem");
    expect(itens[0]).toHaveTextContent("hoje, 10:02, zap");
    expect(itens[1]).toHaveTextContent("hoje, 10:02, pela conversa");
    expect(itens[1]).toHaveTextContent("Motivo: achei mais");
    expect(itens[2]).toHaveTextContent("na planilha que a senhora entregou");
    fireEvent.click(within(itens[1] as HTMLElement).getByRole("button", { name: "Desfazer" }));
    await esperar();
    await waitFor(() => expect(acoes.desfazerMudanca).toHaveBeenCalledWith("ev-0009", expect.any(String)));
    expect(await screen.findByText("só a última mudança de um item dá para desfazer")).toBeInTheDocument();
  });

  it("sem mudança nenhuma, diz isso", () => {
    montar(<HistoricoDoItem historico={[]} />);
    expect(screen.getByText("Nenhuma mudança ainda.")).toBeInTheDocument();
  });
});

describe("os casos de borda", () => {
  it("compra pela conversa, compra já devolvida e a devolução que não muda as outras", async () => {
    acoes.devolverCompra.mockResolvedValue(deu({ texto: "Devolvi." }));
    const base = LISTA.orcamento.compras[0] as ListaDaDespensa["orcamento"]["compras"][number];
    montar(
      <PainelDoOrcamento
        orcamento={{
          ...LISTA.orcamento,
          compras: [
            { ...base, id: 5, canal: "conversa" },
            { ...base, id: 4, estornada: true, pode_estornar: false, descricao: "Milho (despensa)" },
            { ...base, id: 3, item_id: null, descricao: "Tomate avulso" },
          ],
        }}
        aoRegistrarCompra={() => {}}
      />,
    );
    const [maisNova, devolvida, avulsa] = screen.getAllByRole("listitem");
    expect(maisNova).toHaveTextContent("hoje, 10:02, pela conversa");
    expect(within(devolvida as HTMLElement).getByText("Voltou para o orçamento")).toBeInTheDocument();
    expect(within(devolvida as HTMLElement).queryByRole("link")).not.toBeInTheDocument();
    expect(within(avulsa as HTMLElement).queryByRole("link")).not.toBeInTheDocument();
    fireEvent.click(within(maisNova as HTMLElement).getByRole("button", { name: "Devolver ao orçamento" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Devolver" }));
    await esperar();
    expect(acoes.devolverCompra).toHaveBeenCalledWith(5, expect.any(String));
  });

  it("filtro desconhecido na URL aparece como veio; pergunta de item fora da lista não pergunta a quantidade", () => {
    irPara("/despensa?confianca=xyz&origem=abc&categoria=joias");
    montar(<TelaDaDespensa lista={{ ...LISTA, pendencias: [{ ...pendencia("preco_pago"), id: "sumiu" }] }} />);
    const ativos = screen.getByRole("list", { name: "Filtros ativos" });
    expect(within(ativos).getByRole("button", { name: "xyz: tirar este filtro" })).toBeInTheDocument();
    expect(within(ativos).getByRole("button", { name: "abc: tirar este filtro" })).toBeInTheDocument();
    expect(within(ativos).getByRole("button", { name: "joias: tirar este filtro" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Quanto veio por esse preço/)).not.toBeInTheDocument();
    // "Limpar filtros" dos chips ativos tira tudo de uma vez.
    fireEvent.click(screen.getAllByRole("button", { name: "Limpar filtros" })[0] as HTMLElement);
    expect(window.location.search).toBe("");
    // A folha fecha pelo X também.
    fireEvent.click(screen.getByRole("button", { name: /^Filtros/ }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Filtros" })).getByRole("button", { name: "Fechar" }));
    expect(screen.getByRole("button", { name: /^Filtros/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("unidade que a tela não conhece: o custo é por unidade; sem o orçamento, o formulário se vira", () => {
    montar(
      <DetalheDoIngrediente detalhe={{ ...PECA, unidade: "dz" }} receitas={[]} categorias={LISTA.categorias_para_escolher} />,
    );
    expect(screen.getByText("Custo por unidade")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByRole("dialog", { name: "Corrigir Peito de frango" })).toBeInTheDocument();
  });
});

describe("semLancar", () => {
  it("a ação que lança vira falha de rede", async () => {
    await expect(semLancar(() => Promise.reject(new Error("fora do ar")))).resolves.toMatchObject({
      ok: false,
      erro: { categoria: "rede" },
    });
  });
});
