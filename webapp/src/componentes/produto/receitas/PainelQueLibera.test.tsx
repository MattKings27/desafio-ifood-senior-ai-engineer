/**
 * "Responda e eu libero mais receitas": as perguntas que seguram as receitas,
 * juntas pelo que perguntam, com a contagem que a API escreveu e a resposta
 * ali mesmo, pelo mesmo caminho dos cards de "Falta uma resposta sua".
 */

import { screen, within } from "@testing-library/react";
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
import type { PerguntaDaReceita, PerguntaQueLibera } from "@/lib/api/receitas";
import { montar } from "@/teste/receitas";

import { PainelQueLibera } from "./PainelQueLibera";

const acao = vi.mocked(acoes);

afterEach(() => {
  vi.clearAllMocks();
});

function pergunta(extras: Partial<PerguntaDaReceita>): PerguntaDaReceita {
  return {
    tipo: "ingrediente",
    assunto: "ingrediente",
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

const GRELHAR: PerguntaQueLibera = {
  pergunta: pergunta({
    tipo: "tecnica",
    assunto: "tecnica",
    campo: "grelhar",
    texto: "A senhora tem prática com grelhar?",
    opcoes: [
      { rotulo: "Faço", resposta: "sim" },
      { rotulo: "Não faço", resposta: "nao" },
      { rotulo: "Não sei", resposta: "nao_sei" },
    ],
  }),
  receitas: 3,
  liberadas: 3,
  sem_compra: 2,
  sem_compra_texto: "2 delas usam só o que a senhora tem",
  nomes: ["Alcatra com molho de queijo", "Bola de carne moída", "Picadinho de alcatra"],
  slugs: ["alcatra", "bola", "picadinho"],
  rota: "/receitas?aba=falta_resposta",
  texto: "libera 3 receitas",
};

const CENOURA: PerguntaQueLibera = {
  pergunta: pergunta({
    assunto: "preco_de_compra",
    campo: "cenoura",
    texto: "Quanto custa cenoura aí na sua região, e por qual quantidade (o quilo, a lata, o pacote)?",
    motivo: "sem o preço não dá para saber se cabe no orçamento",
    compras: [{ ingrediente: "cenoura", quantidade_texto: "90 g" }],
    entrada: { tipo: "texto" },
  }),
  receitas: 2,
  liberadas: 0,
  sem_compra: 0,
  sem_compra_texto: null,
  nomes: ["Bola de carne moída", "Picadinho de alcatra"],
  slugs: ["bola", "picadinho"],
  rota: "/receitas?aba=falta_resposta",
  texto: "ajuda a liberar 2 receitas",
};

const ALCATRA: PerguntaQueLibera = {
  pergunta: pergunta({
    assunto: "mesmo_ingrediente",
    campo: "6 bifes de alcatra",
    texto: "A receita pede alcatra. É o seu miolo de alcatra?",
    opcoes: [
      { rotulo: "É, sim", resposta: "sim" },
      { rotulo: "Não é", resposta: "nao" },
    ],
  }),
  receitas: 1,
  liberadas: 1,
  sem_compra: 1,
  sem_compra_texto: "usa só o que a senhora tem",
  nomes: ["Alcatra com molho de queijo"],
  slugs: ["alcatra"],
  rota: "/receitas/alcatra",
  texto: "libera 1 receita",
};

const TODAS = new Set(["alcatra", "bola", "picadinho"]);

describe("o painel das perguntas que liberam receitas", () => {
  it("sem pergunta, não aparece", () => {
    montar(<PainelQueLibera perguntas={[]} curtidas={TODAS} />);
    expect(screen.queryByRole("region", { name: "Responda e eu libero mais receitas" })).not.toBeInTheDocument();
  });

  it("só a pergunta da cozinha, com a contagem, as receitas e a resposta ali mesmo; preço e item parecido nunca", async () => {
    const { container } = montar(<PainelQueLibera perguntas={[GRELHAR, CENOURA, ALCATRA]} curtidas={TODAS} />);
    const painel = screen.getByRole("region", { name: "Responda e eu libero mais receitas" });
    const perguntas = within(painel).getAllByRole("listitem");
    expect(perguntas).toHaveLength(1);
    const [grelhar] = perguntas as [HTMLElement];
    expect(within(grelhar).getByText("Libera 3 receitas")).toBeInTheDocument();
    expect(within(grelhar).getByText("2 delas usam só o que a senhora tem")).toBeInTheDocument();
    expect(within(grelhar).getByText("Alcatra com molho de queijo, Bola de carne moída e mais 1")).toBeInTheDocument();
    expect(within(grelhar).getByRole("group", { name: GRELHAR.pergunta.texto })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Quanto custa|É o seu/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("o gosto vem antes: sem nenhuma receita que ela gosta de fazer, a pergunta da cozinha não entra", () => {
    montar(<PainelQueLibera perguntas={[GRELHAR]} curtidas={new Set(["outra"])} />);
    expect(screen.queryByRole("region", { name: "Responda e eu libero mais receitas" })).not.toBeInTheDocument();
  });

  it("a pergunta de uma receita só diz o motivo; a de muitas, não", () => {
    const deUma = { ...GRELHAR, receitas: 1, liberadas: 0, sem_compra_texto: null, nomes: ["Picadinho"], slugs: ["picadinho"], texto: "ajuda a liberar 1 receita", pergunta: { ...GRELHAR.pergunta, motivo: "o picadinho vai à grelha" } };
    montar(<PainelQueLibera perguntas={[deUma]} curtidas={TODAS} />);
    expect(screen.getByText("Ajuda a liberar 1 receita")).toBeInTheDocument();
    expect(screen.getByText("O picadinho vai à grelha.")).toBeInTheDocument();
    expect(acao.responderSobreACozinha).not.toHaveBeenCalled();
  });
});
