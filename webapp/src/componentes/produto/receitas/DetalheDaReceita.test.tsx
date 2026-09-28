/**
 * O detalhe de uma receita: a foto com o crédito e a página de origem, a
 * cozinha em palavras dela, o que ela tem ao lado do que falta comprar (com a
 * conta de cada compra), as linhas que a leitura não entendeu, os passos com o
 * que pedem, o custo por porção (ou o porquê de ainda não ter) e o preço
 * preliminar. "Pôr preço" só com a cozinha liberando e ela gostando.
 */

import { fireEvent, screen, within } from "@testing-library/react";
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

import type { Estimativa } from "@/lib/api/preco";
import type {
  CustoDaPorcao,
  GrupoDoChecklist,
  IngredienteDaReceita,
  ItemDoChecklist,
  PerguntaDaReceita,
  DetalheDaReceita as Receita,
  Requisito,
} from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";
import { PERGUNTA_DAS_BOCAS, TEXTOS_QUE_NUNCA_APARECEM, montar } from "@/teste/receitas";

import type { CustoNaTela } from "./CustoDaReceita";
import { DetalheDaReceita } from "./DetalheDaReceita";

const RECEITA = contrato<Receita>("receita.json");
const CUSTO = contrato<CustoDaPorcao>("custo.json");
const ESTIMATIVA = contrato<Estimativa>("estimativa.json");
const RECUSADO: CustoNaTela = { tipo: "recusado", motivo: "Ainda não calculo o custo de carne moída: antes preciso saber uma coisa." };

afterEach(() => {
  vi.clearAllMocks();
});

function detalhe(receita: Receita = RECEITA, custo: CustoNaTela = RECUSADO, estimativa: Estimativa | null = ESTIMATIVA) {
  return montar(<DetalheDaReceita receita={receita} custo={custo} estimativa={estimativa} />);
}

const secao = (nome: string) => screen.getByRole("region", { name: nome });

/** O parágrafo inteiro, como ela lê (o "R$" preso ao número vira espaço comum). */
const paragrafoDe = (elemento: HTMLElement) => elemento.closest("p")?.textContent?.replace(/\s+/g, " ").trim();

function requisito(extras: Partial<Requisito>): Requisito {
  return {
    tipo: "equipamento",
    id: "batedeira",
    nome: "Batedeira",
    estado: "desconhecido",
    suposto: false,
    evidencia: "",
    trecho: "bata",
    rotulo_estado: "ainda não perguntei",
    substituto: null,
    conferido: true,
    ...extras,
  };
}

