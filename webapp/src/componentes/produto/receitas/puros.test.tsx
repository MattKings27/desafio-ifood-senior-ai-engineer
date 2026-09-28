/**
 * As peças puras da tela de receitas: os filtros na URL, o jeito de responder
 * cada pergunta, as frases que a tela escreve e o plano B da foto.
 */

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DetalheDaReceita, PerguntaDaReceita, VereditoDaCozinha } from "@/lib/api/receitas";
import { lerFiltros } from "@/lib/filtros/url";
import { contrato } from "@/teste/fixturas";

import { IconeDoPrato, tomDaFoto } from "./aparencia";
import {
  ESQUEMA_DAS_RECEITAS,
  chaveDoPedido,
  paraBusca,
  paraPedido,
  receitasTexto,
  resumoDaBusca,
  rotuloDoTempo,
  rotuloDoUsa,
} from "./filtros";
import { formaDaConferencia } from "../precificar/formaDaConferencia";

import { comoResponder, daCozinha } from "./perguntas";
import {
  comMaiuscula,
  ondeEntrou,
  ondeFicou,
  permissaoDePreco,
  progressoDaDescoberta,
  rascunhoDaPergunta,
  rascunhoDoPreco,
  semQuebrarValor,
} from "./textos";

const RECEITA = contrato<DetalheDaReceita>("receita.json");

function pergunta(extras: Partial<PerguntaDaReceita>): PerguntaDaReceita {
  return {
    tipo: "ingrediente",
    assunto: "ingrediente",
    campo: "x",
    texto: "?",
    motivo: "",
    compras: [],
    opcoes: [],
    entrada: null,
    passos: [],
    ...extras,
  };
}

const cozinha = (codigo: VereditoDaCozinha["codigo"], motivo = "Porque sim."): VereditoDaCozinha => ({
  codigo,
  rotulo: "r",
  motivo,
});

describe("os filtros da grade", () => {
  it("lê a URL com o esquema e monta o pedido à API, sem o que a API não aceita", () => {
    const filtros = lerFiltros(
      new URLSearchParams("aba=ranking&q=%20Frango%20&usa=cebola&tempo_max=45&so_com_o_que_tenho=true&nota_min=70&ordem=tempo"),
      ESQUEMA_DAS_RECEITAS,
    );
    expect(paraPedido(filtros)).toEqual({
      aba: "ranking",
      q: "Frango",
      usa: "cebola",
      tempo_max: 45,
      so_com_o_que_tenho: true,
      nota_min: 70,
      ordem: "tempo",
    });
    const fora = lerFiltros(new URLSearchParams("aba=nao_quer&tempo_max=0&nota_min=120&ordem=x"), ESQUEMA_DAS_RECEITAS);
    expect(paraPedido(fora)).toEqual({
      aba: "pode_fazer",
      q: undefined,
      usa: undefined,
      tempo_max: undefined,
      so_com_o_que_tenho: undefined,
      nota_min: undefined,
      ordem: undefined,
    });
    expect(paraPedido(lerFiltros(new URLSearchParams("tempo_max=2.5&nota_min=-1"), ESQUEMA_DAS_RECEITAS))).toMatchObject({
      tempo_max: undefined,
      nota_min: undefined,
    });
  });

  it("a chave é a mesma para o mesmo pedido, em qualquer ordem", () => {
    expect(chaveDoPedido({ ordem: "tempo", aba: "ranking", q: "arroz" })).toBe("?aba=ranking&q=arroz&ordem=tempo");
    expect(chaveDoPedido({ aba: "pode_fazer" })).toBe("?aba=pode_fazer");
  });

  it("o searchParams do Next vira URLSearchParams, com as listas repetidas", () => {
    expect(paraBusca({ q: "a", ordem: undefined, usa: ["x", "y"] }).toString()).toBe("q=a&usa=x&usa=y");
  });

  it("os rótulos dos filtros e o resumo, sem plural com parênteses", () => {
    expect(rotuloDoTempo(30)).toBe("Até 30 min");
    expect(rotuloDoTempo(60)).toBe("Até 1 hora");
    expect(rotuloDoTempo(120)).toBe("Até 2 horas");
    expect(rotuloDoTempo(90)).toBe("Até 1 h 30 min");
    expect(rotuloDoUsa("peito-de-frango")).toBe("Usa peito de frango");
    expect(rotuloDoUsa("item-4f7a1c2e")).toBe("Usa um item da despensa");
    expect([0, 1, 3].map(resumoDaBusca)).toEqual(["Nenhuma encontrada", "1 encontrada", "3 encontradas"]);
    expect([1, 2].map(receitasTexto)).toEqual(["1 receita", "2 receitas"]);
  });
});

