/**
 * As regras da interface que não dependem de uma tela só.
 *
 * 1. **Nenhum jargão chega a ela.** As peças da casca, as primitivas e os
 *    componentes de produto são montados com os dados dos contratos, e o texto
 *    (inclusive o que só o leitor de tela lê, e os atributos `aria-label`,
 *    `title`, `alt` e `placeholder`) não pode ter "motor", "portão", "APTO",
 *    "FALTA INFO", "BLOQUEADO", "veredito", "CMV", "food cost",
 *    "append-only" nem "make api". Os textos das fixtures de contrato que vão
 *    para a tela também são conferidos: é o que o backend promete mandar.
 * 2. **A interface não calcula dinheiro.** Todo valor em reais vem da API com
 *    o texto pronto. O código-fonte é varrido atrás de conta ou formatação com
 *    `.valor`: comparar para ordenar e filtrar pode (`compararDinheiro`),
 *    somar, subtrair, multiplicar, dividir ou formatar não.
 *
 * Uma tela nova entra em TELAS abaixo, para o texto dela ser conferido também.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { render } from "@testing-library/react";
import { Fragment, createElement, type ReactElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const caminhoAtual = vi.fn(() => "/despensa");
vi.mock("next/navigation", () => ({
  usePathname: () => caminhoAtual(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));

import { EsqueletoDaPagina } from "@/componentes/compartilhados/Esqueleto";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { Problema } from "@/componentes/compartilhados/Problema";
import { SeloVeredito } from "@/componentes/compartilhados/Chip";
import { Valor } from "@/componentes/compartilhados/Valor";
import { BotaoConversa, BotaoPerguntar, ProvedorDaConversa } from "@/componentes/conversa";
import { Composer } from "@/componentes/conversa/Composer";
import { EstadoInicial } from "@/componentes/conversa/EstadoInicial";
import { ListaDeConversas } from "@/componentes/conversa/ListaDeConversas";
import { MensagemDela, RespostaDaConsultoraNaTela, RespostaEmAndamento } from "@/componentes/conversa/Mensagem";
import { BarraInferior } from "@/componentes/globais/BarraInferior";
import { Cabecalho } from "@/componentes/globais/Cabecalho";
import { ErroDaPagina } from "@/componentes/globais/ErroDaPagina";
import { MenuMais } from "@/componentes/globais/MenuMais";
import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";
import { Provedores } from "@/componentes/globais/Provedores";
import { ConteudoDasPreferencias } from "@/componentes/globais/Preferencias";
import { Rodape } from "@/componentes/globais/Rodape";
import { CartaoIngrediente, PainelDoOrcamento } from "@/componentes/produto/despensa";
import { DetalheDoIngrediente } from "@/componentes/produto/despensa/DetalheDoIngrediente";
import { ItemDaCozinha } from "@/componentes/produto/cozinha";
import { LimitesDaRotina } from "@/componentes/produto/cozinha/LimitesDaRotina";
import { ProgressoDaCozinha } from "@/componentes/produto/cozinha/TelaDaCozinha";
import { TodaCozinha } from "@/componentes/produto/cozinha/TodaCozinha";
import { TelaDoCardapio } from "@/componentes/produto/cardapio";
import { TelaDoHistorico } from "@/componentes/produto/historico";
import { TelaInicial } from "@/componentes/produto/inicio";
import {
  CenariosDePreco,
  ConferenciaDoPrato,
  ConfirmarACozinhaNoPreco,
  CustoDaPorcao as CustoNaTelaDePreco,
  IngredientesDoPrato,
  TelaDePorPreco,
} from "@/componentes/produto/precificar";
import type { CustoNaTela } from "@/componentes/produto/receitas/CustoDaReceita";
import { DetalheDaReceita as TelaDoDetalhe } from "@/componentes/produto/receitas/DetalheDaReceita";
import { TelaDasReceitas } from "@/componentes/produto/receitas/TelaDasReceitas";
import type { CategoriaDeErro } from "@/lib/api/base";
import type { Conversa as ConversaDaApi } from "@/lib/api/conversa";
import { ESTADO_INICIAL, reduzirConversa } from "@/lib/conversa/estado";
import type { PaginaDeAtividades } from "@/lib/api/atividades";
import type { CardapioCompleto } from "@/lib/api/cardapio";
import type { DetalheDoItem, ListaDaDespensa, PendenciaDaDespensa } from "@/lib/api/despensa";
import type { PerfilDaCozinha } from "@/lib/api/perfil";
import type { Avaliacao, CMV, Estimativa, TabelaPrecos } from "@/lib/api/preco";
import type { VisaoGeral } from "@/lib/api/visao-geral";
import type { CustoDaPorcao, DetalheDaReceita, ListaDeReceitas } from "@/lib/api/receitas";
import type { Veredito } from "@/lib/formato";
import { PALAVRAS_PROIBIDAS, ROTULO_DO_VEREDITO, encontrarJargao } from "@/lib/formato";
import { lojaDeTeste } from "@/teste/conversa";
import { contrato, doRepositorio, doWebapp, eventosDoContrato } from "@/teste/fixturas";

afterEach(() => {
  vi.restoreAllMocks();
});

/* -------------------------------------------------------------------------- */
/* 1. Nenhum jargão na tela                                                    */
/* -------------------------------------------------------------------------- */

