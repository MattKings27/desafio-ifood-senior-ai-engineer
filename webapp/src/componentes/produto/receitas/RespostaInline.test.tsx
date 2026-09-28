/**
 * A pergunta da cozinha que segura uma receita, respondida ali mesmo: cada
 * tipo com a sua resposta, a Server Action certa com o pedido certo, o aviso
 * do que mudou, e a recusa escrita perto do campo. O que não se responde com
 * um toque vai para a conversa, com o rascunho. Peso, medida, quantidade,
 * preço e o item parecido nunca aparecem.
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({
  responderSobreAReceita: vi.fn(),
  responderSobreACozinha: vi.fn(),
  responderLimiteDaCozinha: vi.fn(),
  informarPrecoDoQueFalta: vi.fn(),
  avaliarReceita: vi.fn(),
  anotarReceita: vi.fn(),
  trazerReceita: vi.fn(),
}));

import * as acoes from "@/lib/acoes/receitas";
import type { PerguntaDaReceita } from "@/lib/api/receitas";
import {
  PERGUNTAS_QUE_NAO_SAO_DELA,
  PERGUNTA_DO_TEMPO,
  TEXTOS_QUE_NUNCA_APARECEM,
  deuCerto,
  deuErrado,
  montar,
} from "@/teste/receitas";

import { ESPERA_DA_GRAVACAO_MS } from "@/componentes/produto/cozinha/useGravacaoAdiada";

import { PerguntaDePosse } from "./PerguntaDePosse";
import { PerguntaEmLinha } from "./RespostaInline";

const acao = vi.mocked(acoes);
const RECEITA = { slug: "pudim", nome: "Pudim de leite" };

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

/** O assunto de cada tipo, como a API manda: a rotina, o equipamento, a técnica. */
const ASSUNTO_DO_TIPO: Readonly<Record<string, PerguntaDaReceita["assunto"]>> = {
  operacional: "rotina",
  equipamento: "equipamento",
  tecnica: "tecnica",
};

function pergunta(extras: Partial<PerguntaDaReceita>): PerguntaDaReceita {
  return {
    tipo: "ingrediente",
    assunto: ASSUNTO_DO_TIPO[extras.tipo ?? ""] ?? "ingrediente",
    campo: "x",
    texto: "Pergunta?",
    motivo: "",
    compras: [],
    opcoes: [],
    entrada: null,
    passos: [],
    ...extras,
  };
}

const FORNO = pergunta({
  tipo: "equipamento",
  assunto: "equipamento",
  campo: "forno",
  texto: "A senhora tem forno?",
  motivo: "pudim precisa de forno",
  opcoes: [
    { rotulo: "Tenho", resposta: "sim" },
    { rotulo: "Não tenho", resposta: "nao" },
    { rotulo: "Não sei", resposta: "nao_sei" },
  ],
});