describe("como cada pergunta se responde ali mesmo: só a cozinha é pergunta", () => {
  it("equipamento, técnica e os limites da rotina se respondem; sem opção que a tela entenda, pela conversa", () => {
    const forno = pergunta({
      tipo: "equipamento",
      assunto: "equipamento",
      campo: "forno",
      opcoes: [
        { rotulo: "Tenho", resposta: "sim" },
        { rotulo: "Não tenho", resposta: "nao" },
        { rotulo: "Não sei", resposta: "nao_sei" },
        { rotulo: "Outra", resposta: "outra" },
      ],
    });
    expect(comoResponder(forno)).toEqual({
      tipo: "posse",
      lista: "equipamentos",
      id: "forno",
      opcoes: [
        { rotulo: "Tenho", estado: "tem" },
        { rotulo: "Não tenho", estado: "nao_tem" },
        { rotulo: "Não sei", estado: "nao_sei" },
      ],
    });
    expect(comoResponder(pergunta({ tipo: "tecnica", assunto: "tecnica", campo: "refogar", opcoes: [{ rotulo: "Faço", resposta: "sim" }] }))).toMatchObject({
      tipo: "posse",
      lista: "tecnicas",
    });
    expect(comoResponder(pergunta({ tipo: "equipamento", assunto: "modo_preparo", campo: "modo_preparo", entrada: { tipo: "texto" } }))).toEqual({
      tipo: "conversa",
    });
    const bocas = { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 };
    expect(
      comoResponder(pergunta({ tipo: "operacional", assunto: "rotina", campo: "bocas_fogao", entrada: bocas, opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }] })),
    ).toEqual({ tipo: "limite", campo: "bocas_fogao", entrada: bocas, comNaoSei: true });
    const horas = { tipo: "horas", unidade: "horas", min: 0.5, max: 12, passo: 0.5, casas: 2 };
    expect(comoResponder(pergunta({ tipo: "operacional", assunto: "rotina", campo: "tempo_max_por_fornada_min", entrada: horas }))).toEqual({
      tipo: "limite",
      campo: "tempo_max_por_fornada_min",
      entrada: horas,
      comNaoSei: false,
    });
    expect(comoResponder(pergunta({ tipo: "operacional", assunto: "rotina", campo: "tem_gas_sobrando", opcoes: [{ rotulo: "Sim", resposta: "sim" }] }))).toEqual({
      tipo: "sim_nao",
      campo: "tem_gas_sobrando",
    });
    expect(comoResponder(pergunta({ tipo: "operacional", assunto: "rotina", campo: "outro", entrada: { tipo: "texto" } }))).toEqual({ tipo: "conversa" });
  });

  it("peso, medida, quantidade, rendimento, o tempo da receita, preço e o item parecido nunca são pergunta", () => {
    const tempo = { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 };
    for (const naoEDela of [
      pergunta({ tipo: "operacional", assunto: "tempo_cozimento", campo: "tempo_cozimento_min", entrada: tempo }),
      pergunta({ tipo: "operacional", assunto: "rendimento", campo: "rendimento_porcoes", entrada: tempo }),
      pergunta({ assunto: "linha_nao_lida", campo: "sal" }),
      pergunta({ assunto: "preco_de_compra", campo: "milho verde" }),
      pergunta({ assunto: "medida", campo: "1 peito", entrada: { tipo: "peso", unidade: "g", peso_de: null } }),
      pergunta({ assunto: "mesmo_ingrediente", campo: "alcatra", opcoes: [{ rotulo: "É, sim", resposta: "sim" }] }),
      pergunta({ assunto: "peso_da_embalagem", campo: "farinha" }),
      pergunta({ tipo: "gosto", assunto: "gosto", campo: "gosto" }),
    ]) {
      expect(comoResponder(naoEDela)).toEqual({ tipo: "nenhuma" });
      expect(daCozinha(naoEDela)).toBe(false);
    }
  });
});

