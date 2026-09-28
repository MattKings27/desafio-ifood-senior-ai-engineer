/**
 * O redutor da conversa, com sequências gravadas: o turno normal do contrato,
 * ferramentas e cards, texto e ferramentas intercalados, parar, falhar por
 * categoria, reprodução com `seq` repetido, retomada ao recarregar, valores
 * retirados e card de tipo desconhecido.
 */

import { describe, expect, it } from "vitest";

import type { Conversa, PedidoDeTurno } from "@/lib/api/conversa";
import { contrato, eventosDoContrato } from "@/teste/fixturas";

import { SENTINELA } from "./mascara";

import type { AcaoDaConversa, EstadoDaConversa, RespostaDaConsultora } from "./estado";
import {
  ESTADO_INICIAL,
  TITULO_PADRAO,
  cartaoNaTela,
  estaRespondendo,
  perguntaAntes,
  reduzirConversa,
  ultimaResposta,
} from "./estado";

const EVENTOS = eventosDoContrato<Record<string, unknown>>("chat-eventos.jsonl");
const CONVERSA = contrato<Conversa>("conversa.json");

function aplicar(estado: EstadoDaConversa, ...acoes: AcaoDaConversa[]): EstadoDaConversa {
  return acoes.reduce(reduzirConversa, estado);
}

const pedido = (texto = "Tenho forno.", extras: Partial<PedidoDeTurno> = {}): PedidoDeTurno => ({
  texto,
  id_cliente: "u-1",
  ...extras,
});

/** Uma conversa carregada e vazia, com o envio dela já aceito (turno t-88c1). */
function comTurno(id = "t-88c1"): EstadoDaConversa {
  return aplicar(
    ESTADO_INICIAL,
    { tipo: "carregou", conversa: { ...CONVERSA, mensagens: [] }, em: 0 },
    { tipo: "enviar", pedido: pedido(), em: 10 },
    { tipo: "enviado", idCliente: "u-1", turnoId: id, em: 20 },
  );
}

const eventos = (...lista: Record<string, unknown>[]): AcaoDaConversa => ({ tipo: "eventos", eventos: lista, em: 100 });

