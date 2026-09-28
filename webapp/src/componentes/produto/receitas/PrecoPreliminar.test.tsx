/**
 * O preço preliminar com as premissas que ela muda ali mesmo: o valor da hora
 * e a embalagem de uma porção. A tela grava pela API e pede a estimativa de
 * novo; os números que aparecem depois são os que a API mandou, e o valor
 * gravado aparece como dela porque volta com `origem: "dela"`.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("@/lib/api/preco", async (importar) => ({
  ...(await importar<typeof import("@/lib/api/preco")>()),
  preco: { estimativa: vi.fn(), parametro: vi.fn(), definirParametro: vi.fn() },
}));

import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { Dinheiro } from "@/lib/api/base";
import type { Estimativa, Premissa } from "@/lib/api/preco";
import { preco } from "@/lib/api/preco";
import { contrato } from "@/teste/fixturas";
import { roteador } from "@/teste/navegacao";
import { montar } from "@/teste/receitas";

import { PrecoPreliminar } from "./CustoDaReceita";

const BASE = contrato<Estimativa>("estimativa.json");

const HORA_DO_PADRAO: Premissa = {
  nome: "valor_hora",
  rotulo: "Valor da hora da senhora",
  valor: { valor: 7.37, texto: "R$ 7,37 por hora" },
  origem: "padrao",
  fonte: "o valor de uma hora de salário mínimo em 2026, pelo decreto do governo",
  fonte_url: "https://www.planalto.gov.br/decreto",
  atualizado_texto: "conferido em 26/09/2026",
  editavel: true,
};

const HORA_DELA: Premissa = {
  ...HORA_DO_PADRAO,
  valor: { valor: 20.5, texto: "R$ 20,50 por hora" },
  origem: "dela",
  fonte: "informado pela senhora",
  fonte_url: null,
  atualizado_texto: "hoje, 10:30",
};

const EMBALAGEM_DELA: Premissa = {
  nome: "embalagem_por_porcao",
  rotulo: "Embalagem por porção",
  valor: { valor: 1.2, texto: "R$ 1,20 por porção" },
  origem: "dela",
  fonte: "informado pela senhora",
  fonte_url: null,
  atualizado_texto: "hoje, 10:31",
  editavel: true,
};

/** A estimativa do contrato com o valor da hora, a mão de obra e o piso que a "API" mandou. */
function estimativa(hora: Premissa, maoDeObra: Dinheiro, piso: Dinheiro): Estimativa {
  return {
    ...BASE,
    linhas: BASE.linhas.map((linha) =>
      linha.id === "mao_de_obra" ? { ...linha, valor: maoDeObra, derivacao: `40 min ÷ 60 × ${hora.valor?.texto ?? ""} ÷ 4 porções` } : linha,
    ),
    premissas: BASE.premissas.map((premissa) => (premissa.nome === hora.nome ? hora : premissa)),
    piso: { ...piso, derivacao: "o custo de produção ÷ 0,90" },
  };
}

const ANTES = estimativa(HORA_DO_PADRAO, { valor: 1.23, texto: "R$ 1,23" }, { valor: 4.43, texto: "R$ 4,43" });
const DEPOIS = estimativa(HORA_DELA, { valor: 3.42, texto: "R$ 3,42" }, { valor: 6.76, texto: "R$ 6,76" });

const COM_EMBALAGEM: Estimativa = {
  ...ANTES,
  linhas: ANTES.linhas.map((linha) =>
    linha.id === "embalagem" ? { ...linha, valor: { valor: 1.2, texto: "R$ 1,20" }, derivacao: "o que a senhora paga numa porção" } : linha,
  ),
  premissas: ANTES.premissas.map((premissa) => (premissa.nome === EMBALAGEM_DELA.nome ? EMBALAGEM_DELA : premissa)),
};

const definir = vi.mocked(preco.definirParametro);
const refazerConta = vi.mocked(preco.estimativa);

afterEach(() => {
  vi.resetAllMocks();
});

/** O parágrafo inteiro, como ela lê (o "R$" preso ao número vira espaço comum). */
const paragrafoDe = (elemento: HTMLElement) => elemento.closest("p")?.textContent?.replace(/\s+/g, " ").trim();

function abrirHora() {
  fireEvent.click(screen.getByRole("button", { name: "Mudar o valor da hora" }));
  return screen.getByRole("textbox", { name: "Valor da hora da senhora" });
}

