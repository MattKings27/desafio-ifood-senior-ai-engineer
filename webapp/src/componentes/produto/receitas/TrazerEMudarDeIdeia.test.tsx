/**
 * Duas saídas da grade: "Trazer uma receita" pelo endereço (os estados do
 * campo: vazio, endereço que não é de página, lendo, trouxe, já estava aqui,
 * a página sem receita) e "Não gosto de fazer", que não aparece sem nenhuma
 * (a seção inteira, com o "Mudei de ideia", está em `GostoNaGrade.test.tsx`).
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({ avaliarReceita: vi.fn(), trazerReceita: vi.fn() }));

import * as acoes from "@/lib/acoes/receitas";
import type { ReceitaTrazidaNaTela } from "@/lib/acoes/receitas";
import { MENSAGENS } from "@/lib/api/base";
import { irPara } from "@/teste/navegacao";
import { ARROZ, adiado, deuCerto, deuErrado, lista, montar } from "@/teste/receitas";

import { TelaDasReceitas } from "./TelaDasReceitas";
import { TrazerReceita } from "./TrazerReceita";

const acao = vi.mocked(acoes);

beforeEach(() => {
  irPara("/receitas");
});

afterEach(() => {
  vi.resetAllMocks();
  vi.restoreAllMocks();
});

const TRAZIDA: ReceitaTrazidaNaTela = {
  slug: "3f16fc90b8a2c436",
  nome: "Frango com milho verde",
  rota: "/receitas/3f16fc90b8a2c436",
  imagem: null,
  site: "TudoGostoso",
  nova: true,
  cozinha: { codigo: "comprando", rotulo: "Dá, comprando o que falta", motivo: "Falta comprar milho verde." },
  gosta: null,
};

function folhaDeTrazer() {
  const aoFechar = vi.fn();
  const resultado = montar(<TrazerReceita aberta aoFechar={aoFechar} />);
  const folha = screen.getByRole("dialog", { name: "Trazer uma receita" });
  const campo = within(folha).getByRole("textbox", { name: "Endereço da receita" });
  // Enquanto lê a página, o botão se chama "Lendo a página…".
  const botao = () => within(folha).getByRole("button", { name: /^(Trazer|Lendo a página…)$/ });
  const trazer = () => fireEvent.click(botao());
  /** Espera a leitura anterior terminar de vez (a transição), para o próximo toque valer. */
  const livre = () => waitFor(() => expect(botao()).not.toHaveAttribute("aria-busy"));
  return { ...resultado, aoFechar, folha, campo, trazer, livre };
}

