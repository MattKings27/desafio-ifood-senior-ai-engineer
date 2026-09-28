/**
 * As peças pequenas da conversa: as frases das atividades, os tipos de card,
 * as sugestões por tela, os rascunhos em primeira pessoa, o nome do modelo e
 * o que chega no endereço da página.
 */

import { describe, expect, it } from "vitest";

import { eventosDoContrato } from "@/teste/fixturas";

import {
  ROTULOS_DAS_FERRAMENTAS,
  ROTULO_GENERICO,
  comMaiuscula,
  detalheDaAtividade,
  normalizarFerramenta,
  rotuloFeitoGuardado,
  rotulosDaAtividade,
  rotulosDaFerramenta,
  tempoDecorrido,
} from "./atividades";
import { CARTOES_COM_DINHEIRO, TIPOS_DE_CARTAO, caminhoDaRota, ehTipoDeCartao } from "./cartoes";
import { chegadaDaBusca } from "./chegada";
import { FRASE_SEM_MODELO, fraseDoModelo, nomeDoModelo } from "./modelo";
import { emMinusculas, rascunhos, respostaDaPergunta, textoDaOpcao } from "./perguntas";
import {
  ROTULO_DA_TELA,
  acaoValida,
  chipsDoCartao,
  contextoDaPagina,
  contextoDaTela,
  opcoesValidas,
  rotuloDoContexto,
  sugestoesDaTela,
  telaDoCaminho,
} from "./sugestoes";

describe("atividades", () => {
  it("normaliza o nome da ferramenta, com ou sem o prefixo do MCP", () => {
    expect(normalizarFerramenta("mcp_mise_avaliar_receita")).toBe("avaliar_receita");
    expect(normalizarFerramenta(" MCP__MISE__calcular_cmv ")).toBe("calcular_cmv");
    expect(normalizarFerramenta("web_search")).toBe("web_search");
  });

  it("o plano B por ferramenta, com o genérico para as de consulta e as desconhecidas", () => {
    expect(rotulosDaFerramenta("mcp_mise_diagnostico_despensa")).toEqual(ROTULOS_DAS_FERRAMENTAS.diagnostico_despensa);
    expect(rotulosDaFerramenta("consultar_qualquer_coisa").rotulo).toBe("consultando as anotações");
    expect(rotulosDaFerramenta("ferramenta_nova")).toEqual(ROTULO_GENERICO);
    expect(rotulosDaFerramenta(null)).toEqual(ROTULO_GENERICO);
  });

  it("usa as frases do backend quando servem, e esconde dinheiro nelas", () => {
    const [, iniciada] = eventosDoContrato<Record<string, unknown>>("chat-eventos.jsonl");
    expect(rotulosDaAtividade(iniciada ?? {})).toEqual({
      rotulo: "conferindo se a senhora consegue fazer arroz com frango",
      rotuloFeito: "conferi se a senhora consegue fazer arroz com frango",
    });
    expect(
      rotulosDaAtividade({ ferramenta: "web_search", rotulo: "procurando até R$ 30", rotulo_feito: "procurei até R$ 30" }),
    ).toEqual({ rotulo: "procurando até R$ ···", rotuloFeito: "procurei até R$ ···" });
  });

  it("frase técnica, com jargão, vazia ou comprida cai para o plano B inteiro", () => {
    const planoB = ROTULOS_DAS_FERRAMENTAS.calcular_cmv;
    expect(rotulosDaAtividade({ ferramenta: "calcular_cmv", rotulo: "calculando o CMV", rotulo_feito: "calculei" })).toEqual(planoB);
    expect(rotulosDaAtividade({ ferramenta: "calcular_cmv", rotulo: "chamando calcular_cmv", rotulo_feito: "ok" })).toEqual(planoB);
    expect(rotulosDaAtividade({ ferramenta: "calcular_cmv", rotulo: "   ", rotulo_feito: "x" })).toEqual(planoB);
    expect(rotulosDaAtividade({ ferramenta: "calcular_cmv", rotulo: "a".repeat(200), rotulo_feito: "x" })).toEqual(planoB);
    expect(rotulosDaAtividade({ ferramenta: 3, rotulo: 1 })).toEqual(ROTULO_GENERICO);
  });

  it("rótulo guardado e detalhe: a frase quando serve, senão nada", () => {
    expect(rotuloFeitoGuardado("olhei sua despensa")).toBe("olhei sua despensa");
    expect(rotuloFeitoGuardado("Traceback (most recent call last)")).toBeNull();
    expect(detalheDaAtividade("buscando “bolo de cenoura”")).toBe("buscando “bolo de cenoura”");
    expect(detalheDaAtividade(undefined)).toBeUndefined();
  });

  it("maiúscula no começo, e o tempo passado em palavras", () => {
    expect(comMaiuscula("olhei a despensa")).toBe("Olhei a despensa");
    expect(comMaiuscula("")).toBe("");
    expect(tempoDecorrido(-5)).toBe("0 s");
    expect(tempoDecorrido(42_300)).toBe("42 s");
    expect(tempoDecorrido(60_000)).toBe("1 min");
    expect(tempoDecorrido(65_000)).toBe("1 min 5 s");
  });
});

