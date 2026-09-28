/**
 * O modo minimalista nos cards das listas, nos dois modos: desligado, tudo
 * como sempre; ligado, só o essencial (as contas e o texto de apoio somem, e
 * a pergunta espera o Responder). Os dados são os dos contratos, e cada card
 * passa pelo axe nos dois modos.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/acoes/despensa", () => ({
  adicionarItem: vi.fn(),
  corrigirItem: vi.fn(),
  removerItem: vi.fn(),
  desfazerMudanca: vi.fn(),
  devolverCompra: vi.fn(),
}));
vi.mock("@/lib/acoes/cozinha", () => ({ definirPosse: vi.fn(), definirRestricao: vi.fn() }));
vi.mock("@/lib/acoes/cardapio", () => ({ tirarDoCardapio: vi.fn(), desfazerNoCardapio: vi.fn() }));
vi.mock("@/lib/acoes/receitas", () => ({
  responderSobreAReceita: vi.fn(),
  responderSobreACozinha: vi.fn(),
  responderLimiteDaCozinha: vi.fn(),
  informarPrecoDoQueFalta: vi.fn(),
}));

import { CabecalhoDaPagina, TituloSecao } from "@/componentes/compartilhados/Titulos";
import type { CardapioCompleto } from "@/lib/api/cardapio";
import type { ItemDaDespensa, ListaDaDespensa } from "@/lib/api/despensa";
import type { ItemDaCozinha as Item, PerfilDaCozinha } from "@/lib/api/perfil";
import type { PrecoDeReferencia } from "@/lib/api/receitas";
import type { VisaoGeral } from "@/lib/api/visao-geral";
import { contrato } from "@/teste/fixturas";
import { modoMinimalista } from "@/teste/minimalista";
import { irPara } from "@/teste/navegacao";
import { FRANGO, PERGUNTA_DAS_BOCAS, item, montar } from "@/teste/receitas";

import { CartaoDoPrato } from "./cardapio/CartaoDoPrato";
import { ItemDaCozinha } from "./cozinha/ItemDaCozinha";
import { CartaoIngrediente } from "./despensa/CartaoIngrediente";
import { Indicadores } from "./inicio/Indicadores";
import { Perguntas } from "./inicio/Perguntas";
import { CartaoDeReceita, CartaoPendente } from "./receitas/CartaoDeReceita";

const DESPENSA = contrato<ListaDaDespensa>("despensa.json");
const VISAO = contrato<VisaoGeral>("visao-geral.json");
const CARDAPIO = contrato<CardapioCompleto>("cardapio.json");
const PERFIL = contrato<PerfilDaCozinha>("perfil.json");

const ingrediente = (id: string) => DESPENSA.itens.find((i) => i.id === id) as ItemDaDespensa;
const daCozinha = (id: string) => [...PERFIL.equipamentos, ...PERFIL.tecnicas].find((i) => i.id === id) as Item;

const REFERENCIA: PrecoDeReferencia = {
  ingrediente: "milho verde",
  texto: "Preço médio em São Paulo: R$ 3,40 pela lata de 170 g (média de 2 mercados de São Paulo: R$ 20,00/kg e R$ 20,00/kg, em 27/09/2026); a senhora pode corrigir.",
  preco_texto: "R$ 3,40 pela lata de 170 g, preço médio em São Paulo, 27/09/2026",
  produto: "Milho Verde Quero Lata 170g",
  site: "mercado de São Paulo",
  url: "https://www.mambo.com.br/milho-verde-quero-lata-170g/p",
  data_texto: "27/09/2026",
  titulo: "Preço médio em São Paulo",
  preco_medio_texto: "R$ 20,00/kg",
  unidade_base: "kg",
  mercados_na_media: 2,
  media_texto: "média de 2 mercados de São Paulo: R$ 20,00/kg e R$ 20,00/kg, em 27/09/2026",
  fontes: [],
};

/** Confere o axe no modo de agora. */
async function semViolacao(container: HTMLElement) {
  expect(await axe(container)).toHaveNoViolations();
}

