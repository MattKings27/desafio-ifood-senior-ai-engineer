/**
 * O checklist de produção da receita, com o do contrato: os cinco grupos em
 * lista, o estado e a origem de cada item em palavras, a resposta ali mesmo do
 * que falta saber, o "Mudar" do que foi pré-determinado, o "Não tenho" do
 * suposto e o "Confirmar a cozinha" que grava tudo de uma vez. E a nota
 * "Confirme a cozinha" no card da grade.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
}));
vi.mock("@/lib/acoes/cozinha", () => ({ confirmarSupostos: vi.fn(), definirPosse: vi.fn(), definirRestricao: vi.fn() }));

import * as cozinha from "@/lib/acoes/cozinha";
import * as receitas from "@/lib/acoes/receitas";
import type { ConfirmacaoDaCozinha } from "@/lib/api/perfil";
import type { ChecklistDeProducao, DetalheDaReceita, ItemDaGrade } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { ARROZ, deuCerto, deuErrado, montar } from "@/teste/receitas";

import { CartaoDeReceita } from "./CartaoDeReceita";
import { ChecklistDeProducaoDaReceita } from "./ChecklistDeProducao";

const RECEITA = contrato<DetalheDaReceita>("receita.json");
const CHECKLIST = RECEITA.checklist;
const CONFIRMACAO = contrato<{ resposta: ConfirmacaoDaCozinha }>("perfil-supostos.json").resposta;
const NOS_DADOS = { slug: RECEITA.slug, nome: RECEITA.nome };
const acoesDaCozinha = vi.mocked(cozinha);
const acoesDaReceita = vi.mocked(receitas);

afterEach(() => {
  vi.clearAllMocks();
});

function lista(checklist: ChecklistDeProducao = CHECKLIST) {
  return montar(
    <ChecklistDeProducaoDaReceita receita={NOS_DADOS} checklist={checklist} />,
  );
}

/** O item da lista pelo nome, como ela lê. */
const item = (nome: string) =>
  screen.getAllByRole("listitem").find((li) => li.querySelector("p")?.textContent === nome) as HTMLElement;