describe("carregar", () => {
  it("começa vazio, carrega, e a mesma conversa não é esvaziada ao recarregar", () => {
    const carregando = reduzirConversa(ESTADO_INICIAL, { tipo: "carregar", id: "cv-7f3a" });
    expect(carregando).toMatchObject({ id: "cv-7f3a", carregamento: "carregando", itens: [] });
    const pronta = reduzirConversa(carregando, { tipo: "carregou", conversa: CONVERSA, em: 0 });
    expect(pronta.carregamento).toBe("pronto");
    expect(pronta.itens).toHaveLength(2);
    const denovo = reduzirConversa(pronta, { tipo: "carregar", id: "cv-7f3a" });
    expect(denovo.itens).toHaveLength(2);
    expect(denovo.carregamento).toBe("carregando");
    expect(reduzirConversa(pronta, { tipo: "carregar", id: null })).toMatchObject({ id: null, itens: [] });
  });

  it("sem conversa, pronta e vazia; falha e ausente guardam o erro", () => {
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "semConversa" })).toMatchObject({ carregamento: "pronto", id: null });
    const erro = { categoria: "rede", mensagem: "caiu" };
    expect(reduzirConversa(comTurno(), { tipo: "falhouAoCarregar", erro })).toMatchObject({
      carregamento: "falhou",
      erro,
      turno: null,
    });
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "falhouAoCarregar", erro, ausente: true }).carregamento).toBe("ausente");
  });

  it("a conversa do contrato: a mensagem dela e a resposta com card e atividades", () => {
    const estado = reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa: CONVERSA, em: 0 });
    const [dela, resposta] = estado.itens;
    expect(dela).toMatchObject({ tipo: "senhora", texto: "Quero vender arroz com frango.", envio: "enviada", quandoTexto: "hoje, 14:58" });
    expect(resposta).toMatchObject({
      tipo: "consultora",
      estado: "concluido",
      rascunho: false,
      texto: "Dá pra fazer hoje, com o que a senhora tem. A porção sai **R$ 2,47** de ingrediente.",
      atividades: [
        { rotuloFeito: "conferi se a senhora consegue fazer arroz com frango", ok: true },
        { rotuloFeito: "calculei o custo por porção", ok: true },
      ],
    });
    expect((resposta as RespostaDaConsultora).cartoes).toEqual([
      {
        id: "k-1",
        tipo: "custo_porcao",
        dados: { prato: "Arroz com frango", total: { valor: 2.47, texto: "R$ 2,47" } },
        ref: { rota: "/api/receitas/arroz-com-frango/custo" },
        geradoTexto: "conta de hoje, 14:59",
        aoVivo: false,
      },
    ]);
    expect(estado.titulo).toBe("Arroz com frango");
  });

  it("mensagens guardadas estranhas são ignoradas, e os campos extras são lidos com cuidado", () => {
    const conversa: Conversa = {
      id: "cv-x",
      titulo: "  ",
      turno_em_andamento: null,
      mensagens: [
        { id: 3 as unknown as string, papel: "senhora", partes: [], quando_texto: "" },
        { id: "m-0", papel: "sistema" as "senhora", partes: [], quando_texto: "" },
        {
          id: "m-1",
          papel: "senhora",
          partes: [{ tipo: "texto", texto: "Oi" }],
          quando_texto: "hoje",
          contexto: { tela: "despensa", tipo: "ingrediente", id: "alho", rotulo: "Alho" },
          turno_id: "t-1",
        },
        {
          id: "m-2",
          papel: "consultora",
          partes: [
            { tipo: "texto", texto: "Parei no meio: ", rascunho: true },
            { tipo: "texto", texto: "  " },
            { tipo: "cartao", cartao: { cartao_id: "k-9", tipo_cartao: "inventado", ref: { rota: null }, gerado_texto: "", dados: {} } },
            { tipo: "cartao", cartao: { cartao_id: "k-1", tipo_cartao: "orcamento", ref: { rota: 3 } as never, gerado_texto: "", dados: null } },
            { tipo: "cartao", cartao: { cartao_id: "k-1", tipo_cartao: "orcamento", ref: { rota: "/api/orcamento", parametros: { a: 1 } }, gerado_texto: "agora", dados: { restante: 1 } } },
          ],
          quando_texto: "hoje",
          estado: "cancelado",
          retirados: 2.7,
          atividades: [{ rotulo_feito: "olhei a despensa" }, { rotulo_feito: "rodei calcular_cmv", ok: false }, { rotulo_feito: "vi o orçamento", ok: false }],
          acao_resultado: { ok: false, texto: "Não anotei." },
          erro: { categoria: 5 as never, mensagem: 7 as never },
          sugestoes: [{ rotulo: "De novo", texto: "Pergunta de novo." }],
        },
        {
          id: "m-3",
          papel: "consultora",
          partes: "quebrado" as never,
          quando_texto: "hoje",
          estado: "inventado",
          atividades: "nada" as never,
          erro: "texto" as never,
          acao_resultado: { ok: true, texto: 3 } as never,
        },
      ],
    };
    const estado = reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa, em: 0 });
    expect(estado.titulo).toBe(TITULO_PADRAO);
    expect(estado.itens.map((item) => item.chave)).toEqual(["m:m-1", "m:m-2", "m:m-3"]);
    expect(estado.itens[0]).toMatchObject({ contexto: { tela: "despensa", tipo: "ingrediente", id: "alho", rotulo: "Alho" }, turnoId: "t-1" });
    const parada = estado.itens[1] as RespostaDaConsultora;
    expect(parada).toMatchObject({
      estado: "cancelado",
      rascunho: true,
      texto: "Parei no meio:",
      retirados: 2,
      resultados: [{ ok: false, texto: "Não anotei." }],
      erro: { categoria: "consultora", mensagem: "" },
      atividades: [
        { rotuloFeito: "olhei a despensa", ok: true },
        { rotuloFeito: "vi o orçamento", ok: false },
      ],
    });
    expect(parada.cartoes).toEqual([
      { id: "k-1", tipo: "orcamento", dados: { restante: 1 }, ref: { rota: "/api/orcamento", parametros: { a: 1 } }, geradoTexto: "agora", aoVivo: false },
    ]);
    const quebrada = estado.itens[2] as RespostaDaConsultora;
    expect(quebrada).toMatchObject({ estado: "concluido", texto: "", cartoes: [], atividades: [], resultados: [], erro: null });
    // A última resposta terminou bem: as sugestões dela ficam para os chips.
    expect(estado.sugestoes).toEqual([]);
  });

  it("um turno em andamento é assinado desde o começo; o mesmo turno continua", () => {
    const rodando: Conversa = {
      ...CONVERSA,
      turno_em_andamento: { turno_id: "t-88c1", estado: "em_andamento", ultimo_seq: 7, iniciado_texto: "hoje" },
    };
    const estado = reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa: rodando, em: 50 });
    expect(estado.turno).toMatchObject({ id: "t-88c1", idCliente: null, fase: "conectando", ultimoSeq: 0, iniciadoEm: 50 });
    expect(estado.sugestoes).toEqual([]);

    const andou = reduzirConversa(estado, eventos(...EVENTOS.slice(0, 3)));
    const recarregada = reduzirConversa(andou, { tipo: "carregou", conversa: rodando, em: 60 });
    expect(recarregada.turno).toBe(andou.turno);

    const terminado: Conversa = { ...rodando, turno_em_andamento: { ...rodando.turno_em_andamento!, estado: "concluido" } };
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa: terminado, em: 0 }).turno).toBeNull();
    const semEstado: Conversa = { ...rodando, turno_em_andamento: { turno_id: "t-9" } as never };
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa: semEstado, em: 0 }).turno?.id).toBe("t-9");
  });

  it("o envio dela ainda a caminho: a bolha otimista sobrevive a um recarregamento", () => {
    const enviando = aplicar(
      ESTADO_INICIAL,
      { tipo: "carregou", conversa: { ...CONVERSA, mensagens: [] }, em: 0 },
      { tipo: "enviar", pedido: pedido(), em: 10 },
    );
    const recarregada = reduzirConversa(enviando, { tipo: "carregou", conversa: CONVERSA, em: 20 });
    expect(recarregada.turno?.fase).toBe("enviando");
    expect(recarregada.itens.at(-1)).toMatchObject({ tipo: "senhora", idCliente: "u-1", envio: "enviando" });

    // Outra conversa não herda nada.
    const outra = reduzirConversa(enviando, { tipo: "carregou", conversa: { ...CONVERSA, id: "cv-outra" }, em: 20 });
    expect(outra.turno).toBeNull();
  });
});