/** Todo texto que alguém pode ler ou ouvir: o conteúdo e os atributos de nome. */
function textoParaEla(raiz: HTMLElement): string {
  const partes = [raiz.textContent ?? ""];
  for (const elemento of raiz.querySelectorAll("[aria-label], [title], [alt], [placeholder]")) {
    for (const atributo of ["aria-label", "title", "alt", "placeholder"]) {
      const valor = elemento.getAttribute(atributo);
      if (valor) partes.push(valor);
    }
  }
  return partes.join("\n");
}

const DESPENSA = contrato<ListaDaDespensa>("despensa.json");
const PENDENCIA = DESPENSA.pendencias[0] as PendenciaDaDespensa;
const RECEITA = contrato<DetalheDaReceita>("receita.json");
const CUSTO = contrato<CMV>("custo.json");

/** Uma conferência de hoje (o /avaliar), montada com os textos dos contratos da receita e do custo. */
const AVALIACAO: Avaliacao = {
  prato: RECEITA.nome,
  veredito: "FALTA INFO",
  pode_precificar: false,
  resumo: RECEITA.resumo,
  impedimentos: [{ tipo: "equipamento", id: "forno", motivo: "a receita vai ao forno e a senhora disse que não tem" }],
  perguntas: RECEITA.perguntas,
  ingredientes_na_despensa: CUSTO.linhas.map((l) => ({
    ingrediente: l.ingrediente,
    quantidade: l.quantidade,
    custo: l.custo,
    derivacao: l.derivacao,
  })),
  falta_comprar: [{ ingrediente: "milho verde", quanto: "1 lata", custo: null }],
  a_gosto: RECEITA.ingredientes.filter((i) => i.situacao === "a_gosto").map((i) => i.nome),
  pode_aceitar: RECEITA.checklist.pode_aceitar,
  falta_para_aceitar: RECEITA.checklist.falta_para_aceitar,
  confirmar_a_cozinha: RECEITA.checklist.confirmar_a_cozinha,
};

/**
 * A conversa do contrato já carregada, e um turno do contrato no meio (antes
 * do fim): o que a tela da conversa mostra, montado sem esperar a rede.
 */
const CONVERSA_CARREGADA = reduzirConversa(ESTADO_INICIAL, {
  tipo: "carregou",
  conversa: contrato<ConversaDaApi>("conversa.json"),
  em: 0,
});
const TURNO_NO_MEIO = reduzirConversa(
  reduzirConversa(CONVERSA_CARREGADA, { tipo: "enviar", pedido: { texto: "Tenho forno.", id_cliente: "u-1" }, em: 0 }),
  { tipo: "enviado", idCliente: "u-1", turnoId: "t-88c1", em: 0 },
);
const EM_ANDAMENTO = reduzirConversa(TURNO_NO_MEIO, {
  tipo: "eventos",
  eventos: eventosDoContrato<Record<string, unknown>>("chat-eventos.jsonl").filter((evento) => evento.tipo !== "turno.concluido"),
  em: 0,
}).turno;

