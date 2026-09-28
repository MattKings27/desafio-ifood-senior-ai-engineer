/**
 * A conversa na tela: as mensagens guardadas, a resposta em andamento com os
 * valores escondidos até a conta fechar, o anúncio só do texto conferido, os
 * desfechos (parou, falhou, interrompeu), as respostas rápidas, as faixas de
 * sem internet e fora do ar, e o começo de conversa.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const caminhoAtual = vi.fn(() => "/despensa");
vi.mock("next/navigation", () => ({
  usePathname: () => caminhoAtual(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import type { Conversa as ConversaDaApi } from "@/lib/api/conversa";
import { SENTINELA } from "@/lib/conversa/mascara";
import { PASSOS_DA_CONSULTORA, definirPreferenciaDe } from "@/lib/preferencias";
import { conversaVazia, esperarPromessas, lojaDeTeste, mensagem } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";
import { contrato } from "@/teste/fixturas";

import { Conversa } from "./Conversa";
import { TEXTO_DA_DEMORA } from "./LinhaDoTempo";
import { TEXTO_DO_CANCELADO, TEXTO_DO_INTERROMPIDO } from "./Mensagem";
import { ProvedorDaConversa } from "./ProvedorDaConversa";
import { opcoesDaVez } from "./RespostasRapidas";
import { LEGENDA_DOS_VALORES, LEGENDA_DOS_VALORES_PARADOS } from "./TextoDaConsultora";

const CONVERSA = contrato<ConversaDaApi>("conversa.json");

function lojaCom(conversa: ConversaDaApi | null, sobrescrever: Parameters<typeof lojaDeTeste>[0] = {}): LojaDeTeste {
  return lojaDeTeste(
    {
      listar: async () => ({ atual: conversa?.id ?? null, conversas: [] }),
      ler: async (id: string) => (conversa && conversa.id === id ? conversa : conversaVazia(id)),
      ...sobrescrever,
    },
    { agora: () => Date.now() },
  );
}

async function montar(t: LojaDeTeste, abrir: string | null = "cv-7f3a") {
  if (abrir) await t.loja.abrirConversa(abrir);
  const resultado = render(
    <ProvedorDaConversa loja={t.loja}>
      <Conversa caminho="/despensa" />
    </ProvedorDaConversa>,
  );
  await act(async () => {
    await esperarPromessas();
  });
  return resultado;
}

const log = () => screen.getByRole("log", { name: "Mensagens da conversa" });
const anuncio = () => document.querySelector('[role="status"][aria-live="polite"].sr-only')?.textContent;

beforeEach(() => {
  caminhoAtual.mockReturnValue("/despensa");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a conversa guardada", () => {
  it("a mensagem dela, a resposta conferida, o card e o que o agente fez (recolhido)", async () => {
    await montar(lojaCom(CONVERSA));
    const mensagens = log();
    expect(within(mensagens).getByText("Quero vender arroz com frango.")).toBeInTheDocument();
    // O valor aparece no texto conferido e, grande, no card do custo da porção.
    const card = within(mensagens).getByRole("article", { name: "Arroz com frango" });
    expect(within(card).getByText("R$ 2,47", { selector: "span.text-3xl" })).toBeInTheDocument();
    const noTexto = within(mensagens)
      .getAllByText("R$ 2,47")
      .filter((elemento) => !card.contains(elemento));
    expect(noTexto).toHaveLength(1);
    expect(noTexto[0]).toHaveClass("numero");
    expect(within(mensagens).getByText("Ver o que eu fiz (2 passos)").closest("details")).not.toHaveAttribute("open");
    expect(within(mensagens).getAllByText("hoje, 14:58").length).toBeGreaterThan(0);
    expect(mensagens).toHaveAttribute("aria-live", "off");
    expect(mensagens).not.toHaveAttribute("aria-busy");
  });

  it("com 'mostrar o que o agente fez' ligado, os passos já vêm abertos", async () => {
    definirPreferenciaDe(PASSOS_DA_CONSULTORA, "abertos");
    await montar(lojaCom(CONVERSA));
    expect(screen.getByText("Ver o que eu fiz (2 passos)").closest("details")).toHaveAttribute("open");
  });

  it("a mensagem dela com o assunto que foi junto", async () => {
    const conversa: ConversaDaApi = {
      ...conversaVazia("cv-1"),
      mensagens: [mensagem("m-1", "senhora", "Quanto sai?", { contexto: { tela: "despensa", tipo: "ingrediente", id: "alho", rotulo: "Alho" } })],
    };
    await montar(lojaCom(conversa), "cv-1");
    expect(screen.getByText("Vendo: Alho")).toBeInTheDocument();
  });

  it("parou: o rascunho fica escondido, e dá para perguntar de novo", async () => {
    const conversa: ConversaDaApi = {
      ...conversaVazia("cv-1"),
      mensagens: [
        mensagem("m-1", "senhora", "Quanto cobro?"),
        mensagem("m-2", "consultora", `A porção sai ${SENTINELA}`, { estado: "cancelado" }),
      ],
    };
    const t = lojaCom(conversa);
    await montar(t, "cv-1");
    expect(screen.getByText(TEXTO_DO_CANCELADO)).toBeInTheDocument();
    expect(screen.getByText(LEGENDA_DOS_VALORES_PARADOS)).toBeInTheDocument();
    expect(screen.getByText("valor escondido")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Perguntar de novo" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith("cv-1", expect.objectContaining({ texto: "Quanto cobro?" }));
  });

  it.each([
    ["rede", "Não consegui falar com o agente"],
    ["tempo", "A resposta demorou demais"],
    ["regra", "Não deu para fazer isso agora"],
    ["qualquer", "O agente não conseguiu responder"],
  ])("falhou por %s: o título certo, sem texto técnico", async (categoria, titulo) => {
    const conversa: ConversaDaApi = {
      ...conversaVazia("cv-1"),
      mensagens: [
        mensagem("m-1", "senhora", "Oi"),
        mensagem("m-2", "consultora", "", { estado: "falhou", erro: { categoria, mensagem: "Traceback 500" } }),
      ],
    };
    await montar(lojaCom(conversa), "cv-1");
    expect(screen.getByText(titulo)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
    expect(screen.getByRole("button", { name: "Perguntar de novo" })).toBeInTheDocument();
  });

  it("interrompida: diz o que houve", async () => {
    const conversa: ConversaDaApi = {
      ...conversaVazia("cv-1"),
      mensagens: [mensagem("m-2", "consultora", "Comecei", { estado: "interrompido" })],
    };
    await montar(lojaCom(conversa), "cv-1");
    expect(screen.getByText(TEXTO_DO_INTERROMPIDO)).toBeInTheDocument();
  });

  it("valores retirados: aviso e 'Trazer a conta', que só preenche a caixa", async () => {
    const conversa: ConversaDaApi = {
      ...conversaVazia("cv-1"),
      mensagens: [
        mensagem("m-2", "consultora", "Sai [valor retirado] a porção.", { retirados: 1 }),
        mensagem("m-3", "consultora", "Dois [valor retirado] e [valor retirado].", { retirados: 2, acao_resultado: { ok: true, texto: "Anotei: a senhora tem forno." } }),
      ],
    };
    const t = lojaCom(conversa);
    await montar(t, "cv-1");
    expect(screen.getByText("Tirei desta resposta um valor que eu não consegui conferir com a conta.")).toBeInTheDocument();
    expect(screen.getByText("Tirei desta resposta 2 valores que eu não consegui conferir com a conta.")).toBeInTheDocument();
    expect(screen.getAllByText("valor retirado")).toHaveLength(3);
    expect(screen.getByText("Anotei: a senhora tem forno.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Trazer a conta" })[0]!);
    expect(t.loja.ler().caixa.texto).toBe("Me mostra a conta de cada valor que ficou de fora?");
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });
});

describe("a resposta em andamento", () => {
  it("rascunho com os valores escondidos, o texto conferido no lugar, e o anúncio só do final", async () => {
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Quanto sai a porção?");
    });
    expect(log()).toHaveAttribute("aria-busy", "true");
    // No instante em que ela manda: os pontinhos, e ainda nenhuma linha do tempo.
    expect(document.querySelector("[data-indicador-de-escrita]")).not.toBeNull();
    expect(screen.queryByText(/Trabalhando há/)).toBeNull();

    act(() => {
      t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.iniciado" });
      t.emitir({ seq: 2, turno_id: "t-1", tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "calcular_cmv", rotulo: "calculando o custo por porção", rotulo_feito: "calculei o custo por porção" });
      t.descarregar();
    });
    expect(anuncio()).toBe("Calculando o custo por porção…");
    expect(screen.getByText(/Trabalhando há/)).toBeInTheDocument();

    act(() => {
      t.emitir({ seq: 3, turno_id: "t-1", tipo: "atividade.concluida", atividade_id: "a", ok: true });
      t.emitir({ seq: 4, turno_id: "t-1", tipo: "texto.parcial", delta: `A porção sai ${SENTINELA} e mais R$ 66` });
      t.descarregar();
    });
    const regiao = log();
    expect(document.querySelector("[data-indicador-de-escrita]")).toBeNull();
    expect(regiao.querySelector("[data-escrevendo]")).not.toBeNull();
    expect(regiao.textContent).not.toMatch(/66|2,47/);
    expect(screen.getAllByText("valor em conferência").length).toBeGreaterThan(0);
    expect(screen.getByText(LEGENDA_DOS_VALORES)).toBeInTheDocument();

    act(() => {
      t.emitir({ seq: 5, turno_id: "t-1", tipo: "texto.final", texto: "A porção sai **R$ 2,47**.", retirados: 0 });
      t.descarregar();
    });
    expect(screen.getByText("Conferindo a resposta…")).toBeInTheDocument();
    expect(screen.getByText("R$ 2,47")).toBeInTheDocument();

    act(() => {
      t.emitir({ seq: 6, turno_id: "t-1", tipo: "turno.concluido" });
    });
    expect(log()).not.toHaveAttribute("aria-busy");
    expect(anuncio()).toBe("Resposta pronta: A porção sai R$ 2,47.");
    expect(screen.getByText("Ver o que eu fiz (1 passo)")).toBeInTheDocument();
  });

  it("parada, e sem texto conferido: o anúncio diz isso", async () => {
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    act(() => {
      t.emitir({ seq: 1, turno_id: "t-1", tipo: "texto.parcial", delta: "Vou" });
      t.descarregar();
    });
    await act(async () => {
      await t.loja.parar();
    });
    expect(screen.getAllByText("Parando…")).toHaveLength(2);
    act(() => t.emitir({ seq: 2, turno_id: "t-1", tipo: "turno.cancelado" }));
    expect(anuncio()).toBe(TEXTO_DO_CANCELADO);

    await act(async () => {
      await t.loja.enviar("De novo");
    });
    act(() => t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.falhou", categoria: "rede" }));
    expect(anuncio()).toBe("A resposta não chegou ao fim. A senhora pode perguntar de novo.");

    await act(async () => {
      await t.loja.enviar("Mais uma");
    });
    act(() => t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.concluido" }));
    expect(anuncio()).toBe("Resposta pronta.");
  });

  it("demorando mais de 90 s: avisa e oferece parar; a conexão que oscila também aparece", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    act(() => t.conexao("reconectando"));
    expect(screen.getByText(/A conexão oscilou/)).toBeInTheDocument();
    act(() => {
      t.conexao("aberta");
      vi.advanceTimersByTime(91_000);
    });
    expect(screen.getByText(TEXTO_DA_DEMORA)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Parar a resposta" }));
      await esperarPromessas();
    });
    expect(t.transporte.parar).toHaveBeenCalledWith("cv-1", "t-1");
  });

  it("a atividade que falhou diz que não deu certo, com o resumo", async () => {
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    act(() => {
      t.emitir({ seq: 1, turno_id: "t-1", tipo: "atividade.iniciada", atividade_id: "a", ferramenta: "web_search", detalhe: "buscando bolo" });
      t.descarregar();
    });
    expect(screen.getByText("buscando bolo")).toBeInTheDocument();
    act(() => {
      t.emitir({ seq: 2, turno_id: "t-1", tipo: "atividade.concluida", atividade_id: "a", ok: false, resumo: "o site não abriu" });
      t.descarregar();
    });
    expect(screen.getByText("Pesquisando receitas na internet: não deu certo")).toBeInTheDocument();
    expect(screen.getByText("o site não abriu")).toBeInTheDocument();
    act(() => t.emitir({ seq: 3, turno_id: "t-1", tipo: "turno.concluido" }));
    fireEvent.click(screen.getByText("Ver o que eu fiz (1 passo)"));
    expect(screen.getByText("(não deu certo)")).toBeInTheDocument();
  });

  it("não enviou: diz, e 'Tentar de novo' manda o mesmo pedido", async () => {
    const t = lojaCom(conversaVazia("cv-1"), { enviar: vi.fn().mockRejectedValueOnce(new Error("caiu")).mockResolvedValue({ turno_id: "t-2", anexado: false }) as never });
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent("Não enviou.");
    await act(async () => {
      fireEvent.click(within(alerta).getByRole("button", { name: "Tentar de novo" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenLastCalledWith("cv-1", expect.objectContaining({ id_cliente: "u-1" }));
  });
});

describe("carregando, falhou, não existe, vazia", () => {
  it("enquanto carrega, a forma da conversa", async () => {
    const t = lojaCom(null, { ler: () => new Promise(() => {}) });
    void t.loja.abrirConversa("cv-1");
    render(
      <ProvedorDaConversa loja={t.loja}>
        <Conversa caminho="/despensa" />
      </ProvedorDaConversa>,
    );
    expect(screen.getByText("Carregando a conversa…")).toBeInTheDocument();
  });

  it("falhou: tentar de novo abre a mesma", async () => {
    const t = lojaCom(null, {
      ler: vi.fn().mockRejectedValueOnce(new Error("caiu")).mockRejectedValueOnce(new Error("caiu")).mockResolvedValue(conversaVazia("cv-1")) as never,
    });
    await montar(t, "cv-1");
    expect(screen.getByText("Não consegui abrir a conversa")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
      await esperarPromessas();
    });
    expect(screen.getByText("Olá, Dona Maria")).toBeInTheDocument();
  });

  it("não existe mais: começar outra", async () => {
    const { ErroDoMotor } = await import("@/lib/api/base");
    const t = lojaCom(null, { ler: async () => Promise.reject(new ErroDoMotor("Não achei.", "ausente")) });
    await montar(t, "cv-1");
    expect(screen.getByText("Essa conversa não existe mais")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Começar outra conversa" }));
      await esperarPromessas();
    });
    expect(t.transporte.criar).toHaveBeenCalled();
  });

  it("vazia: a apresentação e as perguntas da página, que mandam com o contexto", async () => {
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    expect(screen.getByRole("heading", { level: 3, name: "Olá, Dona Maria" })).toBeInTheDocument();
    act(() => t.loja.definirContexto({ tela: "despensa", tipo: "tela", id: "despensa", rotulo: "Despensa" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Onde está o meu dinheiro parado na despensa?" }));
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenCalledWith(
      "cv-1",
      expect.objectContaining({ texto: "Onde está o meu dinheiro parado na despensa?", contexto: expect.objectContaining({ tela: "despensa" }) }),
    );
  });

  it("vazia e fora do ar: as perguntas prontas ficam esperando", async () => {
    const t = lojaCom(conversaVazia("cv-1"), { estadoDoChat: async () => ({ disponivel: false }) });
    await montar(t, "cv-1");
    const pergunta = screen.getByRole("button", { name: "Onde está o meu dinheiro parado na despensa?" });
    expect(pergunta).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(pergunta);
    await esperarPromessas();
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });
});

describe("respostas rápidas", () => {
  it("as do backend depois da resposta; tocar manda na hora", async () => {
    const t = lojaCom(conversaVazia("cv-1"));
    await montar(t, "cv-1");
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    act(() => {
      t.emitir({ seq: 1, turno_id: "t-1", tipo: "texto.final", texto: "Olá.", retirados: 0 });
      t.emitir({ seq: 2, turno_id: "t-1", tipo: "sugestoes", opcoes: [{ rotulo: "Quanto cobrar?", texto: "Quanto eu cobro por porção?" }] });
      t.emitir({ seq: 3, turno_id: "t-1", tipo: "turno.concluido" });
    });
    const grupo = screen.getByRole("group", { name: "Sugestões de resposta" });
    const chip = within(grupo).getByRole("button", { name: "Quanto cobrar?" });
    expect(chip).toHaveAttribute("title", "Quanto eu cobro por porção?");
    await act(async () => {
      fireEvent.click(chip);
      await esperarPromessas();
    });
    expect(t.transporte.enviar).toHaveBeenLastCalledWith("cv-1", expect.objectContaining({ texto: "Quanto eu cobro por porção?" }));
  });

  it("sem sugestão do backend: as do último card, e depois as da página", () => {
    const base = { id: "cv", titulo: "", carregamento: "pronto" as const, erro: null, turno: null, sugestoes: [] };
    const resposta = {
      tipo: "consultora" as const,
      chave: "t:1",
      id: null,
      turnoId: "t-1",
      estado: "concluido" as const,
      texto: "Olha",
      rascunho: false,
      retirados: 0,
      cartoes: [{ id: "k", tipo: "ingrediente" as const, dados: { nome: "Alho" }, ref: { rota: null }, geradoTexto: "", aoVivo: true }],
      atividades: [],
      resultados: [],
      erro: null,
      sugestoes: [],
      quandoTexto: null,
      pedido: null,
      incompleta: false,
    };
    expect(opcoesDaVez({ ...base, itens: [resposta] }, "/despensa").map((o) => o.rotulo)).toEqual(["Receitas com ele"]);
    expect(opcoesDaVez({ ...base, itens: [{ ...resposta, cartoes: [] }] }, "/receitas")[0]?.rotulo).toBe("O que dá pra fazer hoje?");
    expect(opcoesDaVez({ ...base, itens: [{ ...resposta, estado: "falhou" as const }] }, "/cozinha")[0]?.rotulo).toBe("O que falta saber?");
  });
});

describe("as faixas e a rolagem", () => {
  it("sem internet: a faixa diz, e a caixa não manda", async () => {
    const t = lojaCom(CONVERSA);
    await montar(t);
    act(() => t.loja.definirOnline(false));
    expect(screen.getByText("Sem internet agora")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Mensagem para o agente" })).toBeDisabled();
    expect(screen.queryByRole("group", { name: "Sugestões de resposta" })).toBeNull();
  });

  it("fora do ar: a faixa, o motivo dela quando vem limpo, e 'Tentar agora'", async () => {
    const t = lojaCom(CONVERSA, { estadoDoChat: vi.fn().mockResolvedValue({ disponivel: false, motivo: "Ele está em manutenção." }) as never });
    await montar(t);
    expect(screen.getByText("O agente está fora do ar agora")).toBeInTheDocument();
    expect(screen.getByText("Ele está em manutenção.")).toBeInTheDocument();
    t.transporte.estadoDoChat.mockResolvedValue({ disponivel: false });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tentar agora" }));
      await esperarPromessas();
    });
    expect(screen.getByText(/As outras telas continuam funcionando normalmente/)).toBeInTheDocument();
    t.transporte.estadoDoChat.mockResolvedValue({ disponivel: true });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tentar agora" }));
      await esperarPromessas();
    });
    expect(screen.queryByText("O agente está fora do ar agora")).toBeNull();
  });

  it("ela subiu para reler: 'Ir para o fim' aparece e leva de volta", async () => {
    const t = lojaCom(CONVERSA);
    await montar(t);
    const rolagem = log().closest(".overflow-y-auto") as HTMLDivElement;
    Object.defineProperty(rolagem, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(rolagem, "clientHeight", { configurable: true, value: 500 });
    rolagem.scrollTop = 100;
    fireEvent.scroll(rolagem);
    const irParaOFim = screen.getByRole("button", { name: "Ir para o fim" });
    rolagem.scrollTo = vi.fn();
    fireEvent.click(irParaOFim);
    expect(rolagem.scrollTo).toHaveBeenCalledWith({ top: 2000, behavior: "smooth" });
    expect(screen.queryByRole("button", { name: "Ir para o fim" })).toBeNull();

    // Com "reduzir movimento", sem deslizar; sem scrollTo, pelo scrollTop.
    document.documentElement.setAttribute("data-movimento", "reduzir");
    rolagem.scrollTop = 0;
    fireEvent.scroll(rolagem);
    fireEvent.click(screen.getByRole("button", { name: "Ir para o fim" }));
    expect(rolagem.scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: "auto" });
    document.documentElement.removeAttribute("data-movimento");
    rolagem.scrollTo = undefined as never;
    rolagem.scrollTop = 0;
    fireEvent.scroll(rolagem);
    fireEvent.click(screen.getByRole("button", { name: "Ir para o fim" }));
    expect(rolagem.scrollTop).toBe(2000);
  });
});