describe("enviar", () => {
  it("bolha otimista, turno enviando, e o 202 abre a conexão", () => {
    const enviando = aplicar(ESTADO_INICIAL, { tipo: "carregou", conversa: { ...CONVERSA, mensagens: [] }, em: 0 }, {
      tipo: "enviar",
      pedido: pedido("Oi", { contexto: { tela: "despensa", tipo: "tela", id: "despensa" } }),
      em: 10,
    });
    expect(estaRespondendo(enviando)).toBe(true);
    expect(enviando.itens[0]).toMatchObject({ tipo: "senhora", chave: "c:u-1", texto: "Oi", envio: "enviando", contexto: { tela: "despensa" } });
    expect(enviando.turno).toMatchObject({ id: null, idCliente: "u-1", fase: "enviando" });
    expect(reduzirConversa(enviando, { tipo: "enviar", pedido: pedido("outra"), em: 11 })).toBe(enviando);

    const aceito = reduzirConversa(enviando, { tipo: "enviado", idCliente: "u-1", turnoId: "t-1", em: 30 });
    expect(aceito.turno).toMatchObject({ id: "t-1", fase: "conectando", iniciadoEm: 30 });
    expect(aceito.itens[0]).toMatchObject({ envio: "enviada", turnoId: "t-1" });
    expect(reduzirConversa(aceito, { tipo: "enviado", idCliente: "u-1", turnoId: "t-2", em: 40 })).toBe(aceito);
    expect(reduzirConversa(aceito, { tipo: "enviado", idCliente: "u-9", turnoId: "t-2", em: 40 })).toBe(aceito);
  });

  it("não enviou: a bolha diz, e reenviar usa o mesmo pedido", () => {
    const enviando = aplicar(ESTADO_INICIAL, { tipo: "carregou", conversa: { ...CONVERSA, mensagens: [] }, em: 0 }, {
      tipo: "enviar",
      pedido: pedido(),
      em: 10,
    });
    const erro = { categoria: "rede", mensagem: "sem conexão" };
    expect(reduzirConversa(enviando, { tipo: "envioFalhou", idCliente: "outro", erro })).toBe(enviando);
    const falhou = reduzirConversa(enviando, { tipo: "envioFalhou", idCliente: "u-1", erro });
    expect(falhou.turno).toBeNull();
    expect(falhou.itens[0]).toMatchObject({ envio: "falhou", erroDoEnvio: erro });

    const denovo = reduzirConversa(falhou, { tipo: "reenviar", idCliente: "u-1", em: 50 });
    expect(denovo.itens[0]).toMatchObject({ envio: "enviando", erroDoEnvio: null });
    expect(denovo.turno).toMatchObject({ idCliente: "u-1", fase: "enviando", pedido: pedido() });
    expect(reduzirConversa(denovo, { tipo: "reenviar", idCliente: "u-1", em: 60 })).toBe(denovo);
    expect(reduzirConversa(falhou, { tipo: "reenviar", idCliente: "nenhum", em: 60 })).toBe(falhou);
  });

  it("reenviar uma bolha já enviada mantém o estado dela", () => {
    const enviada = aplicar(comTurno(), eventos(...EVENTOS));
    const guardada = reduzirConversa(enviada, { tipo: "reenviar", idCliente: "u-1", em: 1 });
    expect(guardada.itens[0]).toMatchObject({ envio: "enviada" });
  });

  it("recusado (já havia um turno): a bolha otimista sai", () => {
    const enviando = aplicar(ESTADO_INICIAL, { tipo: "enviar", pedido: pedido(), em: 0 });
    expect(reduzirConversa(enviando, { tipo: "envioRecusado", idCliente: "x" })).toBe(enviando);
    const recusado = reduzirConversa(enviando, { tipo: "envioRecusado", idCliente: "u-1" });
    expect(recusado.itens).toEqual([]);
    expect(recusado.turno).toBeNull();
  });
});