/** As peças da conversa dentro do provedor, com uma loja de teste (sem rede). */
function naConversa(loja: ReturnType<typeof lojaDeTeste>["loja"], ...filhos: ReactNode[]): ReactElement {
  return createElement(ProvedorDaConversa, { loja, children: createElement(Fragment, null, ...filhos) });
}

const VEREDITOS = Object.keys(ROTULO_DO_VEREDITO) as Veredito[];
const CATEGORIAS: CategoriaDeErro[] = ["rede", "tempo", "ausente", "dado", "regra", "uso"];

/** O que chegaria à tela se a API mandasse o pior texto possível. */
const MENSAGEM_TECNICA = "motor respondeu 503: [Errno 2] .estado/auditoria.jsonl (make api)";

const TELAS: [string, () => ReactElement][] = [
  [
    "a casca inteira",
    () =>
      createElement(
        Provedores,
        null,
        createElement(Cabecalho),
        createElement(BarraInferior),
        createElement(Rodape),
        createElement(BotaoConversa),
      ),
  ],
  [
    "as preferências abertas",
    () => naConversa(lojaDeTeste().loja, createElement(ConteudoDasPreferencias)),
  ],
  ["a folha Mais (fechada)", () => createElement(MenuMais)],
  ["os selos de viabilidade", () => createElement("div", null, ...VEREDITOS.map((v) => createElement(SeloVeredito, { key: v, veredito: v })))],
  [
    "os problemas, com a pior mensagem possível",
    () =>
      createElement(
        "div",
        null,
        ...CATEGORIAS.map((categoria) =>
          createElement(Problema, { key: categoria, categoria, mensagem: MENSAGEM_TECNICA, recarregar: true }),
        ),
      ),
  ],
  [
    "a página que falhou",
    () => createElement(ErroDaPagina, { error: new Error(MENSAGEM_TECNICA), retry: () => {} }),
  ],
  ["a página que não existe", () => createElement(NaoEncontrada)],
  [
    "a conversa: as mensagens do contrato e a resposta em andamento",
    () =>
      naConversa(
        lojaDeTeste().loja,
        ...CONVERSA_CARREGADA.itens.map((item) =>
          item.tipo === "senhora"
            ? createElement(MensagemDela, { key: item.chave, mensagem: item })
            : createElement(RespostaDaConsultoraNaTela, { key: item.chave, resposta: item }),
        ),
        EM_ANDAMENTO ? createElement(RespostaEmAndamento, { turno: EM_ANDAMENTO }) : null,
      ),
  ],
  [
    "o começo de conversa, a lista e a caixa com o rascunho da pendência",
    () => {
      const { loja } = lojaDeTeste();
      loja.preencher({ rascunho: PENDENCIA.rascunho_chat, contexto: { tela: "despensa", tipo: "pendencia", id: PENDENCIA.id, rotulo: PENDENCIA.ingrediente } });
      return naConversa(
        loja,
        createElement(EstadoInicial, { caminho: "/despensa" }),
        createElement(ListaDeConversas),
        createElement(Composer),
      );
    },
  ],
  [
    "o botão de perguntar",
    () => createElement(ProvedorDaConversa, null, createElement(BotaoPerguntar, { rascunho: RECEITA.rascunho_chat })),
  ],
  ["os esqueletos", () => createElement(EsqueletoDaPagina, { variante: "grade" })],
  ["um vazio", () => createElement(EstadoVazio, { titulo: "Nenhuma receita ainda", descricao: "Traga uma receita pelo endereço." })],
  ["um valor desconhecido", () => createElement(Valor, { dinheiro: null })],
  [
    "a tela inicial",
    () => naConversa(lojaDeTeste().loja, createElement(TelaInicial, { visao: contrato<VisaoGeral>("visao-geral.json") })),
  ],
  [
    "o cardápio, com o histórico das decisões",
    () =>
      naConversa(lojaDeTeste().loja, createElement(TelaDoCardapio, { cardapio: contrato<CardapioCompleto>("cardapio.json") })),
  ],
  [
    "o histórico, agrupado por dia",
    () =>
      createElement(TelaDoHistorico, {
        inicial: contrato<PaginaDeAtividades>("atividades.json"),
        chaveInicial: "",
      }),
  ],
  [
    "pôr preço: o formulário, a conferência, o custo e os caminhos",
    () =>
      naConversa(
        lojaDeTeste().loja,
        createElement(TelaDePorPreco),
        createElement(ConferenciaDoPrato, { avaliacao: AVALIACAO, aoResponder: () => {}, aoResponderNaReceita: () => {} }),
        createElement(IngredientesDoPrato, { avaliacao: AVALIACAO }),
        createElement(CustoNaTelaDePreco, { custo: CUSTO }),
        createElement(CenariosDePreco, {
          tabela: contrato<{ dados: TabelaPrecos }>("cartoes/cenarios.json").dados,
          aoEscolher: () => {},
        }),
        createElement(ConfirmarACozinhaNoPreco, { avaliacao: AVALIACAO, idDoMotivo: "falta", aoMudar: () => {} }),
      ),
  ],
  [
    "a despensa: os cartões, o orçamento e a página de um item",
    () =>
      createElement(
        ProvedorDaConversa,
        null,
        ...DESPENSA.itens.slice(0, 8).map((item) => createElement(CartaoIngrediente, { key: item.id, item })),
        createElement(PainelDoOrcamento, { orcamento: DESPENSA.orcamento, aoRegistrarCompra: () => {} }),
        createElement(DetalheDoIngrediente, {
          detalhe: contrato<DetalheDoItem>("despensa-item-comprado.json"),
          receitas: [],
          categorias: DESPENSA.categorias_para_escolher,
          orcamento: DESPENSA.orcamento,
        }),
      ),
  ],
  [
    "a cozinha: o progresso, os limites e cada item, com o seletor",
    () => {
      const perfil = contrato<PerfilDaCozinha>("perfil.json");
      return createElement(
        "div",
        null,
        createElement(TodaCozinha, { bloco: perfil.toda_cozinha }),
        createElement(ProgressoDaCozinha, { perfil }),
        createElement(LimitesDaRotina, { restricoes: perfil.restricoes }),
        createElement(
          "ul",
          null,
          ...perfil.equipamentos.map((item) => createElement(ItemDaCozinha, { key: item.id, item, tipo: "equipamentos" })),
          ...perfil.tecnicas.map((item) => createElement(ItemDaCozinha, { key: item.id, item, tipo: "tecnicas" })),
        ),
      );
    },
  ],
  [
    "a grade de receitas, com a descoberta e as abas",
    () =>
      naConversa(
        lojaDeTeste().loja,
        createElement(TelaDasReceitas, { inicial: contrato<ListaDeReceitas>("receitas.json"), chaveInicial: "?aba=pode_fazer" }),
      ),
  ],
  [
    "o detalhe de uma receita, com o custo recusado e o preço preliminar",
    () =>
      naConversa(
        lojaDeTeste().loja,
        createElement(TelaDoDetalhe, {
          receita: RECEITA,
          custo: { tipo: "recusado", motivo: "Ainda não calculo o custo de carne moída com arroz: antes preciso saber uma coisa." } satisfies CustoNaTela,
          estimativa: contrato<Estimativa>("estimativa.json"),
        }),
      ),
  ],
  [
    "o detalhe de uma receita, com o custo pronto",
    () =>
      naConversa(
        lojaDeTeste().loja,
        createElement(TelaDoDetalhe, {
          receita: RECEITA,
          custo: { tipo: "pronto", custo: contrato<CustoDaPorcao>("custo.json") } satisfies CustoNaTela,
          estimativa: null,
        }),
      ),
  ],
];