describe("cartoes", () => {
  it("conhece os 15 tipos do contrato (com o de fontes) e ignora o resto", () => {
    expect(TIPOS_DE_CARTAO).toHaveLength(15);
    expect(ehTipoDeCartao("fontes")).toBe(true);
    expect(ehTipoDeCartao("custo_porcao")).toBe(true);
    expect(ehTipoDeCartao("desconhecido")).toBe(false);
    expect(ehTipoDeCartao(3)).toBe(false);
    expect(CARTOES_COM_DINHEIRO.has("cenarios")).toBe(true);
    expect(CARTOES_COM_DINHEIRO.has("pergunta")).toBe(false);
  });

  it("a rota do card vira caminho da API, e só isso", () => {
    expect(caminhoDaRota("/api/custo?prato=Arroz%20com%20frango")).toBe("/custo?prato=Arroz%20com%20frango");
    expect(caminhoDaRota("/api/receitas/arroz-com-frango")).toBe("/receitas/arroz-com-frango");
    expect(caminhoDaRota("/api/../segredo")).toBeNull();
    expect(caminhoDaRota("/api//outro")).toBeNull();
    expect(caminhoDaRota("https://fora.com/api/x")).toBeNull();
    expect(caminhoDaRota("/receitas/x")).toBeNull();
    expect(caminhoDaRota(null)).toBeNull();
  });
});

