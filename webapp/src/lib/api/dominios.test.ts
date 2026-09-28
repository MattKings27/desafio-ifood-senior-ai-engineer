/**
 * Cada função de cada domínio chega à rota certa, com o método e o corpo que a
 * API espera; e cada tipo do contrato v1 tem exatamente as chaves das fixtures
 * de `contratos/web/`. Se o backend mudar uma forma sem mudar a fixture (ou o
 * contrário), um dos lados fica vermelho.
 */

import { readdirSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TIPOS_DE_CARTAO } from "@/lib/conversa/cartoes";
import { acaoValida } from "@/lib/conversa/sugestoes";
import { contrato, doRepositorio, eventosDoContrato } from "@/teste/fixturas";

import { atividades } from "./atividades";
import type { Atividade, GrupoDeAtividades, PaginaDeAtividades } from "./atividades";
import { cardapio, cardapioDeHoje } from "./cardapio";
import type { CardapioCompleto, DecisaoNoHistorico, PratoDoCardapio, PratoRecusado, ResumoDoCardapio } from "./cardapio";
import { conversa } from "./conversa";
import type {
  CartaoDaConversa,
  Conversa,
  ListaDeConversas,
  MensagemDaConversa,
  ResumoDaConversa,
} from "./conversa";
import { dados } from "./dados";
import type { ExportacaoDosDados, RestauracaoDosDados } from "./dados";
import { despensa, despensaDeHoje } from "./despensa";
import type {
  CompraDoOrcamento,
  DetalheDoItem,
  EventoDaDespensa,
  ItemDaDespensa,
  ListaDaDespensa,
  OrcamentoDaDespensa,
  PaginaDeEventos,
  PendenciaDaDespensa,
  ReceitasAfetadas,
  RespostaDaEscrita,
  RespostaDoEstorno,
  RespostaInline,
} from "./despensa";
import type { RespostaDoConhecimento, TrechoDoConhecimento } from "./conhecimento";
import { api } from "./index";
import { perfil, perfilDeHoje } from "./perfil";
import type {
  ConfirmacaoDaCozinha,
  ContagensDaCozinha,
  ImpactoDaMudanca,
  ItemDaCozinha,
  ItemDeTodaCozinha,
  PedidoDeConfirmacao,
  PerfilDaCozinha,
  RespostaDaCozinha,
  Restricao,
  RestricaoGravada,
  TodaCozinha,
} from "./perfil";
import { preco, precoDeHoje } from "./preco";
import type { DinheiroComConta, Estimativa, LinhaDaEstimativa, Premissa, PontoDaEstimativa } from "./preco";
import { receitas, receitasDeHoje } from "./receitas";
import type {
  AvaliacaoDaReceita,
  ChecklistDeProducao,
  ConfirmarACozinha,
  CustoDaPorcao,
  DetalheDaReceita,
  EntradaDaPergunta,
  EsperandoResposta,
  SemPrecoNaInternet,
  EstadoDaDescoberta,
  FonteDaReceita,
  GrupoDoChecklist,
  IngredienteDaReceita,
  IngredienteQueFalta,
  InicioDaDescoberta,
  ItemAConfirmar,
  ItemDaGrade,
  ItemDoChecklist,
  FonteDoPreco,
  PrecoDeReferencia,
  RendimentoDaReceita,
  LeiturasDoPeso,
  LimiteDoPasso,
  ListaDeReceitas,
  Passo,
  PerguntaDaReceita,
  PerguntaQueLibera,
  Requisito,
  RequisitoDaReceita,
  RespostaDaAvaliacao,
  RespostaDasNotas,
  RespostaSobreAReceita,
  TemposDaReceita,
  VereditoDaCozinha,
} from "./receitas";
import { visaoGeral } from "./visao-geral";
import type { ItemParado, PerguntaDaCozinha, VisaoGeral } from "./visao-geral";

const envelope = (dados: unknown) => ({ ok: true, dados, erro: null, categoria: null, pergunta: null });