describe("nenhum jargão chega a ela", () => {
  it.each(TELAS)("%s", (_nome, montar) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(montar());
    expect(encontrarJargao(textoParaEla(container))).toEqual([]);
  });

  it("a conferência de verdade: o texto que mais acumulava jargão", () => {
    // Um exemplo que falharia: se alguém voltar a escrever o valor técnico na
    // tela, este teste mostra qual palavra entrou.
    const { container } = render(createElement("p", null, "FALTA INFO"));
    expect(encontrarJargao(textoParaEla(container))).toEqual(["FALTA INFO"]);
  });

  it("os atributos também contam (aria-label, title, alt, placeholder)", () => {
    const { container } = render(createElement("input", { "aria-label": "custo pelo CMV", placeholder: "o motor" }));
    expect(encontrarJargao(textoParaEla(container))).toEqual(["motor", "CMV"]);
  });
});

/** Campos das fixtures que a tela mostra (o resto é valor técnico: id, rota, veredito…). */
const CAMPOS_DE_TEXTO = new Set([
  "texto",
  "rotulo",
  "rotulo_feito",
  "pergunta",
  "resumo",
  "descricao",
  "motivo",
  "motivo_texto",
  "derivacao",
  "titulo",
  "previa",
  "mensagem",
  "credito",
  "texto_humano",
  "fonte",
  "nome",
  "prato",
  "delta",
  "rascunho_chat",
]);