describe("sugestoes: a tela e o contexto", () => {
  it.each([
    ["/", "inicio"],
    ["/despensa", "despensa"],
    ["/despensa/alcaparras?x=1", "despensa"],
    ["/receitas#topo", "receitas"],
    ["/trilha", "historico"],
    ["/conversa", "conversa"],
    ["/um-lugar-qualquer", "conversa"],
    [null, "inicio"],
  ] as const)("%s → %s", (caminho, tela) => {
    expect(telaDoCaminho(caminho)).toBe(tela);
  });

  it("o contexto da tela leva o nome dela; na conversa, não há contexto", () => {
    expect(contextoDaTela("/despensa")).toEqual({ tela: "despensa", tipo: "tela", id: "despensa", rotulo: "Despensa" });
    expect(contextoDaTela("/precificar")?.rotulo).toBe("Pôr preço");
    expect(contextoDaTela("/conversa")).toBeUndefined();
  });

  it("numa página de detalhe, o contexto é o item, com o nome do título", () => {
    expect(contextoDaPagina("/despensa/arroz-branco-tipo-1", "  Arroz branco\n tipo 1 ")).toEqual({
      tela: "despensa",
      tipo: "ingrediente",
      id: "arroz-branco-tipo-1",
      rotulo: "Arroz branco tipo 1",
    });
    expect(contextoDaPagina("/receitas/bolo%20de%20milho", "Bolo de milho")).toMatchObject({
      tipo: "receita",
      id: "bolo de milho",
      rotulo: "Bolo de milho",
    });
    expect(contextoDaPagina("/receitas/x", null)?.rotulo).toBe("Receitas");
    expect(contextoDaPagina("/receitas/x", "t".repeat(130))?.rotulo).toBe("Receitas");
    expect(contextoDaPagina("/receitas/%E0%A4%A", "Nome")).toEqual(contextoDaTela("/receitas"));
    expect(contextoDaPagina("/cozinha/forno", "Forno")).toEqual(contextoDaTela("/cozinha"));
    expect(contextoDaPagina("/despensa", "Despensa")).toEqual(contextoDaTela("/despensa"));
    expect(contextoDaPagina("/conversa", "Conversa")).toBeUndefined();
  });

  it("o chip mostra o rótulo, ou o nome da tela, ou uma frase neutra", () => {
    expect(rotuloDoContexto({ tela: "receitas", tipo: "receita", rotulo: " Arroz " })).toBe("Arroz");
    expect(rotuloDoContexto({ tela: "cardapio", tipo: "tela" })).toBe(ROTULO_DA_TELA.cardapio);
    expect(rotuloDoContexto({ tela: "outra", tipo: "tela" })).toBe("esta tela");
  });

  it("as sugestões de começo mudam com a página", () => {
    expect(sugestoesDaTela("/despensa")[0]?.rotulo).toBe("Dinheiro parado");
    expect(sugestoesDaTela("/receitas/x").map((s) => s.rotulo)).toContain("Outra receita");
    expect(sugestoesDaTela("/conversa")).toHaveLength(4);
  });
});