describe("o topo: foto, origem, cozinha e as ações", () => {
  it("a receita do contrato, com o que falta responder e Pôr preço desabilitado com o motivo", async () => {
    const { container, loja } = detalhe();
    expect(screen.getByRole("heading", { level: 1, name: RECEITA.nome })).toBeInTheDocument();
    expect(screen.getByText("Foto: TudoGostoso")).toBeInTheDocument();
    const origem = screen.getByRole("link", { name: /Ver a receita no TudoGostoso/ });
    expect(origem).toHaveAttribute("href", RECEITA.fonte.url);
    expect(origem).toHaveAttribute("target", "_blank");
    expect(screen.getByText("Receita de Leuda M. V. Xavier")).toBeInTheDocument();
    expect(screen.getByText("45 min no total")).toBeInTheDocument();
    expect(screen.getByText("40 min de fogo e trabalho")).toBeInTheDocument();
    expect(screen.getByText("Rende 4 porções")).toBeInTheDocument();
    expect(screen.getByText("Falta uma resposta da senhora")).toBeInTheDocument();
    expect(screen.getByText(RECEITA.veredito_da_cozinha.motivo)).toBeInTheDocument();
    // O aviso das bocas aparece na caixa da cozinha e, de novo, no item Bocas do checklist.
    expect(screen.getAllByText(RECEITA.avisos[0]?.texto ?? "")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Receitas" })).toHaveAttribute("href", "/receitas");

    const porPreco = screen.getByRole("button", { name: "Pôr preço" });
    expect(porPreco).toHaveAttribute("aria-disabled", "true");
    // O que falta vem do checklist, item por item: a cozinha a confirmar. A frase que repete a
    // pergunta da linha que a leitura não entendeu não aparece: quantidade não é pergunta.
    expect(porPreco).toHaveAccessibleDescription(
      [RECEITA.checklist.resumo, ...RECEITA.checklist.falta_para_aceitar.filter((f) => !f.includes("Não entendi"))].join(" "),
    );
    for (const texto of TEXTOS_QUE_NUNCA_APARECEM) expect(container.textContent).not.toMatch(texto);
    fireEvent.click(porPreco);
    expect(loja.ler().caixa.texto).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "Perguntar" }));
    expect(loja.ler().caixa.texto).toBe(RECEITA.rascunho_chat);
    expect(loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "receita", id: RECEITA.slug, rotulo: RECEITA.nome });

    // A linha não entendida se responde nos ingredientes: não repete em "Antes de decidir".
    expect(screen.queryByRole("region", { name: "Antes de decidir, preciso saber" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("com o checklist liberando o aceite, Pôr preço abre a conversa com o pedido e a receita", () => {
    const pronta: Receita = {
      ...RECEITA,
      veredito_da_cozinha: { codigo: "com_o_que_tem", rotulo: "Com o que a senhora tem", motivo: "Tem tudo." },
      pode_precificar: true,
      perguntas: [],
      linhas_nao_entendidas: [],
      checklist: { ...RECEITA.checklist, pode_aceitar: true, falta_para_aceitar: [], confirmar_a_cozinha: null, resumo: "Está tudo certo para a senhora aceitar este prato." },
    };
    const { loja } = detalhe(pronta, { tipo: "pronto", custo: CUSTO });
    const porPreco = screen.getByRole("button", { name: "Pôr preço" });
    expect(porPreco).not.toHaveAttribute("aria-disabled");
    fireEvent.click(porPreco);
    expect(loja.ler().caixa.texto).toBe(`Quero pôr preço na ${RECEITA.nome}`);
    expect(loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "receita", id: RECEITA.slug, rotulo: RECEITA.nome });
  });

  it("a receita que ela ditou: sem site, sem página, sem crédito, sem tempos", () => {
    const dita: Receita = {
      ...RECEITA,
      imagem: null,
      fonte: { site: null, url: null, autor: null },
      origem: "dita",
      tempo_texto: null,
      rendimento_texto: null,
      tempos: { preparo_min: null, cozimento_min: null, total_min: null, ativo_min: null },
      veredito_da_cozinha: { codigo: "nao_da", rotulo: "Não dá", motivo: "Vai ao forno, e a senhora não tem." },
      respostas: [],
      checklist: {
        ...RECEITA.checklist,
        pode_aceitar: false,
        resumo: "Pelo que a senhora me disse, esta receita não dá.",
        falta_para_aceitar: ["A receita precisa de forno e a senhora não tem."],
        confirmar_a_cozinha: null,
      },
    };
    detalhe(dita, RECUSADO, null);
    expect(screen.getByText("Receita que a senhora ditou")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Ver a receita/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/no total/)).not.toBeInTheDocument();
    expect(screen.getByText("Não dá")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pôr preço" })).toHaveAccessibleDescription(
      "Pelo que a senhora me disse, esta receita não dá. A receita precisa de forno e a senhora não tem.",
    );
    expect(screen.queryByRole("region", { name: "Preço preliminar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "O que a senhora já me disse" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Ingredientes" })).toHaveTextContent("Contra a despensa da senhora.");
  });
});

