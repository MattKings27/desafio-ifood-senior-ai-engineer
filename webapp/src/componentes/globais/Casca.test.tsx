/**
 * A casca: cabeçalho (com a engrenagem das Preferências), barra de baixo,
 * folha Mais, provedores, o script do `<head>`, rodapé, a página que falhou e
 * a que não existe.
 *
 * O que importa: o Conversar está à vista nos dois tamanhos de tela e abre a
 * conversa ali mesmo, cada seção é alcançável, a aparência vale antes da
 * primeira pintura, e nenhuma falha mostra texto técnico.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const caminhoAtual = vi.fn(() => "/");
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => caminhoAtual(),
  useRouter: () => ({ push, refresh }),
}));

import { ProvedorDaConversa } from "@/componentes/conversa/ProvedorDaConversa";
import { SCRIPT_DA_APARENCIA } from "@/lib/preferencias";
import { CHAVE_DO_TEMA } from "@/lib/tema";
import { lojaDeTeste } from "@/teste/conversa";

import { BarraInferior } from "./BarraInferior";
import { Cabecalho } from "./Cabecalho";
import { ErroDaPagina } from "./ErroDaPagina";
import { MenuMais } from "./MenuMais";
import { NaoEncontrada } from "./NaoEncontrada";
import { Provedores } from "./Provedores";
import { LinkPular, Rodape } from "./Rodape";
import { ScriptDoTema } from "./ScriptDoTema";

afterEach(() => {
  caminhoAtual.mockReturnValue("/");
  push.mockClear();
  refresh.mockClear();
  vi.restoreAllMocks();
});

const dialogo = () => document.querySelector("dialog") as HTMLDialogElement;

describe("Cabecalho", () => {
  it("tem o selo que volta ao início, o Conversar em destaque, a engrenagem e o Mais", () => {
    render(<Cabecalho />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sabor da Maria/ })).toHaveAttribute("href", "/");
    const conversar = screen.getByRole("link", { name: "Conversar com o agente" });
    expect(conversar).toHaveAttribute("href", "/conversa");
    expect(conversar.className).toContain("bg-marca-fundo");
    const engrenagem = screen.getByRole("button", { name: "Preferências" });
    expect(screen.getByRole("button", { name: "Mais" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Seções" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aparência/ })).toBeNull();
    // Uma engrenagem só, no canto direito, em toda largura.
    expect(screen.getAllByRole("button", { name: "Preferências" })).toHaveLength(1);
    expect(engrenagem.closest(".hidden")).toBeNull();
  });

  it("a pílula abre a conversa ali mesmo, com o contexto da página", () => {
    const t = lojaDeTeste();
    render(
      <ProvedorDaConversa loja={t.loja}>
        <Cabecalho />
      </ProvedorDaConversa>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Conversar com o agente" }));
    expect(t.loja.ler().painelAberto).toBe(true);
    expect(t.loja.ler().caixa.contexto).toMatchObject({ tipo: "tela" });
  });

  it("o Conversar vem antes das seções na ordem do Tab", () => {
    render(<Cabecalho />);
    const links = screen.getAllByRole("link");
    const conversar = links.findIndex((a) => a.textContent === "Conversar com o agente");
    const primeiraSecao = links.findIndex((a) => a.textContent === "Início");
    expect(conversar).toBeGreaterThan(-1);
    expect(conversar).toBeLessThan(primeiraSecao);
  });

  it("não tem violação do axe", async () => {
    const { container } = render(<Cabecalho />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("BarraInferior", () => {
  it("Início · Despensa · Conversar · Receitas · Cardápio, com rótulos sempre visíveis", () => {
    render(<BarraInferior />);
    const barra = screen.getByRole("navigation", { name: "Seções principais" });
    const links = within(barra).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["Início", "Despensa", "Conversar", "Receitas", "Cardápio"]);
    expect(links[2]).toHaveAttribute("href", "/conversa");
  });

  it("marca a seção atual, e o Conversar na página da conversa", () => {
    caminhoAtual.mockReturnValue("/receitas/arroz-com-frango");
    const { rerender } = render(<BarraInferior />);
    expect(screen.getByRole("link", { name: "Receitas" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Conversar" })).not.toHaveAttribute("aria-current");

    caminhoAtual.mockReturnValue("/conversa");
    rerender(<BarraInferior />);
    expect(screen.getByRole("link", { name: "Conversar" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText(/está respondendo/)).not.toBeInTheDocument();
  });

  it("o Conversar abre a folha da conversa, com o contexto da página", () => {
    caminhoAtual.mockReturnValue("/receitas");
    window.history.replaceState(null, "", "/receitas");
    const t = lojaDeTeste();
    render(
      <ProvedorDaConversa loja={t.loja}>
        <BarraInferior />
      </ProvedorDaConversa>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().painelAberto).toBe(true);
    expect(t.loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "tela", id: "receitas", rotulo: "Receitas" });
    window.history.replaceState(null, "", "/");
  });

  it("não tem violação do axe", async () => {
    const { container } = render(<BarraInferior />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MenuMais", () => {
  it("abre a folha com Cozinha, Pôr preço e Histórico; a aparência mora nas Preferências", () => {
    render(<MenuMais />);
    const mais = screen.getByRole("button", { name: "Mais" });
    expect(mais).toHaveAttribute("aria-haspopup", "dialog");
    mais.focus();
    fireEvent.click(mais);
    expect(dialogo().open).toBe(true);
    expect(mais).toHaveAttribute("aria-expanded", "true");
    const secoes = screen.getByRole("navigation", { name: "Mais seções" });
    expect(within(secoes).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "/cozinha",
      "/precificar",
      "/trilha",
    ]);
    expect(screen.queryByRole("group", { name: "Aparência" })).toBeNull();
  });

  it("escolher uma seção fecha a folha e devolve o foco ao Mais", () => {
    render(<MenuMais />);
    const mais = screen.getByRole("button", { name: "Mais" });
    mais.focus();
    fireEvent.click(mais);
    fireEvent.click(screen.getByRole("link", { name: /Cozinha/ }));
    expect(dialogo().open).toBe(false);
    expect(mais).toHaveFocus();
  });

  it("numa seção de dentro do Mais, o botão fica aceso e a seção marcada", () => {
    caminhoAtual.mockReturnValue("/trilha");
    render(<MenuMais />);
    expect(screen.getByRole("button", { name: "Mais" }).className).toContain("bg-tinta/8");
    fireEvent.click(screen.getByRole("button", { name: "Mais" }));
    expect(screen.getByRole("link", { name: /Histórico/ })).toHaveAttribute("aria-current", "page");
  });

  it("mudar de página por outro caminho fecha a folha", () => {
    const { rerender } = render(<MenuMais />);
    fireEvent.click(screen.getByRole("button", { name: "Mais" }));
    expect(dialogo().open).toBe(true);
    caminhoAtual.mockReturnValue("/cozinha");
    rerender(<MenuMais />);
    expect(dialogo().open).toBe(false);
  });

  it("o ✕ da folha fecha", () => {
    render(<MenuMais />);
    fireEvent.click(screen.getByRole("button", { name: "Mais" }));
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(dialogo().open).toBe(false);
  });
});

describe("Provedores, rodapé e o script do tema", () => {
  it("os provedores mostram a tela e aplicam o tema e a aparência guardados antes da pintura", () => {
    localStorage.setItem(CHAVE_DO_TEMA, "escuro");
    localStorage.setItem("texto", "grande");
    render(
      <Provedores>
        <p>a tela</p>
      </Provedores>,
    );
    expect(screen.getByText("a tela")).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-tema", "escuro");
    expect(document.documentElement).toHaveAttribute("data-texto", "grande");
    document.documentElement.removeAttribute("data-texto");
    document.documentElement.removeAttribute("data-movimento");
  });

  it("o link de pular leva ao conteúdo, e o rodapé diz de onde vêm os números", () => {
    render(
      <>
        <LinkPular />
        <Rodape />
      </>,
    );
    expect(screen.getByRole("link", { name: "Pular para o conteúdo" })).toHaveAttribute("href", "#conteudo");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Todo valor nesta tela vem da conta");
  });

  it("o script da aparência sai no HTML, pronto para rodar antes do React", () => {
    const { container } = render(<ScriptDoTema />);
    const script = container.querySelector("script#script-do-tema");
    expect(script?.innerHTML).toBe(SCRIPT_DA_APARENCIA);
  });
});

describe("ErroDaPagina e NaoEncontrada", () => {
  it("a página que falhou diz o que houve do jeito dela e deixa tentar de novo", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const retry = vi.fn();
    const erro = Object.assign(new Error("An error occurred in the Server Components render"), { digest: "123" });
    render(<ErroDaPagina error={erro} retry={retry} titulo="Não consegui abrir a despensa" />);
    expect(screen.getByRole("heading", { level: 1, name: "Não consegui abrir a despensa" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).not.toHaveTextContent(/Server Components|digest|123/);
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Voltar ao início" })).toHaveAttribute("href", "/");
    expect(log).toHaveBeenCalledWith("a página não abriu", "123");
  });

  it("sem digest, o erro inteiro vai para o log; o título padrão aparece", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const erro = new Error("falhou");
    render(<ErroDaPagina error={erro} retry={() => {}} />);
    expect(screen.getByRole("heading", { level: 1, name: "Não consegui abrir esta página" })).toBeInTheDocument();
    expect(log).toHaveBeenCalledWith("a página não abriu", erro);
  });

  it("não encontrei: título de página e o caminho de volta", async () => {
    const { container, rerender } = render(<NaoEncontrada />);
    expect(screen.getByRole("heading", { level: 1, name: "Não encontrei esta página" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao início" })).toHaveAttribute("href", "/");
    expect(await axe(container)).toHaveNoViolations();

    rerender(
      <NaoEncontrada
        titulo="Não encontrei esse ingrediente"
        descricao="Ele pode ter sido tirado da despensa."
        voltar={{ href: "/despensa", rotulo: "Ver a despensa" }}
      />,
    );
    expect(screen.getByRole("link", { name: "Ver a despensa" })).toHaveAttribute("href", "/despensa");
  });
});