describe("o turno do contrato, evento a evento", () => {
  it("termina com o texto conferido, o card, os passos e as sugestões", () => {
    const fim = reduzirConversa(comTurno(), eventos(...EVENTOS));
    expect(fim.turno).toBeNull();
    const resposta = ultimaResposta(fim);
    expect(resposta).toMatchObject({
      estado: "concluido",
      rascunho: false,
      texto: "Dá pra fazer. A porção sai R$ 2,47 de ingrediente.",
      retirados: 0,
      atividades: [{ rotuloFeito: "conferi se a senhora consegue fazer arroz com frango", ok: true }],
      incompleta: false,
      pedido: pedido(),
    });
    expect(resposta?.cartoes.map((c) => [c.tipo, c.aoVivo])).toEqual([["viabilidade", true]]);
    expect(fim.sugestoes.map((s) => s.rotulo)).toEqual(["Quanto cobrar?", "Outra receita"]);
    expect(fim.itens[0]).toMatchObject({ tipo: "senhora", envio: "enviada", turnoId: "t-88c1" });
    expect(perguntaAntes(fim, resposta!.chave)).toMatchObject({ texto: "Tenho forno." });
  });

  it("as fases mudam com os eventos, e o recurso alterado é guardado", () => {
    let estado = reduzirConversa(comTurno(), eventos(EVENTOS[0]!));
    expect(estado.turno?.fase).toBe("pensando");
    estado = reduzirConversa(estado, eventos(EVENTOS[1]!));
    expect(estado.turno?.fase).toBe("trabalhando");
    expect(estado.turno?.atividades[0]).toMatchObject({ id: "at-1", ferramenta: "avaliar_receita", estado: "fazendo" });
    estado = reduzirConversa(estado, eventos(EVENTOS[2]!));
    expect(estado.turno?.fase).toBe("pensando");
    estado = reduzirConversa(estado, eventos(EVENTOS[3]!, EVENTOS[4]!));
    expect(estado.turno?.fase).toBe("escrevendo");
    expect(estado.turno?.rascunho).toBe(`Dá pra fazer. A porção sai ${SENTINELA} de ingrediente`);
    estado = reduzirConversa(estado, eventos(EVENTOS[5]!, EVENTOS[6]!));
    expect(estado.turno?.recursos).toEqual(["receitas", "perfil"]);
    expect(estado.turno?.fase).toBe("conferido");
    expect(estado.turno?.textoFinal).toBe("Dá pra fazer. A porção sai R$ 2,47 de ingrediente.");
  });

  it("repetido, de outro turno ou sem forma: ignorado; um salto no seq marca a lacuna", () => {
    const inicio = reduzirConversa(comTurno(), eventos(EVENTOS[0]!, EVENTOS[1]!));
    expect(reduzirConversa(inicio, eventos(EVENTOS[0]!, EVENTOS[1]!))).toBe(inicio);
    expect(reduzirConversa(inicio, eventos({ ...EVENTOS[2]!, turno_id: "t-outro" }))).toBe(inicio);
    expect(reduzirConversa(inicio, eventos(null as never, { seq: 9 }))).toBe(inicio);
    const pulou = reduzirConversa(inicio, eventos(EVENTOS[5]!));
    expect(pulou.turno?.lacuna).toBe(true);
    const fim = reduzirConversa(pulou, eventos({ seq: 9, tipo: "turno.concluido" }));
    expect(ultimaResposta(fim)?.incompleta).toBe(true);
    // Sem turno, nenhum evento muda nada.
    expect(reduzirConversa(ESTADO_INICIAL, eventos(EVENTOS[0]!))).toBe(ESTADO_INICIAL);
  });

  it("evento sem seq anda sem mexer no último visto; tipo novo só anda o seq", () => {
    const estado = reduzirConversa(comTurno(), eventos({ tipo: "texto.parcial", delta: "Oi" }, { seq: 3, tipo: "algo.novo" }));
    expect(estado.turno).toMatchObject({ rascunho: "Oi", ultimoSeq: 3 });
  });

  it("ferramentas e texto intercalados, com atividade repetida, falhada e sem id", () => {
    const estado = reduzirConversa(
      comTurno(),
      eventos(
        { seq: 1, tipo: "turno.iniciado" },
        { seq: 2, tipo: "texto.parcial", delta: "Vou olhar. " },
        { seq: 3, tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "mcp_mise_diagnostico_despensa", detalhe: "olhando até R$ 30" },
        { seq: 4, tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "diagnostico_despensa", rotulo: "olhando a despensa", rotulo_feito: "olhei a despensa" },
        { seq: 5, tipo: "atividade.iniciada", ferramenta: "web_search" },
        { seq: 6, tipo: "atividade.concluida", atividade_id: "a", ok: false, resumo: "não abriu" },
        { seq: 7, tipo: "texto.parcial", delta: "" },
        { seq: 8, tipo: "atividade.concluida", atividade_id: "at-5", ok: true },
        { seq: 9, tipo: "texto.comentario", texto: "  Achei algo.  " },
        { seq: 10, tipo: "texto.comentario", texto: " " },
      ),
    );
    const turno = estado.turno!;
    expect(turno.atividades).toEqual([
      { id: "a", ferramenta: "diagnostico_despensa", rotulo: "olhando a despensa", rotuloFeito: "olhei a despensa", estado: "falhou", resumo: "não abriu" },
      { id: "at-5", ferramenta: "web_search", rotulo: "pesquisando receitas na internet", rotuloFeito: "pesquisei receitas na internet", estado: "feito" },
    ]);
    // "Vou olhar." veio antes da ferramenta: era bastidor, e o rascunho recomeçou.
    expect(turno.rascunho).toBe("Achei algo.");
    expect(turno.fase).toBe("escrevendo");

    const comDetalhe = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "atividade.iniciada", atividade_id: "b", ferramenta: "web_search", detalhe: "buscando até R$ 30" }));
    expect(comDetalhe.turno?.atividades[0]?.detalhe).toBe("buscando até R$ ···");
    const soComentario = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "texto.comentario", texto: "Oi" }));
    expect(soComentario.turno?.rascunho).toBe("Oi");
  });

  it("cards: tipo desconhecido é ignorado, o mesmo id é trocado, a ação pode trazer card", () => {
    const estado = reduzirConversa(
      comTurno(),
      eventos(
        { seq: 1, tipo: "cartao", cartao_id: "k-1", tipo_cartao: "inventado", dados: {}, ref: { rota: null } },
        { seq: 2, tipo: "cartao", cartao_id: "", tipo_cartao: "orcamento", dados: {}, ref: {} },
        { seq: 3, tipo: "cartao", cartao_id: "k-2", tipo_cartao: "orcamento", dados: { v: 1 }, ref: { rota: "/api/orcamento" }, gerado_texto: "conta de hoje" },
        { seq: 4, tipo: "cartao", cartao_id: "k-2", tipo_cartao: "orcamento", dados: { v: 2 }, ref: "x" },
        { seq: 5, tipo: "acao.resultado", ok: true, texto: "Anotei: a senhora tem forno.", cartao: { cartao_id: "k-3", tipo_cartao: "cozinha_atualizada", dados: {}, ref: { rota: "/api/perfil" } } },
        { seq: 6, tipo: "acao.resultado", ok: false },
        { seq: 7, tipo: "acao.resultado", ok: false, texto: "Não deu." },
        { seq: 8, tipo: "cartao" },
      ),
    );
    expect(estado.turno?.cartoes.map((c) => [c.id, c.tipo, c.dados, c.ref.rota])).toEqual([
      ["k-2", "orcamento", { v: 2 }, null],
      ["k-3", "cozinha_atualizada", {}, "/api/perfil"],
    ]);
    expect(estado.turno?.resultados).toEqual([
      { ok: true, texto: "Anotei: a senhora tem forno." },
      { ok: false, texto: "Não deu." },
    ]);
  });

  it("valores retirados do texto final aparecem na resposta", () => {
    const fim = reduzirConversa(
      comTurno(),
      eventos(
        { seq: 1, tipo: "texto.final", texto: "Sai [valor retirado].", retirados: 1.9 },
        { seq: 2, tipo: "texto.final" },
        { seq: 3, tipo: "turno.concluido" },
      ),
    );
    expect(ultimaResposta(fim)).toMatchObject({ texto: "Sai [valor retirado].", retirados: 1, rascunho: false });
    const semRetirados = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "texto.final", texto: "Ok", retirados: -3 }));
    expect(semRetirados.turno?.retirados).toBe(0);
  });

  it("o texto de antes de uma ferramenta nova sai do rascunho; a mesma atividade repetida, não", () => {
    const estado = reduzirConversa(
      comTurno(),
      eventos(
        { seq: 1, tipo: "texto.parcial", delta: "Agora vou conferir se a cozinha dela dá conta." },
        { seq: 2, tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "avaliar_receita" },
        { seq: 3, tipo: "texto.parcial", delta: "Dá para fazer" },
        { seq: 4, tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "avaliar_receita", rotulo: "conferindo" },
        { seq: 5, tipo: "texto.parcial", delta: " as três." },
      ),
    );
    expect(estado.turno?.rascunho).toBe("Dá para fazer as três.");
  });

  it("concluído sem texto final: a resposta fica incompleta e a loja busca a gravada", () => {
    const fim = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "texto.parcial", delta: "Rascunho" }, { seq: 2, tipo: "turno.concluido" }));
    expect(ultimaResposta(fim)).toMatchObject({ rascunho: true, incompleta: true, texto: "Rascunho" });
  });
});