describe("os casos de borda do detalhe", () => {
  it("sem avisos, a página sem nome de site, o ingrediente sem o quanto tem e o passo sem nada pedido", () => {
    const receita: Receita = {
      ...RECEITA,
      avisos: [],
      fonte: { site: null, url: "https://receitas.exemplo.com.br/bolo", autor: null },
      opcionais: [],
      ingredientes: [
        { nome: "Farinha", item_id: "farinha", precisa: { texto: "2 xícaras" }, tem: null, sobra: null, situacao: "tem", compra: null, medida_de_referencia: null },
        { nome: "Sal", item_id: "sal", precisa: { texto: "a gosto" }, tem: null, sobra: null, situacao: "a_gosto", compra: null, medida_de_referencia: null },
      ],
      passos: [{ ordem: 1, texto: "Misture tudo.", requisitos: [], limites: [] }],
      requisitos_da_receita: [],
    };
    detalhe(receita, RECUSADO, { ...ESTIMATIVA, premissas: [] });
    expect(screen.getByRole("link", { name: /Ver a receita na página de origem/ })).toHaveAttribute("href", "https://receitas.exemplo.com.br/bolo");
    // Sem aviso, a caixa da cozinha não diz nada das bocas; o item Bocas do checklist continua dizendo.
    expect(screen.getAllByText(RECEITA.avisos[0]?.texto ?? "")).toHaveLength(1);
    const tem = screen.getByRole("heading", { name: "A senhora tem" }).parentElement as HTMLElement;
    expect(within(tem).getByText("2 xícaras")).toBeInTheDocument();
    expect(within(tem).queryByText("Tem")).not.toBeInTheDocument();
    expect(screen.getByText("Sal.")).toBeInTheDocument();
    expect(screen.queryByText("Opcional")).not.toBeInTheDocument();
    expect(screen.getByText("Misture tudo.")).toBeInTheDocument();
    expect(screen.queryByText("De onde vêm os números")).not.toBeInTheDocument();
  });

  it("só o opcional, sem nada a gosto", () => {
    detalhe({ ...RECEITA, ingredientes: RECEITA.ingredientes.filter((i) => i.situacao !== "a_gosto") });
    expect(screen.queryByText("Vai a gosto", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByText("Opcional", { selector: "dt" })).toBeInTheDocument();
  });

  it("a premissa sem data: a dela diz que a senhora disse, a do padrão mostra a fonte", () => {
    detalhe(RECEITA, RECUSADO, {
      ...ESTIMATIVA,
      premissas: [
        { nome: "valor_hora", rotulo: "Valor da hora", valor: { valor: 8, texto: "R$ 8,00" }, origem: "dela", fonte: "informado pela senhora", fonte_url: null, atualizado_texto: null, editavel: true },
        { nome: "botijao_preco", rotulo: "Preço do botijão", valor: { valor: 120, texto: "R$ 120,00" }, origem: "padrao", fonte: "a pesquisa da ANP", fonte_url: null, atualizado_texto: null, editavel: true },
      ],
    });
    const preco = secao("Preço preliminar");
    expect(paragrafoDe(within(preco).getByText("R$ 8,00"))).toBe("Valor da hora: R$ 8,00, a senhora disse");
    expect(within(preco).queryByText("informado pela senhora")).not.toBeInTheDocument();
    expect(within(preco).getByText("a pesquisa da ANP")).toBeInTheDocument();
  });
});

describe("as perguntas e os passos", () => {
  it("as perguntas da cozinha se respondem no checklist; o passo não repete o que já foi perguntado", () => {
    const forno = { ...PERGUNTA_DAS_BOCAS, tipo: "equipamento", assunto: "equipamento" as const, campo: "forno", texto: "A senhora tem forno?", entrada: null, opcoes: [{ rotulo: "Tenho", resposta: "sim" }] };
    const [equipamentos, tecnicas, rotina, ...resto] = RECEITA.checklist.grupos as [GrupoDoChecklist, GrupoDoChecklist, GrupoDoChecklist, ...GrupoDoChecklist[]];
    const pendente = (id: string, nome: string, pergunta: PerguntaDaReceita): ItemDoChecklist => ({
      id,
      tipo: pergunta.tipo,
      nome,
      detalhe: pergunta.texto,
      status: "falta_saber",
      status_texto: "falta saber",
      origem: "receita",
      origem_texto: "receita",
      pergunta,
      editar: null,
    });
    const receita: Receita = {
      ...RECEITA,
      checklist: {
        ...RECEITA.checklist,
        grupos: [
          { ...equipamentos, itens: [...equipamentos.itens, pendente("forno", "Forno", forno)] },
          tecnicas,
          { ...rotina, itens: [pendente("bocas_fogao", "Bocas do fogão", PERGUNTA_DAS_BOCAS), ...rotina.itens.slice(1)] },
          ...resto,
        ],
      },
      perguntas: [forno, PERGUNTA_DAS_BOCAS, ...RECEITA.perguntas],
      passos: [
        {
          ordem: 1,
          texto: "Bata a massa e leve ao forno.",
          requisitos: [
            requisito({ id: "forno", nome: "Forno" }),
            requisito({}),
            requisito({ tipo: "tecnica", id: "bater", nome: "Bater claras", conferido: false }),
          ],
          limites: [],
        },
        { ordem: 2, texto: "Bata de novo.", requisitos: [requisito({})], limites: [] },
      ],
      requisitos_da_receita: [
        { ...requisito({ tipo: "tecnica", id: "fritar", nome: "Fritar" }), origem: "nome" },
        { ...requisito({ id: "fogao", nome: "Fogão", estado: "tem", rotulo_estado: "a senhora tem" }), origem: "receita" },
        { ...requisito({ id: "forno2", nome: "Forno elétrico", estado: "nao_tem", rotulo_estado: "a senhora não tem" }), origem: "receita" },
        {
          ...requisito({ id: "forno3", nome: "Forno a gás", substituto: { id: "air_fryer", nome: "Air fryer" }, rotulo_estado: "a senhora resolve com air fryer" }),
          origem: "receita",
        },
      ],
    };
    detalhe(receita);
    expect(screen.queryByRole("region", { name: "Antes de decidir, preciso saber" })).not.toBeInTheDocument();
    const checklist = secao("Checklist de produção");
    expect(within(checklist).getByRole("group", { name: "A senhora tem forno?" })).toBeInTheDocument();
    expect(within(checklist).getByRole("textbox", { name: "Bocas" })).toBeInTheDocument();
    // A linha que a leitura não entendeu não vira pergunta em lugar nenhum.
    expect(within(checklist).queryByRole("link", { name: "Responder em Ingredientes" })).not.toBeInTheDocument();
    expect(within(checklist).queryByRole("textbox", { name: /temperos de sua preferência/ })).not.toBeInTheDocument();

    const preparo = secao("Modo de preparo");
    expect(within(preparo).getByText("Passo 1:")).toBeInTheDocument();
    expect(within(preparo).queryByRole("group", { name: "A senhora tem forno?" })).not.toBeInTheDocument();
    expect(within(preparo).getAllByRole("group", { name: "A senhora tem batedeira?" })).toHaveLength(1);
    expect(within(preparo).queryByRole("group", { name: /bater claras/ })).not.toBeInTheDocument();
    expect(within(preparo).getByText("Bater claras: ainda não perguntei")).toBeInTheDocument();
    expect(within(preparo).getByRole("group", { name: "A senhora sabe fritar?" })).toBeInTheDocument();
    expect(within(preparo).getByText("Fogão: a senhora tem")).toBeInTheDocument();
    expect(within(preparo).getByText("Forno elétrico: a senhora não tem")).toBeInTheDocument();
    expect(within(preparo).getByText("Forno a gás: a senhora resolve com air fryer")).toBeInTheDocument();
  });

  it("os passos do contrato: o que cada um pede, suposto dito do jeito dela, e os limites", () => {
    detalhe();
    const preparo = secao("Modo de preparo");
    expect(within(preparo).getAllByRole("listitem").length).toBeGreaterThan(4);
    expect(within(preparo).getAllByText("Fogão: toda cozinha tem").length).toBeGreaterThan(0);
    expect(within(preparo).getByText("Refogar: toda cozinheira faz")).toBeInTheDocument();
    expect(within(preparo).getAllByText("5 min no fogo").length).toBe(2);
    expect(within(preparo).getByText("mais uma boca do fogão ao mesmo tempo")).toBeInTheDocument();
    expect(within(preparo).getByText("A receita também pede")).toBeInTheDocument();
    expect(within(preparo).getByText("Panela de pressão: toda cozinha tem")).toBeInTheDocument();
  });

  it("sem modo de preparo, diz que a página não trouxe", () => {
    detalhe({ ...RECEITA, passos: [], requisitos_da_receita: [] });
    expect(within(secao("Modo de preparo")).getByText("A página não trouxe o modo de preparo desta receita.")).toBeInTheDocument();
  });
});

describe("os ingredientes contra a despensa", () => {
  it("tem, falta comprar com a conta, a gosto, opcional e a linha não entendida", () => {
    detalhe();
    const ingredientes = secao("Ingredientes");
    expect(ingredientes).toHaveTextContent("Para 4 porções, contra a despensa da senhora.");
    const tem = within(ingredientes).getByRole("heading", { name: "A senhora tem" }).parentElement as HTMLElement;
    expect(within(tem).getByText("Carne moída (patinho)")).toBeInTheDocument();
    expect(within(tem).getByText("1,5 kg")).toBeInTheDocument();
    expect(within(tem).getAllByText("Sobra")).toHaveLength(5);

    const falta = within(ingredientes).getByRole("heading", { name: "Falta comprar" }).parentElement as HTMLElement;
    expect(within(falta).getByText("milho verde")).toBeInTheDocument();
    expect(within(falta).getByText("Precisa 1 lata. Compra: 1 lata, R$ 6,00")).toBeInTheDocument();
    expect(within(falta).getByText("Cabe no orçamento")).toBeInTheDocument();
    expect(within(falta).getByText(RECEITA.falta_comprar.itens[0]?.derivacao ?? "")).toBeInTheDocument();
    expect(within(falta).getByText("R$ 6,00")).toBeInTheDocument();
    expect(within(falta).getByText("Falta comprar milho verde, R$ 6,00; cabe nos R$ 80,00 que restam.")).toBeInTheDocument();

    expect(within(ingredientes).getByText("Sal (a senhora tem 1 kg).")).toBeInTheDocument();
    expect(within(ingredientes).getByText(/Salsinha \(cheiro-verde\): cheiro-verde a gosto \(opcional\)/)).toBeInTheDocument();
    // A linha que a leitura não entendeu aparece, sem a pergunta de quanto vai.
    expect(within(ingredientes).getByText("temperos de sua preferência")).toBeInTheDocument();
    expect(within(ingredientes).queryByRole("textbox", { name: "Quanto vai" })).not.toBeInTheDocument();
    expect(ingredientes.textContent).not.toMatch(/Não entendi quanto vai/);
  });

  it("o item parecido da despensa fica com o que ela tem, sem a pergunta \"é o seu?\"", () => {
    const parecido = {
      tipo: "ingrediente",
      assunto: "mesmo_ingrediente" as const,
      campo: "6 bifes de alcatra",
      texto: "A receita pede alcatra. É o seu miolo de alcatra?",
      motivo: "se for, a receita usa o que a senhora já tem; se não for, entra na lista de compras",
      compras: [],
      opcoes: [
        { rotulo: "É, sim", resposta: "sim" },
        { rotulo: "Não é", resposta: "nao" },
      ],
      entrada: null,
      passos: [],
    };
    const confirmar: IngredienteDaReceita = {
      nome: "alcatra",
      item_id: null,
      precisa: { texto: "500 g" },
      tem: null,
      sobra: null,
      situacao: "confirmar",
      compra: null,
      medida_de_referencia: null,
    };
    detalhe({ ...RECEITA, ingredientes: [...RECEITA.ingredientes, confirmar], perguntas: [...RECEITA.perguntas, parecido] });
    const ingredientes = secao("Ingredientes");
    expect(within(ingredientes).queryByRole("heading", { name: "Confirme comigo" })).not.toBeInTheDocument();
    const tem = within(ingredientes).getByRole("heading", { name: "A senhora tem" }).parentElement as HTMLElement;
    expect(within(tem).getByText("alcatra")).toBeInTheDocument();
    expect(within(tem).getByText("Parecido com um item da despensa da senhora.")).toBeInTheDocument();
    expect(screen.queryByText(parecido.texto)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "É, sim" })).not.toBeInTheDocument();
  });

  it("a parte que ela tem, o que não tem preço, o que passa do orçamento e a linha sem pergunta pronta", () => {
    const ing = (extras: Partial<IngredienteDaReceita>): IngredienteDaReceita => ({
      nome: "x",
      item_id: null,
      precisa: { texto: "1 un" },
      tem: null,
      sobra: null,
      situacao: "falta",
      compra: null,
      medida_de_referencia: null,
      ...extras,
    });
    const receita: Receita = {
      ...RECEITA,
      perguntas: [],
      rendimento_texto: null,
      ingredientes: [
        ing({ nome: "Farinha", situacao: "tem_parte", tem: { texto: "200 g" }, compra: { texto: "1 kg, R$ 5,00", cabe: false } }),
        ing({ nome: "Creme de leite", compra: { texto: "1 caixa", cabe: null } }),
        ing({ nome: "Açúcar", situacao: "a_gosto" }),
        ing({ nome: "Fermento" }),
      ],
      linhas_nao_entendidas: [{ texto: "um punhado de queijo", pergunta: "Quanto vai de queijo?" }],
      opcionais: [],
      falta_comprar: {
        itens: [{ nome: "Farinha", quantidade_texto: "1 kg", preco_conhecido: true, custo_compra: null, custo_no_prato: null, derivacao: "a conta da farinha" }],
        custo: null,
        cabe_no_orcamento: false,
        texto: "falta comprar farinha e creme de leite",
      },
    };
    detalhe(receita);
    const ingredientes = secao("Ingredientes");
    expect(ingredientes).toHaveTextContent("Contra a despensa da senhora.");
    expect(within(ingredientes).getByText("Tem só uma parte: o resto está em Falta comprar.")).toBeInTheDocument();
    expect(within(ingredientes).getAllByText("Farinha")).toHaveLength(2);
    expect(within(ingredientes).getByText("Passa do orçamento")).toBeInTheDocument();
    expect(within(ingredientes).getByText("a conta da farinha")).toBeInTheDocument();
    expect(within(ingredientes).getByText("Ainda sem preço")).toBeInTheDocument();
    // Sem preço, nada de pergunta: o corrigir discreto abre o campo, se ela quiser.
    expect(ingredientes.textContent).not.toMatch(/Quanto custa/);
    fireEvent.click(within(ingredientes).getByRole("button", { name: "corrigir o preço de Creme de leite" }));
    expect(within(ingredientes).getByRole("textbox", { name: "Preço" })).toBeInTheDocument();
    expect(within(ingredientes).getByText("Precisa 1 un")).toBeInTheDocument();
    expect(within(ingredientes).getByText("Açúcar.")).toBeInTheDocument();
    expect(within(ingredientes).getByText("Falta comprar farinha e creme de leite.")).toHaveClass("text-perigo");
    expect(within(ingredientes).queryByText("A compra toda")).not.toBeInTheDocument();
    expect(within(ingredientes).getByText("um punhado de queijo")).toBeInTheDocument();
    expect(within(ingredientes).queryByText("Quanto vai de queijo?")).not.toBeInTheDocument();
    expect(within(ingredientes).queryByRole("textbox", { name: "Quanto vai" })).not.toBeInTheDocument();
  });

  it("sem nada da despensa e sem nada a comprar, cada lado diz", () => {
    detalhe({
      ...RECEITA,
      ingredientes: [],
      linhas_nao_entendidas: [],
      opcionais: [],
      perguntas: [],
      falta_comprar: { itens: [], custo: { valor: 0, texto: "R$ 0,00" }, cabe_no_orcamento: true, texto: "nada a comprar" },
    });
    expect(screen.getByText("Nenhum ingrediente desta receita está na despensa.")).toBeInTheDocument();
    expect(screen.getByText("Nada a comprar. A senhora tem tudo o que a receita pede.")).toBeInTheDocument();
  });
});