function textosDaFixture(valor: unknown, caminho = "$"): [string, string][] {
  if (Array.isArray(valor)) return valor.flatMap((item, indice) => textosDaFixture(item, `${caminho}[${indice}]`));
  if (valor === null || typeof valor !== "object") return [];
  return Object.entries(valor).flatMap(([chave, dentro]): [string, string][] => {
    const aqui = `${caminho}.${chave}`;
    const ehTexto = CAMPOS_DE_TEXTO.has(chave) || chave.endsWith("_texto") || chave.endsWith("_rotulo");
    if (typeof dentro === "string") return ehTexto ? [[aqui, dentro]] : [];
    return textosDaFixture(dentro, aqui);
  });
}

const FIXTURAS_JSON = [
  "atividades.json",
  "avaliacao-escrita.json",
  "cardapio.json",
  "conhecimento.json",
  "conversa-turno.json",
  "conversa.json",
  "conversas.json",
  "custo.json",
  "descoberta-inicio.json",
  "despensa-escrita.json",
  "despensa-item.json",
  "despensa.json",
  "estimativa.json",
  "exportacao.json",
  "notas-escrita.json",
  "parametro-escrita.json",
  "perfil-escrita.json",
  "perfil-supostos.json",
  "perfil.json",
  "receita.json",
  "receitas.json",
  "visao-geral.json",
  ...readdirSync(doRepositorio("contratos", "web", "cartoes")).map((nome) => `cartoes/${nome}`),
];

describe("os textos que o contrato promete mandar para a tela", () => {
  it.each(FIXTURAS_JSON)("%s", (arquivo) => {
    const achados = textosDaFixture(contrato(arquivo)).filter(([, texto]) => encontrarJargao(texto).length > 0);
    expect(achados).toEqual([]);
  });

  it.each(["chat-eventos.jsonl", "receitas-descoberta.jsonl"])("%s", (arquivo) => {
    const achados = textosDaFixture(eventosDoContrato(arquivo)).filter(([, texto]) => encontrarJargao(texto).length > 0);
    expect(achados).toEqual([]);
  });

  it("o valor técnico existe nas fixtures, e nunca é o texto mostrado", () => {
    expect(encontrarJargao(RECEITA.veredito)).not.toEqual([]);
    expect(encontrarJargao(RECEITA.veredito_rotulo)).toEqual([]);
    expect(encontrarJargao(RECEITA.veredito_da_cozinha.rotulo)).toEqual([]);
    for (const item of contrato<ListaDeReceitas>("receitas.json").itens) {
      expect(encontrarJargao(item.selo.texto)).toEqual([]);
    }
  });

  it("a varredura lê só os campos de texto", () => {
    expect(
      textosDaFixture({ veredito: "APTO", rotulo: "Dá pra fazer", itens: [{ nome: "Sal", id: "sal" }], n: 3 }),
    ).toEqual([
      ["$.rotulo", "Dá pra fazer"],
      ["$.itens[0].nome", "Sal"],
    ]);
  });
});

/* -------------------------------------------------------------------------- */
/* 2. A interface não calcula dinheiro                                         */
/* -------------------------------------------------------------------------- */

const RAIZ = doWebapp("src");

function arquivosDoCodigo(pasta: string): string[] {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = join(pasta, nome);
    if (statSync(caminho).isDirectory()) return nome === "teste" ? [] : arquivosDoCodigo(caminho);
    if (!/\.(ts|tsx)$/.test(nome) || /\.test\.(ts|tsx)$/.test(nome) || nome.endsWith(".d.ts")) return [];
    return [caminho];
  });
}