describe("sugestoes: o que vem do backend", () => {
  it("só aceita as três formas de ação", () => {
    expect(acaoValida({ tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" })).toEqual({
      tipo: "responder",
      tipo_pergunta: "equipamento",
      campo: "forno",
      resposta: "sim",
    });
    expect(acaoValida({ tipo: "responder", campo: "forno" })).toBeUndefined();
    expect(
      acaoValida({ tipo: "responder", tipo_pergunta: "ingrediente", campo: "6 bifes de alcatra", resposta: "sim", receita_id: "alcatra" }),
    ).toEqual({ tipo: "responder", tipo_pergunta: "ingrediente", campo: "6 bifes de alcatra", resposta: "sim", receita_id: "alcatra" });
    expect(acaoValida({ tipo: "responder", tipo_pergunta: "ingrediente", campo: "x", resposta: "sim", receita_id: 3 })).toEqual({
      tipo: "responder",
      tipo_pergunta: "ingrediente",
      campo: "x",
      resposta: "sim",
    });
    expect(acaoValida({ tipo: "decidir", prato: "Arroz", decisao: "aceito", preco: 18 })).toEqual({
      tipo: "decidir",
      prato: "Arroz",
      decisao: "aceito",
      preco: 18,
    });
    expect(acaoValida({ tipo: "decidir", prato: "Arroz", decisao: "aceito" })).toEqual({
      tipo: "decidir",
      prato: "Arroz",
      decisao: "aceito",
    });
    expect(acaoValida({ tipo: "decidir", prato: "Arroz", decisao: "aceito", preco: "18" })).toBeUndefined();
    expect(acaoValida({ tipo: "decidir", prato: 1 })).toBeUndefined();
    expect(
      acaoValida({ tipo: "avaliar", receita_id: "arroz", gosta: true, notas: "boa", estrelas: { sabor: 5, tempo: null, apelo: 9, outra: 3 } }),
    ).toEqual({ tipo: "avaliar", receita_id: "arroz", gosta: true, notas: "boa", estrelas: { sabor: 5, tempo: null } });
    expect(acaoValida({ tipo: "avaliar", receita_id: "arroz", gosta: "sim" })).toEqual({ tipo: "avaliar", receita_id: "arroz" });
    expect(acaoValida({ tipo: "avaliar", receita: "arroz" })).toBeUndefined();
    expect(acaoValida({ tipo: "apagar_tudo" })).toBeUndefined();
    expect(acaoValida(null)).toBeUndefined();
    expect(acaoValida(["x"])).toBeUndefined();
  });

  it("opções válidas: rótulo e texto curtos, no máximo quatro", () => {
    const [ultima] = eventosDoContrato<{ tipo: string; opcoes?: unknown }>("chat-eventos.jsonl").filter(
      (evento) => evento.tipo === "sugestoes",
    );
    expect(opcoesValidas(ultima?.opcoes)).toEqual([
      { rotulo: "Quanto cobrar?", texto: "Quanto eu cobro por porção?" },
      { rotulo: "Outra receita", texto: "Me mostra outra receita com o que eu tenho." },
    ]);
    const muitas = Array.from({ length: 6 }, (_, i) => ({ rotulo: `op ${i}`, texto: `texto ${i}` }));
    expect(opcoesValidas(muitas)).toHaveLength(4);
    expect(
      opcoesValidas([
        { rotulo: "  ", texto: "x" },
        { rotulo: "a".repeat(61), texto: "x" },
        { rotulo: "ok", texto: 3 },
        null,
        { rotulo: "Tenho", texto: "Tenho forno.", acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" } },
      ]),
    ).toEqual([
      {
        rotulo: "Tenho",
        texto: "Tenho forno.",
        acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
      },
    ]);
    expect(opcoesValidas("nada")).toEqual([]);
  });

  it("os chips que cada card sugere", () => {
    expect(chipsDoCartao(null)).toEqual([]);
    expect(chipsDoCartao({ tipo: "inventado", dados: {} })).toEqual([]);
    expect(chipsDoCartao({ tipo: "custo_porcao", dados: null }).map((c) => c.rotulo)).toEqual(["Quanto cobrar?"]);
    expect(
      chipsDoCartao({ tipo: "pergunta", dados: { opcoes: [{ rotulo: "Tenho", texto: "Tenho forno." }] } }),
    ).toEqual([{ rotulo: "Tenho", texto: "Tenho forno." }]);
    const ponto = chipsDoCartao({ tipo: "ponto_de_preco", dados: {}, ref: { parametros: { prato: "Arroz", preco: 18 } } });
    expect(ponto[0]).toMatchObject({ acao: { tipo: "decidir", prato: "Arroz", decisao: "aceito", preco: 18 } });
    expect(chipsDoCartao({ tipo: "ponto_de_preco", dados: {} }).map((c) => c.rotulo)).toEqual(["Quero outro preço"]);
    expect(chipsDoCartao({ tipo: "viabilidade", dados: { pode_precificar: true } })).toHaveLength(1);
    expect(chipsDoCartao({ tipo: "viabilidade", dados: { pode_precificar: false } })).toEqual([]);
    expect(chipsDoCartao({ tipo: "ingrediente", dados: { nome: "Peito de frango" } })).toEqual([
      { rotulo: "Receitas com ele", texto: "Que receitas usam peito de frango?" },
    ]);
    expect(chipsDoCartao({ tipo: "ingrediente", dados: {} })).toEqual([]);
    expect(chipsDoCartao({ tipo: "avaliacao_da_receita", dados: {} })).toEqual([]);
  });
});

describe("perguntas: os rascunhos na voz dela", () => {
  it("minúscula no meio da frase, sigla fica", () => {
    expect(emMinusculas(" Bolo de cenoura")).toBe("bolo de cenoura");
    expect(emMinusculas("CMV")).toBe("CMV");
  });

  it("cada rascunho, em primeira pessoa", () => {
    expect(rascunhos.podeFazer(" Bolo de cenoura ")).toBe("Dá pra eu fazer Bolo de cenoura?");
    expect(rascunhos.quantoCobrar("Arroz com frango")).toBe("Quanto eu cobro por uma porção de arroz com frango?");
    expect(rascunhos.oQueFazerCom("Peito de frango")).toBe("O que eu posso fazer com peito de frango?");
    expect(rascunhos.embalagem("Cobertura de chocolate")).toBe("A embalagem de cobertura de chocolate tem ");
    expect(rascunhos.explicarConta("Arroz")).toBe("Me explica essa conta de arroz?");
    expect(rascunhos.mudarPreco("Arroz")).toBe("Quero mudar o preço de arroz para ");
    expect(rascunhos.vouCobrar(" R$ 18,00 ", "Arroz")).toBe("Vou cobrar R$ 18,00 por porção de arroz.");
    expect(rascunhos.trazerConta()).toBe("Me mostra a conta de cada valor que ficou de fora?");
  });

  it("o texto de uma opção, e a resposta a uma pergunta como turno estruturado", () => {
    expect(textoDaOpcao({ rotulo: "Tenho", texto: " Tenho forno. " })).toBe("Tenho forno.");
    expect(textoDaOpcao({ rotulo: "Faço" })).toBe("Faço.");
    expect(textoDaOpcao({ rotulo: "Não sei?" })).toBe("Não sei?");
    const pergunta = { tipo: "equipamento", campo: "forno" };
    expect(respostaDaPergunta(pergunta, { rotulo: "Tenho", resposta: "sim" })).toEqual({
      rotulo: "Tenho",
      texto: "Tenho.",
      acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
    });
    expect(respostaDaPergunta(pergunta, { rotulo: "Não sei", resposta: "nao_sei" })).toEqual({
      rotulo: "Não sei",
      texto: "Não sei.",
    });
    expect(respostaDaPergunta({ tipo: "tecnica", campo: "" }, { rotulo: "Sei", resposta: "sim" })).toEqual({
      rotulo: "Sei",
      texto: "Sei.",
    });
  });
});

describe("modelo", () => {
  it.each([
    ["claude-fable-5-1", "Claude Fable 5.1"],
    ["claude-opus-5-5", "Claude Opus 5.5"],
    ["claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"],
    ["anthropic/claude-haiku-4-5", "Claude Haiku 4.5"],
    ["gpt-4o", "Gpt 4o"],
  ])("%s → %s", (id, nome) => {
    expect(nomeDoModelo(id)).toBe(nome);
  });

  it("identificador estranho não vira nome", () => {
    expect(nomeDoModelo(null)).toBeNull();
    expect(nomeDoModelo("  ")).toBeNull();
    expect(nomeDoModelo("<script>")).toBeNull();
    expect(nomeDoModelo("a".repeat(90))).toBeNull();
    expect(nomeDoModelo("x--20250101")).toBe("X");
  });

  it("a frase de quem responde", () => {
    expect(fraseDoModelo("claude-fable-5-1")).toBe(
      "Quem conversa com a senhora é o Claude Fable 5.1, um modelo de inteligência artificial da Anthropic.",
    );
    expect(fraseDoModelo("modelo-local-2")).toBe(
      "Quem conversa com a senhora é o modelo Modelo Local 2, de inteligência artificial.",
    );
    expect(fraseDoModelo(undefined)).toBe(FRASE_SEM_MODELO);
  });
});

describe("chegada na página da conversa", () => {
  it("a conversa, o rascunho e o contexto do endereço", () => {
    expect(
      chegadaDaBusca({
        c: "cv-7f3a",
        rascunho: ["Dá pra eu fazer Bolo?", "outro"],
        tela: "receitas",
        tipo: "receita",
        id: "bolo",
        rotulo: "Bolo",
      }),
    ).toEqual({
      conversa: "cv-7f3a",
      rascunho: "Dá pra eu fazer Bolo?",
      contexto: { tela: "receitas", tipo: "receita", id: "bolo", rotulo: "Bolo" },
    });
    expect(chegadaDaBusca({ tela: "inicio", tipo: "pendencia" })).toEqual({ contexto: { tela: "inicio", tipo: "pendencia" } });
    expect(chegadaDaBusca({ tela: "inicio", rascunho: "  " })).toEqual({});
  });
});
