/**
 * O transporte até a API.
 *
 * O que importa aqui é o tratamento de erro. A API distingue "falta um dado" de
 * "recusei por regra" de "não existe" de "você chamou errado", e essa
 * distinção é o que permite à tela fazer uma pergunta em vez de mostrar um
 * erro. E nenhuma mensagem que chega à tela fala de "motor" ou de comando.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { encontrarJargao, pareceTecnico } from "@/lib/formato";

import {
  ErroDoMotor,
  MENSAGENS,
  TEMPO_LIMITE_PADRAO_MS,
  base,
  buscar,
  comCorpo,
  consulta,
  ehRotaQueFalta,
  erroDaResposta,
  pedir,
  pedirComStatus,
  pedirTexto,
  urlDeEventos,
} from "./base";

const envelope = (dados: unknown) => ({ ok: true, dados, erro: null, categoria: null, pergunta: null });

function resposta(corpo: unknown, status = 200): Response {
  return new Response(corpo === undefined ? null : JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let buscarNaRede: ReturnType<typeof vi.fn>;

function chamada(n = 0): [string, RequestInit] {
  const feita = buscarNaRede.mock.calls[n];
  if (!feita) throw new Error(`esperava ao menos ${n + 1} chamada(s)`);
  return feita as [string, RequestInit];
}

beforeEach(() => {
  buscarNaRede = vi.fn();
  vi.stubGlobal("fetch", buscarNaRede);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("envelope de sucesso", () => {
  it("devolve os dados de dentro do envelope", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({ itens: [] })));
    await expect(pedir("/despensa")).resolves.toEqual({ itens: [] });
  });

  it("com o status, quando ele diz algo (201 criado, 200 já existia)", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({ slug: "s1" }), 201));
    await expect(pedirComStatus("/receitas")).resolves.toEqual({ dados: { slug: "s1" }, status: 201 });
    buscarNaRede.mockResolvedValue(resposta(envelope({ slug: "s1" })));
    await expect(pedirComStatus("/receitas")).resolves.toEqual({ dados: { slug: "s1" }, status: 200 });
  });

  it("não usa cache, manda JSON, e tem tempo limite", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    await pedir("/perfil");
    const [, init] = chamada();
    expect(init).toMatchObject({ cache: "no-store", headers: { "Content-Type": "application/json" } });
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("tempo limite 0 desliga o sinal", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    await pedir("/perfil", { tempoLimiteMs: 0 });
    expect(chamada()[1].signal).toBeUndefined();
  });

  it("junta o sinal de quem chamou com o do tempo limite", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    const controle = new AbortController();
    await pedir("/perfil", { signal: controle.signal });
    const sinal = chamada()[1].signal as AbortSignal;
    expect(sinal).not.toBe(controle.signal);
    controle.abort();
    expect(sinal.aborted).toBe(true);
  });

  it("com o limite desligado, usa só o sinal de quem chamou", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    const controle = new AbortController();
    await pedir("/perfil", { signal: controle.signal, tempoLimiteMs: 0 });
    expect(chamada()[1].signal).toBe(controle.signal);
  });

  it("o limite padrão é de 15 s", () => {
    expect(TEMPO_LIMITE_PADRAO_MS).toBe(15_000);
  });
});

describe("erro dentro do envelope (status 200)", () => {
  it("falta de dado chega com a pergunta que destrava", async () => {
    buscarNaRede.mockResolvedValue(
      resposta({
        ok: false,
        dados: null,
        erro: "Falta o peso da embalagem.",
        categoria: "dado",
        pergunta: "Quanto pesa o pacote?",
      }),
    );
    await expect(pedir("/despensa")).rejects.toMatchObject({
      categoria: "dado",
      pergunta: "Quanto pesa o pacote?",
      message: "Falta o peso da embalagem.",
    });
  });

  it("recusa por regra preserva a categoria", async () => {
    buscarNaRede.mockResolvedValue(
      resposta({ ok: false, dados: null, erro: "Ainda falta confirmar.", categoria: "regra", pergunta: null }),
    );
    await expect(pedir("/cmv")).rejects.toMatchObject({ categoria: "regra" });
  });

  it("envelope ok mas sem dados também é erro", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope(null)));
    await expect(pedir("/despensa")).rejects.toBeInstanceOf(ErroDoMotor);
  });

  it("recusa sem motivo ainda produz mensagem legível, sem a palavra motor", async () => {
    buscarNaRede.mockResolvedValue(resposta({ ok: false, dados: null, erro: null, categoria: null, pergunta: null }));
    const erro = (await pedir("/despensa").catch((e: unknown) => e)) as ErroDoMotor;
    expect(erro).toMatchObject({ message: MENSAGENS.semMotivo, categoria: "uso" });
    expect(encontrarJargao(erro.message)).toEqual([]);
  });

  it("resposta sem envelope nenhum é falha de caminho", async () => {
    buscarNaRede.mockResolvedValue(new Response("<html>proxy</html>", { status: 200 }));
    await expect(pedir("/despensa")).rejects.toMatchObject({ categoria: "rede", message: MENSAGENS.rede });
  });
});

describe("erro com status HTTP", () => {
  it("404 com envelope é `ausente`, com a frase da API", async () => {
    buscarNaRede.mockResolvedValue(
      resposta(
        { ok: false, dados: null, erro: "Não encontrei esse item.", categoria: "ausente", pergunta: null },
        404,
      ),
    );
    await expect(pedir("/despensa/itens/x")).rejects.toMatchObject({
      categoria: "ausente",
      message: "Não encontrei esse item.",
      status: 404,
    });
  });

  it("envelope de erro sem categoria usa a do status; sem mensagem, a padrão", async () => {
    buscarNaRede.mockResolvedValue(
      resposta({ ok: false, dados: null, erro: null, categoria: "dado", pergunta: "Quanto?" }, 422),
    );
    await expect(pedir("/x")).rejects.toMatchObject({
      categoria: "dado",
      message: MENSAGENS.semMotivo,
      pergunta: "Quanto?",
    });

    buscarNaRede.mockResolvedValue(resposta({ ok: false, dados: null, erro: "Recusei.", categoria: null, pergunta: null }, 404));
    await expect(pedir("/x")).rejects.toMatchObject({ categoria: "ausente", message: "Recusei." });
  });

  it.each([
    [404, "ausente", MENSAGENS.ausente],
    [408, "tempo", MENSAGENS.tempo],
    [504, "tempo", MENSAGENS.tempo],
    [409, "uso", MENSAGENS.uso],
    [422, "uso", MENSAGENS.uso],
    [400, "uso", MENSAGENS.uso],
    [500, "rede", MENSAGENS.rede],
    [503, "rede", MENSAGENS.rede],
  ] as const)("%s vira %s, com mensagem para ela", async (status, categoria, mensagem) => {
    buscarNaRede.mockResolvedValue(resposta({ detail: "trilha indisponível: [Errno 2]" }, status));
    const erro = (await pedir("/x").catch((e: unknown) => e)) as ErroDoMotor;
    expect(erro).toMatchObject({ categoria, message: mensagem, status });
    // O detalhe técnico fica para quem investiga, nunca na mensagem.
    expect(erro.detalhe).toContain(`HTTP ${status}`);
    expect(pareceTecnico(erro.message)).toBe(false);
  });

  it("guarda o `detail` do FastAPI no detalhe, inclusive a lista de validação", async () => {
    buscarNaRede.mockResolvedValue(resposta({ detail: "trilha indisponível" }, 503));
    await expect(pedir("/auditoria")).rejects.toMatchObject({ detalhe: "HTTP 503: trilha indisponível" });

    buscarNaRede.mockResolvedValue(resposta({ detail: [{ loc: ["body", "url"] }] }, 422));
    await expect(pedir("/receitas")).rejects.toMatchObject({
      detalhe: 'HTTP 422: [{"loc":["body","url"]}]',
    });
  });

  it("corpo que não é JSON não impede a tradução", async () => {
    const erro = await erroDaResposta(new Response("Bad Gateway", { status: 502 }));
    expect(erro).toMatchObject({ categoria: "rede", detalhe: "HTTP 502" });
  });
});

describe("erro de caminho", () => {
  it("sem conexão: frase para ela, sem 'motor' nem comando, e a causa encadeada", async () => {
    const causa = new TypeError("fetch failed");
    buscarNaRede.mockRejectedValue(causa);

    const erro = (await pedir("/despensa").catch((e: unknown) => e)) as ErroDoMotor;
    expect(erro).toBeInstanceOf(ErroDoMotor);
    expect(erro.categoria).toBe("rede");
    expect(erro.message).toBe(MENSAGENS.rede);
    expect(erro.message).not.toMatch(/motor|make api/i);
    expect(erro.detalhe).toContain("fetch failed");
    // Sem a causa encadeada não dá para distinguir DNS de conexão recusada.
    expect((erro as { cause?: unknown }).cause).toBe(causa);
  });

  it("tempo esgotado vira `tempo`", async () => {
    buscarNaRede.mockRejectedValue(new DOMException("tempo", "TimeoutError"));
    await expect(pedir("/despensa")).rejects.toMatchObject({ categoria: "tempo", message: MENSAGENS.tempo });
  });

  it("o limite que estourou de verdade também vira `tempo`", async () => {
    vi.useFakeTimers();
    // O AbortSignal.timeout do ambiente não obedece ao relógio falso; este sim.
    vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
      const controle = new AbortController();
      setTimeout(() => controle.abort(new DOMException("tempo", "TimeoutError")), ms);
      return controle.signal;
    });
    try {
      buscarNaRede.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolver, rejeitar) => {
            init.signal?.addEventListener("abort", () => rejeitar(init.signal?.reason));
          }),
      );
      const pendente = pedir("/lento", { tempoLimiteMs: 50 }).catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(60);
      expect(await pendente).toMatchObject({ categoria: "tempo" });
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancelamento de quem chamou volta como veio, para ser ignorado", async () => {
    const controle = new AbortController();
    controle.abort();
    const aborto = new DOMException("cancelado", "AbortError");
    buscarNaRede.mockRejectedValue(aborto);
    await expect(pedir("/despensa", { signal: controle.signal })).rejects.toBe(aborto);
  });

  it("AbortError sem sinal de quem chamou também volta como veio", async () => {
    const aborto = new DOMException("cancelado", "AbortError");
    buscarNaRede.mockRejectedValue(aborto);
    await expect(buscar("/x", { tempoLimiteMs: 0 })).rejects.toBe(aborto);
  });
});

describe("onde fica a API", () => {
  it("no navegador passa pelo proxy do Next, que evita CORS", async () => {
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    await pedir("/gostos");
    expect(chamada()[0]).toBe("/motor/gostos");
    expect(base()).toBe("/motor");
  });

  it("no servidor fala direto com a API: a porta padrão, ou a de MISE_API", async () => {
    vi.stubGlobal("window", undefined);
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    await pedir("/gostos");
    expect(chamada()[0]).toBe("http://127.0.0.1:8777/api/gostos");

    vi.stubEnv("MISE_API", "http://motor:9000");
    buscarNaRede.mockResolvedValue(resposta(envelope({})));
    await pedir("/gostos");
    expect(chamada(1)[0]).toBe("http://motor:9000/api/gostos");
  });
});

describe("montagem do pedido", () => {
  it("consulta pula o vazio, repete listas e escreve booleanos", () => {
    expect(consulta({})).toBe("");
    expect(consulta({ q: "", a: undefined, b: null, c: false })).toBe("");
    expect(consulta({ q: "pão de queijo", n: 3, so: true })).toBe("?q=p%C3%A3o+de+queijo&n=3&so=true");
    expect(consulta({ veredito: ["APTO", "FALTA INFO"] })).toBe("?veredito=APTO&veredito=FALTA+INFO");
    expect(consulta({ desde: 0 })).toBe("?desde=0");
  });

  it("comCorpo manda JSON; sem corpo, só o método", () => {
    expect(comCorpo("POST", { a: 1 })).toEqual({ method: "POST", body: '{"a":1}' });
    expect(comCorpo("DELETE")).toEqual({ method: "DELETE" });
  });

  it("urlDeEventos é sempre pelo proxy, com a retomada", () => {
    expect(urlDeEventos("/receitas/descoberta/eventos")).toBe("/motor/receitas/descoberta/eventos");
    expect(urlDeEventos("/conversas/c/turnos/t/eventos", 7)).toBe("/motor/conversas/c/turnos/t/eventos?desde=7");
  });
});

describe("rota que ainda não existe", () => {
  it("404, 405 e 501 dizem que a rota falta; o resto é erro de verdade", () => {
    for (const status of [404, 405, 501]) {
      expect(ehRotaQueFalta(new ErroDoMotor("x", "uso", undefined, undefined, status))).toBe(true);
    }
    expect(ehRotaQueFalta(new ErroDoMotor("x", "regra", undefined, undefined, 409))).toBe(false);
    expect(ehRotaQueFalta(new ErroDoMotor("x", "rede"))).toBe(false);
    expect(ehRotaQueFalta(new Error("x"))).toBe(false);
  });
});

describe("texto puro", () => {
  it("devolve o corpo como veio", async () => {
    buscarNaRede.mockResolvedValue(new Response("DESPENSA DA DONA MARIA", { status: 200 }));
    await expect(pedirTexto("/despensa/planilha.txt")).resolves.toBe("DESPENSA DA DONA MARIA");
  });

  it("erro de status e de caminho seguem as mesmas categorias", async () => {
    buscarNaRede.mockResolvedValue(resposta({ detail: "x" }, 404));
    await expect(pedirTexto("/despensa/planilha.txt")).rejects.toMatchObject({ categoria: "ausente" });

    buscarNaRede.mockRejectedValue(new TypeError("fetch failed"));
    await expect(pedirTexto("/despensa/planilha.txt")).rejects.toMatchObject({ categoria: "rede" });
  });
});