function resposta(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

let rede: ReturnType<typeof vi.fn>;

function ultima(): { url: string; metodo: string; corpo: unknown } {
  const feita = rede.mock.calls.at(-1) as [string, RequestInit] | undefined;
  if (!feita) throw new Error("nenhuma chamada");
  const [url, init] = feita;
  return {
    url,
    metodo: init.method ?? "GET",
    corpo: init.body === undefined ? undefined : JSON.parse(String(init.body)),
  };
}

beforeEach(() => {
  rede = vi.fn(async () => resposta(envelope({})));
  vi.stubGlobal("fetch", rede);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

type Caso = [string, () => Promise<unknown>, string, string, unknown?];

const NOVO_ITEM = {
  nome: "Creme de leite",
  estoque: 2,
  unidade: "un 200g",
  quantidade_comprada: 2,
  preco_pago: 9,
  origem: "orcamento" as const,
  id_cliente: "c1f0e2d3",
};

const CASOS: Caso[] = [
  // despensa
  ["despensa.listar", () => despensa.listar(), "GET", "/motor/despensa"],
  [
    "despensa.listar com filtros",
    () => despensa.listar({ q: "choco", categoria: "confeitaria", ordem: "nome" }),
    "GET",
    "/motor/despensa?q=choco&categoria=confeitaria&ordem=nome",
  ],
  ["despensa.item", () => despensa.item("peito de frango"), "GET", "/motor/despensa/itens/peito%20de%20frango"],
  ["despensa.adicionar", () => despensa.adicionar(NOVO_ITEM), "POST", "/motor/despensa/itens", NOVO_ITEM],
  [
    "despensa.corrigir",
    () => despensa.corrigir("cobertura-de-chocolate", { conteudo_da_embalagem: "1 kg" }),
    "PATCH",
    "/motor/despensa/itens/cobertura-de-chocolate",
    { conteudo_da_embalagem: "1 kg" },
  ],
  ["despensa.remover", () => despensa.remover("item-4f7a1c2e"), "DELETE", "/motor/despensa/itens/item-4f7a1c2e"],
  [
    "despensa.remover com a chave",
    () => despensa.remover("item-4f7a1c2e", "k-1"),
    "DELETE",
    "/motor/despensa/itens/item-4f7a1c2e?id_cliente=k-1",
  ],
  ["despensa.eventos", () => despensa.eventos(), "GET", "/motor/despensa/eventos"],
  [
    "despensa.eventos com cursor",
    () => despensa.eventos({ limite: 3, cursor: "ev-0006" }),
    "GET",
    "/motor/despensa/eventos?limite=3&cursor=ev-0006",
  ],
  ["despensa.desfazerEvento", () => despensa.desfazerEvento("ev-1"), "POST", "/motor/despensa/eventos/ev-1/desfazer"],
  [
    "despensa.desfazerEvento com a chave",
    () => despensa.desfazerEvento("ev-1", "k-2"),
    "POST",
    "/motor/despensa/eventos/ev-1/desfazer",
    { id_cliente: "k-2" },
  ],
  ["despensa.estornarCompra", () => despensa.estornarCompra(12), "POST", "/motor/compras/12/estorno"],
  [
    "despensa.estornarCompra com a chave",
    () => despensa.estornarCompra(12, "k-3"),
    "POST",
    "/motor/compras/12/estorno",
    { id_cliente: "k-3" },
  ],
  ["despensaDeHoje.orcamento", () => despensaDeHoje.orcamento(), "GET", "/motor/orcamento"],
  [
    "despensaDeHoje.registrarCompra",
    () => despensaDeHoje.registrarCompra({ prato: "Arroz", ingrediente: "milho", quantidade: 1, valor: 6 }),
    "POST",
    "/motor/compra",
    { prato: "Arroz", ingrediente: "milho", quantidade: 1, valor: 6, unidade: "" },
  ],
  // receitas
  ["receitas.listar", () => receitas.listar(), "GET", "/motor/receitas"],
  [
    "receitas.listar com filtros",
    () =>
      receitas.listar({
        aba: "ranking",
        q: "frango",
        usa: "peito-de-frango",
        tempo_max: 40,
        so_com_o_que_tenho: true,
        nota_min: 70,
        ordem: "pontuacao",
      }),
    "GET",
    "/motor/receitas?aba=ranking&q=frango&usa=peito-de-frango&tempo_max=40&so_com_o_que_tenho=true&nota_min=70&ordem=pontuacao",
  ],
  ["receitas.listar na aba de quem falta resposta", () => receitas.listar({ aba: "falta_resposta" }), "GET", "/motor/receitas?aba=falta_resposta"],
  ["receitas.detalhe", () => receitas.detalhe("arroz-com-frango"), "GET", "/motor/receitas/arroz-com-frango"],
  [
    "receitas.trazer",
    () => receitas.trazer("https://www.tudogostoso.com.br/receita/1"),
    "POST",
    "/motor/receitas",
    { url: "https://www.tudogostoso.com.br/receita/1" },
  ],
  [
    "receitas.avaliar",
    () => receitas.avaliar("s1", { gosta: true, estrelas: { sabor: 5, apelo: null } }),
    "PUT",
    "/motor/receitas/s1/avaliacao",
    { gosta: true, estrelas: { sabor: 5, apelo: null } },
  ],
  ["receitas.salvarNotas", () => receitas.salvarNotas("s1", "Testar"), "PUT", "/motor/receitas/s1/notas", { texto: "Testar" }],
  [
    "receitas.responder",
    () => receitas.responder("s1", { campo: "rendimento_porcoes", resposta: "6" }),
    "POST",
    "/motor/receitas/s1/resposta",
    { campo: "rendimento_porcoes", resposta: "6" },
  ],
  ["receitas.custo", () => receitas.custo("s1"), "GET", "/motor/receitas/s1/custo"],
  ["receitas.descobrir", () => receitas.descobrir(), "POST", "/motor/receitas/descoberta"],
  ["receitasDeHoje.receita", () => receitasDeHoje.receita("Arroz com frango"), "GET", "/motor/receita?prato=Arroz%20com%20frango"],
  [
    "receitasDeHoje.receitaDaWeb",
    () => receitasDeHoje.receitaDaWeb("https://x.com.br/r", "X"),
    "POST",
    "/motor/receita-da-web",
    { url: "https://x.com.br/r", fonte: "X" },
  ],
  // perfil
  ["perfil.ler", () => perfil.ler(), "GET", "/motor/perfil"],
  [
    "perfil.definirPosse",
    () => perfil.definirPosse("equipamentos", "forno", "nao_sei"),
    "PUT",
    "/motor/perfil/equipamentos/forno",
    { estado: "nao_sei" },
  ],
  [
    "perfil.definirRestricao",
    () => perfil.definirRestricao("bocas_fogao", 4),
    "PUT",
    "/motor/perfil/restricoes/bocas_fogao",
    { valor: 4 },
  ],
  ["perfil.confirmarSupostos", () => perfil.confirmarSupostos(), "POST", "/motor/perfil/supostos/confirmar", {}],
  [
    "perfil.confirmarSupostos de uma receita",
    () => perfil.confirmarSupostos({ receita: "arroz-com-frango" }),
    "POST",
    "/motor/perfil/supostos/confirmar",
    { receita: "arroz-com-frango" },
  ],
  [
    "perfil.confirmarSupostos dos itens",
    () => perfil.confirmarSupostos({ itens: [{ tipo: "equipamento", id: "fogao" }] }),
    "POST",
    "/motor/perfil/supostos/confirmar",
    { itens: [{ tipo: "equipamento", id: "fogao" }] },
  ],
  ["perfilDeHoje.perfil", () => perfilDeHoje.perfil(), "GET", "/motor/perfil"],
  [
    "perfilDeHoje.responder",
    () => perfilDeHoje.responder("equipamento", "forno", "sim"),
    "POST",
    "/motor/resposta",
    { tipo: "equipamento", campo: "forno", resposta: "sim" },
  ],
  // preço
  ["preco.estimativa", () => preco.estimativa("arroz-com-frango"), "GET", "/motor/receitas/arroz-com-frango/estimativa"],
  ["preco.parametro", () => preco.parametro("valor_hora"), "GET", "/motor/parametros/valor_hora"],
  ["preco.definirParametro", () => preco.definirParametro("valor_hora", 15), "PUT", "/motor/parametros/valor_hora", { valor: 15 }],
  ["precoDeHoje.avaliar", () => precoDeHoje.avaliar({ nome: "Bolo", ingredientes: [] }), "POST", "/motor/avaliar", { nome: "Bolo", ingredientes: [] }],
  ["precoDeHoje.cmv", () => precoDeHoje.cmv({ nome: "Bolo", ingredientes: [] }), "POST", "/motor/cmv", { nome: "Bolo", ingredientes: [] }],
  [
    "precoDeHoje.precos com o custo a conferir",
    () => precoDeHoje.precos("Bolo de Cenoura & Chocolate", 12.5),
    "GET",
    "/motor/precos?prato=Bolo%20de%20Cenoura%20%26%20Chocolate&cmv=12.5",
  ],
  ["precoDeHoje.precos", () => precoDeHoje.precos("Arroz"), "GET", "/motor/precos?prato=Arroz"],
  ["precoDeHoje.precoEm", () => precoDeHoje.precoEm("Arroz", 20), "GET", "/motor/preco-em?prato=Arroz&preco=20"],
  ["precoDeHoje.precosDeMercado", () => precoDeHoje.precosDeMercado(), "GET", "/motor/precos-mercado"],
  [
    "precoDeHoje.registrarPreco",
    () => precoDeHoje.registrarPreco("milho", 6, { quantidade: 1, unidade: "lata" }),
    "POST",
    "/motor/preco-mercado",
    { ingrediente: "milho", valor: 6, quantidade: 1, unidade: "lata", origem: "informado_por_ela" },
  ],
  [
    "precoDeHoje.registrarPreco sem opções",
    () => precoDeHoje.registrarPreco("milho", 6),
    "POST",
    "/motor/preco-mercado",
    { ingrediente: "milho", valor: 6, unidade: "", origem: "informado_por_ela" },
  ],
  // cardápio
  ["cardapio.ler", () => cardapio.ler(), "GET", "/motor/cardapio"],
  [
    "cardapio.decidir",
    () => cardapio.decidir({ prato: "Arroz", decisao: "recusado", id_cliente: "u1" }),
    "POST",
    "/motor/decisao",
    { prato: "Arroz", decisao: "recusado", id_cliente: "u1", motivo: "" },
  ],
  ["cardapio.desfazer", () => cardapio.desfazer("Arroz com frango"), "POST", "/motor/cardapio/Arroz%20com%20frango/desfazer"],
  ["cardapio.desfazer com a chave", () => cardapio.desfazer("Arroz", "u2"), "POST", "/motor/cardapio/Arroz/desfazer"],
  ["cardapio.salvarNotas", () => cardapio.salvarNotas("arroz-com-frango", "Com farofa"), "PUT", "/motor/cardapio/arroz-com-frango/notas", { texto: "Com farofa" }],
  [
    "cardapioDeHoje.registrarGosto sem impedimento manda texto vazio",
    () => cardapioDeHoje.registrarGosto("Feijoada", true),
    "POST",
    "/motor/gosto",
    { prato: "Feijoada", gosta: true, impedimento: "" },
  ],
  // atividades
  ["atividades.listar", () => atividades.listar(), "GET", "/motor/atividades"],
  [
    "atividades.listar com filtros",
    () => atividades.listar({ cursor: "decisao-3", quem: "consultora", categoria: "receitas", dia: "2026-09-26", q: "alcaparras" }),
    "GET",
    "/motor/atividades?cursor=decisao-3&quem=consultora&categoria=receitas&dia=2026-09-26&q=alcaparras",
  ],
  // visão geral
  ["visaoGeral.ler", () => visaoGeral.ler(), "GET", "/motor/visao-geral"],
  // conversa
  ["conversa.listar", () => conversa.listar(), "GET", "/motor/conversas"],
  ["conversa.criar", () => conversa.criar(), "POST", "/motor/conversas", {}],
  ["conversa.criar com título", () => conversa.criar("Arroz"), "POST", "/motor/conversas", { titulo: "Arroz" }],
  ["conversa.ler", () => conversa.ler("cv-7f3a"), "GET", "/motor/conversas/cv-7f3a"],
  ["conversa.renomear", () => conversa.renomear("cv-7f3a", "Bolo"), "PATCH", "/motor/conversas/cv-7f3a", { titulo: "Bolo" }],
  ["conversa.apagar", () => conversa.apagar("cv-7f3a"), "DELETE", "/motor/conversas/cv-7f3a"],
  ["conversa.estadoDoTurno", () => conversa.estadoDoTurno("cv-7f3a", "t-88c1"), "GET", "/motor/conversas/cv-7f3a/turnos/t-88c1"],
  ["conversa.parar", () => conversa.parar("cv-7f3a", "t-88c1"), "POST", "/motor/conversas/cv-7f3a/turnos/t-88c1/parar"],
];

describe("cada função chega à rota certa", () => {
  it.each(CASOS)("%s", async (_nome, chamar, metodo, url, corpo) => {
    await chamar();
    const feita = ultima();
    expect(feita.url).toBe(url);
    expect(feita.metodo).toBe(metodo);
    expect(feita.corpo).toEqual(corpo);
  });

  it("a planilha em texto vem como texto", async () => {
    rede.mockResolvedValue(new Response("DESPENSA", { status: 200 }));
    await expect(despensa.planilhaTxt()).resolves.toBe("DESPENSA");
    expect(ultima().url).toBe("/motor/despensa/planilha.txt");
  });

  it("os fluxos de eventos passam pelo proxy", () => {
    expect(receitas.urlDaDescoberta()).toBe("/motor/receitas/descoberta/eventos");
    expect(receitas.urlDaDescoberta(3)).toBe("/motor/receitas/descoberta/eventos?desde=3");
    const { eventos } = contrato<{ eventos: string }>("descoberta-inicio.json");
    expect(receitas.urlDaRodada(eventos)).toBe("/motor/receitas/descoberta/eventos?execucao=dx-0007");
    expect(receitas.urlDaRodada(eventos, 4)).toBe("/motor/receitas/descoberta/eventos?execucao=dx-0007&desde=4");
    expect(receitas.urlDaRodada("/api/receitas/descoberta/eventos")).toBe("/motor/receitas/descoberta/eventos");
    // Um endereço que não é o fluxo da descoberta nunca é aberto: vira o fluxo geral.
    expect(receitas.urlDaRodada("https://outro.site/x?y=1", 2)).toBe("/motor/receitas/descoberta/eventos?desde=2");
    expect(conversa.urlDosEventos("cv-7f3a", "t-88c1")).toBe("/motor/conversas/cv-7f3a/turnos/t-88c1/eventos");
    expect(conversa.urlDosEventos("cv-7f3a", "t-88c1", 0)).toBe(
      "/motor/conversas/cv-7f3a/turnos/t-88c1/eventos?desde=0",
    );
  });

  it("o objeto `api` junta os domínios", () => {
    expect(Object.keys(api).sort()).toEqual(
      ["atividades", "cardapio", "conversa", "dados", "despensa", "perfil", "preco", "receitas", "visaoGeral"].sort(),
    );
    expect(api.despensa).toBe(despensa);
  });

  it("os dados dela saem por um link para o arquivo, pelo proxy", () => {
    expect(dados).toMatchObject({ urlDaExportacao: "/motor/exportacao", nomeDoArquivo: "sabor-da-maria-dados.json" });
  });

  it("restaurar os dados manda a confirmação e a chave do clique, no corpo e no cabeçalho", async () => {
    await dados.restaurar("clique-1");
    const [url, init] = rede.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toBe("/motor/dados/restaurar");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ confirmar: true, id_cliente: "clique-1" });
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe("clique-1");
  });
});

describe("trazer uma receita pelo endereço", () => {
  it("201 é receita nova; 200 é uma que o servidor já conhecia", async () => {
    const detalhe = contrato<DetalheDaReceita>("receita.json");
    rede.mockResolvedValue(resposta(envelope(detalhe), 201));
    await expect(receitas.trazer("https://www.tudogostoso.com.br/receita/1")).resolves.toEqual({ receita: detalhe, nova: true });
    rede.mockResolvedValue(resposta(envelope(detalhe), 200));
    await expect(receitas.trazer("https://www.tudogostoso.com.br/receita/1")).resolves.toEqual({ receita: detalhe, nova: false });
  });

  it("a página sem receita estruturada é recusada com a pergunta dela", async () => {
    rede.mockResolvedValue(
      resposta({
        ok: false,
        dados: null,
        erro: "a página abriu, mas não traz a receita em formato estruturado",
        categoria: "dado",
        pergunta: "Esse site não publica a receita de um jeito que eu leia. Tenta outro?",
      }),
    );
    await expect(receitas.trazer("https://exemplo.com.br/x")).rejects.toMatchObject({
      categoria: "dado",
      pergunta: "Esse site não publica a receita de um jeito que eu leia. Tenta outro?",
    });
  });
});

describe("a ação `avaliar` de um card segue o contrato", () => {
  it("leva o id da receita e só as estrelas de 1 a 5 (ou null, que apaga)", () => {
    expect(
      acaoValida({
        tipo: "avaliar",
        receita_id: "arroz-com-frango",
        gosta: true,
        estrelas: { sabor: 5, apelo: null, tempo: 9, entrega: "4", facilidade: 2.5, cor: 3 },
        notas: "Com farofa.",
        extra: "some",
      }),
    ).toEqual({
      tipo: "avaliar",
      receita_id: "arroz-com-frango",
      gosta: true,
      notas: "Com farofa.",
      estrelas: { sabor: 5, apelo: null },
    });
    expect(acaoValida({ tipo: "avaliar", receita_id: "x", gosta: null })).toEqual({
      tipo: "avaliar",
      receita_id: "x",
      gosta: null,
    });
    expect(acaoValida({ tipo: "avaliar", receita_id: "x", gosta: "sim", notas: 3 })).toEqual({
      tipo: "avaliar",
      receita_id: "x",
    });
  });

  it("sem o id da receita não há ação", () => {
    expect(acaoValida({ tipo: "avaliar", receita: "arroz-com-frango", sabor: 5 })).toBeUndefined();
  });
});

describe("enviar um turno da conversa", () => {
  const pedido = contrato<{ pedido: Parameters<typeof conversa.enviarTurno>[1] }>("conversa-turno.json").pedido;

  it("202 começa um turno novo", async () => {
    rede.mockResolvedValue(resposta(envelope({ turno_id: "t-88c1" }), 202));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).resolves.toEqual({ turno_id: "t-88c1", anexado: false });
    expect(ultima()).toMatchObject({ url: "/motor/conversas/cv-7f3a/turnos", metodo: "POST", corpo: pedido });
  });

  it("409 com o turno que já roda: anexa, não é erro", async () => {
    rede.mockResolvedValue(
      resposta({ ok: false, dados: { turno_id: "t-88c0" }, erro: "já respondendo", categoria: "uso", pergunta: null }, 409),
    );
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).resolves.toEqual({ turno_id: "t-88c0", anexado: true });

    rede.mockResolvedValue(resposta({ turno_id: "t-88c0" }, 409));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).resolves.toEqual({ turno_id: "t-88c0", anexado: true });
  });

  it("409 sem turno é erro de uso; 500 é de rede", async () => {
    rede.mockResolvedValue(resposta({ detail: "conflito" }, 409));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).rejects.toMatchObject({ categoria: "uso" });

    rede.mockResolvedValue(resposta({ detail: "caiu" }, 500));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).rejects.toMatchObject({ categoria: "rede" });
  });

  it("resposta sem turno_id é falha de caminho", async () => {
    rede.mockResolvedValue(resposta(envelope({ outro: 1 }), 202));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).rejects.toMatchObject({ categoria: "rede" });

    rede.mockResolvedValue(resposta(envelope(null), 202));
    await expect(conversa.enviarTurno("cv-7f3a", pedido)).rejects.toMatchObject({ categoria: "rede" });
  });
});