describe("o checklist de produção", () => {
  it("os cinco grupos, na ordem, cada item com o estado e a origem em palavras", async () => {
    const { container } = lista();
    const titulos = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titulos).toEqual(["Equipamentos", "Técnicas", "Rotina", "Ingredientes", "Pré-determinados"]);

    const fogao = item("Fogão");
    expect(within(fogao).getByText("Suposto: confirme")).toBeInTheDocument();
    expect(within(fogao).getByText("Toda cozinha tem, e a senhora ainda não confirmou.")).toBeInTheDocument();
    // No suposto, o estado já diz de onde veio: a origem não se repete.
    expect(within(fogao).queryByText("Suposto")).not.toBeInTheDocument();

    const panela = item("Panela de pressão");
    expect(within(panela).getByText("Confirmado pela senhora")).toBeInTheDocument();
    expect(within(panela).getByText("A senhora disse")).toBeInTheDocument();

    const gas = item("Gás");
    expect(within(gas).getByText("Não precisa")).toBeInTheDocument();
    expect(within(gas).getByText("Receita")).toBeInTheDocument();

    // O pré-determinado aparece como estimado, com a fonte.
    const cebola = item("Cebola");
    expect(within(cebola).getByText("Estimado")).toBeInTheDocument();
    expect(within(cebola).getByText("Referência de medidas do IBGE")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Confirmar a cozinha: a pergunta, uma só, o que ela confirma, e um toque grava tudo pela receita", async () => {
    acoesDaCozinha.confirmarSupostos.mockResolvedValue(deuCerto(CONFIRMACAO));
    lista();
    const grupo = screen.getByRole("group", { name: CHECKLIST.confirmar_a_cozinha?.pergunta });
    const itens = within(within(grupo).getByRole("list", { name: "O que a senhora confirma" })).getAllByRole("listitem");
    expect(itens.map((li) => li.textContent)).toEqual(["Fogão", "Refogar"]);
    fireEvent.click(within(grupo).getByRole("button", { name: "Confirmar a cozinha" }));
    await waitFor(() => expect(acoesDaCozinha.confirmarSupostos).toHaveBeenCalledWith({ receita: RECEITA.slug }));
    expect(await screen.findByText(CONFIRMACAO.texto)).toBeInTheDocument();
  });

  it("a recusa da confirmação vira aviso, com a frase da API", async () => {
    acoesDaCozinha.confirmarSupostos.mockResolvedValue(deuErrado("Não encontrei essa receita."));
    lista();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar a cozinha" }));
    expect(await screen.findByText("Não encontrei essa receita.")).toBeInTheDocument();
  });

  it("sem nada suposto, não há o que confirmar; o grupo vazio diz por quê", () => {
    lista({
      ...CHECKLIST,
      confirmar_a_cozinha: null,
      grupos: CHECKLIST.grupos.map((grupo) => (grupo.id === "tecnicas" ? { ...grupo, itens: [] } : grupo)),
    });
    expect(screen.queryByRole("button", { name: "Confirmar a cozinha" })).not.toBeInTheDocument();
    expect(screen.getByText("Esta receita não pede técnica especial.")).toBeInTheDocument();
  });

  it("o Não tenho do suposto grava só ele, pelo perfil da cozinha", async () => {
    acoesDaReceita.responderSobreACozinha.mockResolvedValue(deuCerto({ texto: "Sem fogão, Carne moída deixa de dar." }));
    lista();
    fireEvent.click(within(item("Refogar")).getByRole("button", { name: "Não faço: Refogar" }));
    await waitFor(() => expect(acoesDaReceita.responderSobreACozinha).toHaveBeenCalledWith("tecnicas", "refogar", "nao_tem"));
    fireEvent.click(within(item("Fogão")).getByRole("button", { name: "Não tenho: Fogão" }));
    await waitFor(() => expect(acoesDaReceita.responderSobreACozinha).toHaveBeenCalledWith("equipamentos", "fogao", "nao_tem"));
    expect((await screen.findAllByText("Sem fogão, Carne moída deixa de dar.")).length).toBeGreaterThan(0);
  });

  it("a linha que a leitura não entendeu fica em falta saber, sem a pergunta de quanto vai", () => {
    const { container } = lista();
    const linha = item("Temperos de sua preferência");
    expect(within(linha).getByText("Falta saber")).toBeInTheDocument();
    expect(within(linha).queryByRole("textbox")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Não entendi quanto vai|quanto pesa|Quanto custa/i);
  });

  it("o pré-determinado se corrige pelo corrigir discreto, sem pergunta: as porções e o peso", async () => {
    acoesDaReceita.responderSobreAReceita.mockResolvedValue(
      deuCerto({ slug: RECEITA.slug, nome: RECEITA.nome, cozinha: RECEITA.veredito_da_cozinha }),
    );
    lista();
    const porcoes = item("Porções");
    expect(within(porcoes).getByText("Rende 4 porções.")).toBeInTheDocument();
    fireEvent.click(within(porcoes).getByRole("button", { name: "corrigir o valor de porções" }));
    fireEvent.change(within(porcoes).getByRole("textbox", { name: "Porções" }), { target: { value: "6" } });
    fireEvent.click(within(porcoes).getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(acoesDaReceita.responderSobreAReceita).toHaveBeenCalledWith(RECEITA.slug, "rendimento_porcoes", "6"));
    const cebola = item("Cebola");
    fireEvent.click(within(cebola).getByRole("button", { name: "corrigir o valor de cebola" }));
    expect(within(cebola).getByRole("textbox", { name: "Peso" })).toBeInTheDocument();
    expect(within(cebola).queryByText(/quanto pesa/i)).not.toBeInTheDocument();
  });
});

describe("a nota da cozinha no card da grade", () => {
  it("Confirme a cozinha quando a API manda; sem nota, nada", () => {
    const comNota: ItemDaGrade = { ...ARROZ, nota_da_cozinha: "Confirme a cozinha" };
    const { rerender } = render(<CartaoDeReceita item={comNota} />);
    expect(screen.getByText("Confirme a cozinha")).toBeInTheDocument();
    rerender(<CartaoDeReceita item={{ ...ARROZ, nota_da_cozinha: null }} />);
    expect(screen.queryByText("Confirme a cozinha")).not.toBeInTheDocument();
  });
});
