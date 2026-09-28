/**
 * Testes das primitivas.
 *
 * O que estes testes protegem não é a aparência, e sim a regra de que a
 * interface não calcula e não inventa. `Valor` renderiza o texto que veio do motor;
 * `Derivacao` deixa a conta visível; `SeloVeredito` não usa o vermelho da
 * marca. São exatamente as coisas que um refactor bem-intencionado quebra sem
 * perceber.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Dinheiro } from "@/lib/api/base";

import {
  Barra,
  Botao,
  Card,
  Chip,
  Derivacao,
  Esqueleto,
  Problema,
  SeloVeredito,
  TituloSecao,
  Valor,
  Vazio,
} from "./Primitivas";

const dinheiro = (valor: number, texto: string): Dinheiro => ({ valor, texto });

describe("Valor", () => {
  it("mostra o texto que veio do motor, não um número reformatado", () => {
    render(<Valor dinheiro={dinheiro(1234.56, "R$ 1.234,56")} />);
    expect(screen.getByText("R$ 1.234,56")).toBeInTheDocument();
  });

  it("não deixa a formatação do navegador vazar para a tela", () => {
    // Se alguém trocar `dinheiro.texto` por `dinheiro.valor`, aparece "1234.56".
    render(<Valor dinheiro={dinheiro(1234.56, "R$ 1.234,56")} />);
    expect(screen.queryByText(/1234\.56/)).not.toBeInTheDocument();
  });

  it("valor negativo é lido como negativo sem precisar dizer", () => {
    const { container } = render(<Valor dinheiro={dinheiro(-10, "-R$ 10,00")} />);
    expect(container.querySelector(".text-perigo")).toBeInTheDocument();
  });

  it("o tom explícito vence a inferência pelo sinal", () => {
    const { container } = render(
      <Valor dinheiro={dinheiro(-10, "-R$ 10,00")} tom="marca" />,
    );
    expect(container.querySelector(".text-marca")).toBeInTheDocument();
    expect(container.querySelector(".text-perigo")).not.toBeInTheDocument();
  });
});

describe("SeloVeredito", () => {
  it.each([
    ["APTO", "Dá pra fazer", "sucesso"],
    ["APTO COM COMPRA", "Dá, comprando", "info"],
    ["FALTA INFO", "Falta saber", "atencao"],
    ["BLOQUEADO", "Não dá", "perigo"],
  ] as const)("%s aparece como '%s', no tom %s", (veredito, rotulo, tom) => {
    // O rótulo é o que ela lê: nada de "FALTA INFO" ou "BLOQUEADO" na tela dela.
    const { container } = render(<SeloVeredito veredito={veredito} />);
    expect(screen.getByText(rotulo)).toBeInTheDocument();
    expect(screen.queryByText(veredito)).not.toBeInTheDocument();
    expect(container.querySelector(`.text-${tom}`)).toBeInTheDocument();
  });

  it("BLOQUEADO nunca usa o vermelho da marca", () => {
    // No iFood o vermelho da marca significa *ação*. Um bloqueio pintado com
    // ele seria lido como botão.
    const { container } = render(<SeloVeredito veredito="BLOQUEADO" />);
    expect(container.querySelector(".text-marca")).not.toBeInTheDocument();
  });
});

describe("Problema", () => {
  it("falta de dado é apresentada como pergunta, não como erro", () => {
    render(
      <Problema
        mensagem="massa da embalagem desconhecida"
        categoria="dado"
        pergunta="Quanto pesa o pacote de chocolate?"
      />,
    );
    expect(screen.getByText("Falta uma informação")).toBeInTheDocument();
    expect(screen.getByText("Quanto pesa o pacote de chocolate?")).toBeInTheDocument();
  });

  it("recusa por regra não vira 'erro', que mentiria sobre o que houve", () => {
    render(<Problema mensagem="Ainda falta confirmar que dá pra fazer." categoria="regra" />);
    expect(screen.getByText("Ainda não dá para fazer isso")).toBeInTheDocument();
    expect(screen.queryByText(/erro/i)).not.toBeInTheDocument();
  });

  it("categoria de dado sem pergunta continua sendo falta de informação, com a mensagem", () => {
    render(<Problema mensagem="Falta o peso da embalagem." categoria="dado" />);
    expect(screen.getByText("Falta uma informação")).toBeInTheDocument();
    expect(screen.getByText("Falta o peso da embalagem.")).toBeInTheDocument();
  });

  it("o título de antes, 'A conta não fechou', não aparece mais", () => {
    render(<Problema mensagem="motor respondeu 503" categoria="rede" />);
    expect(screen.queryByText("A conta não fechou")).not.toBeInTheDocument();
    expect(screen.getByText("Não consegui falar com o sistema")).toBeInTheDocument();
    expect(screen.queryByText(/motor/)).not.toBeInTheDocument();
  });

  it("anuncia-se para leitor de tela sem roubar o foco", () => {
    render(<Problema mensagem="algo" categoria="rede" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("Barra", () => {
  it("expõe a proporção como meter, com rótulo", () => {
    render(<Barra fracao={0.42} rotulo="orçamento usado" />);
    const medidor = screen.getByRole("meter", { name: "orçamento usado" });
    expect(medidor).toHaveAttribute("aria-valuenow", "42");
  });

  it.each([
    [-0.5, "0"],
    [1.7, "100"],
  ])("fração %s é presa dentro de 0 a 100 (%s)", (fracao, esperado) => {
    render(<Barra fracao={fracao} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", esperado);
  });
});

describe("Botao", () => {
  it("é um botão de verdade, alcançável pelo teclado", () => {
    render(<Botao>Calcular</Botao>);
    expect(screen.getByRole("button", { name: "Calcular" })).toBeInTheDocument();
  });

  it.each(["primario", "secundario", "terciario", "texto"] as const)(
    "a variante %s renderiza",
    (variante) => {
      render(<Botao variante={variante}>Ok</Botao>);
      expect(screen.getByRole("button")).toBeInTheDocument();
    },
  );

  it("desabilitado não recebe clique", () => {
    render(<Botao disabled>Ok</Botao>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("estrutura e estados", () => {
  it("Card aceita conteúdo", () => {
    render(<Card>conteúdo</Card>);
    expect(screen.getByText("conteúdo")).toBeInTheDocument();
  });

  it("TituloSecao é um cabeçalho de nível 2", () => {
    render(<TituloSecao titulo="Despensa" apoio="37 itens" />);
    expect(screen.getByRole("heading", { level: 2, name: "Despensa" })).toBeInTheDocument();
    expect(screen.getByText("37 itens")).toBeInTheDocument();
  });

  it("Derivacao mostra a conta, sem esconder atrás de clique", () => {
    render(<Derivacao>R$ 15,98 ÷ 2 kg = R$ 7,99/kg</Derivacao>);
    expect(screen.getByText("R$ 15,98 ÷ 2 kg = R$ 7,99/kg")).toBeInTheDocument();
  });

  it("Esqueleto é decorativo e não é anunciado", () => {
    const { container } = render(<Esqueleto />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("Vazio explica o vazio em vez de deixar a tela muda", () => {
    render(<Vazio titulo="Nada ainda" descricao="registre o primeiro prato" />);
    expect(screen.getByText("Nada ainda")).toBeInTheDocument();
    expect(screen.getByText("registre o primeiro prato")).toBeInTheDocument();
  });

  it("Chip aceita os tons sem quebrar", () => {
    render(<Chip tom="sucesso">apto</Chip>);
    expect(screen.getByText("apto")).toBeInTheDocument();
  });
});