/* -------------------------------------------------------------------------- */
/* Os tipos batem com as fixtures do contrato                                  */
/* -------------------------------------------------------------------------- */

type Presenca = "sempre" | "opcional";
type Chaves<T> = Record<keyof T, Presenca>;

/**
 * Toda chave obrigatória do tipo está na fixture, e toda chave da fixture está
 * no tipo. O `satisfies Chaves<T>` faz o TypeScript cobrar a lista completa.
 */
function conferir<T>(nome: string, fixture: unknown, chaves: Chaves<T>) {
  const objeto = fixture as Record<string, unknown>;
  const doTipo = Object.keys(chaves);
  const obrigatorias = doTipo.filter((c) => chaves[c as keyof T] === "sempre");
  const faltando = obrigatorias.filter((c) => !(c in objeto));
  const sobrando = Object.keys(objeto).filter((c) => !doTipo.includes(c));
  expect({ nome, faltando, sobrando }).toEqual({ nome, faltando: [], sobrando: [] });
}

const ITEM_DA_DESPENSA = {
  id: "sempre",
  nome: "sempre",
  categoria: "sempre",
  categoria_rotulo: "sempre",
  estoque: "sempre",
  unidade: "sempre",
  estoque_texto: "sempre",
  pago: "sempre",
  custo_unitario: "sempre",
  derivacao: "sempre",
  confianca: "sempre",
  confianca_rotulo: "sempre",
  fracao_do_total: "sempre",
  fracao_texto: "sempre",
  origem: "sempre",
  origem_rotulo: "sempre",
  imagem: "sempre",
  receitas_que_usam: "sempre",
  receitas_que_usam_texto: "sempre",
  pendente: "sempre",
  rota: "sempre",
} satisfies Chaves<ItemDaDespensa>;