/** O código sem os comentários, com a numeração de linhas preservada. */
function semComentarios(codigo: string): string {
  return codigo
    .replace(/\/\*[\s\S]*?\*\//g, (bloco) => bloco.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`])\/\/.*$/gm, (_tudo, antes: string) => antes);
}

const CONTA_COM_VALOR: readonly RegExp[] = [
  // `x.valor * 6`, `x.valor + 1`, `a.valor - b.valor`
  /\.valor\b\s*[-+*/%](?![=+\->])/,
  // `6 * x.valor`, `1 - x.valor`, `(a / b.valor)`
  /[-+*/%]\s*\(*\s*[\w$.?!\]]+\.valor\b/,
  // `x.valor.toFixed(2)`, `x.valor.toLocaleString()`: formatar é dar o texto sem a API
  /\.valor\b\)?\s*\.(?:toFixed|toLocaleString|toPrecision)\s*\(/,
  // `Math.round(x.valor)`, `Math.ceil(x.valor * 100)`
  /Math\.\w+\(\s*[^)]*\.valor\b/,
];

type Achado = { arquivo: string; linha: number; trecho: string };

function contasCom(codigo: string, arquivo: string): Achado[] {
  return semComentarios(codigo)
    .split("\n")
    .flatMap((linha, indice): Achado[] =>
      CONTA_COM_VALOR.some((padrao) => padrao.test(linha))
        ? [{ arquivo, linha: indice + 1, trecho: linha.trim() }]
        : [],
    );
}

/**
 * Onde ainda há conta, por arquivo, com quantas linhas. É uma catraca: a
 * contagem tem que bater exatamente, então consertar sem tirar daqui também
 * reprova. Vazia desde que os limites do controle de preço passaram a vir da
 * API (`controle{min,max,passo}`).
 */
const CONTAS_CONHECIDAS: Readonly<Record<string, number>> = {};

describe("a interface não calcula dinheiro", () => {
  const achados = arquivosDoCodigo(RAIZ).flatMap((caminho) =>
    contasCom(readFileSync(caminho, "utf-8"), relative(RAIZ, caminho).replaceAll("\\", "/")),
  );

  it("nenhuma conta com `.valor` fora das dívidas conhecidas", () => {
    const porArquivo: Record<string, number> = {};
    for (const achado of achados) porArquivo[achado.arquivo] = (porArquivo[achado.arquivo] ?? 0) + 1;
    expect(porArquivo, JSON.stringify(achados, null, 2)).toEqual(CONTAS_CONHECIDAS);
  });

  it.each([
    ["const maximo = Math.ceil(tabela.cmv.valor * 6);", true],
    ["const minimo = tabela.preco_minimo.valor * 100;", true],
    ["return a.valor - b.valor;", true],
    ["const total = 1 + item.pago.valor;", true],
    ["<span>{dinheiro.valor.toFixed(2)}</span>", true],
    ["if (a.valor < b.valor) return -1;", false],
    ["const negativo = typeof dinheiro?.valor === 'number' && dinheiro.valor < 0;", false],
    ["await motor.precos(composicao.prato, composicao.total.valor);", false],
    ["// a.valor * 2, num comentário, não conta", false],
    ["lista.sort((a, b) => compararDinheiro(a.custo, b.custo));", false],
    ["const valor = x.valor;", false],
  ])("%s → conta? %s", (linha, esperado) => {
    expect(contasCom(linha, "exemplo.ts").length > 0).toBe(esperado);
  });

  it("comentário de bloco também não conta, e a linha continua certa", () => {
    const codigo = "/*\n x.valor * 2\n*/\nconst y = z.valor * 3;";
    expect(contasCom(codigo, "exemplo.ts")).toEqual([{ arquivo: "exemplo.ts", linha: 4, trecho: "const y = z.valor * 3;" }]);
  });

  it("a lista de palavras proibidas é a do plano, e a varredura enxerga código de verdade", () => {
    expect(PALAVRAS_PROIBIDAS).toHaveLength(10);
    expect(arquivosDoCodigo(RAIZ).length).toBeGreaterThan(40);
  });
});