describe("parar e falhar", () => {
  it("parar vira cancelando; o que chega depois não muda a fase; o fim fica mascarado", () => {
    const escrevendo = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "texto.parcial", delta: "A porção sai R$ 7" }));
    const parando = reduzirConversa(escrevendo, { tipo: "parar" });
    expect(parando.turno).toMatchObject({ fase: "cancelando", faseAnterior: "escrevendo" });
    expect(reduzirConversa(parando, { tipo: "parar" })).toBe(parando);
    const aindaParando = reduzirConversa(parando, eventos({ seq: 2, tipo: "atividade.iniciada", atividade_id: "x", ferramenta: "web_search" }));
    expect(aindaParando.turno?.fase).toBe("cancelando");
    const comFinal = reduzirConversa(aindaParando, eventos({ seq: 3, tipo: "texto.final", texto: "Pronto.", retirados: 0 }));
    expect(comFinal.turno?.fase).toBe("cancelando");

    const cancelado = reduzirConversa(aindaParando, eventos({ seq: 4, tipo: "turno.cancelado" }));
    expect(ultimaResposta(cancelado)).toMatchObject({ estado: "cancelado", rascunho: true, texto: "A porção sai R$ 7", sugestoes: [] });
  });

  it("parar sem turno aceito não faz nada; a falha ao parar volta à fase de antes", () => {
    const enviando = aplicar(ESTADO_INICIAL, { tipo: "enviar", pedido: pedido(), em: 0 });
    expect(reduzirConversa(enviando, { tipo: "parar" })).toBe(enviando);
    expect(reduzirConversa(comTurno(), { tipo: "pararFalhou" })).toEqual(comTurno());
    const voltou = aplicar(comTurno(), { tipo: "parar" }, { tipo: "pararFalhou" });
    expect(voltou.turno).toMatchObject({ fase: "conectando", faseAnterior: null });
    const semAnterior = reduzirConversa(
      { ...comTurno(), turno: { ...comTurno().turno!, fase: "cancelando", faseAnterior: null } },
      { tipo: "pararFalhou" },
    );
    expect(semAnterior.turno?.fase).toBe("pensando");
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "pararFalhou" })).toBe(ESTADO_INICIAL);
  });

  it.each(["rede", "tempo", "consultora", "regra"])("falhou por %s, com a mensagem", (categoria) => {
    const fim = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "turno.falhou", categoria, mensagem: "Não consegui." }));
    expect(ultimaResposta(fim)).toMatchObject({ estado: "falhou", erro: { categoria, mensagem: "Não consegui." }, rascunho: true });
  });

  it("interrompido (o backend reiniciou), e falha sem categoria", () => {
    const interrompido = reduzirConversa(comTurno(), eventos({ seq: 1, tipo: "turno.falhou", interrompido: true }));
    expect(ultimaResposta(interrompido)).toMatchObject({
      estado: "interrompido",
      erro: { categoria: "consultora", mensagem: "", interrompido: true },
    });
  });
});