const PENDENCIA = {
  id: "sempre",
  ingrediente: "sempre",
  tipo: "sempre",
  pergunta: "sempre",
  impacto: "sempre",
  impacto_texto: "sempre",
  resposta_inline: "sempre",
  rascunho_chat: "sempre",
  rota: "sempre",
} satisfies Chaves<PendenciaDaDespensa>;

const RESPOSTA_INLINE = {
  tipo: "sempre",
  rotulo: "sempre",
  unidades: "sempre",
  campos: "opcional",
} satisfies Chaves<RespostaInline>;

const ORCAMENTO = {
  inicial: "sempre",
  restante: "sempre",
  gasto: "sempre",
  fracao_gasta: "sempre",
  texto: "sempre",
  compras: "sempre",
} satisfies Chaves<OrcamentoDaDespensa>;

const COMPRA = {
  id: "sempre",
  descricao: "sempre",
  ingrediente: "sempre",
  item_id: "sempre",
  valor: "sempre",
  quando_texto: "sempre",
  canal: "sempre",
  estornada: "sempre",
  estorno: "sempre",
  pode_estornar: "sempre",
  rota_estorno: "sempre",
} satisfies Chaves<CompraDoOrcamento>;

const EVENTO = {
  id: "sempre",
  tipo: "sempre",
  acao: "sempre",
  texto: "sempre",
  quando_texto: "sempre",
  canal: "sempre",
  pode_desfazer: "sempre",
  desfaz: "sempre",
  item_id: "sempre",
  item_nome: "sempre",
  motivo: "sempre",
  rota: "sempre",
} satisfies Chaves<EventoDaDespensa>;

const AFETADAS = {
  liberadas: "sempre",
  bloqueadas: "sempre",
  mudaram: "sempre",
  texto: "sempre",
} satisfies Chaves<ReceitasAfetadas>;

const ESCRITA = {
  item: "sempre",
  id: "sempre",
  ingrediente: "sempre",
  repetida: "sempre",
  evento: "sempre",
  removido: "sempre",
  estorno: "sempre",
  compra: "sempre",
  pendencias_resolvidas: "sempre",
  pendencia: "sempre",
  receitas_afetadas: "sempre",
  orcamento: "sempre",
  texto: "sempre",
} satisfies Chaves<RespostaDaEscrita>;

/** O contrato mostra os campos que a tela lê; a API manda também os de fora dele. */
const FORA_DO_CONTRATO = ["mudou", "antes", "depois", "orcamento_mudou"];

/** A resposta de uma escrita, sem os campos que a API manda e o contrato não lista. */
function doContrato(resposta: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(resposta).filter(([chave]) => !FORA_DO_CONTRATO.includes(chave)));
}

const ITEM_DA_GRADE = {
  slug: "sempre",
  nome: "sempre",
  imagem: "sempre",
  site: "sempre",
  tempo_texto: "sempre",
  selo: "sempre",
  usa_texto: "sempre",
  falta_texto: "sempre",
  pontuacao: "sempre",
  gosta: "sempre",
  pergunta: "sempre",
  referencias: "sempre",
  nota_da_cozinha: "sempre",
  rota: "sempre",
} satisfies Chaves<ItemDaGrade>;

const PRECO_DE_REFERENCIA = {
  ingrediente: "sempre",
  texto: "sempre",
  preco_texto: "sempre",
  produto: "sempre",
  site: "sempre",
  url: "sempre",
  data_texto: "sempre",
  titulo: "sempre",
  preco_medio_texto: "sempre",
  media_texto: "sempre",
  fontes: "sempre",
} satisfies Chaves<PrecoDeReferencia>;

const FONTE_DO_PRECO = {
  site: "sempre",
  produto: "sempre",
  preco_texto: "sempre",
  por_unidade_texto: "sempre",
  url: "sempre",
  data_texto: "sempre",
  na_media: "sempre",
} satisfies Chaves<FonteDoPreco>;

const PERGUNTA_DA_RECEITA = {
  tipo: "sempre",
  assunto: "sempre",
  campo: "sempre",
  texto: "sempre",
  motivo: "sempre",
  compras: "sempre",
  opcoes: "sempre",
  entrada: "sempre",
  passos: "sempre",
} satisfies Chaves<PerguntaDaReceita>;

const ENTRADA_DA_PERGUNTA = {
  tipo: "sempre",
  unidade: "opcional",
  min: "opcional",
  max: "opcional",
  passo: "opcional",
  casas: "opcional",
  peso_de: "opcional",
} satisfies Chaves<EntradaDaPergunta>;

/** A pergunta e a forma de responder: o peso de uma linha traz de quanto pode ser. */
function conferirPergunta(pergunta: PerguntaDaReceita) {
  conferir<PerguntaDaReceita>(pergunta.campo, pergunta, PERGUNTA_DA_RECEITA);
  if (!pergunta.entrada) return;
  conferir<EntradaDaPergunta>(`entrada de ${pergunta.campo}`, pergunta.entrada, ENTRADA_DA_PERGUNTA);
  if (pergunta.entrada.peso_de) {
    conferir<LeiturasDoPeso>(`peso de ${pergunta.campo}`, pergunta.entrada.peso_de, { cada: "sempre", tudo: "sempre" });
  }
}

/** O checklist de produção: os grupos, cada item com o estado, a origem e o que responder. */
function conferirChecklist(checklist: ChecklistDeProducao) {
  conferir<ChecklistDeProducao>("checklist", checklist, {
    titulo: "sempre",
    pode_aceitar: "sempre",
    resumo: "sempre",
    falta_para_aceitar: "sempre",
    confirmar_a_cozinha: "sempre",
    grupos: "sempre",
  });
  if (checklist.confirmar_a_cozinha) {
    conferir<ConfirmarACozinha>("confirmar a cozinha", checklist.confirmar_a_cozinha, { pergunta: "sempre", itens: "sempre" });
    for (const item of checklist.confirmar_a_cozinha.itens) {
      conferir<ItemAConfirmar>(item.id, item, { tipo: "sempre", id: "sempre", nome: "sempre" });
    }
  }
  expect(checklist.grupos.map((g) => g.id)).toEqual(["equipamentos", "tecnicas", "rotina", "ingredientes", "pre_determinados"]);
  for (const grupo of checklist.grupos) {
    conferir<GrupoDoChecklist>(grupo.id, grupo, { id: "sempre", titulo: "sempre", status: "sempre", itens: "sempre", vazio_texto: "sempre" });
    for (const item of grupo.itens) {
      conferir<ItemDoChecklist>(item.id, item, {
        id: "sempre",
        tipo: "sempre",
        nome: "sempre",
        detalhe: "sempre",
        status: "sempre",
        status_texto: "sempre",
        origem: "sempre",
        origem_texto: "sempre",
        pergunta: "sempre",
        editar: "sempre",
      });
      expect(["confirmado", "pre_determinado", "suposto", "falta_saber", "nao_da"]).toContain(item.status);
      expect(["a_senhora_disse", "suposto", "referencia", "receita"]).toContain(item.origem);
      if (item.pergunta) conferirPergunta(item.pergunta);
      if (item.editar) conferirPergunta(item.editar);
    }
  }
}

const REQUISITO = {
  tipo: "sempre",
  id: "sempre",
  nome: "sempre",
  estado: "sempre",
  suposto: "sempre",
  evidencia: "sempre",
  trecho: "sempre",
  rotulo_estado: "sempre",
  substituto: "sempre",
  conferido: "sempre",
} satisfies Chaves<Requisito>;

const AVALIACAO_DA_RECEITA = {
  gosta: "sempre",
  estrelas: "sempre",
  notas: "sempre",
  pontuacao: "sempre",
} satisfies Chaves<AvaliacaoDaReceita>;

const ITEM_DA_COZINHA = {
  id: "sempre",
  nome: "sempre",
  categoria: "sempre",
  estado: "sempre",
  pressuposto: "opcional",
  pressuposta: "opcional",
  suposto: "sempre",
  pergunta: "sempre",
  dificuldade: "opcional",
  imagem: "sempre",
  receitas_afetadas: "sempre",
  receitas_afetadas_texto: "sempre",
  atualizado_por: "sempre",
  atualizado_texto: "sempre",
  nao_sei: "sempre",
} satisfies Chaves<ItemDaCozinha>;

