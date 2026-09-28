/**
 * Pôr preço num prato: o formulário (com o tempo no fogo), a conferência com
 * as respostas ali mesmo, o custo de uma porção, os três caminhos sem destaque,
 * o controle com os limites da API e a decisão dela. A API é trocada por
 * espiões: a tela não faz conta, só mostra o que volta.
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

const sincronizacao = vi.hoisted(() => ({ avisar: vi.fn() }));
vi.mock("@/lib/dados/sincronizacao", async (original) => ({
  ...(await original<typeof import("@/lib/dados/sincronizacao")>()),
  useSincronizacao: () => ({ avisar: sincronizacao.avisar, assinar: () => () => {} }),
}));

import { ErroDoMotor } from "@/lib/api/base";
import { cardapio, cardapioDeHoje } from "@/lib/api/cardapio";
import { perfil } from "@/lib/api/perfil";
import type { ConfirmacaoDaCozinha, RespostaDaCozinha } from "@/lib/api/perfil";
import type { Avaliacao, CMV, PontoPreco, TabelaPrecos } from "@/lib/api/preco";
import { precoDeHoje } from "@/lib/api/preco";
import type { PerguntaDaReceita, ReceitaGuardada } from "@/lib/api/receitas";
import { receitas, receitasDeHoje } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { montar } from "@/teste/receitas";

import { PAUSA_DO_CONTROLE_MS } from "./ControleDePreco";
import { RASCUNHO_VAZIO, rascunhoDe, receitaDo } from "./rascunho";
import { TelaDePorPreco } from "./TelaDePorPreco";

const CUSTO = contrato<CMV>("custo.json");
const TABELA = contrato<{ dados: TabelaPrecos }>("cartoes/cenarios.json").dados;

function pergunta(extras: Partial<PerguntaDaReceita>): PerguntaDaReceita {
  return {
    tipo: "operacional",
    assunto: "rotina",
    campo: "x",
    texto: "Uma pergunta?",
    motivo: "um motivo",
    compras: [],
    opcoes: [],
    entrada: null,
    passos: [],
    ...extras,
  };
}

const TEMPO = pergunta({
  assunto: "tempo_cozimento",
  campo: "tempo_cozimento_min",
  texto: "Quanto tempo fica no fogo?",
  entrada: { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 },
});

function avaliacao(extras: Partial<Avaliacao> = {}): Avaliacao {
  return {
    prato: "Bolo de cenoura",
    receita_id: "bolo-de-cenoura",
    veredito: "APTO",
    pode_precificar: true,
    resumo: "Dá pra fazer com o que a senhora tem.",
    impedimentos: [],
    perguntas: [],
    ingredientes_na_despensa: [{ ingrediente: "Farinha", quantidade: "2 xícaras", custo: { valor: 1.2, texto: "R$ 1,20" }, derivacao: "0,24 kg a R$ 5,00 o quilo" }],
    falta_comprar: [],
    a_gosto: [],
    pode_aceitar: true,
    falta_para_aceitar: [],
    confirmar_a_cozinha: null,
    ...extras,
  };
}

function ponto(preco: number, extras: Partial<PontoPreco> = {}): PontoPreco {
  const texto = `R$ ${preco.toFixed(2).replace(".", ",")}`;
  return {
    preco: { valor: preco, texto },
    taxa: { valor: 0, texto: "R$ 0,99" },
    recebe: { valor: 0, texto: "R$ 9,99" },
    lucro: { valor: 1, texto: "R$ 99,99" },
    food_cost: 0.25,
    margem: 0.5,
    da_prejuizo: false,
    explicacao: `A conta de ${texto}, escrita pela API.`,
    ...extras,
  };
}

let avaliar: MockInstance<typeof precoDeHoje.avaliar>;
let cmv: MockInstance<typeof precoDeHoje.cmv>;
let precos: MockInstance<typeof precoDeHoje.precos>;
let precoEm: MockInstance<typeof precoDeHoje.precoEm>;
let decidir: MockInstance<typeof cardapio.decidir>;

beforeEach(() => {
  avaliar = vi.spyOn(precoDeHoje, "avaliar").mockResolvedValue(avaliacao());
  cmv = vi.spyOn(precoDeHoje, "cmv").mockResolvedValue(CUSTO);
  precos = vi.spyOn(precoDeHoje, "precos").mockResolvedValue(structuredClone(TABELA));
  precoEm = vi.spyOn(precoDeHoje, "precoEm").mockImplementation(async (_prato, valor) => ponto(valor));
  decidir = vi.spyOn(cardapio, "decidir").mockResolvedValue({ prato: "Bolo de cenoura", decisao: "aceito", texto: "A senhora aceitou o bolo de cenoura a R$ 8,57.", cardapio: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function preencher({ tempo }: { tempo?: string } = {}) {
  fireEvent.change(screen.getByRole("textbox", { name: /Nome do prato/ }), { target: { value: "Bolo de cenoura" } });
  fireEvent.change(screen.getByRole("textbox", { name: /Ingredientes, um por linha/ }), { target: { value: "2 xícaras de farinha\n3 cenouras" } });
  fireEvent.change(screen.getByRole("textbox", { name: /Como a senhora faz/ }), { target: { value: "Bata tudo.\nLeve ao forno." } });
  if (tempo) fireEvent.change(screen.getByRole("textbox", { name: /Quanto tempo fica no fogo/ }), { target: { value: tempo } });
}

async function conferir() {
  fireEvent.click(screen.getByRole("button", { name: "Conferir se dá pra fazer" }));
  await waitFor(() => expect(avaliar).toHaveBeenCalled());
}

describe("o formulário", () => {
  it("o tempo no fogo é opcional e vai na receita que a conferência recebe", async () => {
    montar(<TelaDePorPreco />);
    preencher({ tempo: "40" });
    await conferir();
    expect(avaliar).toHaveBeenCalledWith(expect.objectContaining({ nome: "Bolo de cenoura", tempo_cozimento_min: 40, rendimento_porcoes: 4 }));
    expect(avaliar.mock.calls[0]?.[0].modo_preparo).toEqual(["Bata tudo.", "Leve ao forno."]);
  });

  it("sem nome ou sem ingrediente, diz o que falta e não chama a API", () => {
    montar(<TelaDePorPreco />);
    fireEvent.click(screen.getByRole("button", { name: "Conferir se dá pra fazer" }));
    expect(screen.getByText("Escreva o nome do prato.")).toBeInTheDocument();
    expect(screen.getByText("Escreva pelo menos um ingrediente, um por linha.")).toBeInTheDocument();
    expect(avaliar).not.toHaveBeenCalled();
  });

  it("trazer a receita pelo endereço preenche os campos, e diz se falta o rendimento", async () => {
    const trazida = vi.spyOn(receitasDeHoje, "receitaDaWeb").mockResolvedValue({
      receita: { nome: "Frango assado", rendimento_porcoes: 4, rendimento_informado: false, modo_preparo: ["Asse."], url: "https://x.com.br/f", fonte: "X", ingredientes: [{ texto: "1 frango", nome: "frango", quantidade: 1, medida: "un" }] },
      procedencia: { url: "https://x.com.br/f", fonte: "TudoGostoso", citacao: "" },
    });
    montar(<TelaDePorPreco />);
    fireEvent.click(screen.getByRole("button", { name: "Trazer receita" }));
    expect(screen.getByText("Cole o endereço da receita, que começa com https://.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /Endereço da receita/ }), { target: { value: " https://x.com.br/f " } });
    fireEvent.click(screen.getByRole("button", { name: "Trazer receita" }));
    await waitFor(() => expect(trazida).toHaveBeenCalledWith("https://x.com.br/f"));
    expect(await screen.findByText("Receita do TudoGostoso. O site não diz quantas porções rende: preencha abaixo.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Nome do prato/ })).toHaveValue("Frango assado");
    await conferir();
    expect(avaliar).toHaveBeenCalledWith(expect.objectContaining({ url: "https://x.com.br/f", fonte: "TudoGostoso" }));
  });

  it("a receita trazida com o rendimento pede só para conferir, e o erro vira frase dela", async () => {
    const trazida = vi.spyOn(receitasDeHoje, "receitaDaWeb");
    trazida.mockRejectedValueOnce(new ErroDoMotor("Essa página não tem uma receita que eu consiga ler.", "uso"));
    trazida.mockResolvedValueOnce({
      receita: { nome: "Pudim", rendimento_porcoes: 8, rendimento_informado: true, modo_preparo: [], url: null, fonte: null, ingredientes: [] },
      procedencia: { url: "https://x.com.br/p", fonte: "Panelinha", citacao: "" },
    });
    montar(<TelaDePorPreco />);
    fireEvent.change(screen.getByRole("textbox", { name: /Endereço da receita/ }), { target: { value: "https://x.com.br/p" } });
    fireEvent.click(screen.getByRole("button", { name: "Trazer receita" }));
    expect(await screen.findByText("Essa página não tem uma receita que eu consiga ler.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Trazer receita" }));
    expect(await screen.findByText("Receita do Panelinha. Confira as linhas antes de seguir.")).toBeInTheDocument();
  });

  it("vindo de outra tela, abre com a receita guardada", () => {
    const guardada: ReceitaGuardada = {
      nome: "Arroz com frango",
      rendimento_porcoes: 4,
      rendimento_informado: true,
      modo_preparo: ["Refogue."],
      tempo_cozimento_min: 40,
      url: null,
      fonte: null,
      ingredientes: [{ texto: "500 g de frango", nome: "frango", quantidade: 500, medida: "g" }],
    };
    montar(<TelaDePorPreco inicial={guardada} />);
    expect(screen.getByRole("textbox", { name: /Nome do prato/ })).toHaveValue("Arroz com frango");
    expect(screen.getByRole("textbox", { name: /Quanto tempo fica no fogo/ })).toHaveValue("40");
  });
});

describe("o peso de uma linha e o item parecido, respondidos ali mesmo", () => {
  const PESO = pergunta({
    tipo: "ingrediente",
    assunto: "medida",
    campo: "2 peitos de frango",
    texto: "Não sei quanto pesa um peito de frango. Se a senhora souber, em gramas, eu calculo.",
    entrada: { tipo: "peso", unidade: "g", peso_de: { cada: "1 peito de frango", tudo: "2 peitos de frango" } },
  });
  const PARECIDO = pergunta({
    tipo: "ingrediente",
    assunto: "mesmo_ingrediente",
    campo: "300 g de alcatra",
    texto: "A receita pede alcatra. É o seu miolo de alcatra?",
    opcoes: [
      { rotulo: "É, sim", resposta: "sim" },
      { rotulo: "Não é", resposta: "nao" },
    ],
  });

  it("o peso vai para a receita guardada, de uma unidade, e a tela confere de novo", async () => {
    const responder = vi.spyOn(receitas, "responder").mockResolvedValue({} as never);
    avaliar.mockResolvedValueOnce(avaliacao({ veredito: "FALTA INFO", pode_precificar: false, perguntas: [PESO] }));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    fireEvent.change(await screen.findByRole("textbox", { name: "Quanto pesa" }), { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() =>
      expect(responder).toHaveBeenCalledWith("bolo-de-cenoura", { campo: "2 peitos de frango", resposta: "300 g", por_unidade: true }),
    );
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
  });

  it("o peso da linha inteira também vale; sem número, diz o que escrever", async () => {
    const responder = vi.spyOn(receitas, "responder").mockResolvedValue({} as never);
    avaliar.mockResolvedValueOnce(avaliacao({ veredito: "FALTA INFO", pode_precificar: false, perguntas: [PESO] }));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    fireEvent.click(await screen.findByRole("button", { name: "Responder" }));
    expect(await screen.findByText("Escreva quanto pesa, por exemplo: 300 g.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Quanto pesa" }), { target: { value: "0,6" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Unidade" }), { target: { value: "kg" } });
    fireEvent.click(screen.getByText("2 peitos de frango", { selector: "span" }));
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() =>
      expect(responder).toHaveBeenCalledWith("bolo-de-cenoura", { campo: "2 peitos de frango", resposta: "0,6 kg", por_unidade: false }),
    );
  });

  it("É o seu item? vai para a receita guardada, e a tela confere de novo", async () => {
    const responder = vi.spyOn(receitas, "responder").mockResolvedValue({} as never);
    avaliar.mockResolvedValueOnce(avaliacao({ veredito: "FALTA INFO", pode_precificar: false, perguntas: [PARECIDO] }));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    fireEvent.click(await screen.findByRole("button", { name: "É, sim" }));
    await waitFor(() => expect(responder).toHaveBeenCalledWith("bolo-de-cenoura", { campo: "300 g de alcatra", resposta: "sim" }));
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
  });

  it("sem a receita guardada, a pergunta vai para a conversa", async () => {
    avaliar.mockResolvedValueOnce(avaliacao({ receita_id: undefined, veredito: "FALTA INFO", pode_precificar: false, perguntas: [PESO] }));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    expect(await screen.findByRole("button", { name: "Responder no chat" })).toBeInTheDocument();
  });
});

describe("a conferência", () => {
  it("sem liberar, mostra o que falta saber e nenhum preço", async () => {
    avaliar.mockResolvedValue(avaliacao({ veredito: "FALTA INFO", pode_precificar: false, perguntas: [TEMPO], resumo: "Falta saber uma coisa." }));
    const { container } = montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    expect(await screen.findByText("O que eu ainda preciso saber")).toBeInTheDocument();
    expect(screen.getByText("O preço só aparece depois que eu confirmo que a senhora consegue fazer este prato.")).toBeInTheDocument();
    expect(cmv).not.toHaveBeenCalled();
    expect(screen.queryByText("Três caminhos de preço")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a pergunta do tempo no fogo volta para a receita, e não para as respostas da cozinha", async () => {
    avaliar.mockResolvedValueOnce(avaliacao({ veredito: "FALTA INFO", pode_precificar: false, perguntas: [TEMPO] }));
    const restricao = vi.spyOn(perfil, "definirRestricao");
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    const campo = await screen.findByRole("textbox", { name: "Minutos no fogo" });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    expect(await screen.findByText("Escreva o número de minutos.")).toBeInTheDocument();
    fireEvent.change(campo, { target: { value: "35" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
    expect(avaliar.mock.calls[1]?.[0].tempo_cozimento_min).toBe(35);
    expect(restricao).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: /Quanto tempo fica no fogo/ })).toHaveValue("35");
  });

  it("o rendimento também volta para a receita", async () => {
    const rende = pergunta({ assunto: "rendimento", campo: "rendimento_porcoes", texto: "Rende quantas?", entrada: { tipo: "inteiro", unidade: "porções", min: 1, max: 500 } });
    avaliar.mockResolvedValueOnce(avaliacao({ pode_precificar: false, veredito: "FALTA INFO", perguntas: [rende] }));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    fireEvent.change(await screen.findByRole("textbox", { name: "Porções" }), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() => expect(avaliar.mock.calls[1]?.[0].rendimento_porcoes).toBe(6));
  });

  it("equipamento, rotina, gás e gosto vão cada um para o seu lugar, e a tela confere de novo", async () => {
    const forno = pergunta({ tipo: "equipamento", assunto: "equipamento", campo: "forno", texto: "Tem forno?", opcoes: [{ rotulo: "Tenho", resposta: "sim" }, { rotulo: "Não tenho", resposta: "nao" }] });
    const bocas = pergunta({ campo: "bocas_fogao", texto: "Quantas bocas?", opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }], entrada: { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 } });
    const gas = pergunta({ campo: "tem_gas_sobrando", texto: "Tem gás sobrando?", opcoes: [{ rotulo: "Sim", resposta: "sim" }] });
    const gosto = pergunta({ tipo: "gosto", assunto: "gosto", campo: "Bolo de cenoura", texto: "Gosta de fazer?" });
    avaliar.mockResolvedValue(avaliacao({ pode_precificar: false, veredito: "FALTA INFO", perguntas: [forno, bocas, gas, gosto] }));
    const posse = vi.spyOn(perfil, "definirPosse").mockResolvedValue({} as never);
    const restricao = vi.spyOn(perfil, "definirRestricao").mockResolvedValue({} as never);
    const gostou = vi.spyOn(cardapioDeHoje, "registrarGosto").mockResolvedValue({} as never);
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    fireEvent.click(await screen.findByRole("button", { name: "Tenho" }));
    await waitFor(() => expect(posse).toHaveBeenCalledWith("equipamentos", "forno", "tem"));
    fireEvent.change(screen.getByRole("textbox", { name: "Bocas" }), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() => expect(restricao).toHaveBeenCalledWith("bocas_fogao", 4));
    fireEvent.click(screen.getAllByRole("button", { name: "Não sei" })[0] as HTMLElement);
    await waitFor(() => expect(restricao).toHaveBeenCalledWith("bocas_fogao", null));
    fireEvent.click(screen.getByRole("button", { name: "Sim" }));
    await waitFor(() => expect(restricao).toHaveBeenCalledWith("tem_gas_sobrando", true));
    fireEvent.click(screen.getByRole("button", { name: /Ver mais/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /Algum impedimento/ }), { target: { value: "suja o forno" } });
    fireEvent.click(screen.getByRole("button", { name: "Gosto de fazer" }));
    await waitFor(() => expect(gostou).toHaveBeenCalledWith("Bolo de cenoura", true, "suja o forno"));
    expect(avaliar.mock.calls.length).toBeGreaterThanOrEqual(5);
  });

  it("o preço do que falta vai com a quantidade, e a resposta que a API recusa aparece", async () => {
    const falta = pergunta({ tipo: "ingrediente", assunto: "preco_de_compra", campo: "milho verde", texto: "Falta comprar: milho verde. Quanto custa?" });
    avaliar.mockResolvedValue(avaliacao({ pode_precificar: false, veredito: "FALTA INFO", perguntas: [falta], falta_comprar: [{ ingrediente: "milho verde", quanto: "1 lata", custo: null }] }));
    const registrar = vi.spyOn(precoDeHoje, "registrarPreco");
    registrar.mockRejectedValueOnce(new ErroDoMotor("Esse preço não serve.", "uso"));
    registrar.mockResolvedValue({} as never);
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    expect(await screen.findByText("falta o preço")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar o preço" }));
    expect(screen.getByText("Diga o preço de milho verde e por qual quantidade: 1 lata, 1 kg, 1 pacote.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Preço" }), { target: { value: "6" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Medida" }), { target: { value: "lata" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar o preço" }));
    expect(await screen.findByText("Esse preço não serve.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar o preço" }));
    await waitFor(() => expect(registrar).toHaveBeenLastCalledWith("milho verde", 6, { quantidade: 1, unidade: "lata" }));
  });

  it("o preparo e a linha se corrigem na receita; o resto vai para a conversa", async () => {
    const preparo = pergunta({ tipo: "equipamento", assunto: "modo_preparo", campo: "modo_preparo", texto: "Como faz?" });
    const linha = pergunta({ tipo: "ingrediente", assunto: "linha_nao_lida", campo: "sal", texto: "Não entendi quanto vai de sal nessa receita, a senhora sabe?" });
    const outra = pergunta({ tipo: "ingrediente", assunto: "ingrediente", campo: "outra", texto: "Uma pergunta que só a conversa responde." });
    avaliar.mockResolvedValue(
      avaliacao({ pode_precificar: false, veredito: "BLOQUEADO", perguntas: [preparo, linha, outra], impedimentos: [{ tipo: "equipamento", id: "forno", motivo: "a receita vai ao forno" }, { tipo: "estranho", id: "x", motivo: "um motivo" }] }),
    );
    const { loja } = montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    expect(await screen.findByText("O que impede")).toBeInTheDocument();
    expect(screen.getByText("Equipamentos")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ir para o campo" }));
    expect(screen.getByRole("textbox", { name: /Como a senhora faz/ })).toHaveFocus();
    expect(screen.getByText(/Escreva na linha dessa receita/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Responder no chat" }));
    expect(loja.ler().caixa.texto).toBe("Sobre Bolo de cenoura: ");
  });

  it("a conferência que falha mostra o problema, e Tentar de novo confere de novo", async () => {
    avaliar.mockRejectedValueOnce(new ErroDoMotor("não deu", "uso"));
    avaliar.mockRejectedValueOnce(new Error("rede"));
    montar(<TelaDePorPreco />);
    preencher();
    await conferir();
    expect(await screen.findByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Não consegui falar com o sistema")).toBeInTheDocument();
  });
});

describe("o preço", () => {
  async function ateOsPrecos() {
    const tela = montar(<TelaDePorPreco />);
    preencher({ tempo: "40" });
    await conferir();
    await screen.findByText("Três caminhos de preço");
    return tela;
  }

  it("com a conferência liberada, mostra o custo e os três caminhos, sem nenhum em destaque", async () => {
    const { container } = await ateOsPrecos();
    expect(precos).toHaveBeenCalledWith(CUSTO.prato, CUSTO.total.valor);
    expect(screen.getByText(`Custo de uma porção de ${CUSTO.prato}`)).toBeInTheDocument();
    expect(screen.getByText(CUSTO.total.texto)).toBeInTheDocument();
    const caminhos = within(screen.getByRole("region", { name: "Três caminhos de preço" })).getAllByRole("article");
    expect(caminhos).toHaveLength(3);
    for (const [indice, cenario] of TABELA.cenarios.entries()) {
      expect(within(caminhos[indice] as HTMLElement).getByRole("button", { name: `Vou cobrar ${cenario.preco.texto}` })).toBeInTheDocument();
      expect(caminhos[indice]).not.toHaveClass("ring-1");
    }
    expect(screen.queryByText(/equilíbrio/i)).not.toBeInTheDocument();
    expect(screen.getByText("Nenhum é recomendação: quem escolhe é a senhora.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("o controle usa os limites da API, começa no mínimo e mostra só o que a API respondeu", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await ateOsPrecos();
    const controle = screen.getByRole("slider", { name: "Preço de uma porção" });
    expect(controle).toHaveAttribute("min", String(TABELA.controle.min.valor));
    expect(controle).toHaveAttribute("max", String(TABELA.controle.max.valor));
    expect(controle).toHaveAttribute("step", String(TABELA.controle.passo));
    expect(controle).toHaveValue(String(TABELA.controle.min.valor));
    expect(screen.getByText(`mínimo sem prejuízo ${TABELA.controle.min.texto}`)).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTime(PAUSA_DO_CONTROLE_MS));
    await waitFor(() => expect(precoEm).toHaveBeenCalledWith(TABELA.prato, TABELA.controle.min.valor));
    fireEvent.change(controle, { target: { value: "12" } });
    await act(async () => vi.advanceTimersByTime(PAUSA_DO_CONTROLE_MS));
    await waitFor(() => expect(precoEm).toHaveBeenLastCalledWith(TABELA.prato, 12));
    // O lucro é o texto da API (R$ 99,99), não uma conta feita aqui.
    expect(await screen.findByText("R$ 99,99")).toBeInTheDocument();
    expect(controle).toHaveAttribute("aria-valuetext", "R$ 12,00");
  });

  it("o prejuízo aparece em destaque, e o erro do ponto vira frase dela", async () => {
    precoEm.mockResolvedValueOnce(ponto(3.34, { da_prejuizo: true, lucro: { valor: -0.1, texto: "-R$ 0,10" } }));
    precoEm.mockRejectedValueOnce(new Error("sem rede"));
    await ateOsPrecos();
    expect(await screen.findByText("-R$ 0,10")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("slider", { name: "Preço de uma porção" }), { target: { value: "5" } });
    expect(await screen.findByText("Não consegui fazer a conta desse preço. Tente de novo.")).toBeInTheDocument();
  });

  it("escolher um caminho grava a decisão com o preço da API, e diz o que ficou", async () => {
    await ateOsPrecos();
    fireEvent.click(screen.getByRole("button", { name: `Vou cobrar ${TABELA.cenarios[1]?.preco.texto}` }));
    await waitFor(() =>
      expect(decidir).toHaveBeenCalledWith(expect.objectContaining({ prato: TABELA.prato, decisao: "aceito", preco: TABELA.cenarios[1]?.preco.valor })),
    );
    expect(await screen.findByText("A senhora aceitou o bolo de cenoura a R$ 8,57.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver o cardápio" })).toHaveAttribute("href", "/cardapio");
    // O cardápio (e o início) se refazem com o prato que ela acabou de pôr.
    expect(sincronizacao.avisar).toHaveBeenCalledWith(expect.arrayContaining(["cardapio", "visao-geral"]));
  });

  it("o preço do controle também se escolhe, e pensar ou recusar também são decisões dela", async () => {
    decidir.mockResolvedValueOnce({ prato: "x", decisao: "aceito", texto: "Aceitou.", cardapio: [], da_prejuizo: true, aviso: "A senhora perde R$ 0,10 por porção." });
    await ateOsPrecos();
    const cobrar = await screen.findByRole("button", { name: `Vou cobrar ${TABELA.controle.min.texto}` });
    fireEvent.click(cobrar);
    expect(await screen.findByText("A senhora perde R$ 0,10 por porção.")).toBeInTheDocument();
  });

  it("deixar para pensar e recusar gravam a decisão; o erro aparece sem sumir com a tela", async () => {
    decidir.mockRejectedValueOnce(new ErroDoMotor("não deu para anotar", "uso"));
    await ateOsPrecos();
    fireEvent.click(screen.getByRole("button", { name: "Deixa eu pensar" }));
    expect(await screen.findByText("não deu para anotar")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Esse prato não" }));
    await waitFor(() => expect(decidir).toHaveBeenLastCalledWith(expect.objectContaining({ decisao: "recusado" })));
  });

  it("uma faixa de custo aparece como faixa, com o topo usado no preço", async () => {
    cmv.mockResolvedValue({ ...CUSTO, e_faixa: true, rendimento_original: 1 });
    await ateOsPrecos();
    expect(screen.getByText(`entre ${CUSTO.minimo.texto} e ${CUSTO.maximo.texto}`)).toBeInTheDocument();
    expect(screen.getByText("entre dois valores")).toBeInTheDocument();
  });
});

describe("a cozinha a confirmar antes do Vou cobrar", () => {
  const PERGUNTA = "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?";
  const FALTA = ["Confirmar que a senhora tem fogão e que sabe refogar."];
  const ESPERANDO = avaliacao({
    pode_aceitar: false,
    falta_para_aceitar: FALTA,
    confirmar_a_cozinha: {
      pergunta: PERGUNTA,
      itens: [
        { tipo: "equipamento", id: "fogao", nome: "Fogão" },
        { tipo: "tecnica", id: "refogar", nome: "Refogar" },
      ],
    },
  });
  const CONFIRMACAO = contrato<{ resposta: ConfirmacaoDaCozinha }>("perfil-supostos.json").resposta;

  async function ateOsPrecos() {
    avaliar.mockResolvedValueOnce(ESPERANDO).mockResolvedValue(avaliacao());
    const tela = montar(<TelaDePorPreco />);
    preencher({ tempo: "40" });
    await conferir();
    await screen.findByText("Três caminhos de preço");
    return tela;
  }

  it("o preço aparece, mas o Vou cobrar espera: desabilitado, com o que falta, e sem gravar nada", async () => {
    const { container } = await ateOsPrecos();
    const guarda = screen.getByRole("region", { name: "Antes de cobrar, falta confirmar" });
    expect(within(guarda).getByText(PERGUNTA)).toBeInTheDocument();
    expect(within(guarda).getByText(FALTA[0] as string)).toBeInTheDocument();
    const caminho = screen.getByRole("button", { name: `Vou cobrar ${TABELA.cenarios[0]?.preco.texto}` });
    expect(caminho).toHaveAttribute("aria-disabled", "true");
    expect(caminho).toHaveAccessibleDescription(`Para a senhora cobrar este preço, falta: ${FALTA[0]}`);
    fireEvent.click(caminho);
    const doControle = await screen.findByRole("button", { name: `Vou cobrar ${TABELA.controle.min.texto}` });
    expect(doControle).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(doControle);
    expect(decidir).not.toHaveBeenCalled();
    // Pensar mais e deixar de fora valem sempre.
    expect(screen.getByRole("button", { name: "Deixa eu pensar" })).not.toHaveAttribute("aria-disabled");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Sim, tenho tudo isso confirma pela receita que a conferência guardou, e a conferência roda de novo", async () => {
    const confirmar = vi.spyOn(perfil, "confirmarSupostos").mockResolvedValue(CONFIRMACAO);
    await ateOsPrecos();
    fireEvent.click(screen.getByRole("button", { name: "Sim, tenho tudo isso" }));
    await waitFor(() => expect(confirmar).toHaveBeenCalledWith({ receita: "bolo-de-cenoura" }));
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Antes de cobrar, falta confirmar" })).not.toBeInTheDocument());
    expect(sincronizacao.avisar).toHaveBeenCalledWith(["perfil", "receitas"]);
    const caminho = await screen.findByRole("button", { name: `Vou cobrar ${TABELA.cenarios[1]?.preco.texto}` });
    expect(caminho).not.toHaveAttribute("aria-disabled");
    fireEvent.click(caminho);
    await waitFor(() => expect(decidir).toHaveBeenCalledWith(expect.objectContaining({ decisao: "aceito" })));
  });

  it("sem o id da receita, confirma os itens; o Não tenho grava só o item; a recusa aparece", async () => {
    avaliar.mockResolvedValueOnce({ ...ESPERANDO, receita_id: undefined }).mockResolvedValue(ESPERANDO);
    const confirmar = vi.spyOn(perfil, "confirmarSupostos").mockRejectedValue(new ErroDoMotor("não deu", "uso", "A senhora tem fogão?"));
    const naoTem = vi.spyOn(perfil, "definirPosse").mockResolvedValue(contrato<{ resposta: RespostaDaCozinha }>("perfil-escrita.json").resposta);
    montar(<TelaDePorPreco />);
    preencher({ tempo: "40" });
    await conferir();
    await screen.findByText("Três caminhos de preço");
    fireEvent.click(screen.getByRole("button", { name: "Sim, tenho tudo isso" }));
    await waitFor(() =>
      expect(confirmar).toHaveBeenCalledWith({
        itens: [
          { tipo: "equipamento", id: "fogao" },
          { tipo: "tecnica", id: "refogar" },
        ],
      }),
    );
    expect(await screen.findByText("A senhora tem fogão?")).toHaveAttribute("role", "alert");
    fireEvent.click(screen.getByRole("button", { name: "Não faço: Refogar" }));
    await waitFor(() => expect(naoTem).toHaveBeenCalledWith("tecnicas", "refogar", "nao_tem"));
    await waitFor(() => expect(avaliar).toHaveBeenCalledTimes(2));
  });
});

describe("o rascunho", () => {
  it("vazio, e da receita guardada, vira a receita que vai para a API", () => {
    expect(rascunhoDe(null)).toEqual(RASCUNHO_VAZIO);
    expect(receitaDo(RASCUNHO_VAZIO)).toBeNull();
    const rascunho = { ...RASCUNHO_VAZIO, nome: "Pudim", linhas: "1 lata de leite", rende: null, tempo: 50, origem: { url: "https://x.com.br", fonte: "X" } };
    expect(receitaDo(rascunho)).toMatchObject({ nome: "Pudim", rendimento_porcoes: 4, tempo_cozimento_min: 50, url: "https://x.com.br", fonte: "X" });
  });
});