describe("a tela de preço antiga responde cada pergunta da conferência no lugar dela", () => {
  it("equipamento e técnica com opções vão para a cozinha; sem opção, para a conversa", () => {
    const equipamento = formaDaConferencia(
      pergunta({
        tipo: "equipamento",
        campo: "forno",
        opcoes: [
          { rotulo: "Tenho", resposta: "sim" },
          { rotulo: "Não tenho", resposta: "nao" },
          { rotulo: "Não sei", resposta: "nao_sei" },
          { rotulo: "Outra", resposta: "outra" },
        ],
      }),
    );
    expect(equipamento).toEqual({
      tipo: "posse",
      lista: "equipamentos",
      id: "forno",
      opcoes: [
        { rotulo: "Tenho", estado: "tem" },
        { rotulo: "Não tenho", estado: "nao_tem" },
        { rotulo: "Não sei", estado: "nao_sei" },
      ],
    });
    expect(formaDaConferencia(pergunta({ tipo: "tecnica", campo: "refogar", opcoes: [{ rotulo: "Faço", resposta: "sim" }] }))).toMatchObject({
      tipo: "posse",
      lista: "tecnicas",
    });
    expect(formaDaConferencia(pergunta({ tipo: "equipamento", campo: "modo_preparo", entrada: { tipo: "texto" } }))).toEqual({ tipo: "conversa" });
  });

  it("o tempo no fogo e o rendimento são da receita; os limites da rotina, da cozinha", () => {
    const tempo = { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 };
    expect(formaDaConferencia(pergunta({ tipo: "operacional", campo: "tempo_cozimento_min", entrada: tempo }))).toEqual({
      tipo: "receita",
      campo: "tempo_cozimento_min",
      entrada: tempo,
    });
    const bocas = { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 };
    expect(
      formaDaConferencia(pergunta({ tipo: "operacional", campo: "bocas_fogao", entrada: bocas, opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }] })),
    ).toEqual({ tipo: "limite", campo: "bocas_fogao", entrada: bocas, comNaoSei: true });
    expect(formaDaConferencia(pergunta({ tipo: "operacional", campo: "bocas_fogao", entrada: bocas }))).toMatchObject({ comNaoSei: false });
    // As horas cozinhando de uma vez também são um limite da cozinha, respondido em horas.
    const horas = { tipo: "horas", unidade: "horas", min: 0.5, max: 12, passo: 0.5, casas: 2 };
    expect(
      formaDaConferencia(pergunta({ tipo: "operacional", campo: "tempo_max_por_fornada_min", entrada: horas, opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }] })),
    ).toEqual({ tipo: "limite", campo: "tempo_max_por_fornada_min", entrada: horas, comNaoSei: true });
    expect(
      formaDaConferencia(pergunta({ tipo: "operacional", campo: "tem_gas_sobrando", opcoes: [{ rotulo: "Sim", resposta: "sim" }] })),
    ).toEqual({ tipo: "sim_nao", campo: "tem_gas_sobrando" });
    expect(formaDaConferencia(pergunta({ tipo: "operacional", campo: "outro", entrada: { tipo: "texto" } }))).toEqual({ tipo: "conversa" });
  });

  it("a pergunta de ingrediente vai pelo assunto que a API diz, nunca pelo texto", () => {
    const linha = pergunta({ assunto: "linha_nao_lida", campo: "temperos a gosto", texto: "Uma pergunta qualquer?" });
    const preco = pergunta({
      assunto: "preco_de_compra",
      campo: "milho verde,creme de leite",
      compras: [
        { ingrediente: "milho verde", quantidade_texto: "1 lata" },
        { ingrediente: "creme de leite", quantidade_texto: "200 g" },
      ],
    });
    expect(formaDaConferencia(linha)).toEqual({ tipo: "linha", campo: "temperos a gosto" });
    expect(formaDaConferencia(preco)).toEqual({ tipo: "preco", ingredientes: ["milho verde", "creme de leite"] });
    // Sem as compras, os nomes saem do campo.
    expect(formaDaConferencia(pergunta({ assunto: "preco_de_compra", campo: "milho verde,creme de leite" }))).toEqual({
      tipo: "preco",
      ingredientes: ["milho verde", "creme de leite"],
    });
    // As listas do detalhe também confirmam.
    expect(formaDaConferencia(pergunta({ campo: "temperos a gosto" }), { linhas: ["temperos a gosto"] })).toEqual({ tipo: "linha", campo: "temperos a gosto" });
    expect(formaDaConferencia(pergunta({ campo: "Milho Verde" }), { semPreco: ["milho verde"] })).toEqual({ tipo: "preco", ingredientes: ["Milho Verde"] });
    // O texto sozinho não decide: sem assunto nem lista, é pela conversa.
    expect(formaDaConferencia(pergunta({ campo: "milho", texto: "Falta comprar: milho. Quanto custa?" }))).toEqual({ tipo: "conversa" });
    expect(formaDaConferencia(pergunta({ campo: "sal", texto: "Não entendi quanto vai de sal nessa receita?" }))).toEqual({ tipo: "conversa" });
    expect(formaDaConferencia(pergunta({ assunto: "preco_de_compra", campo: "" }))).toEqual({ tipo: "conversa" });
    expect(formaDaConferencia(pergunta({ assunto: "peso_da_embalagem", campo: "farinha", texto: "Quanto pesa a embalagem?" }))).toEqual({ tipo: "conversa" });
    expect(formaDaConferencia(pergunta({ tipo: "gosto", assunto: "gosto", campo: "gosto" }))).toEqual({ tipo: "conversa" });
  });

  it("a medida que um peso resolve se responde ali mesmo; a que não resolve vai para a conversa", () => {
    const pesoDe = { cada: "1 colher de sopa", tudo: "2 colheres de sopa" };
    const colheres = pergunta({ assunto: "medida", campo: "2 colheres de sopa de alcaparras", entrada: { tipo: "peso", unidade: "g", peso_de: pesoDe } });
    expect(formaDaConferencia(colheres)).toEqual({ tipo: "peso", campo: "2 colheres de sopa de alcaparras", pesoDe });
    const peito = pergunta({ assunto: "medida", campo: "1 peito", entrada: { tipo: "peso", unidade: "g", peso_de: null } });
    expect(formaDaConferencia(peito)).toEqual({ tipo: "peso", campo: "1 peito", pesoDe: null });
    expect(formaDaConferencia(pergunta({ assunto: "medida", campo: "1 caixinha de leite", entrada: { tipo: "texto" } }))).toEqual({ tipo: "conversa" });
  });
});