const RESTRICAO = {
  valor: "sempre",
  tipo: "sempre",
  unidade: "opcional",
  min: "opcional",
  max: "opcional",
  passo: "opcional",
  casas: "opcional",
  valor_texto: "opcional",
  pergunta: "sempre",
  atualizado_por: "sempre",
  atualizado_texto: "sempre",
  nao_sei: "sempre",
} satisfies Chaves<Restricao>;

/** "O que toda cozinha tem": o bloco e cada item, com a foto e o estado dito para ela. */
function conferirTodaCozinha(toda: TodaCozinha) {
  conferir<TodaCozinha>("toda cozinha", toda, {
    titulo: "sempre",
    texto: "sempre",
    a_confirmar: "sempre",
    a_confirmar_texto: "sempre",
    tudo_confirmado: "sempre",
    itens: "sempre",
  });
  expect(toda.itens.length).toBeGreaterThan(0);
  for (const item of toda.itens) {
    conferir<ItemDeTodaCozinha>(item.id, item, {
      tipo: "sempre",
      id: "sempre",
      nome: "sempre",
      imagem: "sempre",
      estado: "sempre",
      status: "sempre",
      status_texto: "sempre",
    });
  }
}

const CONTAGENS = {
  respondidos: "sempre",
  supostos: "sempre",
  em_aberto: "sempre",
  fracao_respondida: "sempre",
  resumo: "sempre",
  progresso_texto: "sempre",
} satisfies Chaves<ContagensDaCozinha>;