describe("o custo por porção e o preço preliminar", () => {
  it("o custo pronto: o total, cada linha com a conta, o que vai a gosto e o rendimento", () => {
    detalhe(RECEITA, { tipo: "pronto", custo: CUSTO }, null);
    const custo = secao("Custo por porção");
    expect(within(custo).getByText("R$ 2,37")).toBeInTheDocument();
    for (const linha of CUSTO.linhas) expect(within(custo).getByText(linha.derivacao)).toBeInTheDocument();
    expect(within(custo).getByText("A gosto, com custo que quase não pesa: sal.")).toBeInTheDocument();
    expect(within(custo).getByText("A receita inteira rende 4 porções; os valores já são de uma.")).toBeInTheDocument();
    expect(within(custo).queryByText(/porque um dos pesos é estimado/)).not.toBeInTheDocument();
  });

  it("a faixa quando um peso é estimado, e a receita de uma porção só", () => {
    detalhe(RECEITA, { tipo: "pronto", custo: { ...CUSTO, e_faixa: true, rendimento_original: 1, itens_a_gosto: [] } }, null);
    const custo = secao("Custo por porção");
    expect(within(custo).getByText("Entre R$ 2,33 e R$ 2,41, porque um dos pesos é estimado.")).toBeInTheDocument();
    expect(within(custo).getByText("A receita inteira rende 1 porção; os valores já são de uma.")).toBeInTheDocument();
  });

  it("recusado, o porquê da API e Responder no chat com o rascunho dela; sem conseguir buscar, diz", () => {
    const { unmount, loja } = detalhe();
    const custo = secao("Custo por porção");
    expect(within(custo).getByText(/^Ainda não calculo o custo/)).toBeInTheDocument();
    fireEvent.click(within(custo).getByRole("button", { name: "Responder no chat" }));
    expect(loja.ler().caixa.texto).toBe("O que falta para eu saber o custo por porção de carne moída com arroz na panela de pressão?");
    expect(loja.ler().caixa.contexto).toEqual({ tela: "receitas", tipo: "receita", id: RECEITA.slug, rotulo: RECEITA.nome });
    unmount();
    detalhe(RECEITA, { tipo: "falhou", mensagem: "Não consegui buscar o custo agora." }, null);
    expect(within(secao("Custo por porção")).getByText("Não consegui buscar o custo agora.")).toBeInTheDocument();
    expect(within(secao("Custo por porção")).queryByRole("button", { name: "Responder no chat" })).not.toBeInTheDocument();
  });

  it("o preço preliminar: as linhas com a conta, o que falta saber, os três preços e de onde vêm os números", () => {
    detalhe();
    const preco = secao("Preço preliminar");
    expect(within(preco).getByText(ESTIMATIVA.texto)).toBeInTheDocument();
    expect(within(preco).getByText("Mão de obra sugerida")).toBeInTheDocument();
    expect(within(preco).getByText("falta saber")).toBeInTheDocument();
    for (const ponto of ESTIMATIVA.pontos) expect(within(preco).getByText(ponto.derivacao)).toBeInTheDocument();
    expect(within(preco).getByText("R$ 5,86")).toBeInTheDocument();
    // O valor da hora e a embalagem ficam embaixo da linha que usa cada um, com o botão para mudar.
    expect(paragrafoDe(within(preco).getByText("R$ 15,00 por hora"))).toBe(
      "Valor da hora da senhora: R$ 15,00 por hora, a senhora disse (hoje, 10:20)",
    );
    expect(within(preco).getByRole("button", { name: "Mudar o valor da hora" })).toBeInTheDocument();
    expect(paragrafoDe(within(preco).getByText("a senhora ainda não disse"))).toBe("Embalagem por porção: a senhora ainda não disse");
    expect(within(preco).getByRole("button", { name: "Dizer quanto paga na embalagem" })).toBeInTheDocument();
    // As outras premissas ficam em De onde vêm os números.
    fireEvent.click(within(preco).getByText("De onde vêm os números"));
    expect(paragrafoDe(within(preco).getByText("R$ 120,00 o botijão de 13 kg"))).toBe(
      "Preço do botijão de gás: R$ 120,00 o botijão de 13 kg, a senhora disse (hoje, 10:21)",
    );
    expect(within(preco).getByText(ESTIMATIVA.referencias_texto)).toBeInTheDocument();
  });

  it("o preço preliminar sem conta fechada: sem pontos, com o que falta confirmar e a fonte com endereço", () => {
    const incompleta: Estimativa = {
      ...ESTIMATIVA,
      custo_producao: null,
      piso: null,
      minimo_so_ingrediente: null,
      pontos: [],
      sinais: { ...ESTIMATIVA.sinais, falta_confirmar: ["O tempo no fogo que a receita não diz."] },
      premissas: [
        {
          nome: "valor_hora",
          rotulo: "Valor da hora",
          valor: null,
          origem: "padrao",
          fonte: "Decreto do salário mínimo",
          fonte_url: "https://www.planalto.gov.br/decreto",
          atualizado_texto: "conferido em 26/09/2026",
          editavel: true,
        },
        { nome: "embalagem", rotulo: "Embalagem", valor: null, origem: "falta", fonte: null, fonte_url: null, atualizado_texto: null, editavel: true },
      ],
    };
    detalhe(RECEITA, RECUSADO, incompleta);
    const preco = secao("Preço preliminar");
    expect(within(preco).queryByText("O mínimo para não perder")).not.toBeInTheDocument();
    expect(within(preco).getByText("O tempo no fogo que a receita não diz.")).toBeInTheDocument();
    expect(within(preco).getByRole("link", { name: /Decreto do salário mínimo/ })).toHaveAttribute("href", "https://www.planalto.gov.br/decreto");
    expect(within(preco).getAllByText("a senhora ainda não disse")).toHaveLength(2);
    expect(within(preco).getByRole("button", { name: "Dizer o valor da hora" })).toBeInTheDocument();
  });

  it("o que ela já disse sobre a receita", () => {
    detalhe();
    expect(within(secao("O que a senhora já me disse")).getByText(/A senhora disse que rende 4 porções\./)).toBeInTheDocument();
    expect(within(secao("O que a senhora já me disse")).getByText("(hoje, 14:30)")).toBeInTheDocument();
  });
});