describe("o valor da hora e a embalagem, mudados no preço preliminar", () => {
  it("grava o número que ela escreveu com vírgula, pede a estimativa de novo e mostra a conta da API, com o valor como dela", async () => {
    definir.mockResolvedValue(HORA_DELA);
    refazerConta.mockResolvedValue(DEPOIS);
    montar(<PrecoPreliminar estimativa={ANTES} />);
    expect(paragrafoDe(screen.getByText("R$ 7,37 por hora"))).toBe("Valor da hora da senhora: R$ 7,37 por hora");
    expect(screen.getByRole("link", { name: /salário mínimo em 2026/ })).toHaveAttribute("href", "https://www.planalto.gov.br/decreto");

    const campo = abrirHora();
    expect(campo).toHaveFocus();
    expect(campo).toHaveValue("7,37");
    expect(campo).toHaveAccessibleDescription("Quanto a senhora quer ganhar por uma hora de trabalho.");
    fireEvent.change(campo, { target: { value: "20,50" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("R$ 3,42")).toBeInTheDocument();
    expect(definir).toHaveBeenCalledWith("valor_hora", 20.5);
    expect(refazerConta).toHaveBeenCalledWith(BASE.slug);
    expect(screen.queryByText("R$ 1,23")).not.toBeInTheDocument();
    expect(screen.getByText("R$ 6,76")).toBeInTheDocument();
    expect(paragrafoDe(screen.getByText("R$ 20,50 por hora"))).toBe("Valor da hora da senhora: R$ 20,50 por hora, a senhora disse (hoje, 10:30)");
    expect(screen.queryByRole("link", { name: /salário mínimo em 2026/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    // O foco volta ao botão num efeito depois da gravação: sob carga, ele chega depois do texto novo.
    await waitFor(() => expect(screen.getByRole("button", { name: "Mudar o valor da hora" })).toHaveFocus());
    expect(await screen.findByText("Anotei R$ 20,50 por hora e refiz a conta.")).toBeInTheDocument();
    // A página é refeita também: voltar para esta receita traz a conta nova.
    expect(roteador.refresh).toHaveBeenCalledTimes(1);
  });

  it("a embalagem que ela ainda não disse: Dizer quanto paga, Enter grava, e a linha passa a ter o valor da API", async () => {
    definir.mockResolvedValue(EMBALAGEM_DELA);
    refazerConta.mockResolvedValue(COM_EMBALAGEM);
    montar(<PrecoPreliminar estimativa={ANTES} />);
    expect(screen.getByText("falta saber")).toBeInTheDocument();
    expect(paragrafoDe(screen.getByText("a senhora ainda não disse"))).toBe("Embalagem por porção: a senhora ainda não disse");

    fireEvent.click(screen.getByRole("button", { name: "Dizer quanto paga na embalagem" }));
    const campo = screen.getByRole("textbox", { name: "Embalagem por porção" });
    expect(campo).toHaveValue("");
    fireEvent.change(campo, { target: { value: "1,2" } });
    // O Enter no campo envia o formulário.
    fireEvent.submit(campo.closest("form") as HTMLFormElement);

    expect(await screen.findByText("R$ 1,20")).toBeInTheDocument();
    expect(definir).toHaveBeenCalledWith("embalagem_por_porcao", 1.2);
    expect(screen.queryByText("falta saber")).not.toBeInTheDocument();
    expect(paragrafoDe(screen.getByText("R$ 1,20 por porção"))).toBe("Embalagem por porção: R$ 1,20 por porção, a senhora disse (hoje, 10:31)");
    expect(screen.getByRole("button", { name: "Mudar o valor da embalagem" })).toBeInTheDocument();
  });

  it("a API recusa o valor: o porquê aparece no campo, em português, e a conta não é refeita", async () => {
    definir.mockRejectedValue(new ErroDoMotor("valor da hora da senhora fora da faixa que eu consigo usar", "uso", undefined, undefined, 422));
    montar(<PrecoPreliminar estimativa={ANTES} />);
    const campo = abrirHora();
    fireEvent.change(campo, { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    const recusa = await screen.findByText("Valor da hora da senhora fora da faixa que eu consigo usar.");
    expect(recusa.closest("[role=alert]")).not.toBeNull();
    expect(definir).toHaveBeenCalledWith("valor_hora", 5000);
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(campo).toHaveAccessibleDescription(/fora da faixa que eu consigo usar/);
    expect(campo).toHaveFocus();
    expect(refazerConta).not.toHaveBeenCalled();
    expect(roteador.refresh).not.toHaveBeenCalled();
    expect(screen.getByText("R$ 1,23")).toBeInTheDocument();

    // Ela corrige: o aviso some enquanto escreve.
    fireEvent.change(campo, { target: { value: "25" } });
    expect(screen.queryByText("Valor da hora da senhora fora da faixa que eu consigo usar.")).not.toBeInTheDocument();
  });

  it("sem conseguir falar com a API, o aviso da categoria, e o campo continua aberto com o que ela escreveu", async () => {
    definir.mockRejectedValue(new ErroDoMotor(MENSAGENS.rede, "rede"));
    montar(<PrecoPreliminar estimativa={ANTES} />);
    const campo = abrirHora();
    fireEvent.change(campo, { target: { value: "18" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    const aviso = await screen.findByText("Não consegui falar com o sistema");
    expect(aviso.closest("[role=alert]")).not.toBeNull();
    expect(campo).toHaveValue("18");
    expect(campo).not.toHaveAttribute("aria-invalid");
  });

  it("sem número no campo, pede o valor sem chamar a API; Esc e Cancelar fecham e devolvem ao botão", () => {
    montar(<PrecoPreliminar estimativa={ANTES} />);
    fireEvent.click(screen.getByRole("button", { name: "Dizer quanto paga na embalagem" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByText("Escreva o valor em reais.").closest("[role=alert]")).not.toBeNull();
    const campo = screen.getByRole("textbox", { name: "Embalagem por porção" });
    fireEvent.change(campo, { target: { value: "uns dois reais" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByText("Escreva só o número, como 12,50.")).toBeInTheDocument();

    fireEvent.keyDown(campo, { key: "Escape" });
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dizer quanto paga na embalagem" })).toHaveFocus();

    abrirHora();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("button", { name: "Mudar o valor da hora" })).toHaveFocus();
    expect(definir).not.toHaveBeenCalled();
  });

  it("gravou, mas a conta não voltou: diz que a conta ficou para depois e por quê, e Tentar de novo traz a da API", async () => {
    const porque = "Ainda não estimo o preço de arroz com frango: antes a receita tem que dar para fazer.";
    definir.mockResolvedValue(HORA_DELA);
    refazerConta.mockRejectedValueOnce(new ErroDoMotor(porque, "regra")).mockResolvedValueOnce(DEPOIS);
    montar(<PrecoPreliminar estimativa={ANTES} />);
    fireEvent.change(abrirHora(), { target: { value: "20,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    const aviso = await screen.findByText("Anotei, mas não consegui refazer a conta");
    expect(aviso.closest("[role=alert]")).not.toBeNull();
    expect(screen.getByText(porque)).toBeInTheDocument();
    expect(screen.queryByText("Anotei R$ 20,50 por hora e refiz a conta.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("R$ 3,42")).toBeInTheDocument();
    expect(screen.queryByText("Anotei, mas não consegui refazer a conta")).not.toBeInTheDocument();
    expect(refazerConta).toHaveBeenCalledTimes(2);
  });

  it("quando a página é refeita (outra resposta, a conversa), vale a estimativa que chegou do servidor", () => {
    const { refazer } = montar(<PrecoPreliminar estimativa={ANTES} />);
    expect(screen.getByText("R$ 1,23")).toBeInTheDocument();
    refazer(<PrecoPreliminar estimativa={DEPOIS} />);
    expect(screen.getByText("R$ 3,42")).toBeInTheDocument();
    expect(paragrafoDe(screen.getByText("R$ 20,50 por hora"))).toBe("Valor da hora da senhora: R$ 20,50 por hora, a senhora disse (hoje, 10:30)");
  });

  it("sem violação de acessibilidade, lendo e mudando", async () => {
    const { container } = montar(<PrecoPreliminar estimativa={ANTES} />);
    expect(await axe(container)).toHaveNoViolations();
    abrirHora();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("as premissas sem botão", () => {
  it("a premissa que a API não deixa mudar fica em De onde vêm os números, sem botão", async () => {
    const travada: Estimativa = {
      ...ANTES,
      premissas: ANTES.premissas.map((premissa) => (premissa.nome === "valor_hora" ? { ...premissa, editavel: false } : premissa)),
    };
    montar(<PrecoPreliminar estimativa={travada} />);
    expect(screen.queryByRole("button", { name: "Mudar o valor da hora" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("De onde vêm os números"));
    await waitFor(() => expect(screen.getByText("R$ 7,37 por hora")).toBeInTheDocument());
  });
});