beforeEach(() => {
  irPara("/");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("os títulos das telas de lista", () => {
  it("resumível, a descrição da página e o apoio da seção somem no minimalista; sem a marca, ficam", () => {
    render(
      <>
        <CabecalhoDaPagina titulo="Despensa" descricao="O que a senhora tem." resumivel />
        <CabecalhoDaPagina titulo="Peito de frango" descricao="A conta do quilo." />
        <TituloSecao titulo="Os pratos" apoio="A conta de cada um." resumivel />
        <TituloSecao titulo="O custo" apoio="Contra a despensa." />
      </>,
    );
    modoMinimalista(false);
    for (const texto of ["O que a senhora tem.", "A conta do quilo.", "A conta de cada um.", "Contra a despensa."]) {
      expect(screen.getByText(texto)).toBeVisible();
    }
    modoMinimalista(true);
    expect(screen.getByText("O que a senhora tem.")).not.toBeVisible();
    expect(screen.getByText("A conta de cada um.")).not.toBeVisible();
    expect(screen.getByText("A conta do quilo.")).toBeVisible();
    expect(screen.getByText("Contra a despensa.")).toBeVisible();
  });
});

describe("Receitas: o card da grade", () => {
  it("desligado, mostra o site, o quanto usa, o que falta e o preço de referência", async () => {
    const { container } = montar(<CartaoDeReceita item={item({ ...FRANGO, referencias: [REFERENCIA] })} />);
    modoMinimalista(false);
    expect(screen.getByText(/TudoGostoso/)).toBeVisible();
    expect(screen.getByText(FRANGO.usa_texto)).toBeVisible();
    expect(screen.getByText(FRANGO.falta_texto)).toBeVisible();
    expect(screen.getByRole("button", { name: "corrigir o preço de milho verde" })).toBeVisible();
    expect(screen.getByText("Estimado")).toBeVisible();
    await semViolacao(container);
  });

  it("ligado, fica a foto, o nome, o selo e o que falta; o site, o 'usa' e o preço de referência somem", async () => {
    const { container } = montar(<CartaoDeReceita item={item({ ...FRANGO, referencias: [REFERENCIA] })} />);
    modoMinimalista(true);
    expect(screen.getByRole("link", { name: FRANGO.nome })).toBeVisible();
    expect(screen.getByText(/Comprando/)).toBeVisible();
    expect(screen.getByText(FRANGO.falta_texto)).toBeVisible();
    expect(screen.getByText(/TudoGostoso/)).not.toBeVisible();
    expect(screen.getByText(FRANGO.usa_texto)).not.toBeVisible();
    expect(screen.queryByRole("button", { name: "corrigir o preço de milho verde" })).not.toBeInTheDocument();
    await semViolacao(container);
  });
});

describe("Receitas: o card que espera uma resposta", () => {
  const PENDENTE = item({
    ...FRANGO,
    selo: { codigo: "falta_resposta", texto: "Falta uma resposta sua" },
    pergunta: PERGUNTA_DAS_BOCAS,
  });
  const linhas = () => screen.getAllByText(PERGUNTA_DAS_BOCAS.texto);

  it("desligado, a pergunta e a resposta ficam à vista, sem o Responder", async () => {
    const { container } = montar(<CartaoPendente item={PENDENTE} />);
    modoMinimalista(false);
    // O "Responder" que fica é o do formulário; o de abrir só existe no minimalista.
    expect(screen.queryByRole("button", { name: "Responder", expanded: false })).not.toBeInTheDocument();
    expect(linhas().filter((linha) => linha.closest(".hidden") === null)).toHaveLength(1);
    expect(screen.getByText(/duas panelas no fogo/)).toBeVisible();
    expect(screen.getByText(FRANGO.usa_texto)).toBeVisible();
    await semViolacao(container);
  });

  it("ligado, a pergunta fica numa linha e o Responder abre a resposta ali mesmo", async () => {
    const { container } = montar(<CartaoPendente item={PENDENTE} />);
    modoMinimalista(true);
    expect(screen.getByText(FRANGO.usa_texto)).not.toBeVisible();
    expect(screen.getByText(/duas panelas no fogo/)).not.toBeVisible();
    const [curta, inteira] = linhas();
    expect(curta).toBeVisible();
    expect(inteira).not.toBeVisible();
    const responder = screen.getByRole("button", { name: "Responder", expanded: false });
    expect(responder).toHaveAccessibleDescription(PERGUNTA_DAS_BOCAS.texto);
    await semViolacao(container);

    fireEvent.click(responder);
    expect(responder).toHaveAttribute("aria-expanded", "true");
    expect(inteira).toBeVisible();
    expect(curta).not.toBeVisible();
    expect(screen.getByText(/duas panelas no fogo/)).toBeVisible();
    await semViolacao(container);

    fireEvent.click(responder);
    expect(inteira).not.toBeVisible();
  });

  it("sem pergunta, o que falta fica numa linha só", () => {
    montar(<CartaoPendente item={{ ...PENDENTE, pergunta: null }} />);
    modoMinimalista(true);
    expect(screen.getByText(FRANGO.falta_texto)).toHaveClass("minimalista:truncate");
    expect(screen.queryByRole("button", { name: "Responder", expanded: false })).not.toBeInTheDocument();
  });
});

describe("Despensa: o card do ingrediente", () => {
  const PEITO = ingrediente("peito-de-frango");
  const COBERTURA = ingrediente("cobertura-de-chocolate");

  it("desligado, mostra o custo por quilo, a conta e os selos", async () => {
    const { container } = render(<CartaoIngrediente item={PEITO} />);
    modoMinimalista(false);
    expect(screen.getByText(PEITO.estoque_texto)).toBeVisible();
    expect(screen.getByText(/Pagou/)).toBeVisible();
    expect(container.querySelector(".numero.mt-0")).toBeVisible();
    expect(screen.getByText(/entra em 1 receita/i)).toBeVisible();
    await semViolacao(container);
  });

  it("ligado, fica a foto, o nome, o estoque e o que pagou; a conta e os selos somem, menos o que falta responder", async () => {
    const { container } = render(
      <ul>
        <li>
          <CartaoIngrediente item={PEITO} />
        </li>
        <li>
          <CartaoIngrediente item={COBERTURA} />
        </li>
      </ul>,
    );
    modoMinimalista(true);
    const peito = within(screen.getByRole("heading", { name: PEITO.nome }).closest("article, section") as HTMLElement);
    expect(peito.getByText(PEITO.estoque_texto)).toBeVisible();
    expect(peito.getByText(/Pagou/)).toBeVisible();
    expect(peito.getByText(/entra em 1 receita/i)).not.toBeVisible();
    expect(container.querySelector(".numero.mt-0")).not.toBeVisible();
    expect(screen.getByText("Falta uma resposta")).toBeVisible();
    expect(screen.getByText("Custo ainda desconhecido")).not.toBeVisible();
    await semViolacao(container);
  });
});

describe("Início: os cinco números", () => {
  it("desligado, cada número tem a frase de apoio; ligado, fica o nome e o número", async () => {
    const { container } = montar(<Indicadores kpis={VISAO.kpis} />);
    const apoio = screen.getByText(`pagos em ${VISAO.kpis.despensa.texto}`);
    modoMinimalista(false);
    expect(apoio).toBeVisible();
    await semViolacao(container);
    modoMinimalista(true);
    expect(apoio).not.toBeVisible();
    expect(screen.getByText(VISAO.kpis.despensa.total.texto)).toBeVisible();
    expect(screen.getByRole("link", { name: "Despensa" })).toBeVisible();
    await semViolacao(container);
  });
});

describe("Início: as perguntas da cozinha", () => {
  const [DA_COZINHA] = VISAO.perguntas_da_cozinha;

  it("desligado, o rótulo e o Chat em cima, e a resposta à vista, sem o Responder de abrir", async () => {
    const { container } = montar(<Perguntas perguntas={VISAO.perguntas_da_cozinha} />);
    modoMinimalista(false);
    expect(screen.getByText("Sobre a sua cozinha")).toBeVisible();
    expect(screen.getByText(/Responda aqui mesmo/)).toBeVisible();
    expect(screen.queryAllByRole("button", { name: "Responder", expanded: false })).toHaveLength(0);
    await semViolacao(container);
  });

  it("ligado, a pergunta numa linha com o Chat e o Responder; a resposta abre quando ela toca", async () => {
    const { container } = montar(<Perguntas perguntas={VISAO.perguntas_da_cozinha} />);
    modoMinimalista(true);
    expect(screen.getByText("Sobre a sua cozinha")).not.toBeVisible();
    expect(screen.getAllByRole("button", { name: "Chat" })).toHaveLength(1);
    const abrir = screen.getAllByRole("button", { name: "Responder", expanded: false });
    expect(abrir).toHaveLength(1);
    expect(abrir[0]).toHaveAccessibleDescription(DA_COZINHA!.pergunta.texto);
    await semViolacao(container);
    fireEvent.click(abrir[0]!);
    expect(abrir[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("link", { name: "Ver as receitas que esperam" })).toBeVisible();
    await semViolacao(container);
  });
});

describe("Cardápio: o card do prato", () => {
  const [PRATO] = CARDAPIO.pratos;

  it("desligado, o preço, o que chega, o custo, o lucro e a conta escrita", async () => {
    const { container } = montar(<CartaoDoPrato prato={PRATO!} aoTirar={vi.fn()} />);
    modoMinimalista(false);
    for (const rotulo of ["Preço", "Chega para a senhora", "Custo de uma porção", "Lucro por porção"]) {
      expect(screen.getByText(rotulo)).toBeVisible();
    }
    expect(screen.getByText(PRATO!.derivacao!)).toBeVisible();
    await semViolacao(container);
  });

  it("ligado, só o preço e o lucro por porção; a conta escrita, a data e as notas somem", async () => {
    const { container } = montar(<CartaoDoPrato prato={PRATO!} aoTirar={vi.fn()} />);
    modoMinimalista(true);
    expect(screen.getByText("Preço")).toBeVisible();
    expect(screen.getByText("Lucro por porção")).toBeVisible();
    expect(screen.getByText("Chega para a senhora")).not.toBeVisible();
    expect(screen.getByText("Custo de uma porção")).not.toBeVisible();
    expect(screen.getByText(PRATO!.derivacao!)).not.toBeVisible();
    expect(screen.getByText(/Aceito/)).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Mudar preço" })).toBeVisible();
    await semViolacao(container);
  });
});

describe("Cozinha: o item", () => {
  const FOGAO = daCozinha("fogao");

  it("desligado, o crédito da foto e as receitas que dependem dele; ligado, só a foto, o nome e o seletor", async () => {
    const { container } = montar(
      <ul>
        <ItemDaCozinha item={FOGAO} tipo="equipamentos" />
      </ul>,
    );
    const credito = screen.getByText(FOGAO.imagem!.credito);
    modoMinimalista(false);
    expect(credito).toBeVisible();
    expect(screen.getByRole("button", { name: /Muda o que dá para fazer/ })).toBeVisible();
    await semViolacao(container);

    modoMinimalista(true);
    expect(credito).not.toBeVisible();
    expect(screen.queryByRole("button", { name: /Muda o que dá para fazer/ })).not.toBeInTheDocument();
    expect(screen.getByText(FOGAO.nome, { selector: "p" })).toBeVisible();
    expect(screen.getByRole("group", { name: FOGAO.nome })).toBeVisible();
    await semViolacao(container);
  });
});