describe("equipamento e técnica: Tenho, Não tenho, Não sei", () => {
  it("a escolha responde, a cozinha recebe tem, e o aviso diz o que mudou", async () => {
    acao.responderSobreACozinha.mockResolvedValue(deuCerto({ texto: "Com forno, Pudim passa a dar." }));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={FORNO} />);
    const grupo = screen.getByRole("group", { name: "A senhora tem forno?" });
    expect(screen.getByText("Pudim precisa de forno.")).toBeInTheDocument();
    fireEvent.click(within(grupo).getByRole("radio", { name: "Tenho" }));
    expect(within(grupo).getByRole("radio", { name: "Tenho" })).toBeChecked();
    await waitFor(() => expect(acao.responderSobreACozinha).toHaveBeenCalledWith("equipamentos", "forno", "tem"));
    expect(await screen.findByText("Com forno, Pudim passa a dar.")).toBeInTheDocument();
    expect(within(grupo).getByRole("radio", { name: "Tenho" })).toBeChecked();
  });

  it("Não sei também é resposta, e a tela diz que anotou", async () => {
    acao.responderSobreACozinha.mockResolvedValue(deuCerto({ texto: "Anotado." }));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={FORNO} />);
    fireEvent.click(screen.getByRole("radio", { name: "Não sei" }));
    await waitFor(() => expect(acao.responderSobreACozinha).toHaveBeenCalledWith("equipamentos", "forno", "nao_sei"));
    expect(await screen.findByText(/Anotei que a senhora não sabe/)).toBeInTheDocument();
  });

  it("andar pelas opções com as setas manda só a última escolha", async () => {
    vi.useFakeTimers();
    acao.responderSobreACozinha.mockResolvedValue(deuCerto({ texto: "Anotado." }));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={FORNO} />);
    // Cada seta marca a opção seguinte: um `change` por tecla.
    fireEvent.click(screen.getByRole("radio", { name: "Tenho" }));
    fireEvent.click(screen.getByRole("radio", { name: "Não tenho" }));
    fireEvent.click(screen.getByRole("radio", { name: "Não sei" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ESPERA_DA_GRAVACAO_MS - 1);
    });
    expect(acao.responderSobreACozinha).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(acao.responderSobreACozinha).toHaveBeenCalledTimes(1);
    expect(acao.responderSobreACozinha).toHaveBeenCalledWith("equipamentos", "forno", "nao_sei");
  });

  it("a recusa aparece perto da pergunta, uma vez só, e a escolha volta", async () => {
    acao.responderSobreACozinha.mockResolvedValue(deuErrado("Esse equipamento não está na lista.", { pergunta: "Qual é o nome?" }));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={FORNO} />);
    fireEvent.click(screen.getByRole("radio", { name: "Não tenho" }));
    expect(await screen.findByText("Qual é o nome?")).toHaveAttribute("role", "alert");
    expect(screen.getAllByText("Qual é o nome?")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "Não tenho" })).not.toBeChecked();
  });

  it("a recusa sem pergunta mostra a mensagem", async () => {
    acao.responderSobreACozinha.mockResolvedValue(deuErrado("Esse equipamento não está na lista."));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={FORNO} />);
    fireEvent.click(screen.getByRole("radio", { name: "Tenho" }));
    expect(await screen.findByText("Esse equipamento não está na lista.")).toHaveAttribute("role", "alert");
  });

  it("a pergunta do passo também fala com a cozinha, com a pergunta como nome do grupo", async () => {
    acao.responderSobreACozinha.mockResolvedValue(deuCerto({ texto: "Anotado." }));
    montar(<PerguntaDePosse lista="tecnicas" id="fritar" legenda="A senhora sabe fritar?" legendaVisivel />);
    const grupo = screen.getByRole("group", { name: "A senhora sabe fritar?" });
    expect(within(grupo).getAllByRole("radio").map((opcao) => opcao.getAttribute("value"))).toEqual(["tem", "nao_tem", "nao_sei"]);
    fireEvent.click(within(grupo).getByRole("radio", { name: "Faço" }));
    await waitFor(() => expect(acao.responderSobreACozinha).toHaveBeenCalledWith("tecnicas", "fritar", "tem"));
  });
});

describe("número: as bocas do fogão e o espaço na geladeira", () => {
  const GELADEIRA = pergunta({
    tipo: "operacional",
    assunto: "rotina",
    campo: "espaco_geladeira_litros",
    texto: "Quantos litros sobram na geladeira?",
    entrada: { tipo: "inteiro", unidade: "litros", min: 1, max: 500 },
  });

  it("sem número, avisa antes de mandar; a recusa da API aparece no lugar", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuErrado("Não entendi quantos litros."));
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={GELADEIRA} />);
    const campo = screen.getByRole("textbox", { name: "Litros" });
    expect(campo).toHaveAccessibleDescription(GELADEIRA.texto);
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    expect(screen.getByText("Escreva o número de litros.")).toHaveAttribute("role", "alert");
    expect(acao.responderLimiteDaCozinha).not.toHaveBeenCalled();
    fireEvent.change(campo, { target: { value: "40" } });
    expect(screen.queryByText("Escreva o número de litros.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    expect(await screen.findByText("Não entendi quantos litros.")).toHaveAttribute("role", "alert");
    expect(acao.responderLimiteDaCozinha).toHaveBeenCalledWith("espaco_geladeira_litros", 40);
  });

  it("sem unidade, o campo se chama Resposta", () => {
    montar(
      <PerguntaEmLinha
        receita={RECEITA}
        pergunta={pergunta({ tipo: "operacional", assunto: "rotina", campo: "porcoes_por_fornada", entrada: { tipo: "inteiro" } })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    expect(screen.getByText("Escreva o número.")).toHaveAttribute("role", "alert");
    expect(screen.getByRole("textbox", { name: "Resposta" })).toBeInTheDocument();
  });

  it("as bocas do fogão vão para a cozinha, e Não sei manda nulo", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuCerto({ texto: "Anotado. Nenhuma receita muda." }));
    const bocas = pergunta({
      tipo: "operacional",
      assunto: "rotina",
      campo: "bocas_fogao",
      texto: "Seu fogão tem quantas bocas?",
      entrada: { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 },
      opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }],
    });
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={bocas} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Bocas" }), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenCalledWith("bocas_fogao", 4));
    expect(await screen.findByText("Anotado. Nenhuma receita muda.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Não sei" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenLastCalledWith("bocas_fogao", null));
  });
});

describe("as horas cozinhando de uma vez", () => {
  it("a resposta é em horas, com vírgula, e vai para a cozinha como número de horas", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuCerto({ texto: "Anotado." }));
    const tempo = pergunta({
      tipo: "operacional",
      campo: "tempo_max_por_fornada_min",
      texto: "Quanto tempo a senhora consegue ficar cozinhando de uma vez, sem se estressar ou cansar?",
      entrada: { tipo: "horas", unidade: "horas", min: 0.5, max: 12, passo: 0.5, casas: 2 },
      opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }],
    });
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={tempo} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Horas" }), { target: { value: "1,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenCalledWith("tempo_max_por_fornada_min", 1.5));
  });
});