describe("o resto", () => {
  it("conexão muda só no turno certo, e só quando muda", () => {
    const estado = comTurno();
    const aberta = reduzirConversa(estado, { tipo: "conexao", turnoId: "t-88c1", estado: "aberta" });
    expect(aberta.turno?.conexao).toBe("aberta");
    expect(reduzirConversa(aberta, { tipo: "conexao", turnoId: "t-88c1", estado: "aberta" })).toBe(aberta);
    expect(reduzirConversa(aberta, { tipo: "conexao", turnoId: "t-x", estado: "reconectando" })).toBe(aberta);
    expect(reduzirConversa(ESTADO_INICIAL, { tipo: "conexao", turnoId: "t", estado: "aberta" })).toBe(ESTADO_INICIAL);
  });

  it("renomear só a conversa aberta; nome vazio vira o padrão", () => {
    const estado = reduzirConversa(ESTADO_INICIAL, { tipo: "carregou", conversa: CONVERSA, em: 0 });
    expect(reduzirConversa(estado, { tipo: "renomeou", id: "cv-7f3a", titulo: " Bolo " }).titulo).toBe("Bolo");
    expect(reduzirConversa(estado, { tipo: "renomeou", id: "cv-7f3a", titulo: "  " }).titulo).toBe(TITULO_PADRAO);
    expect(reduzirConversa(estado, { tipo: "renomeou", id: "outra", titulo: "x" })).toBe(estado);
  });

  it("perguntas sobre o estado", () => {
    expect(estaRespondendo(ESTADO_INICIAL)).toBe(false);
    expect(ultimaResposta(ESTADO_INICIAL)).toBeNull();
    const soDela = aplicar(ESTADO_INICIAL, { tipo: "enviar", pedido: pedido(), em: 0 });
    expect(ultimaResposta(soDela)).toBeNull();
    expect(perguntaAntes(soDela, "nenhuma")).toBeNull();
  });

  it("cartaoNaTela aceita a forma do evento e a guardada", () => {
    expect(cartaoNaTela(null, true)).toBeNull();
    expect(cartaoNaTela({ cartao_id: "k", tipo: "decisao", ref: { rota: "/api/cardapio" } }, true)).toMatchObject({
      id: "k",
      tipo: "decisao",
      dados: null,
      geradoTexto: "",
      aoVivo: true,
    });
  });
});
