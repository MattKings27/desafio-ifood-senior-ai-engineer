/**
 * O que abre por cima da tela: diálogo, confirmação, folha e aviso.
 *
 * O `<dialog>` do jsdom é o dublê de `src/teste/preparo.ts` (abre, fecha e
 * dispara `close`); o Esc de verdade é do navegador e fica para o Playwright.
 * O que se testa aqui: abrir e fechar pelo estado, o foco voltando a quem
 * abriu, e "fechar" não ser confundido com "cancelar".
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Botao } from "./Botao";
import { Dialogo, DialogoDeConfirmacao } from "./Dialogo";
import { Folha } from "./Folha";
import { ProvedorDeToasts, useToast } from "./Toast";

const dialogo = (container: HTMLElement | Document = document) =>
  container.querySelector("dialog") as HTMLDialogElement;

function ComDialogo({
  aoFechar,
  alerta,
  fecharAoClicarFora,
}: {
  aoFechar?: () => void;
  alerta?: boolean;
  fecharAoClicarFora?: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setAberto(true)}>
        Editar
      </button>
      <Dialogo
        aberto={aberto}
        alerta={alerta}
        fecharAoClicarFora={fecharAoClicarFora}
        aoFechar={() => {
          setAberto(false);
          aoFechar?.();
        }}
        titulo="Editar ingrediente"
        descricao="Mude o que precisar."
        acoes={
          <button type="button" onClick={() => setAberto(false)}>
            Pronto
          </button>
        }
      >
        <input aria-label="Nome" />
      </Dialogo>
    </>
  );
}

function abrirPor(nome: string) {
  const botao = screen.getByRole("button", { name: nome });
  botao.focus();
  fireEvent.click(botao);
  return botao;
}

describe("Dialogo", () => {
  it("abre modal pelo estado, com título e descrição ligados", () => {
    render(<ComDialogo />);
    expect(dialogo().open).toBe(false);
    abrirPor("Editar");
    const aberto = dialogo();
    expect(aberto.open).toBe(true);
    expect(aberto).toHaveAttribute("data-modal");
    expect(aberto).toHaveAccessibleName("Editar ingrediente");
    expect(aberto).toHaveAccessibleDescription("Mude o que precisar.");
  });

  it("o ✕ fecha, avisa, e o foco volta a quem abriu", () => {
    const aoFechar = vi.fn();
    render(<ComDialogo aoFechar={aoFechar} />);
    const origem = abrirPor("Editar");
    screen.getByLabelText("Nome").focus();
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(dialogo().open).toBe(false);
    expect(aoFechar).toHaveBeenCalledOnce();
    expect(origem).toHaveFocus();
  });

  it("fechar pela própria tela (o estado) não é cancelar: aoFechar não é chamado", () => {
    const aoFechar = vi.fn();
    render(<ComDialogo aoFechar={aoFechar} />);
    const origem = abrirPor("Editar");
    fireEvent.click(screen.getByRole("button", { name: "Pronto" }));
    expect(dialogo().open).toBe(false);
    expect(aoFechar).not.toHaveBeenCalled();
    expect(origem).toHaveFocus();
  });

  it("o fechamento nativo (o Esc do navegador) avisa quem usa", () => {
    const aoFechar = vi.fn();
    render(<ComDialogo aoFechar={aoFechar} />);
    abrirPor("Editar");
    act(() => dialogo().close());
    expect(aoFechar).toHaveBeenCalledOnce();
  });

  it("clicar no fundo fecha; clicar dentro, não", () => {
    const aoFechar = vi.fn();
    render(<ComDialogo aoFechar={aoFechar} />);
    abrirPor("Editar");
    fireEvent.click(screen.getByLabelText("Nome"));
    expect(dialogo().open).toBe(true);
    fireEvent.click(dialogo());
    expect(dialogo().open).toBe(false);
    expect(aoFechar).toHaveBeenCalledOnce();
  });

  it("alerta: é alertdialog, sem ✕ e sem fechar clicando fora", () => {
    render(<ComDialogo alerta />);
    abrirPor("Editar");
    expect(dialogo()).toHaveAttribute("role", "alertdialog");
    expect(screen.queryByRole("button", { name: "Fechar" })).not.toBeInTheDocument();
    fireEvent.click(dialogo());
    expect(dialogo().open).toBe(true);
  });

  it("clicar fora pode ser desligado num diálogo comum", () => {
    render(<ComDialogo fecharAoClicarFora={false} />);
    abrirPor("Editar");
    fireEvent.click(dialogo());
    expect(dialogo().open).toBe(true);
  });

  it("sem conteúdo nem ações, e com o foco inicial escolhido", () => {
    render(
      <Dialogo aberto aoFechar={() => {}} titulo="Aviso" tamanho="lg" focoInicial="[data-primeiro]">
        <button type="button" data-primeiro="">
          Entendi
        </button>
      </Dialogo>,
    );
    expect(screen.getByRole("button", { name: "Entendi" })).toHaveFocus();
    expect(dialogo()).not.toHaveAttribute("aria-describedby");
  });

  it("sair da tela aberto ainda devolve o foco", () => {
    function Alternar() {
      const [mostrar, setMostrar] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setMostrar(false)}>
            Sair
          </button>
          {mostrar ? (
            <Dialogo aberto aoFechar={() => {}} titulo="Aberto">
              <p>corpo</p>
            </Dialogo>
          ) : null}
        </>
      );
    }
    const origem = document.createElement("button");
    document.body.appendChild(origem);
    origem.focus();
    render(<Alternar />);
    origem.blur();
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(origem).toHaveFocus();
    origem.remove();
  });
});

function Confirmar({ aoConfirmar, aoCancelar }: { aoConfirmar: () => void; aoCancelar: () => void }) {
  return (
    <DialogoDeConfirmacao
      aberto
      titulo="Tirar da despensa?"
      descricao="O creme de leite sai da lista, e os R$ 9,00 voltam aos complementos."
      rotuloConfirmar="Tirar"
      perigoso
      aoConfirmar={aoConfirmar}
      aoCancelar={aoCancelar}
    />
  );
}

describe("DialogoDeConfirmacao", () => {
  it("é alertdialog, começa no Cancelar e o perigo tem a cor dele", () => {
    const aoConfirmar = vi.fn();
    const aoCancelar = vi.fn();
    render(<Confirmar aoConfirmar={aoConfirmar} aoCancelar={aoCancelar} />);
    expect(dialogo()).toHaveAttribute("role", "alertdialog");
    expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
    const tirar = screen.getByRole("button", { name: "Tirar" });
    expect(tirar.className).toContain("bg-perigo");
    fireEvent.click(tirar);
    expect(aoConfirmar).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(aoCancelar).toHaveBeenCalledOnce();
  });

  it("carregando segura o botão de confirmar; sem perigo, é o primário", () => {
    const aoConfirmar = vi.fn();
    render(
      <DialogoDeConfirmacao
        aberto
        titulo="Aceitar o preço?"
        descricao="R$ 18,00 a porção."
        rotuloConfirmar="Vou cobrar este"
        rotuloCancelar="Voltar"
        carregando
        aoConfirmar={aoConfirmar}
        aoCancelar={() => {}}
      />,
    );
    const confirmar = screen.getByRole("button", { name: "Vou cobrar este" });
    expect(confirmar.className).toContain("bg-marca-fundo");
    expect(confirmar).toHaveAttribute("aria-busy", "true");
    fireEvent.click(confirmar);
    expect(aoConfirmar).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Voltar" })).toBeInTheDocument();
  });
});

function ComFolha({ lado, rodape }: { lado?: "baixo" | "direita" | "auto"; rodape?: ReactNode }) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setAberto(true)}>
        Filtros
      </button>
      <Folha
        aberto={aberto}
        aoFechar={() => setAberto(false)}
        titulo="Filtrar receitas"
        descricao="Escolha o que a senhora quer ver."
        lado={lado}
        rodape={rodape}
      >
        <p>os filtros</p>
      </Folha>
    </>
  );
}

describe("Folha", () => {
  it("abre, fecha pelo ✕ e devolve o foco", () => {
    render(<ComFolha rodape={<Botao>Ver 12 receitas</Botao>} />);
    const origem = abrirPor("Filtros");
    expect(dialogo().open).toBe(true);
    expect(dialogo()).toHaveAccessibleName("Filtrar receitas");
    expect(dialogo()).toHaveAccessibleDescription("Escolha o que a senhora quer ver.");
    expect(screen.getByRole("button", { name: "Ver 12 receitas" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(dialogo().open).toBe(false);
    expect(origem).toHaveFocus();
  });

  it.each([
    ["baixo", "rounded-t-xl", true],
    ["direita", "rounded-l-xl", false],
    ["auto", "lg:rounded-l-xl", true],
  ] as const)("lado %s", (lado, classe, temAlca) => {
    const { container } = render(<ComFolha lado={lado} />);
    expect(dialogo(container).className).toContain(classe);
    expect(Boolean(dialogo(container).querySelector(".w-10.rounded-full"))).toBe(temAlca);
  });

  it("clicar no fundo fecha", () => {
    render(<ComFolha />);
    abrirPor("Filtros");
    fireEvent.click(dialogo());
    expect(dialogo().open).toBe(false);
  });
});

function Avisos() {
  const toast = useToast();
  const [ultimo, setUltimo] = useState(0);
  return (
    <>
      <button type="button" onClick={() => setUltimo(toast.mostrar({ texto: "Anotei o creme de leite.", tom: "sucesso", duracaoMs: 60_000 }))}>
        Sucesso
      </button>
      <button type="button" onClick={() => toast.mostrar({ texto: "Não salvou.", tom: "erro", duracaoMs: 60_000 })}>
        Erro
      </button>
      <button type="button" onClick={() => toast.mostrar({ texto: "Anotado.", duracaoMs: 40 })}>
        Aviso rápido
      </button>
      <button type="button" onClick={() => toast.fechar(ultimo)}>
        Fechar o último
      </button>
    </>
  );
}

function ComAcao({ desfazer }: { desfazer: () => void }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() =>
        toast.mostrar({
          texto: "Tirei o arroz com frango do cardápio.",
          tom: "sucesso",
          acao: { rotulo: "Desfazer", aoClicar: desfazer },
        })
      }
    >
      Tirar
    </button>
  );
}

describe("Toast", () => {
  it("as regiões vivas existem desde o começo, vazias", () => {
    render(
      <ProvedorDeToasts>
        <p>tela</p>
      </ProvedorDeToasts>,
    );
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(screen.getByRole("alert")).toBeEmptyDOMElement();
  });

  it("sucesso vai para a região educada; erro, para a de alerta", () => {
    render(
      <ProvedorDeToasts>
        <Avisos />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sucesso" }));
    fireEvent.click(screen.getByRole("button", { name: "Erro" }));
    expect(screen.getByRole("status")).toHaveTextContent("Anotei o creme de leite.");
    expect(screen.getByRole("alert")).toHaveTextContent("Não salvou.");
  });

  it("o ✕ e o fechar por id tiram o aviso", async () => {
    render(
      <ProvedorDeToasts>
        <Avisos />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Erro" }));
    fireEvent.click(screen.getByRole("button", { name: "Fechar o aviso" }));
    await waitFor(() => expect(screen.queryByText("Não salvou.")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Sucesso" }));
    fireEvent.click(screen.getByRole("button", { name: "Fechar o último" }));
    await waitFor(() => expect(screen.queryByText("Anotei o creme de leite.")).not.toBeInTheDocument());
  });

  it("some sozinho depois do tempo, mas não enquanto o ponteiro está em cima", async () => {
    render(
      <ProvedorDeToasts>
        <Avisos />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Aviso rápido" }));
    const caixa = screen.getByText("Anotado.").parentElement as HTMLElement;
    fireEvent.mouseEnter(caixa);
    await new Promise((r) => setTimeout(r, 120));
    expect(screen.getByText("Anotado.")).toBeInTheDocument();
    fireEvent.mouseLeave(caixa);
    await waitFor(() => expect(screen.queryByText("Anotado.")).not.toBeInTheDocument());
  });

  it("o foco também segura o aviso", async () => {
    render(
      <ProvedorDeToasts>
        <Avisos />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Aviso rápido" }));
    const caixa = screen.getByText("Anotado.").parentElement as HTMLElement;
    fireEvent.focus(caixa);
    await new Promise((r) => setTimeout(r, 120));
    expect(screen.getByText("Anotado.")).toBeInTheDocument();
    fireEvent.blur(caixa);
    await waitFor(() => expect(screen.queryByText("Anotado.")).not.toBeInTheDocument());
  });

  it("a ação do aviso roda e fecha o aviso", async () => {
    const desfazer = vi.fn();
    render(
      <ProvedorDeToasts>
        <ComAcao desfazer={desfazer} />
      </ProvedorDeToasts>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Tirar" }));
    fireEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(desfazer).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.queryByText(/Tirei o arroz/)).not.toBeInTheDocument());
  });

  it("cabem três de uma vez: o mais antigo sai", async () => {
    render(
      <ProvedorDeToasts>
        <Avisos />
      </ProvedorDeToasts>,
    );
    for (let i = 0; i < 4; i += 1) fireEvent.click(screen.getByRole("button", { name: "Sucesso" }));
    await waitFor(() => expect(screen.getAllByText("Anotei o creme de leite.")).toHaveLength(3));
  });

  it("fora do provedor, mostrar não faz nada", () => {
    function Solto() {
      const toast = useToast();
      return (
        <button type="button" onClick={() => expect(toast.mostrar({ texto: "x" })).toBe(-1)}>
          Solto
        </button>
      );
    }
    render(<Solto />);
    fireEvent.click(screen.getByRole("button", { name: "Solto" }));
    expect(screen.queryByText("x")).not.toBeInTheDocument();
  });
});
