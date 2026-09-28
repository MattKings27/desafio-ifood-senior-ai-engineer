/**
 * A loja da conversa, sobre um transporte falso: carregar, enviar (202, 409 e
 * falha), o fluxo do turno com o quadro de animação na mão do teste, parar,
 * a retomada, a lista de conversas, a disponibilidade e as avisos.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { Conversa } from "@/lib/api/conversa";
import { contrato, eventosDoContrato } from "@/teste/fixturas";
import { conversaVazia, esperarPromessas, lojaDeTeste, mensagem, resumo } from "@/teste/conversa";

import type { OuvintesDoTurno, Transporte } from "./transporte";
import {
  AVISO_DE_TURNO_RODANDO,
  ESPERA_ANTES_DE_CONSULTAR_MS,
  LIMITE_DE_CARACTERES,
  MOTIVO_FORA_DO_AR,
  NOVA_VERIFICACAO_MS,
  SILENCIO_MAXIMO_MS,
  agendarNoQuadro,
  paraErroNaTela,
} from "./loja";

const EVENTOS = eventosDoContrato<Record<string, unknown> & { tipo: string }>("chat-eventos.jsonl");
const CONVERSA = contrato<Conversa>("conversa.json");

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("agendarNoQuadro", () => {
  it("roda uma vez, no quadro ou na reserva de tempo, e pode ser cancelado", () => {
    vi.useFakeTimers();
    const quadros: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (tarefa: FrameRequestCallback) => quadros.push(tarefa));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const tarefa = vi.fn();
    agendarNoQuadro(tarefa);
    quadros[0]?.(0);
    vi.advanceTimersByTime(200);
    expect(tarefa).toHaveBeenCalledTimes(1);

    const outra = vi.fn();
    const cancelar = agendarNoQuadro(outra);
    cancelar();
    quadros[1]?.(0);
    vi.advanceTimersByTime(200);
    expect(outra).not.toHaveBeenCalled();
    expect(cancelAnimationFrame).toHaveBeenCalled();
  });

  it("sem quadro de animação (aba de fundo), a reserva de tempo roda", () => {
    vi.useFakeTimers();
    vi.stubGlobal("requestAnimationFrame", undefined);
    vi.stubGlobal("cancelAnimationFrame", undefined);
    const tarefa = vi.fn();
    const cancelar = agendarNoQuadro(tarefa);
    vi.advanceTimersByTime(100);
    expect(tarefa).toHaveBeenCalledTimes(1);
    cancelar();
  });
});

describe("paraErroNaTela", () => {
  it("a frase da API, ou a do caminho", () => {
    expect(paraErroNaTela(new ErroDoMotor("Não achei.", "ausente"))).toEqual({ categoria: "ausente", mensagem: "Não achei." });
    expect(paraErroNaTela(new Error("x"))).toEqual({ categoria: "rede", mensagem: MENSAGENS.rede });
  });
});

describe("abrir e ativar", () => {
  it("ativar carrega a conversa atual da lista, e a disponibilidade com o modelo", async () => {
    const t = lojaDeTeste({
      listar: async () => ({ atual: "cv-7f3a", conversas: [resumo("cv-7f3a")] }),
      ler: async () => CONVERSA,
    });
    const ouvinte = vi.fn();
    const sair = t.loja.assinar(ouvinte);
    t.loja.ativar();
    t.loja.ativar();
    await esperarPromessas(10);
    expect(t.transporte.listar).toHaveBeenCalled();
    expect(t.transporte.ler).toHaveBeenCalledWith("cv-7f3a");
    expect(t.loja.ler().conversa).toMatchObject({ id: "cv-7f3a", carregamento: "pronto" });
    expect(t.loja.ler().disponibilidade).toEqual({ disponivel: true, motivo: null, modelo: "claude-fable-5-1", conferida: true });
    expect(ouvinte).toHaveBeenCalled();
    sair();
  });

  it("sem atual, abre a primeira; sem nenhuma, fica pronta e vazia", async () => {
    const t = lojaDeTeste({ listar: async () => ({ atual: null, conversas: [resumo("cv-a"), resumo("cv-b")] }) });
    await t.loja.abrirConversa();
    expect(t.transporte.ler).toHaveBeenCalledWith("cv-a");

    const vazia = lojaDeTeste();
    await vazia.loja.abrirConversa();
    expect(vazia.loja.ler().conversa).toMatchObject({ id: null, carregamento: "pronto" });
    expect(vazia.loja.ler().lista).toMatchObject({ carregamento: "pronta", atual: null, conversas: [] });
  });

  it("uma lista estranha vira lista vazia", async () => {
    const t = lojaDeTeste({ listar: async () => ({ atual: 3, conversas: [{ id: 1 }, null, "x", resumo("cv-1")] }) as never });
    await t.loja.carregarLista();
    expect(t.loja.ler().lista.conversas.map((c) => c.id)).toEqual(["cv-1"]);
    const nada = lojaDeTeste({ listar: async () => null as never });
    await nada.loja.carregarLista();
    expect(nada.loja.ler().lista.conversas).toEqual([]);
  });

  it("falha ao abrir: ausente (404) ou falhou; a resposta velha de outra abertura é ignorada", async () => {
    const ausente = lojaDeTeste({ ler: async () => Promise.reject(new ErroDoMotor("Não achei.", "ausente")) });
    await ausente.loja.abrirConversa("cv-x");
    expect(ausente.loja.ler().conversa).toMatchObject({ carregamento: "ausente", erro: { categoria: "ausente" } });

    let soltar: (c: Conversa) => void = () => {};
    const devagar = lojaDeTeste({
      ler: vi
        .fn()
        .mockImplementationOnce(() => new Promise<Conversa>((resolver) => (soltar = resolver)))
        .mockImplementation(async (id: string) => conversaVazia(id)),
    });
    const primeira = devagar.loja.abrirConversa("cv-lenta");
    await devagar.loja.abrirConversa("cv-rapida");
    soltar(conversaVazia("cv-lenta"));
    await primeira;
    expect(devagar.loja.ler().conversa.id).toBe("cv-rapida");

    let rejeitar: (erro: unknown) => void = () => {};
    const falhaVelha = lojaDeTeste({
      ler: vi
        .fn()
        .mockImplementationOnce(() => new Promise<Conversa>((_ok, erro) => (rejeitar = erro)))
        .mockImplementation(async (id: string) => conversaVazia(id)),
    });
    const velha = falhaVelha.loja.abrirConversa("cv-1");
    await falhaVelha.loja.abrirConversa("cv-2");
    rejeitar(new Error("caiu"));
    await velha;
    expect(falhaVelha.loja.ler().conversa).toMatchObject({ id: "cv-2", carregamento: "pronto" });

    let listaLenta: (l: unknown) => void = () => {};
    const lista = lojaDeTeste({
      listar: vi
        .fn()
        .mockImplementationOnce(() => new Promise((resolver) => (listaLenta = resolver)))
        .mockImplementation(async () => ({ atual: null, conversas: [] })),
    });
    const semId = lista.loja.abrirConversa();
    await lista.loja.abrirConversa("cv-9");
    listaLenta({ atual: "cv-1", conversas: [] });
    await semId;
    expect(lista.loja.ler().conversa.id).toBe("cv-9");
  });

  it("ativar depois de uma conversa pronta só recarrega a lista", async () => {
    const t = lojaDeTeste();
    await t.loja.abrirConversa("cv-1");
    t.transporte.ler.mockClear();
    t.loja.ativar();
    await esperarPromessas();
    expect(t.transporte.ler).not.toHaveBeenCalled();
    expect(t.transporte.listar).toHaveBeenCalled();
  });

  it("recarregar: nada sem conversa; falha em silêncio; e a conversa trocada no meio não é sobrescrita", async () => {
    const t = lojaDeTeste();
    await t.loja.recarregarConversa();
    expect(t.transporte.ler).not.toHaveBeenCalled();

    await t.loja.abrirConversa("cv-1");
    t.transporte.ler.mockRejectedValueOnce(new Error("caiu"));
    await t.loja.recarregarConversa();
    expect(t.loja.ler().conversa.carregamento).toBe("pronto");

    let soltar: (c: Conversa) => void = () => {};
    t.transporte.ler.mockImplementationOnce(() => new Promise<Conversa>((resolver) => (soltar = resolver)));
    const recarga = t.loja.recarregarConversa();
    await t.loja.abrirConversa("cv-2");
    soltar(conversaVazia("cv-1", "Velha"));
    await recarga;
    expect(t.loja.ler().conversa.id).toBe("cv-2");
  });

  it("a lista que falha antes de ficar pronta diz isso; depois de pronta, fica como estava", async () => {
    const t = lojaDeTeste({ listar: async () => Promise.reject(new Error("caiu")) });
    expect(await t.loja.carregarLista()).toBeNull();
    expect(t.loja.ler().lista.carregamento).toBe("falhou");

    const pronta = lojaDeTeste();
    await pronta.loja.carregarLista();
    pronta.transporte.listar.mockRejectedValueOnce(new Error("caiu"));
    await pronta.loja.carregarLista();
    expect(pronta.loja.ler().lista.carregamento).toBe("pronta");
  });
});

describe("conversas", () => {
  it("nova conversa vira a aberta; falha vira aviso", async () => {
    const t = lojaDeTeste();
    expect(await t.loja.novaConversa()).toBe(true);
    expect(t.loja.ler().conversa).toMatchObject({ id: "cv-nova", carregamento: "pronto" });

    t.transporte.criar.mockRejectedValueOnce(new ErroDoMotor("Não criei.", "uso"));
    expect(await t.loja.novaConversa()).toBe(false);
    expect(t.loja.ler().aviso).toMatchObject({ texto: "Não criei.", tom: "erro" });
    t.loja.limparAviso();
    t.loja.limparAviso();
    expect(t.loja.ler().aviso).toBeNull();
  });

  it("apagar a aberta abre a atual que o backend disse, ou a primeira da lista", async () => {
    const t = lojaDeTeste({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] }),
      apagar: async (id: string) => ({ apagada: id, atual: "cv-2" }),
    });
    await t.loja.abrirConversa();
    expect(await t.loja.apagarConversa("cv-1")).toBe(true);
    expect(t.loja.ler().conversa.id).toBe("cv-2");

    const semAtual = lojaDeTeste({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-3")] }),
      apagar: async (id: string) => ({ apagada: id, atual: id }),
    });
    await semAtual.loja.abrirConversa();
    await semAtual.loja.apagarConversa("cv-1");
    expect(semAtual.loja.ler().conversa.id).toBe("cv-3");

    const outra = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] }) });
    await outra.loja.abrirConversa();
    await outra.loja.apagarConversa("cv-2");
    expect(outra.loja.ler().conversa.id).toBe("cv-1");

    const ultima = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1")] }), apagar: async () => null as never });
    await ultima.loja.abrirConversa();
    ultima.transporte.listar.mockResolvedValue({ atual: null, conversas: [] });
    await ultima.loja.apagarConversa("cv-1");
    expect(ultima.loja.ler().conversa).toMatchObject({ id: null, carregamento: "pronto" });

    ultima.transporte.apagar.mockRejectedValueOnce(new Error("caiu"));
    expect(await ultima.loja.apagarConversa("cv-1")).toBe(false);
    expect(ultima.loja.ler().aviso?.tom).toBe("erro");
  });

  it("renomear: limpa o nome, muda a aberta e a lista; vazio não vai; falha avisa", async () => {
    const t = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] }) });
    await t.loja.abrirConversa();
    expect(await t.loja.renomearConversa("cv-1", "   ")).toBe(false);
    expect(await t.loja.renomearConversa("cv-1", "  Bolo   de\nmilho ")).toBe(true);
    expect(t.transporte.renomear).toHaveBeenCalledWith("cv-1", "Bolo de milho");
    expect(t.loja.ler().conversa.titulo).toBe("Bolo de milho");
    expect(t.loja.ler().lista.conversas.map((c) => c.titulo)).toEqual(["Bolo de milho", "Conversa cv-2"]);
    t.transporte.renomear.mockRejectedValueOnce(new Error("caiu"));
    expect(await t.loja.renomearConversa("cv-1", "Outro")).toBe(false);
  });

  it("o nome que o backend dá à conversa aberta chega ao cabeçalho pela lista", async () => {
    const t = lojaDeTeste({ ler: async (id: string) => conversaVazia(id, "Conversa nova") });
    await t.loja.abrirConversa("cv-1");
    t.transporte.listar.mockResolvedValue({ atual: "cv-1", conversas: [resumo("cv-1", { titulo: "Quanto sai a porção?" })] });
    await t.loja.carregarLista();
    expect(t.loja.ler().conversa.titulo).toBe("Quanto sai a porção?");
    t.transporte.listar.mockResolvedValue({ atual: "cv-1", conversas: [resumo("cv-1", { titulo: "  " })] });
    await t.loja.carregarLista();
    expect(t.loja.ler().conversa.titulo).toBe("Quanto sai a porção?");
  });

  it("trocar abre e marca a atual; a mesma não recarrega; marcar que falha não atrapalha", async () => {
    const t = lojaDeTeste();
    await t.loja.trocarConversa("cv-2");
    expect(t.loja.ler().conversa.id).toBe("cv-2");
    expect(t.transporte.marcarAtual).toHaveBeenCalledWith("cv-2");
    expect(t.loja.ler().lista.atual).toBe("cv-2");
    t.transporte.ler.mockClear();
    await t.loja.trocarConversa("cv-2");
    expect(t.transporte.ler).not.toHaveBeenCalled();

    t.transporte.marcarAtual.mockRejectedValueOnce(new Error("caiu"));
    await t.loja.trocarConversa("cv-3");
    expect(t.loja.ler().conversa.id).toBe("cv-3");

    t.transporte.ler.mockRejectedValueOnce(new ErroDoMotor("Não achei.", "ausente"));
    t.transporte.marcarAtual.mockClear();
    await t.loja.trocarConversa("cv-4");
    expect(t.transporte.marcarAtual).not.toHaveBeenCalled();
  });

  it("apagar todas: uma a uma, e a conversa fica vazia; falha avisa", async () => {
    const t = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] }) });
    await t.loja.abrirConversa();
    t.transporte.listar.mockResolvedValueOnce({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] });
    t.transporte.listar.mockResolvedValue({ atual: null, conversas: [] });
    expect(await t.loja.apagarTodas()).toBe(true);
    expect(t.transporte.apagar.mock.calls.map(([id]) => id)).toEqual(["cv-1", "cv-2"]);
    expect(t.loja.ler().conversa).toMatchObject({ id: null, carregamento: "pronto", itens: [] });
    await esperarPromessas();
    expect(t.loja.ler().lista.conversas).toEqual([]);

    t.transporte.listar.mockResolvedValueOnce({ atual: "cv-9", conversas: [resumo("cv-9")] });
    t.transporte.apagar.mockRejectedValueOnce(new Error("caiu"));
    expect(await t.loja.apagarTodas()).toBe(false);
    expect(t.loja.ler().aviso?.tom).toBe("erro");
  });
});

describe("enviar e o fluxo do turno", () => {
  async function comConversa() {
    const t = lojaDeTeste();
    await t.loja.abrirConversa("cv-1");
    return t;
  }

  it("envia, assina o fluxo do turno, e os eventos chegam no quadro seguinte", async () => {
    const t = await comConversa();
    expect(await t.loja.enviar("  Tenho forno.  ", { contexto: { tela: "receitas", tipo: "receita", id: "arroz" } })).toBe(true);
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", {
      texto: "Tenho forno.",
      contexto: { tela: "receitas", tipo: "receita", id: "arroz" },
      id_cliente: "u-1",
    });
    expect(t.assinaturas).toHaveLength(1);
    expect(t.assinaturas[0]).toMatchObject({ conversaId: "cv-1", turnoId: "t-1", desde: 0 });

    t.emitir({ ...EVENTOS[0]!, turno_id: "t-1" });
    t.emitir({ ...EVENTOS[1]!, turno_id: "t-1" });
    expect(t.loja.ler().conversa.turno?.fase).toBe("conectando");
    t.descarregar();
    expect(t.loja.ler().conversa.turno?.fase).toBe("trabalhando");

    t.conexao("aberta");
    t.conexao("conectando");
    expect(t.loja.ler().conversa.turno?.conexao).toBe("aberta");
    t.conexao("reconectando");
    expect(t.loja.ler().conversa.turno?.conexao).toBe("reconectando");

    t.emitir({ seq: 6, turno_id: "t-1", tipo: "estado.alterado", recursos: ["receitas", 3, "perfil"] } as never);
    expect(t.avisar).toHaveBeenCalledWith(["receitas", "perfil"]);
    t.emitir({ seq: 7, turno_id: "t-1", tipo: "estado.alterado", recursos: [] });
    expect(t.avisar).toHaveBeenCalledTimes(1);

    for (const evento of EVENTOS.slice(6)) t.emitir({ ...evento, turno_id: "t-1" });
    // O fim do turno descarrega na hora, sem esperar o quadro.
    expect(t.loja.ler().conversa.turno).toBeNull();
    expect(t.assinaturas[0]?.fechada).toBe(true);
    expect(t.loja.ler().ultimoDesfecho).toMatchObject({ estado: "concluido" });
    expect(t.loja.ler().naoLidas).toBe(1);
    t.loja.definirVisivel(true);
    expect(t.loja.ler().naoLidas).toBe(0);
    t.loja.definirVisivel(true);
  });

  it("com a conversa à vista, a resposta não conta como nova; incompleta, busca a gravada", async () => {
    const t = await comConversa();
    t.loja.definirVisivel(true);
    await t.loja.enviar("Oi");
    t.transporte.ler.mockClear();
    t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.iniciado" });
    t.emitir({ seq: 3, turno_id: "t-1", tipo: "turno.concluido" });
    expect(t.loja.ler().naoLidas).toBe(0);
    await esperarPromessas();
    expect(t.transporte.ler).toHaveBeenCalledWith("cv-1");
  });

  it("sem texto, sem internet, fora do ar, carregando ou já respondendo: não envia", async () => {
    const t = await comConversa();
    expect(await t.loja.enviar("   ")).toBe(false);
    t.loja.definirOnline(false);
    t.loja.definirOnline(false);
    expect(await t.loja.enviar("Oi")).toBe(false);
    t.loja.definirOnline(true);
    await t.loja.enviar("Oi");
    expect(await t.loja.enviar("De novo")).toBe(false);
    expect(t.transporte.enviar).toHaveBeenCalledTimes(1);
  });

  it("sem conversa aberta, cria uma antes de mandar; se não der, não manda", async () => {
    const t = lojaDeTeste();
    expect(await t.loja.enviar("Oi")).toBe(true);
    expect(t.transporte.criar).toHaveBeenCalled();
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-nova", expect.objectContaining({ texto: "Oi" }));

    const falha = lojaDeTeste({ criar: async () => Promise.reject(new Error("caiu")) });
    expect(await falha.loja.enviar("Oi")).toBe(false);
  });

  it("a primeira mensagem aparece na hora, com os pontinhos, antes de a conversa existir no servidor", async () => {
    let criar: (conversa: Conversa) => void = () => {};
    const t = lojaDeTeste({ criar: () => new Promise((resolver) => (criar = resolver)) });
    const envio = t.loja.enviar("OLÁ");
    // Nada voltou do servidor ainda, e a bolha e o turno já estão na tela.
    expect(t.loja.ler().conversa.itens).toEqual([expect.objectContaining({ tipo: "senhora", texto: "OLÁ", envio: "enviando" })]);
    expect(t.loja.ler().conversa.turno?.fase).toBe("enviando");
    expect(t.transporte.enviar).not.toHaveBeenCalled();
    criar(conversaVazia("cv-nova"));
    expect(await envio).toBe(true);
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-nova", expect.objectContaining({ texto: "OLÁ" }));
    expect(t.loja.ler().conversa.itens).toEqual([expect.objectContaining({ tipo: "senhora", texto: "OLÁ" })]);
  });

  it("o texto passa do limite: vai cortado", async () => {
    const t = await comConversa();
    await t.loja.enviar("a".repeat(LIMITE_DE_CARACTERES + 50));
    expect(t.transporte.enviar.mock.calls[0]?.[1].texto).toHaveLength(LIMITE_DE_CARACTERES);
  });

  it("409: já havia um turno; a bolha sai, o texto volta para a caixa e a tela se anexa", async () => {
    const t = await comConversa();
    t.transporte.enviar.mockResolvedValueOnce({ turno_id: "t-0", anexado: true });
    t.transporte.ler.mockResolvedValueOnce({
      ...conversaVazia("cv-1"),
      turno_em_andamento: { turno_id: "t-0", estado: "em_andamento", ultimo_seq: 3, iniciado_texto: "hoje" },
    });
    await t.loja.enviar("Oi");
    expect(t.loja.ler().caixa.texto).toBe("Oi");
    expect(t.loja.ler().aviso?.texto).toBe(AVISO_DE_TURNO_RODANDO);
    expect(t.loja.ler().conversa.turno?.id).toBe("t-0");
    expect(t.assinaturas.at(-1)).toMatchObject({ turnoId: "t-0", desde: 0 });

    // Com uma ação, ou com a caixa já escrita, o texto não volta.
    const acao = await comConversa();
    acao.transporte.enviar.mockResolvedValueOnce({ turno_id: "t-0", anexado: true });
    acao.loja.definirTexto("outra coisa");
    await acao.loja.enviar("Tenho forno.", { acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" } });
    expect(acao.loja.ler().caixa.texto).toBe("outra coisa");
  });

  it("falha ao enviar: a bolha diz 'não enviou', e reenviar usa o mesmo id", async () => {
    const t = await comConversa();
    t.transporte.enviar.mockRejectedValueOnce(new ErroDoMotor("Sem conexão.", "rede"));
    await t.loja.enviar("Oi");
    expect(t.loja.ler().conversa.itens[0]).toMatchObject({ envio: "falhou", erroDoEnvio: { mensagem: "Sem conexão." } });
    await t.loja.reenviar("u-1");
    expect(t.transporte.enviar).toHaveBeenLastCalledWith("cv-1", expect.objectContaining({ id_cliente: "u-1" }));
    expect(t.loja.ler().conversa.turno?.id).toBe("t-1");
    // Nada a reenviar: bolha que não existe, ou turno rodando.
    await t.loja.reenviar("u-9");
    await t.loja.reenviar("u-1");
    expect(t.transporte.enviar).toHaveBeenCalledTimes(2);
  });

  it("a resposta ao envio que chega depois de ela trocar de conversa é ignorada", async () => {
    const t = await comConversa();
    let soltar: (v: { turno_id: string; anexado: boolean }) => void = () => {};
    t.transporte.enviar.mockImplementationOnce(() => new Promise((resolver) => (soltar = resolver)));
    const envio = t.loja.enviar("Oi");
    await esperarPromessas();
    await t.loja.abrirConversa("cv-2");
    soltar({ turno_id: "t-1", anexado: false });
    await envio;
    expect(t.loja.ler().conversa).toMatchObject({ id: "cv-2", turno: null });
  });

  it("da caixa: manda o texto e o contexto, e limpa; se não sair, o texto volta", async () => {
    const t = await comConversa();
    expect(await t.loja.enviarDaCaixa()).toBe(false);
    t.loja.preencher({ rascunho: "Dá pra eu fazer Bolo?", contexto: { tela: "receitas", tipo: "receita", id: "bolo" } });
    expect(await t.loja.enviarDaCaixa()).toBe(true);
    expect(t.loja.ler().caixa).toMatchObject({ texto: "", contexto: null });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({ contexto: { tela: "receitas", tipo: "receita", id: "bolo" } }));

    const semConversa = lojaDeTeste({ criar: async () => Promise.reject(new Error("caiu")) });
    semConversa.loja.definirTexto("Oi");
    expect(await semConversa.loja.enviarDaCaixa()).toBe(false);
    expect(semConversa.loja.ler().caixa.texto).toBe("Oi");
  });

  it("uma sugestão manda o texto e a ação, e o contexto vai uma vez só", async () => {
    const t = await comConversa();
    t.loja.definirContexto({ tela: "despensa", tipo: "tela", id: "despensa" });
    await t.loja.enviarSugestao({ rotulo: "Tenho", texto: "Tenho forno.", acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" } });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", {
      texto: "Tenho forno.",
      contexto: { tela: "despensa", tipo: "tela", id: "despensa" },
      acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
      id_cliente: "u-1",
    });
    expect(t.loja.ler().caixa.contexto).toBeNull();
    expect(await t.loja.enviarSugestao({ rotulo: "x", texto: "x" })).toBe(false);
  });

  it("perguntar de novo: pelo pedido da resposta, ou pela pergunta dela antes", async () => {
    const t = await comConversa();
    await t.loja.enviar("Quanto cobro?");
    t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.falhou", categoria: "tempo", mensagem: "Demorou." });
    const chave = t.loja.ler().conversa.itens.at(-1)!.chave;
    t.transporte.enviar.mockResolvedValueOnce({ turno_id: "t-2", anexado: false });
    await t.loja.perguntarDeNovo(chave);
    expect(t.transporte.enviar).toHaveBeenLastCalledWith("cv-1", expect.objectContaining({ id_cliente: "u-1", texto: "Quanto cobro?" }));

    const guardada = lojaDeTeste({
      ler: async (id: string) => ({
        ...conversaVazia(id),
        mensagens: [
          mensagem("m-1", "senhora", "Posso vender bolo?", { contexto: { tela: "receitas", tipo: "tela", id: "receitas" } }),
          mensagem("m-2", "consultora", "Parei", { estado: "cancelado" }),
        ],
      }),
    });
    await guardada.loja.abrirConversa("cv-1");
    await guardada.loja.perguntarDeNovo("m:m-2");
    expect(guardada.transporte.enviar).toHaveBeenCalledWith(
      "cv-1",
      expect.objectContaining({ texto: "Posso vender bolo?", contexto: { tela: "receitas", tipo: "tela", id: "receitas" } }),
    );
    guardada.transporte.enviar.mockClear();
    await guardada.loja.perguntarDeNovo("m:m-1");
    await guardada.loja.perguntarDeNovo("nenhuma");
    expect(guardada.transporte.enviar).not.toHaveBeenCalled();

    const semPergunta = lojaDeTeste({
      ler: async (id: string) => ({ ...conversaVazia(id), mensagens: [mensagem("m-2", "consultora", "Oi", { estado: "falhou" })] }),
    });
    await semPergunta.loja.abrirConversa("cv-1");
    await semPergunta.loja.perguntarDeNovo("m:m-2");
    expect(semPergunta.transporte.enviar).not.toHaveBeenCalled();
  });

  it("parar pede ao backend; falhando, volta e avisa; sem turno, nada", async () => {
    const t = await comConversa();
    await t.loja.parar();
    expect(t.transporte.parar).not.toHaveBeenCalled();
    await t.loja.enviar("Oi");
    t.emitir({ seq: 1, turno_id: "t-1", tipo: "texto.parcial", delta: "Olá" });
    t.descarregar();
    t.transporte.parar.mockRejectedValueOnce(new Error("caiu"));
    await t.loja.parar();
    expect(t.loja.ler().conversa.turno?.fase).toBe("escrevendo");
    expect(t.loja.ler().aviso).toMatchObject({ texto: "Não consegui parar agora. Tente de novo.", tom: "erro" });
    await t.loja.parar();
    expect(t.transporte.parar).toHaveBeenLastCalledWith("cv-1", "t-1");
    expect(t.loja.ler().conversa.turno?.fase).toBe("cancelando");
    await t.loja.parar();
    expect(t.transporte.parar).toHaveBeenCalledTimes(2);
    t.emitir({ seq: 2, turno_id: "t-1", tipo: "turno.cancelado" });
    expect(t.loja.ler().conversa.itens.at(-1)).toMatchObject({ estado: "cancelado" });
  });
});

describe("a retomada e a vigilância do fluxo", () => {
  async function rodando(sobrescrever: Parameters<typeof lojaDeTeste>[0] = {}) {
    const t = lojaDeTeste({
      ler: async (id: string) => ({
        ...conversaVazia(id),
        turno_em_andamento: { turno_id: "t-5", estado: "em_andamento", ultimo_seq: 4, iniciado_texto: "hoje" },
      }),
      ...sobrescrever,
    });
    await t.loja.abrirConversa("cv-1");
    return t;
  }

  it("recarregou no meio de um turno: assina desde o começo e reproduz", async () => {
    const t = await rodando();
    expect(t.assinaturas[0]).toMatchObject({ turnoId: "t-5", desde: 0 });
    t.emitir({ seq: 1, turno_id: "t-5", tipo: "turno.iniciado" });
    t.descarregar();
    expect(t.loja.ler().conversa.turno?.fase).toBe("pensando");
  });

  it("caiu sem abrir, ou há mais de um minuto: pergunta se o turno acabou; acabou, busca a resposta", async () => {
    const t = await rodando();
    t.cair({ caidaHaMs: 1_000 });
    expect(t.transporte.estadoDoTurno).not.toHaveBeenCalled();
    t.transporte.estadoDoTurno.mockResolvedValueOnce({ turno_id: "t-5", estado: "concluido", ultimo_seq: 9, iniciado_texto: "hoje" });
    t.transporte.ler.mockResolvedValueOnce({ ...conversaVazia("cv-1"), mensagens: [mensagem("m-9", "consultora", "Pronto.")] });
    t.cair({ caidaHaMs: ESPERA_ANTES_DE_CONSULTAR_MS });
    t.cair({ semAbrir: true });
    await esperarPromessas(10);
    expect(t.transporte.estadoDoTurno).toHaveBeenCalledTimes(1);
    expect(t.loja.ler().conversa.turno).toBeNull();
    expect(t.loja.ler().conversa.itens.at(-1)).toMatchObject({ texto: "Pronto." });
  });

  it("turno que o servidor não conhece mais conta como acabado; outra falha, não", async () => {
    const t = await rodando();
    t.transporte.estadoDoTurno.mockRejectedValueOnce(new Error("caiu"));
    t.cair({ semAbrir: true });
    await esperarPromessas(10);
    expect(t.loja.ler().conversa.turno?.id).toBe("t-5");

    t.transporte.estadoDoTurno.mockRejectedValueOnce(new ErroDoMotor("Não achei.", "ausente"));
    t.cair({ semAbrir: true });
    await esperarPromessas(10);
    expect(t.transporte.ler).toHaveBeenCalledTimes(2);
  });

  it("em silêncio há mais de cinco minutos: consulta o estado do turno", async () => {
    vi.useFakeTimers();
    const t = await rodando();
    t.relogio.agora += 10_000;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(t.transporte.estadoDoTurno).not.toHaveBeenCalled();
    t.relogio.agora += SILENCIO_MAXIMO_MS;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(t.transporte.estadoDoTurno).toHaveBeenCalledWith("cv-1", "t-5");
    t.loja.destruir();
  });

  it("um evento de um fluxo já fechado não chega; destruída, a loja não muda mais", async () => {
    const t = await rodando();
    const velho = t.assinaturas[0]!;
    await t.loja.abrirConversa("cv-2");
    velho.ouvintes.aoEvento({ seq: 1, turno_id: "t-5", tipo: "turno.iniciado", conversa_id: "cv-1" });
    velho.ouvintes.aoMudarEstado?.("aberta");
    velho.ouvintes.aoFalhar?.({ tentativas: 1, caidaHaMs: 0, semAbrir: true });
    expect(t.transporte.estadoDoTurno).not.toHaveBeenCalled();
    t.loja.destruir();
    t.loja.definirTexto("depois");
    t.loja.ativar();
    expect(t.loja.ler().caixa.texto).toBe("");
  });

  it("a assinatura que termina na hora (o fluxo acabou) é fechada", async () => {
    const t = lojaDeTeste({
      ler: async (id: string) => ({
        ...conversaVazia(id),
        turno_em_andamento: { turno_id: "t-5", estado: "em_andamento", ultimo_seq: 1, iniciado_texto: "hoje" },
      }),
    });
    const original = t.transporte.assinar.getMockImplementation() as Transporte["assinar"];
    t.transporte.assinar.mockImplementationOnce((conversaId: string, turnoId: string, desde: number, ouvintes: OuvintesDoTurno) => {
      const assinatura = original(conversaId, turnoId, desde, ouvintes);
      ouvintes.aoEvento({ seq: 1, turno_id: "t-5", tipo: "turno.concluido" });
      return assinatura;
    });
    await t.loja.abrirConversa("cv-1");
    expect(t.assinaturas[0]?.fechada).toBe(true);
    expect(t.loja.ler().conversa.turno).toBeNull();
  });
});

describe("a caixa, o painel e o resto", () => {
  it("texto, contexto, preencher e foco", () => {
    const t = lojaDeTeste();
    const ouvinte = vi.fn();
    t.loja.assinar(ouvinte);
    t.loja.definirTexto("Oi");
    t.loja.definirTexto("Oi");
    expect(ouvinte).toHaveBeenCalledTimes(1);
    t.loja.definirTexto("x".repeat(LIMITE_DE_CARACTERES + 1));
    expect(t.loja.ler().caixa.texto).toHaveLength(LIMITE_DE_CARACTERES);

    t.loja.preencher({ rascunho: "Dá pra eu fazer Bolo?", contexto: { tela: "receitas", tipo: "receita" } });
    expect(t.loja.ler().caixa).toMatchObject({ texto: "Dá pra eu fazer Bolo?", contexto: { tela: "receitas" }, foco: 1 });
    t.loja.preencher({ rascunho: "  " });
    expect(t.loja.ler().caixa).toMatchObject({ texto: "Dá pra eu fazer Bolo?", contexto: { tela: "receitas" }, foco: 2 });
    t.loja.preencher({ rascunho: "y".repeat(LIMITE_DE_CARACTERES + 3), contexto: null });
    expect(t.loja.ler().caixa.texto).toHaveLength(LIMITE_DE_CARACTERES);
    expect(t.loja.ler().caixa.contexto).toBeNull();
    t.loja.pedirFoco();
    expect(t.loja.ler().caixa.foco).toBe(4);
    t.loja.definirContexto({ tela: "inicio", tipo: "tela" });
    expect(t.loja.ler().caixa.contexto).toEqual({ tela: "inicio", tipo: "tela" });
  });

  it("o painel só muda quando muda", () => {
    const t = lojaDeTeste();
    const ouvinte = vi.fn();
    t.loja.assinar(ouvinte);
    t.loja.definirPainel(false);
    expect(ouvinte).not.toHaveBeenCalled();
    t.loja.definirPainel(true);
    expect(t.loja.ler().painelAberto).toBe(true);
  });

  it("fora do ar: guarda o motivo limpo e tenta de novo sozinha; volta, a faixa some", async () => {
    vi.useFakeTimers();
    const t = lojaDeTeste({
      estadoDoChat: async () => ({ disponivel: false, motivo: "Errno 111 connection refused", modelo: "  " }),
    });
    await t.loja.verificarDisponibilidade();
    expect(t.loja.ler().disponibilidade).toEqual({ disponivel: false, motivo: MOTIVO_FORA_DO_AR, modelo: null, conferida: true });
    expect(await t.loja.enviar("Oi")).toBe(false);

    t.transporte.estadoDoChat.mockResolvedValue({ disponivel: true });
    await vi.advanceTimersByTimeAsync(NOVA_VERIFICACAO_MS);
    expect(t.loja.ler().disponibilidade).toMatchObject({ disponivel: true, motivo: null });

    t.transporte.estadoDoChat.mockRejectedValueOnce(new Error("caiu"));
    await t.loja.verificarDisponibilidade();
    expect(t.loja.ler().disponibilidade.disponivel).toBe(true);

    t.transporte.estadoDoChat.mockResolvedValueOnce({ disponivel: false, motivo: "Ela está em manutenção." });
    await t.loja.verificarDisponibilidade();
    expect(t.loja.ler().disponibilidade.motivo).toBe("Ela está em manutenção.");
    t.loja.destruir();
    await vi.advanceTimersByTimeAsync(NOVA_VERIFICACAO_MS);
    expect(t.transporte.estadoDoChat).toHaveBeenCalledTimes(4);
  });

  it("em segundo plano: só abre a conversa se ela ainda estiver respondendo", async () => {
    const t = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1", { respondendo: true })] }) });
    await t.loja.verificarEmSegundoPlano();
    expect(t.transporte.ler).toHaveBeenCalledWith("cv-1");
    await t.loja.verificarEmSegundoPlano();
    expect(t.transporte.ler).toHaveBeenCalledTimes(1);

    const parada = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1")] }) });
    await parada.loja.verificarEmSegundoPlano();
    expect(parada.transporte.ler).not.toHaveBeenCalled();

    const falha = lojaDeTeste({ listar: async () => Promise.reject(new Error("caiu")) });
    await falha.loja.verificarEmSegundoPlano();
    expect(falha.loja.ler().conversa.carregamento).toBe("vazio");

    const ativa = lojaDeTeste();
    ativa.loja.ativar();
    await ativa.loja.verificarEmSegundoPlano();
    expect(ativa.transporte.listar).toHaveBeenCalledTimes(1);
  });
});