describe("trazer uma receita pelo endereço", () => {
  it("abre pela grade, com o foco no campo", () => {
    montar(<TelaDasReceitas inicial={lista()} chaveInicial="?aba=pode_fazer" />);
    fireEvent.click(screen.getByRole("button", { name: "Trazer uma receita" }));
    const folha = screen.getByRole("dialog", { name: "Trazer uma receita" });
    expect(folha).toHaveAttribute("open");
    expect(within(folha).getByRole("textbox", { name: "Endereço da receita" })).toHaveFocus();
  });

  it("vazio e endereço que não é de página são avisados antes de ir ao servidor", () => {
    const { campo, trazer } = folhaDeTrazer();
    trazer();
    expect(screen.getByText("Cole o endereço da página da receita.")).toBeInTheDocument();
    fireEvent.change(campo, { target: { value: "bolo de fubá" } });
    expect(screen.queryByText("Cole o endereço da página da receita.")).not.toBeInTheDocument();
    trazer();
    expect(screen.getByText(/Esse endereço não parece de uma página/)).toBeInTheDocument();
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(acao.trazerReceita).not.toHaveBeenCalled();
  });

  it("lendo a página, depois a receita nova, onde ela entrou, e trazer outra", async () => {
    const espera = adiado<Awaited<ReturnType<typeof acao.trazerReceita>>>();
    acao.trazerReceita.mockReturnValue(espera.promessa);
    const { campo, trazer, folha, container } = folhaDeTrazer();
    fireEvent.change(campo, { target: { value: " https://www.tudogostoso.com.br/receita/3-frango " } });
    trazer();
    await waitFor(() => expect(acao.trazerReceita).toHaveBeenCalledWith("https://www.tudogostoso.com.br/receita/3-frango"));
    expect(screen.getByText("Lendo a página. Pode levar alguns segundos.")).toBeInTheDocument();
    trazer();
    expect(acao.trazerReceita).toHaveBeenCalledTimes(1);
    await act(async () => espera.resolver(deuCerto(TRAZIDA)));
    expect(within(folha).getByText("Trouxe Frango com milho verde.")).toBeInTheDocument();
    expect(within(folha).getByText("Dá, comprando o que falta")).toBeInTheDocument();
    expect(within(folha).getByText("Ela está em Dá para fazer.")).toBeInTheDocument();
    expect(within(folha).getByRole("link", { name: "Ver a receita" })).toHaveAttribute("href", TRAZIDA.rota);
    expect(await axe(container)).toHaveNoViolations();
    fireEvent.click(within(folha).getByRole("button", { name: "Trazer outra" }));
    expect(within(folha).getByRole("textbox", { name: "Endereço da receita" })).toHaveValue("");
  });

  it("a que já estava aqui, e a que a cozinha não permite", async () => {
    const { campo, trazer, folha, livre } = folhaDeTrazer();
    acao.trazerReceita.mockResolvedValueOnce(deuCerto({ ...TRAZIDA, nova: false }));
    fireEvent.change(campo, { target: { value: "https://www.tudogostoso.com.br/receita/3-frango" } });
    trazer();
    expect(await within(folha).findByText("Frango com milho verde já estava aqui.")).toBeInTheDocument();
    fireEvent.click(within(folha).getByRole("button", { name: "Trazer outra" }));
    await livre();
    acao.trazerReceita.mockResolvedValueOnce(
      deuCerto({ ...TRAZIDA, site: null, cozinha: { codigo: "nao_da", rotulo: "Não dá", motivo: "Vai ao forno, e a senhora não tem." } }),
    );
    fireEvent.change(within(folha).getByRole("textbox", { name: "Endereço da receita" }), {
      target: { value: "https://www.panelinha.com.br/receita/assado" },
    });
    trazer();
    expect(await within(folha).findByText(/Ela não entra na lista, porque a cozinha da senhora não dá conta/)).toBeInTheDocument();
  });

  it("a página sem receita é recusada com a pergunta do servidor; sem pergunta, a mensagem limpa", async () => {
    const { campo, trazer, folha, livre } = folhaDeTrazer();
    acao.trazerReceita.mockResolvedValueOnce(
      deuErrado("a página abriu, mas não traz a receita em formato estruturado", {
        categoria: "dado",
        pergunta: "Esse site não publica a receita de um jeito que eu leia. Tenta outro?",
      }),
    );
    fireEvent.change(campo, { target: { value: "https://exemplo.com.br/x" } });
    trazer();
    expect(await within(folha).findByText("Esse site não publica a receita de um jeito que eu leia. Tenta outro?")).toBeInTheDocument();
    await livre();
    acao.trazerReceita.mockResolvedValueOnce(deuErrado("não busco esse endereço: é de uma rede interna"));
    trazer();
    expect(await within(folha).findByText("Não busco esse endereço: é de uma rede interna")).toBeInTheDocument();
    await livre();
    acao.trazerReceita.mockResolvedValueOnce(deuErrado("Traceback: TypeError undefined"));
    trazer();
    expect(await within(folha).findByText(MENSAGENS.semMotivo)).toBeInTheDocument();
  });

  it("fechar no meio da digitação guarda o que ela escreveu; Enter enquanto lê não manda de novo", async () => {
    const espera = adiado<Awaited<ReturnType<typeof acao.trazerReceita>>>();
    acao.trazerReceita.mockReturnValue(espera.promessa);
    const { campo, trazer, folha, aoFechar } = folhaDeTrazer();
    fireEvent.change(campo, { target: { value: "https://www.tudogostoso.com.br/receita/3-frango" } });
    trazer();
    await waitFor(() => expect(acao.trazerReceita).toHaveBeenCalledTimes(1));
    fireEvent.submit(campo.closest("form") as HTMLFormElement);
    expect(acao.trazerReceita).toHaveBeenCalledTimes(1);
    await act(async () => espera.resolver(deuErrado("Não deu.")));
    fireEvent.click(within(folha).getByRole("button", { name: "Fechar" }));
    expect(aoFechar).toHaveBeenCalled();
    expect(within(folha).getByRole("textbox", { name: "Endereço da receita", hidden: true })).toHaveValue(
      "https://www.tudogostoso.com.br/receita/3-frango",
    );
  });

  it("fechar depois de trazer recomeça a folha para a próxima vez", async () => {
    acao.trazerReceita.mockResolvedValue(deuCerto(TRAZIDA));
    const { campo, trazer, folha, aoFechar } = folhaDeTrazer();
    fireEvent.change(campo, { target: { value: "https://www.tudogostoso.com.br/receita/3-frango" } });
    trazer();
    await within(folha).findByText("Trouxe Frango com milho verde.");
    fireEvent.click(within(folha).getByRole("button", { name: "Fechar" }));
    expect(aoFechar).toHaveBeenCalled();
    // Fechada, a folha sai da árvore de acessibilidade; o campo já está vazio para a próxima vez.
    expect(within(folha).getByRole("textbox", { name: "Endereço da receita", hidden: true })).toHaveValue("");
  });
});

describe("não gosto de fazer", () => {
  it("sem nenhuma que ela não quer, a seção fechada não aparece", () => {
    montar(<TelaDasReceitas inicial={lista()} chaveInicial="?aba=pode_fazer" />);
    expect(screen.queryByRole("button", { name: /Não gosto de fazer/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByRole("link", { name: ARROZ.nome })).toBeInTheDocument();
  });
});