describe("o limite sem Não sei", () => {
  it("só o número e Responder", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuErrado("esse número precisa ficar entre 1 e 8 bocas"));
    montar(
      <PerguntaEmLinha
        receita={RECEITA}
        pergunta={pergunta({ tipo: "operacional", campo: "bocas_fogao", entrada: { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 } })}
      />,
    );
    expect(screen.queryByRole("button", { name: "Não sei" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Bocas" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));
    expect(await screen.findByText("esse número precisa ficar entre 1 e 8 bocas")).toHaveAttribute("role", "alert");
  });
});

describe("sim ou não: o gás que sobra", () => {
  it("Sim é verdadeiro, Não é falso e Não sei é nulo", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuCerto({ texto: "Anotado." }));
    const gas = pergunta({
      tipo: "operacional",
      campo: "tem_gas_sobrando",
      texto: "Tem gás sobrando?",
      opcoes: [
        { rotulo: "Sim", resposta: "sim" },
        { rotulo: "Não", resposta: "nao" },
        { rotulo: "Não sei", resposta: "nao_sei" },
      ],
    });
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={gas} />);
    const grupo = screen.getByRole("group", { name: "Tem gás sobrando?" });
    const livre = () => waitFor(() => expect(grupo).not.toHaveAttribute("aria-busy"));
    fireEvent.click(within(grupo).getByRole("button", { name: "Sim" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenCalledWith("tem_gas_sobrando", true));
    await livre();
    fireEvent.click(within(grupo).getByRole("button", { name: "Não" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenLastCalledWith("tem_gas_sobrando", false));
    await livre();
    fireEvent.click(within(grupo).getByRole("button", { name: "Não sei" }));
    await waitFor(() => expect(acao.responderLimiteDaCozinha).toHaveBeenLastCalledWith("tem_gas_sobrando", null));
  });

  it("a recusa aparece perto dos botões", async () => {
    acao.responderLimiteDaCozinha.mockResolvedValue(deuErrado("A resposta aqui é sim ou não."));
    montar(
      <PerguntaEmLinha
        receita={RECEITA}
        pergunta={pergunta({ tipo: "operacional", campo: "tem_gas_sobrando", opcoes: [{ rotulo: "Sim", resposta: "sim" }] })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sim" }));
    expect(await screen.findByText("A resposta aqui é sim ou não.")).toHaveAttribute("role", "alert");
  });
});

describe("o que não é dela nunca vira pergunta", () => {
  it.each(PERGUNTAS_QUE_NAO_SAO_DELA.map((qual) => [qual.assunto, qual] as const))(
    "a pergunta de %s não aparece: nem o texto, nem campo, nem botão",
    (_assunto, qual) => {
      montar(<PerguntaEmLinha receita={RECEITA} pergunta={qual} />);
      expect(document.body.textContent).not.toContain(qual.texto);
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      for (const texto of TEXTOS_QUE_NUNCA_APARECEM) expect(document.body.textContent).not.toMatch(texto);
    },
  );

  it("o tempo no fogo e o rendimento da receita também não: vêm da receita, e ela corrige no detalhe", () => {
    montar(<PerguntaEmLinha receita={RECEITA} pergunta={PERGUNTA_DO_TEMPO} />);
    expect(document.body.textContent).not.toContain(PERGUNTA_DO_TEMPO.texto);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("o que só se responde pela conversa", () => {
  it("abre a conversa com o rascunho e o contexto da receita, sem mandar", () => {
    const { loja } = montar(
      <PerguntaEmLinha
        receita={RECEITA}
        pergunta={pergunta({ tipo: "equipamento", assunto: "modo_preparo", campo: "modo_preparo", texto: "Como a senhora faz?", entrada: { tipo: "texto" } })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Responder no chat" }));
    expect(loja.ler().caixa.texto).toBe("O que falta para eu poder fazer pudim de leite?");
    expect(loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "receita", id: "pudim", rotulo: "Pudim de leite" });
  });
});

describe("acessibilidade", () => {
  it.each([
    ["equipamento", FORNO],
    ["bocas", pergunta({ tipo: "operacional", assunto: "rotina", campo: "bocas_fogao", texto: "Quantas bocas?", entrada: { tipo: "inteiro", unidade: "bocas" } })],
    ["conversa", pergunta({ tipo: "equipamento", assunto: "modo_preparo", campo: "modo_preparo", texto: "Como a senhora faz?" })],
  ])("a pergunta de %s não tem violação", async (_nome, qual) => {
    const { container } = montar(<PerguntaEmLinha receita={RECEITA} pergunta={qual} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
