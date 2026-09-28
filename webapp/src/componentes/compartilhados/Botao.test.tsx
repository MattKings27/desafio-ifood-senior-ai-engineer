/**
 * Botões: o primário é o único vermelho cheio; carregar não tira o foco; o
 * link externo avisa que abre em outra aba; botão de ícone sempre tem nome.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Botao, BotaoIcone } from "./Botao";
import { BotaoLink } from "./BotaoLink";
import { classesDoBotao } from "./estilosDoBotao";

describe("Botao", () => {
  it("é um botão de verdade, do tipo button por padrão (não envia formulário sem querer)", () => {
    render(<Botao>Calcular</Botao>);
    expect(screen.getByRole("button", { name: "Calcular" })).toHaveAttribute("type", "button");
  });

  it("o primário usa o preenchimento da marca; os outros não", () => {
    render(
      <>
        <Botao>Primário</Botao>
        <Botao variante="secundario">Secundário</Botao>
        <Botao variante="perigo">Tirar</Botao>
      </>,
    );
    expect(screen.getByRole("button", { name: "Primário" }).className).toContain("bg-marca-fundo");
    expect(screen.getByRole("button", { name: "Secundário" }).className).not.toContain("bg-marca-fundo");
    expect(screen.getByRole("button", { name: "Tirar" }).className).toContain("bg-perigo");
  });

  it.each([
    ["sm", "h-11"],
    ["md", "h-12"],
    ["lg", "h-14"],
  ] as const)("tamanho %s tem pelo menos 44 px (%s)", (tamanho, altura) => {
    render(<Botao tamanho={tamanho}>Ok</Botao>);
    expect(screen.getByRole("button").className).toContain(altura);
  });

  it("largura total e classe de quem usa, com a de quem usa vencendo", () => {
    render(
      <Botao larguraTotal className="bg-sucesso">
        Ok
      </Botao>,
    );
    const botao = screen.getByRole("button");
    expect(botao.className).toContain("w-full");
    expect(botao.className).toContain("bg-sucesso");
    expect(botao.className).not.toContain("bg-marca-fundo ");
  });

  it("ícones são decorativos: o nome é o texto", () => {
    render(
      <Botao icone={<svg data-testid="antes" />} iconeDepois={<svg data-testid="depois" />}>
        Salvar
      </Botao>,
    );
    expect(screen.getByRole("button", { name: "Salvar" })).toBeInTheDocument();
    expect(screen.getByTestId("antes").parentElement).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("depois").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("carregando: continua focável, anuncia ocupado, ignora o clique e troca o texto", () => {
    const clique = vi.fn();
    render(
      <Botao carregando rotuloCarregando="Salvando…" onClick={clique} iconeDepois={<svg data-testid="depois" />}>
        Salvar
      </Botao>,
    );
    const botao = screen.getByRole("button", { name: "Salvando…" });
    expect(botao).not.toBeDisabled();
    expect(botao).toHaveAttribute("aria-busy", "true");
    expect(botao).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByTestId("depois")).not.toBeInTheDocument();
    fireEvent.click(botao);
    expect(clique).not.toHaveBeenCalled();
  });

  it("carregando sem rótulo próprio mantém o texto", () => {
    render(<Botao carregando>Salvar</Botao>);
    expect(screen.getByRole("button", { name: "Salvar" })).toHaveAttribute("aria-busy", "true");
  });

  it("fora do carregamento, o clique chega; aria-disabled de quem usa é respeitado", () => {
    const clique = vi.fn();
    render(
      <>
        <Botao onClick={clique}>Ok</Botao>
        <Botao aria-disabled>Indisponível</Botao>
        <Botao type="submit">Enviar</Botao>
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Ok" }));
    expect(clique).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Indisponível" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "Enviar" })).toHaveAttribute("type", "submit");
  });

  it("desabilitado não recebe clique", () => {
    render(<Botao disabled>Ok</Botao>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("classesDoBotao", () => {
  it("serve para pintar outro elemento como botão", () => {
    expect(classesDoBotao()).toContain("bg-marca-fundo");
    expect(classesDoBotao({ variante: "texto", tamanho: "sm", larguraTotal: true })).toMatch(/h-11.*w-full/);
  });
});

describe("BotaoLink", () => {
  it("link interno com cara de botão", () => {
    render(
      <BotaoLink href="/receitas" variante="secundario" icone={<svg data-testid="i" />}>
        Ver receitas
      </BotaoLink>,
    );
    const link = screen.getByRole("link", { name: "Ver receitas" });
    expect(link).toHaveAttribute("href", "/receitas");
    expect(link.className).toContain("border-marca");
    expect(link).not.toHaveAttribute("target");
  });

  it("externo abre em outra aba, sem dar acesso à janela, e avisa", () => {
    render(
      <BotaoLink href="https://www.tudogostoso.com.br/receita/1" externo>
        Ver no site
      </BotaoLink>,
    );
    const link = screen.getByRole("link", { name: "Ver no site (abre em outra aba)" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});

describe("BotaoIcone", () => {
  it("tem nome e dica, e o ícone é decorativo", () => {
    render(
      <BotaoIcone rotulo="Fechar">
        <svg data-testid="x" />
      </BotaoIcone>,
    );
    const botao = screen.getByRole("button", { name: "Fechar" });
    expect(botao).toHaveAttribute("title", "Fechar");
    expect(botao).toHaveAttribute("type", "button");
    expect(botao.className).toContain("size-11");
    expect(screen.getByTestId("x").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it.each([
    ["primario", "bg-marca-fundo"],
    ["terciario", "border-borda-campo/60"],
    ["texto", "bg-transparent"],
  ] as const)("variante %s", (variante, classe) => {
    render(
      <BotaoIcone rotulo="Mais" variante={variante} tamanho="md">
        +
      </BotaoIcone>,
    );
    const botao = screen.getByRole("button", { name: "Mais" });
    expect(botao.className).toContain(classe);
    expect(botao.className).toContain("size-12");
  });
});