describe("as frases da tela", () => {
  it("para onde a receita foi depois da resposta", () => {
    expect(ondeFicou("Pudim", cozinha("com_o_que_tem"))).toBe("Anotei. Pudim foi para Dá para fazer.");
    expect(ondeFicou("Pudim", cozinha("comprando"), false)).toBe("Anotei. Pudim continua em Não gosto de fazer.");
    expect(ondeFicou("Pudim", cozinha("falta_resposta", "Falta o forno."))).toBe("Anotei. Pudim ainda espera uma resposta: Falta o forno.");
    expect(ondeFicou("Pudim", cozinha("nao_da", "Não tem forno!"))).toBe(
      "Anotei. Pudim saiu da lista, porque a cozinha não dá conta: Não tem forno.",
    );
  });

  it("onde a receita trazida entrou", () => {
    expect(ondeEntrou(cozinha("com_o_que_tem"), null)).toBe("Ela está em Dá para fazer.");
    expect(ondeEntrou(cozinha("comprando"), false)).toBe("Ela está em Não gosto de fazer.");
    expect(ondeEntrou(cozinha("falta_resposta", "Falta o tempo."), null)).toBe("Ela está em Falta uma resposta sua: Falta o tempo.");
    expect(ondeEntrou(cozinha("nao_da", "Pede forno."), null)).toBe(
      "Ela não entra na lista, porque a cozinha da senhora não dá conta: Pede forno.",
    );
  });

  it("Pôr preço só quando o checklist libera o aceite, e o que falta vem da API, item por item", () => {
    const com = (checklist: Partial<DetalheDaReceita["checklist"]>): DetalheDaReceita => ({
      ...RECEITA,
      checklist: { ...RECEITA.checklist, ...checklist },
    });
    expect(permissaoDePreco(com({ pode_aceitar: true, falta_para_aceitar: [] }))).toEqual({ pode: true });
    // A frase que repete uma pergunta que não é dela (a linha que a leitura não entendeu) não aparece.
    expect(permissaoDePreco(RECEITA)).toEqual({
      pode: false,
      motivo: RECEITA.checklist.resumo,
      faltam: RECEITA.checklist.falta_para_aceitar.filter((falta) => !/Não entendi quanto vai/.test(falta)),
    });
    expect(RECEITA.checklist.falta_para_aceitar.some((falta) => /Não entendi quanto vai/.test(falta))).toBe(true);
    expect(RECEITA.checklist.falta_para_aceitar.at(-1)).toMatch(/^Confirmar que a senhora tem fogão/);
    expect(
      permissaoDePreco(com({ pode_aceitar: false, resumo: "Pelo que a senhora me disse, esta receita não dá.", falta_para_aceitar: ["Sem forno."] })),
    ).toEqual({ pode: false, motivo: "Pelo que a senhora me disse, esta receita não dá.", faltam: ["Sem forno."] });
  });

  it("os rascunhos da conversa, em primeira pessoa", () => {
    expect(rascunhoDoPreco("Pudim de leite")).toBe("Quero pôr preço na Pudim de leite");
    expect(rascunhoDaPergunta(" Pudim de leite ")).toBe("O que falta para eu poder fazer pudim de leite?");
    expect(rascunhoDaPergunta("CMV")).toBe("O que falta para eu poder fazer CMV?");
  });

  it("o progresso da procura, e os textos arrumados", () => {
    expect(progressoDaDescoberta(1, 1)).toBe("1 página lida, 1 receita encontrada");
    expect(progressoDaDescoberta(3, 0)).toBe("3 páginas lidas, 0 receitas encontradas");
    expect(semQuebrarValor("Comprando R$ 6,00, cabe nos R$ 80,00")).toBe("Comprando R$ 6,00, cabe nos R$ 80,00");
    expect(comMaiuscula("a página abriu")).toBe("A página abriu");
  });
});

describe("o plano B da foto", () => {
  it("o tom é sempre o mesmo para a mesma receita, e varia entre elas", () => {
    expect(tomDaFoto("arroz-com-frango")).toBe(tomDaFoto("arroz-com-frango"));
    const tons = new Set(["a", "b", "c", "d", "e", "f", "g", "h"].map(tomDaFoto));
    expect(tons.size).toBeGreaterThan(2);
  });

  it("o ícone vem do tipo de prato, sem acento nem caixa; sem pista, uma tigela", () => {
    const icone = (nome: string) => render(<IconeDoPrato nome={nome} tamanho={20} />).container.innerHTML;
    expect(icone("Bolo de fubá")).not.toBe(icone("Feijão tropeiro"));
    expect(icone("PUDIM de leite")).toBe(icone("Bolo de fubá"));
    expect(icone("Moqueca de peixe")).toBe(icone("Tilápia assada"));
    expect(icone("Uma coisa qualquer")).toBe(icone("Outra coisa"));
  });
});
