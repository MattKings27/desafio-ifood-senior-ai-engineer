/**
 * O que deu errado, do jeito dela: título pela categoria, nenhum texto técnico,
 * e sempre uma saída ("Tentar de novo", ou a ação da tela).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import type { CategoriaDeErro } from "@/lib/api/base";
import { encontrarJargao, pareceTecnico } from "@/lib/formato";

import { Problema } from "./Problema";
import { DESCRICAO_DO_PROBLEMA, TITULO_DO_PROBLEMA, textoDoProblema } from "./textosDoProblema";

afterEach(() => {
  refresh.mockClear();
});

describe("Problema", () => {
  it.each([
    ["rede", "Não consegui falar com o sistema"],
    ["tempo", "Demorou demais"],
    ["ausente", "Não encontrei"],
    ["dado", "Falta uma informação"],
    ["regra", "Ainda não dá para fazer isso"],
    ["uso", "Não deu para registrar"],
  ] as const)("%s tem o título '%s'", (categoria, titulo) => {
    render(<Problema categoria={categoria} />);
    expect(screen.getByText(titulo)).toBeInTheDocument();
  });

  it("nenhum título ou descrição padrão tem jargão ou cara de programa", () => {
    const textos = [...Object.values(TITULO_DO_PROBLEMA), ...Object.values(DESCRICAO_DO_PROBLEMA)];
    for (const texto of textos) {
      expect(encontrarJargao(texto), texto).toEqual([]);
      expect(pareceTecnico(texto), texto).toBe(false);
    }
  });

  it("rede e tempo nunca mostram a mensagem: é o caminho que falhou", () => {
    render(<Problema categoria="rede" mensagem="Não consegui falar com a API em 127.0.0.1" />);
    expect(screen.getByText(DESCRICAO_DO_PROBLEMA.rede)).toBeInTheDocument();
    expect(screen.queryByText(/127/)).not.toBeInTheDocument();
  });

  it.each([
    "motor respondeu 503",
    "trilha indisponível: [Errno 2] No such file or directory: '.estado/auditoria.jsonl'",
    "chame avaliar_receita antes",
    "o CMV não fechou",
  ])("mensagem técnica ou com jargão (%j) cai para a frase da categoria", (mensagem) => {
    render(<Problema categoria="uso" mensagem={mensagem} />);
    expect(screen.getByText(DESCRICAO_DO_PROBLEMA.uso)).toBeInTheDocument();
  });

  it("mensagem limpa da API aparece", () => {
    render(<Problema categoria="ausente" mensagem="Esse ingrediente foi tirado da despensa." />);
    expect(screen.getByText("Esse ingrediente foi tirado da despensa.")).toBeInTheDocument();
  });

  it("título próprio vence o da categoria, e pode ser cabeçalho", () => {
    render(<Problema categoria="ausente" titulo="Não encontrei essa receita" nivelTitulo={1} />);
    expect(screen.getByRole("heading", { level: 1, name: "Não encontrei essa receita" })).toBeInTheDocument();
  });

  it("'Tentar de novo' chama quem usa", () => {
    const tentar = vi.fn();
    render(<Problema categoria="tempo" aoTentarDeNovo={tentar} />);
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(tentar).toHaveBeenCalledOnce();
  });

  it("recarregar refaz a leitura da página", () => {
    render(<Problema categoria="rede" recarregar />);
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("outra saída da tela, sem tentar de novo", () => {
    render(<Problema categoria="ausente" acao={<a href="/despensa">Voltar para a despensa</a>} />);
    expect(screen.getByRole("link", { name: "Voltar para a despensa" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("sem saída nenhuma, sem barra de botões", () => {
    const { container } = render(<Problema categoria="regra" />);
    expect(container.querySelector(".mt-3.flex")).toBeNull();
  });

  it("o que acabou de dar errado por um clique dela pode interromper (alert)", () => {
    render(<Problema categoria="uso" anunciar="alert" className="mt-4" />);
    expect(screen.getByRole("alert")).toHaveClass("mt-4");
  });
});

describe("textoDoProblema", () => {
  it.each<[CategoriaDeErro, string | undefined, string | undefined, string]>([
    ["dado", "Falta o peso.", "Quanto vem na embalagem?", "Quanto vem na embalagem?"],
    ["dado", "Falta o peso.", undefined, "Falta o peso."],
    ["dado", undefined, "status 500", DESCRICAO_DO_PROBLEMA.dado],
    ["tempo", "demorou 15000 ms", undefined, DESCRICAO_DO_PROBLEMA.tempo],
    ["regra", undefined, undefined, DESCRICAO_DO_PROBLEMA.regra],
  ])("%s, %j, %j → %j", (categoria, mensagem, pergunta, esperado) => {
    expect(textoDoProblema(categoria, mensagem, pergunta)).toBe(esperado);
  });
});