describe("contrato v1: as formas batem com contratos/web", () => {
  it("despensa.json", () => {
    const lista = contrato<ListaDaDespensa>("despensa.json");
    conferir<ListaDaDespensa>("lista", lista, {
      itens: "sempre",
      total_investido: "sempre",
      total_itens: "sempre",
      encontrados: "sempre",
      categorias: "sempre",
      categorias_para_escolher: "sempre",
      pendencias: "sempre",
      orcamento: "sempre",
    });
    for (const item of lista.itens) conferir<ItemDaDespensa>(`item ${item.id}`, item, ITEM_DA_DESPENSA);
    for (const p of lista.pendencias) {
      conferir<PendenciaDaDespensa>("pendência", p, PENDENCIA);
      conferir<RespostaInline>("resposta ali mesmo", p.resposta_inline, RESPOSTA_INLINE);
    }
    expect(lista.pendencias.map((p) => p.tipo).sort()).toEqual(["conteudo_embalagem", "preco_pago"]);
    conferir<OrcamentoDaDespensa>("orçamento", lista.orcamento, ORCAMENTO);
    for (const compra of lista.orcamento.compras) conferir<CompraDoOrcamento>("compra", compra, COMPRA);
    expect(lista.categorias_para_escolher.map((c) => c.id)).toContain("outros");
  });

  it.each(["despensa-item.json", "despensa-item-comprado.json"])("%s", (arquivo) => {
    const detalhe = contrato<DetalheDoItem>(arquivo);
    conferir<DetalheDoItem>("detalhe", detalhe, {
      ...ITEM_DA_DESPENSA,
      comprado_texto: "sempre",
      unidade_compra_rotulo: "sempre",
      pendencia: "sempre",
      receitas: "sempre",
      historico: "sempre",
      compras: "sempre",
      rascunho_chat: "sempre",
    });
    for (const evento of detalhe.historico) conferir<EventoDaDespensa>("evento", evento, EVENTO);
    for (const compra of detalhe.compras) conferir<CompraDoOrcamento>("compra", compra, COMPRA);
  });

  it("despensa-eventos.json", () => {
    const pagina = contrato<PaginaDeEventos>("despensa-eventos.json");
    conferir<PaginaDeEventos>("página", pagina, { eventos: "sempre", proximo_cursor: "sempre", total: "sempre", versao: "sempre" });
    for (const evento of pagina.eventos) conferir<EventoDaDespensa>("evento", evento, EVENTO);
  });

  it("despensa-escrita.json", () => {
    const escrita = contrato<Record<string, { resposta: Record<string, unknown> }>>("despensa-escrita.json");
    expect(Object.keys(escrita).sort()).toEqual(
      ["acabou", "adicionar", "adicionar_ja_tinha", "corrigir", "corrigir_preco", "desfazer", "estorno", "remover"].sort(),
    );
    for (const [nome, { resposta }] of Object.entries(escrita)) {
      if (nome === "estorno") continue;
      conferir<RespostaDaEscrita>(nome, doContrato(resposta), ESCRITA);
      conferir<ReceitasAfetadas>(`${nome}: receitas`, resposta.receitas_afetadas, AFETADAS);
      conferir<OrcamentoDaDespensa>(`${nome}: orçamento`, resposta.orcamento, ORCAMENTO);
      if (resposta.item) conferir<ItemDaDespensa>(`${nome}: item`, resposta.item, ITEM_DA_DESPENSA);
    }
    conferir<RespostaDoEstorno>("estorno", escrita.estorno?.resposta, {
      compra_id: "sempre",
      estorno_id: "sempre",
      estorno: "sempre",
      removido: "sempre",
      receitas_afetadas: "sempre",
      orcamento: "sempre",
      texto: "sempre",
    });
  });

  it("receitas.json: a lista, as abas e a descoberta", () => {
    const lista = contrato<ListaDeReceitas>("receitas.json");
    conferir<ListaDeReceitas>("lista", lista, {
      aba: "sempre",
      contagens: "sempre",
      itens: "sempre",
      descoberta: "sempre",
      perguntas_que_liberam: "sempre",
      esperando_resposta: "sempre",
      sem_preco_na_internet: "sempre",
    });
    // As que ficaram de fora só porque o preço não se achou: nada vira pergunta a ela.
    const semPreco = lista.sem_preco_na_internet;
    expect(semPreco).not.toBeNull();
    conferir<SemPrecoNaInternet>("sem_preco_na_internet", semPreco, {
      receitas: "sempre",
      nomes: "sempre",
      slugs: "sempre",
      texto: "sempre",
    });
    if (semPreco) {
      expect(semPreco.nomes).toHaveLength(semPreco.receitas);
      expect(semPreco.slugs).toHaveLength(semPreco.receitas);
    }
    conferir<ListaDeReceitas["contagens"]>("contagens", lista.contagens, {
      pode_fazer: "sempre",
      falta_resposta: "sempre",
      ranking: "sempre",
      nao_quer: "sempre",
    });
    conferir<EstadoDaDescoberta>("descoberta", lista.descoberta, {
      estado: "sempre",
      lidas: "sempre",
      encontradas: "sempre",
      texto: "sempre",
    });
    expect(lista.itens.length).toBeGreaterThan(0);
    for (const item of lista.itens) {
      conferir<ItemDaGrade>(`item ${item.slug}`, item, ITEM_DA_GRADE);
      conferir<ItemDaGrade["selo"]>("selo", item.selo, { codigo: "sempre", texto: "sempre" });
    }
    expect(lista.contagens[lista.aba]).toBe(lista.itens.length);
    expect(lista.perguntas_que_liberam.length).toBeGreaterThan(0);
    for (const grupo of lista.perguntas_que_liberam) {
      conferir<PerguntaQueLibera>(`pergunta que libera ${grupo.texto}`, grupo, {
        pergunta: "sempre",
        receitas: "sempre",
        liberadas: "sempre",
        sem_compra: "sempre",
        sem_compra_texto: "sempre",
        nomes: "sempre",
        slugs: "sempre",
        rota: "sempre",
        texto: "sempre",
      });
      conferirPergunta(grupo.pergunta);
      expect(grupo.slugs).toHaveLength(grupo.nomes.length);
      expect(grupo.liberadas).toBeLessThanOrEqual(grupo.receitas);
      expect(grupo.sem_compra).toBeLessThanOrEqual(grupo.receitas);
      expect(grupo.sem_compra_texto === null).toBe(grupo.sem_compra === 0);
    }
    // Em que pé estão as que esperam resposta: as contas fecham com a aba.
    const espera = lista.esperando_resposta;
    expect(espera).not.toBeNull();
    conferir<EsperandoResposta>("esperando_resposta", espera, {
      receitas: "sempre",
      so_com_o_que_tem: "sempre",
      precisa_comprar: "sempre",
      linha_sem_leitura: "sempre",
      nomes: "sempre",
      slugs: "sempre",
      falta_dizer: "sempre",
      texto: "sempre",
    });
    if (espera) {
      expect(espera.receitas).toBe(lista.contagens.falta_resposta);
      expect(espera.so_com_o_que_tem + espera.precisa_comprar + espera.linha_sem_leitura).toBe(espera.receitas);
      expect(espera.nomes).toHaveLength(espera.so_com_o_que_tem);
      expect(espera.slugs).toHaveLength(espera.nomes.length);
    }
    // O peso de uma linha que não se converte: em gramas, de uma unidade ou da linha inteira.
    const peso = lista.perguntas_que_liberam.find((grupo) => grupo.pergunta.assunto === "medida");
    expect(peso?.pergunta.entrada).toEqual({
      tipo: "peso",
      unidade: "g",
      peso_de: { cada: "1 colher de sopa", tudo: "2 colheres de sopa" },
    });
  });

  it("receita.json: o detalhe com a cozinha, os ingredientes, os passos e a avaliação", () => {
    const detalhe = contrato<DetalheDaReceita>("receita.json");
    conferir<DetalheDaReceita>("detalhe", detalhe, {
      slug: "sempre",
      nome: "sempre",
      imagem: "sempre",
      fonte: "sempre",
      origem: "sempre",
      tempos: "sempre",
      tempo_texto: "sempre",
      rendimento_texto: "sempre",
      rendimento: "sempre",
      veredito: "sempre",
      veredito_rotulo: "sempre",
      veredito_da_cozinha: "sempre",
      resumo: "sempre",
      ingredientes: "sempre",
      linhas_nao_entendidas: "sempre",
      opcionais: "sempre",
      avisos: "sempre",
      falta_comprar: "sempre",
      custo_porcao: "sempre",
      pode_precificar: "sempre",
      passos: "sempre",
      requisitos_da_receita: "sempre",
      perguntas: "sempre",
      avaliacao: "sempre",
      posicao_no_ranking: "sempre",
      respostas: "sempre",
      rascunho_chat: "sempre",
      checklist: "sempre",
      rota: "sempre",
    });
    if (detalhe.rendimento) {
      conferir<RendimentoDaReceita>("rendimento", detalhe.rendimento, {
        porcoes: "sempre",
        estimado: "sempre",
        texto: "sempre",
        derivacao: "sempre",
        pergunta: "sempre",
      });
    }
    conferirChecklist(detalhe.checklist);
    expect(detalhe.respostas.length).toBeGreaterThan(0);
    for (const resposta of detalhe.respostas) {
      conferir<RespostaSobreAReceita>(resposta.campo, resposta, { campo: "sempre", texto: "sempre", quando_texto: "sempre" });
    }
    conferir<FonteDaReceita>("fonte", detalhe.fonte, { site: "sempre", url: "sempre", autor: "sempre" });
    conferir<TemposDaReceita>("tempos", detalhe.tempos, {
      preparo_min: "sempre",
      cozimento_min: "sempre",
      total_min: "sempre",
      ativo_min: "sempre",
    });
    conferir<VereditoDaCozinha>("veredito da cozinha", detalhe.veredito_da_cozinha, {
      codigo: "sempre",
      rotulo: "sempre",
      motivo: "sempre",
    });
    const situacoes = new Set(detalhe.ingredientes.map((i) => i.situacao));
    expect([...situacoes].sort()).toEqual(["a_gosto", "falta", "nao_entendi", "opcional", "tem"]);
    for (const ingrediente of detalhe.ingredientes) {
      conferir<IngredienteDaReceita>(ingrediente.nome, ingrediente, {
        nome: "sempre",
        item_id: "sempre",
        precisa: "sempre",
        tem: "sempre",
        sobra: "sempre",
        situacao: "sempre",
        compra: "sempre",
        medida_de_referencia: "sempre",
      });
    }
    conferir<DetalheDaReceita["linhas_nao_entendidas"][number]>("linha", detalhe.linhas_nao_entendidas[0], {
      texto: "sempre",
      pergunta: "sempre",
    });
    conferir<DetalheDaReceita["opcionais"][number]>("opcional", detalhe.opcionais[0], { nome: "sempre", texto: "sempre" });
    conferir<DetalheDaReceita["avisos"][number]>("aviso", detalhe.avisos[0], { tipo: "sempre", texto: "sempre" });
    conferir<DetalheDaReceita["falta_comprar"]>("falta comprar", detalhe.falta_comprar, {
      itens: "sempre",
      custo: "sempre",
      cabe_no_orcamento: "sempre",
      texto: "sempre",
    });
    const QUE_FALTA = {
      nome: "sempre",
      quantidade_texto: "sempre",
      preco_conhecido: "sempre",
      custo_compra: "sempre",
      custo_no_prato: "sempre",
      derivacao: "sempre",
      origem_preco: "opcional",
      cabe_no_orcamento: "opcional",
      referencia: "opcional",
    } satisfies Chaves<IngredienteQueFalta>;
    for (const item of detalhe.falta_comprar.itens) conferir<IngredienteQueFalta>(item.nome, item, QUE_FALTA);
    conferir<IngredienteQueFalta>("exemplo do custo", contrato<{ ingrediente_que_falta_exemplo: unknown }>("custo.json").ingrediente_que_falta_exemplo, QUE_FALTA);
    const comReferencia = contrato<{ ingrediente_com_preco_de_referencia_exemplo: IngredienteQueFalta }>("custo.json")
      .ingrediente_com_preco_de_referencia_exemplo;
    conferir<IngredienteQueFalta>("exemplo com preço de referência", comReferencia, QUE_FALTA);
    conferir<PrecoDeReferencia>("preço de referência", comReferencia.referencia, PRECO_DE_REFERENCIA);
    const fontes = comReferencia.referencia?.fontes ?? [];
    expect(fontes.length).toBeGreaterThanOrEqual(2);
    for (const fonte of fontes) conferir<FonteDoPreco>(`fonte ${fonte.site}`, fonte, FONTE_DO_PRECO);
    expect(comReferencia.referencia?.titulo).toBe("Preço médio em São Paulo");
    for (const passo of detalhe.passos) {
      conferir<Passo>(`passo ${passo.ordem}`, passo, { ordem: "sempre", texto: "sempre", secao: "sempre", requisitos: "sempre", limites: "sempre" });
      for (const requisito of passo.requisitos) conferir<Requisito>(requisito.id, requisito, REQUISITO);
      for (const limite of passo.limites) {
        conferir<LimiteDoPasso>(limite.tipo, limite, {
          tipo: "sempre",
          minutos: "sempre",
          graus: "sempre",
          texto: "sempre",
          trecho: "sempre",
          equipamento: "sempre",
        });
      }
    }
    for (const requisito of detalhe.requisitos_da_receita) {
      conferir<RequisitoDaReceita>(requisito.id, requisito, { ...REQUISITO, origem: "sempre" });
    }
    for (const pergunta of detalhe.perguntas) conferirPergunta(pergunta);
    conferir<AvaliacaoDaReceita>("avaliação", detalhe.avaliacao, AVALIACAO_DA_RECEITA);
    conferir<AvaliacaoDaReceita["estrelas"]>("estrelas", detalhe.avaliacao.estrelas, {
      sabor: "sempre",
      facilidade: "sempre",
      tempo: "sempre",
      entrega: "sempre",
      apelo: "sempre",
    });
    if (detalhe.avaliacao.pontuacao) {
      conferir<NonNullable<AvaliacaoDaReceita["pontuacao"]>>("pontuação", detalhe.avaliacao.pontuacao, {
        valor: "sempre",
        texto: "sempre",
        derivacao: "sempre",
      });
    }
  });

  it("custo.json: o custo de uma porção, linha a linha", () => {
    const custo = contrato<CustoDaPorcao & { ingrediente_que_falta_exemplo?: unknown; ingrediente_com_preco_de_referencia_exemplo?: unknown }>(
      "custo.json",
    );
    delete custo.ingrediente_que_falta_exemplo;
    delete custo.ingrediente_com_preco_de_referencia_exemplo;
    conferir<CustoDaPorcao>("custo", custo, {
      prato: "sempre",
      rendimento_original: "sempre",
      e_faixa: "sempre",
      total: "sempre",
      minimo: "sempre",
      maximo: "sempre",
      linhas: "sempre",
      itens_a_gosto: "sempre",
      explicacao: "sempre",
    });
    for (const linha of custo.linhas) {
      conferir<CustoDaPorcao["linhas"][number]>(linha.ingrediente, linha, {
        ingrediente: "sempre",
        quantidade: "sempre",
        custo: "sempre",
        derivacao: "sempre",
        fracao: "sempre",
      });
    }
  });

  it("avaliacao-escrita.json e notas-escrita.json", () => {
    const avaliacao = contrato<{ pedido: unknown; resposta: RespostaDaAvaliacao }>("avaliacao-escrita.json");
    conferir<RespostaDaAvaliacao>("resposta da avaliação", avaliacao.resposta, {
      slug: "sempre",
      nome: "sempre",
      avaliacao: "sempre",
      posicao_no_ranking: "sempre",
      atualizado_texto: "sempre",
      texto: "sempre",
    });
    conferir<AvaliacaoDaReceita>("avaliação", avaliacao.resposta.avaliacao, AVALIACAO_DA_RECEITA);
    conferir<{ gosta?: unknown; estrelas?: unknown }>("pedido", avaliacao.pedido, { gosta: "opcional", estrelas: "opcional" });
    const notas = contrato<{ pedido: { texto: string }; resposta: RespostaDasNotas }>("notas-escrita.json");
    conferir<{ texto: string }>("pedido das notas", notas.pedido, { texto: "sempre" });
    conferir<RespostaDasNotas>("resposta das notas", notas.resposta, {
      slug: "sempre",
      notas: "sempre",
      atualizado_texto: "sempre",
      texto: "sempre",
    });
  });

  it("descoberta-inicio.json", () => {
    conferir<InicioDaDescoberta>("início", contrato("descoberta-inicio.json"), {
      execucao_id: "sempre",
      estado: "sempre",
      texto: "sempre",
      eventos: "sempre",
    });
  });

  it("receitas-descoberta.jsonl: todo evento é de um tipo conhecido", () => {
    const tipos = new Set(["progresso", "receita.encontrada", "receita.atualizada", "fim", "erro"]);
    const eventos = eventosDoContrato<{ seq: number; tipo: string; aba?: string; receita?: unknown }>(
      "receitas-descoberta.jsonl",
    );
    for (const evento of eventos) {
      expect(tipos.has(evento.tipo), evento.tipo).toBe(true);
      if (evento.receita) {
        conferir<ItemDaGrade>("receita encontrada", evento.receita, ITEM_DA_GRADE);
        expect(["pode_fazer", "falta_resposta", "ranking", "nao_quer"]).toContain(evento.aba);
      }
    }
  });

  it("perfil.json e perfil-escrita.json", () => {
    const cozinha = contrato<PerfilDaCozinha>("perfil.json");
    conferir<PerfilDaCozinha>("perfil", cozinha, {
      ...CONTAGENS,
      completude: "sempre",
      equipamentos: "sempre",
      tecnicas: "sempre",
      restricoes: "sempre",
      toda_cozinha: "sempre",
    });
    conferirTodaCozinha(cozinha.toda_cozinha);
    for (const item of [...cozinha.equipamentos, ...cozinha.tecnicas]) {
      conferir<ItemDaCozinha>(`item ${item.id}`, item, ITEM_DA_COZINHA);
    }
    for (const [campo, restricao] of Object.entries(cozinha.restricoes)) conferir<Restricao>(campo, restricao, RESTRICAO);
    const escrita = contrato<{ resposta: RespostaDaCozinha; resposta_restricao: RespostaDaCozinha }>("perfil-escrita.json");
    for (const resposta of [escrita.resposta, escrita.resposta_restricao]) {
      conferir<RespostaDaCozinha>("resposta", resposta, { item: "sempre", impacto: "sempre", perfil: "sempre" });
      conferir<ImpactoDaMudanca>("impacto", resposta.impacto, { liberadas: "sempre", bloqueadas: "sempre", pendentes: "sempre", texto: "sempre" });
      conferir<ContagensDaCozinha>("contagens", resposta.perfil, CONTAGENS);
    }
    conferir<ItemDaCozinha>("item gravado", escrita.resposta.item, ITEM_DA_COZINHA);
    conferir<RestricaoGravada>("restrição gravada", escrita.resposta_restricao.item, { ...RESTRICAO, id: "sempre" });
  });

  it("perfil-supostos.json: o Tenho tudo isso, o que uma receita usa e os itens ditos", () => {
    const supostos = contrato<{
      pedido_da_receita: PedidoDeConfirmacao;
      pedido_dos_itens: PedidoDeConfirmacao;
      pedido_de_tudo: PedidoDeConfirmacao;
      resposta: ConfirmacaoDaCozinha;
    }>("perfil-supostos.json");
    expect(supostos.pedido_de_tudo).toEqual({});
    expect(Object.keys(supostos.pedido_da_receita)).toEqual(["receita"]);
    expect(Object.keys(supostos.pedido_dos_itens)).toEqual(["itens"]);
    conferir<ConfirmacaoDaCozinha>("confirmação", supostos.resposta, {
      confirmados: "sempre",
      texto: "sempre",
      perfil: "sempre",
      toda_cozinha: "sempre",
    });
    for (const item of supostos.resposta.confirmados) {
      conferir<ConfirmacaoDaCozinha["confirmados"][number]>(item.id, item, { tipo: "sempre", id: "sempre", nome: "sempre" });
    }
    conferir<ContagensDaCozinha>("contagens", supostos.resposta.perfil, CONTAGENS);
    conferirTodaCozinha(supostos.resposta.toda_cozinha);
  });

  it("estimativa.json e parametro-escrita.json", () => {
    const estimativa = contrato<Estimativa>("estimativa.json");
    conferir<Estimativa>("estimativa", estimativa, {
      slug: "sempre",
      prato: "sempre",
      preliminar: "sempre",
      rotulo: "sempre",
      linhas: "sempre",
      premissas: "sempre",
      custo_producao: "sempre",
      piso: "sempre",
      minimo_so_ingrediente: "sempre",
      pontos: "sempre",
      referencias_de_mercado: "sempre",
      referencias_texto: "sempre",
      sinais: "sempre",
      texto: "sempre",
    });
    expect(estimativa.preliminar).toBe(true);
    expect(estimativa.referencias_de_mercado).toEqual([]);
    expect(estimativa.pontos).toHaveLength(3);
    const PREMISSA = {
      nome: "sempre",
      rotulo: "sempre",
      valor: "sempre",
      origem: "sempre",
      fonte: "sempre",
      fonte_url: "sempre",
      atualizado_texto: "sempre",
      editavel: "sempre",
    } satisfies Chaves<Premissa>;
    for (const premissa of estimativa.premissas) conferir<Premissa>(premissa.nome, premissa, PREMISSA);
    conferir<Premissa>("parâmetro gravado", contrato<{ resposta: unknown }>("parametro-escrita.json").resposta, PREMISSA);
    for (const linha of estimativa.linhas) {
      conferir<LinhaDaEstimativa>(linha.id, linha, {
        id: "sempre",
        rotulo: "sempre",
        valor: "sempre",
        derivacao: "sempre",
        premissas: "sempre",
      });
    }
    for (const ponto of estimativa.pontos) {
      conferir<PontoDaEstimativa>(ponto.nome, ponto, {
        nome: "sempre",
        descricao: "sempre",
        preco: "sempre",
        taxa: "sempre",
        recebe: "sempre",
        lucro: "sempre",
        sobra_real: "sempre",
        derivacao: "sempre",
      });
    }
    for (const conta of [estimativa.custo_producao, estimativa.piso, estimativa.minimo_so_ingrediente]) {
      conferir<DinheiroComConta>("conta", conta, { valor: "sempre", texto: "sempre", derivacao: "sempre" });
    }
  });

  it("conhecimento.json: a busca na plataforma, com fonte e rota", () => {
    const resposta = contrato<RespostaDoConhecimento>("conhecimento.json");
    conferir<RespostaDoConhecimento>("conhecimento", resposta, {
      trechos: "sempre",
      nada_relevante: "sempre",
      texto: "sempre",
    });
    expect(resposta.trechos.length).toBeGreaterThan(0);
    for (const trecho of resposta.trechos) {
      conferir<TrechoDoConhecimento>(trecho.id, trecho, {
        id: "sempre",
        tipo: "sempre",
        rota: "sempre",
        fonte: "sempre",
        texto: "sempre",
        pontuacao: "sempre",
      });
      expect(trecho.rota === null).toBe(trecho.tipo === "conhecimento");
    }
  });

  it("exportacao.json: tudo o que ela tem, num arquivo só", () => {
    conferir<ExportacaoDosDados>("exportação", contrato("exportacao.json"), {
      arquivo: "sempre",
      versao: "sempre",
      gerado_em: "sempre",
      despensa: "sempre",
      despensa_eventos: "sempre",
      cozinha: "sempre",
      cozinha_eventos: "sempre",
      orcamento: "sempre",
      compras: "sempre",
      decisoes: "sempre",
      cardapio: "sempre",
      gostos: "sempre",
      precos_de_mercado: "sempre",
      receitas_em_avaliacao: "sempre",
    });
  });

  it("restauracao.json: o recomeço pela planilha, com a conciliação", () => {
    const feito = contrato<RestauracaoDosDados>("restauracao.json");
    conferir<RestauracaoDosDados>("restauração", feito, {
      texto: "sempre",
      mudou: "sempre",
      conciliacao: "sempre",
      apagado: "sempre",
      mantido: "sempre",
      copia: "sempre",
      recursos: "sempre",
      repetida: "sempre",
    });
    conferir<RestauracaoDosDados["conciliacao"]>("conciliação", feito.conciliacao, {
      ingredientes: "sempre",
      total_pago: "sempre",
      orcamento_inicial: "sempre",
      orcamento_restante: "sempre",
      cozinha_texto: "sempre",
      texto: "sempre",
    });
    conferir<RestauracaoDosDados["mantido"]>("mantido", feito.mantido, { receitas: "sempre", texto: "sempre" });
    expect(feito.conciliacao).toMatchObject({ ingredientes: 37, total_pago: { texto: "R$ 663,39" }, orcamento_restante: { texto: "R$ 80,00" } });
  });

  it("cartoes/: um card de exemplo de cada tipo que a tela conhece", () => {
    const pasta = doRepositorio("contratos", "web", "cartoes");
    const arquivos = readdirSync(pasta).filter((nome) => nome.endsWith(".json"));
    expect(arquivos.map((nome) => nome.replace(/\.json$/, "")).sort()).toEqual([...TIPOS_DE_CARTAO].sort());
    for (const arquivo of arquivos) {
      const cartao = contrato<CartaoDaConversa>(`cartoes/${arquivo}`);
      conferir<CartaoDaConversa>(arquivo, cartao, {
        cartao_id: "sempre",
        tipo_cartao: "sempre",
        ref: "sempre",
        gerado_texto: "sempre",
        dados: "sempre",
      });
      expect(`${cartao.tipo_cartao}.json`).toBe(arquivo);
    }
  });

  it("cardapio.json", () => {
    const completo = contrato<CardapioCompleto>("cardapio.json");
    conferir<CardapioCompleto>("cardápio", completo, {
      pratos: "sempre",
      resumo: "sempre",
      nao_quer: "sempre",
      historico: "sempre",
    });
    for (const prato of completo.pratos) {
      conferir<PratoDoCardapio>(prato.slug, prato, {
        slug: "sempre",
        prato: "sempre",
        imagem: "sempre",
        preco: "sempre",
        recebe: "sempre",
        custo_porcao: "sempre",
        lucro_porcao: "sempre",
        derivacao: "sempre",
        da_prejuizo: "sempre",
        aviso: "sempre",
        nota: "sempre",
        decidido_texto: "sempre",
        notas: "sempre",
        rota: "sempre",
      });
    }
    conferir<ResumoDoCardapio>("resumo", completo.resumo, {
      pratos: "sempre",
      preco_medio: "sempre",
      margem_media_texto: "sempre",
      orcamento_usado: "sempre",
      orcamento_texto: "sempre",
      orcamento_rota: "sempre",
      texto: "sempre",
    });
    for (const recusado of completo.nao_quer) {
      conferir<PratoRecusado>(recusado.prato, recusado, {
        prato: "sempre",
        motivo_texto: "sempre",
        decidido_texto: "sempre",
        rota: "sempre",
      });
    }
    for (const decisao of completo.historico) {
      conferir<DecisaoNoHistorico>("decisão", decisao, {
        id: "sempre",
        prato: "sempre",
        tipo: "sempre",
        tipo_rotulo: "sempre",
        texto_humano: "sempre",
        quando_texto: "sempre",
        canal: "sempre",
        pode_desfazer: "sempre",
        rota: "sempre",
      });
    }
  });

  it("atividades.json", () => {
    const pagina = contrato<PaginaDeAtividades>("atividades.json");
    conferir<PaginaDeAtividades>("página", pagina, {
      grupos: "sempre",
      total: "sempre",
      texto: "sempre",
      proximo_cursor: "sempre",
      categorias: "sempre",
      quem: "sempre",
      dias: "sempre",
    });
    for (const grupo of pagina.grupos) {
      conferir<GrupoDeAtividades>(grupo.dia, grupo, { dia: "sempre", rotulo: "sempre", itens: "sempre" });
      for (const item of grupo.itens) {
        conferir<Atividade>(item.id, item, {
          id: "sempre",
          quem: "sempre",
          quem_rotulo: "sempre",
          categoria: "sempre",
          categoria_rotulo: "sempre",
          texto: "sempre",
          quando_texto: "sempre",
          hora_texto: "sempre",
          dia: "sempre",
          canal_texto: "sempre",
          resultado: "sempre",
          link: "sempre",
        });
      }
    }
  });

  it("visao-geral.json", () => {
    const visao = contrato<VisaoGeral>("visao-geral.json");
    conferir<VisaoGeral>("visão geral", visao, {
      kpis: "sempre",
      proximo_passo: "sempre",
      pendencias: "sempre",
      perguntas_da_cozinha: "sempre",
      dinheiro_parado: "sempre",
      receitas_recomendadas: "sempre",
      cardapio_previa: "sempre",
    });
    for (const r of visao.receitas_recomendadas) conferir<ItemDaGrade>(r.slug, r, ITEM_DA_GRADE);
    for (const p of visao.pendencias) conferir<PendenciaDaDespensa>("pendência", p, PENDENCIA);
    for (const item of visao.dinheiro_parado.itens) {
      conferir<ItemParado>(item.id, item, {
        id: "sempre",
        nome: "sempre",
        pago: "sempre",
        fracao: "sempre",
        fracao_texto: "sempre",
        imagem: "sempre",
        sem_receita: "sempre",
        rota: "sempre",
      });
    }
    expect(visao.dinheiro_parado.itens.length).toBe(visao.dinheiro_parado.total_itens);
    for (const pergunta of visao.perguntas_da_cozinha) {
      conferir<PerguntaDaCozinha>(pergunta.id, pergunta, {
        id: "sempre",
        pergunta: "sempre",
        receita: "sempre",
        receitas: "sempre",
        rascunho_chat: "sempre",
        rota: "sempre",
      });
    }
    expect(visao.cardapio_previa).toEqual(contrato<CardapioCompleto>("cardapio.json").pratos);
  });

  it("conversas.json e conversa.json", () => {
    const lista = contrato<ListaDeConversas>("conversas.json");
    conferir<ListaDeConversas>("lista", lista, { atual: "sempre", conversas: "sempre" });
    for (const c of lista.conversas) {
      conferir<ResumoDaConversa>(c.id, c, {
        id: "sempre",
        titulo: "sempre",
        previa: "sempre",
        atualizado_texto: "sempre",
        respondendo: "sempre",
      });
    }
    const uma = contrato<Conversa>("conversa.json");
    conferir<Conversa>("conversa", uma, {
      id: "sempre",
      titulo: "sempre",
      atual: "opcional",
      turno_em_andamento: "sempre",
      mensagens: "sempre",
    });
    for (const m of uma.mensagens) {
      conferir<MensagemDaConversa>(m.id, m, {
        id: "sempre",
        papel: "sempre",
        partes: "sempre",
        quando_texto: "sempre",
        atividades: "opcional",
        turno_id: "opcional",
        contexto: "opcional",
        estado: "opcional",
        retirados: "opcional",
        acao_resultado: "opcional",
        erro: "opcional",
        sugestoes: "opcional",
      });
    }
  });

  it("chat-eventos.jsonl: todo evento é de um tipo que o tipo EventoDoTurno conhece", () => {
    const conhecidos = new Set([
      "turno.iniciado",
      "acao.resultado",
      "atividade.iniciada",
      "atividade.concluida",
      "cartao",
      "texto.parcial",
      "texto.comentario",
      "texto.final",
      "estado.alterado",
      "sugestoes",
      "turno.concluido",
      "turno.cancelado",
      "turno.falhou",
    ]);
    const eventos = eventosDoContrato<{ seq: number; tipo: string }>("chat-eventos.jsonl");
    expect(eventos.length).toBeGreaterThan(0);
    expect(eventos.map((e) => e.seq)).toEqual([...eventos.map((e) => e.seq)].sort((a, b) => a - b));
    for (const evento of eventos) expect(conhecidos.has(evento.tipo), evento.tipo).toBe(true);
  });
});
