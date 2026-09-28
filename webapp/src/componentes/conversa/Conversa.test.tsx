/**
 * A API pública da conversa: o provedor (abrir com rascunho e contexto sem
 * nunca enviar, o painel no histórico, o voltar do navegador, o título da
 * aba, os avisos), o botão flutuante, o Perguntar dos cards e as entradas
 * que abrem com o contexto da página.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const caminhoAtual = vi.fn(() => "/despensa");
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => caminhoAtual(),
  useRouter: () => ({ push, refresh }),
}));

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import { ProvedorDeSincronizacao } from "@/lib/dados/sincronizacao";
import { definirMidia } from "@/teste/midia";
import { conversaVazia, esperarPromessas, lojaDeTeste, resumo, transporteFalso } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import { avisoDoSelo } from "./BotaoConversa";
import {
  BotaoConversa,
  BotaoPerguntar,
  ProvedorDaConversa,
  enderecoDaConversa,
  useConversa,
} from "./index";
import {
  MARCA_DO_HISTORICO,
  PREFIXO_RESPONDENDO,
  contextoDaPaginaAtual,
  ehPaginaDaConversa,
} from "./ProvedorDaConversa";
import { cliqueSimples, useEntradaDaConversa } from "./useEntradaDaConversa";
import { TELA_LARGA } from "./useMidia";

function comLoja(ui: ReactElement, t: LojaDeTeste = lojaDeTeste()) {
  const resultado = render(
    <ProvedorDeToasts>
      <ProvedorDaConversa loja={t.loja}>{ui}</ProvedorDaConversa>
    </ProvedorDeToasts>,
  );
  return { ...resultado, ...t };
}

function Abridor({ pedido }: { pedido?: Parameters<ReturnType<typeof useConversa>["abrir"]>[0] }) {
  const { abrir, fechar, aberta, respondendo, naoLidas } = useConversa();
  return (
    <div>
      <button type="button" onClick={() => abrir(pedido)}>
        Abrir
      </button>
      <button type="button" onClick={fechar}>
        Fechar
      </button>
      <output>{`${aberta ? "aberta" : "fechada"} ${respondendo ? "respondendo" : "quieta"} ${naoLidas}`}</output>
    </div>
  );
}

beforeEach(() => {
  window.history.replaceState(null, "", "/despensa");
  caminhoAtual.mockReturnValue("/despensa");
});

afterEach(() => {
  push.mockClear();
  refresh.mockClear();
  vi.useRealTimers();
  document.title = "";
  document.body.innerHTML = "";
});

describe("enderecoDaConversa e a página", () => {
  it("sem nada, a página da conversa; com rascunho e contexto, na URL", () => {
    expect(enderecoDaConversa()).toBe("/conversa");
    expect(enderecoDaConversa({ rascunho: "   " })).toBe("/conversa");
    expect(
      enderecoDaConversa({
        rascunho: "Dá pra eu fazer Bolo de cenoura?",
        contexto: { tela: "receita", tipo: "receita", id: "bolo-de-cenoura", rotulo: "Bolo de cenoura" },
      }),
    ).toBe(
      "/conversa?rascunho=D%C3%A1+pra+eu+fazer+Bolo+de+cenoura%3F&tela=receita&tipo=receita&id=bolo-de-cenoura&rotulo=Bolo+de+cenoura",
    );
    expect(enderecoDaConversa({ contexto: { tela: "inicio", tipo: "pendencia" } })).toBe("/conversa?tela=inicio&tipo=pendencia");
  });

  it("a página da conversa é /conversa e as de baixo dela", () => {
    expect(ehPaginaDaConversa("/conversa")).toBe(true);
    expect(ehPaginaDaConversa("/conversa/x")).toBe(true);
    expect(ehPaginaDaConversa("/conversas")).toBe(false);
    expect(ehPaginaDaConversa(null)).toBe(false);
  });

  it("o contexto da página atual lê o título dela", () => {
    window.history.replaceState(null, "", "/despensa/arroz-branco-tipo-1");
    document.body.innerHTML = "<main><h1>Arroz branco tipo 1</h1></main>";
    expect(contextoDaPaginaAtual()).toMatchObject({ tipo: "ingrediente", id: "arroz-branco-tipo-1", rotulo: "Arroz branco tipo 1" });
  });
});

describe("abrir", () => {
  it("abre o painel com o rascunho e o contexto, entra no histórico, e não envia nada", async () => {
    const t = comLoja(
      <Abridor pedido={{ rascunho: "A embalagem da cobertura tem ", contexto: { tela: "despensa", tipo: "pendencia", id: "p1" } }} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(t.loja.ler().painelAberto).toBe(true);
    expect(t.loja.ler().caixa).toMatchObject({ texto: "A embalagem da cobertura tem ", contexto: { tipo: "pendencia" } });
    expect(window.location.search).toBe("?conversa=1");
    expect(window.history.state).toMatchObject({ [MARCA_DO_HISTORICO]: true });
    expect(screen.getByText(/^aberta/)).toBeInTheDocument();
    await esperarPromessas();
    expect(t.transporte.enviar).not.toHaveBeenCalled();

    // Abrir de novo não empilha outra entrada no histórico.
    const tamanho = window.history.length;
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(window.history.length).toBe(tamanho);
  });

  it("abrir sem pedido só pede o foco; fechar tira a entrada do histórico", () => {
    const voltar = vi.spyOn(window.history, "back").mockImplementation(() => {});
    const t = comLoja(<Abridor />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(t.loja.ler().caixa.foco).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(t.loja.ler().painelAberto).toBe(false);
    expect(voltar).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(voltar).toHaveBeenCalledTimes(1);
    voltar.mockRestore();
  });

  it("aberto pela URL (recarregou com o painel aberto): fechar limpa a URL sem voltar", () => {
    window.history.replaceState(null, "", "/despensa?conversa=1&q=arroz");
    const t = comLoja(<Abridor />);
    expect(t.loja.ler().painelAberto).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(window.location.search).toBe("?q=arroz");
  });

  it("fechado sem nada na URL, fechar só fecha", () => {
    const t = comLoja(<Abridor />);
    act(() => t.loja.definirPainel(true));
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(t.loja.ler().painelAberto).toBe(false);
    expect(window.location.pathname).toBe("/despensa");
  });

  it("o voltar e o avançar do navegador abrem e fecham", () => {
    const t = comLoja(<Abridor />);
    window.history.pushState({}, "", "/despensa?conversa=1");
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(t.loja.ler().painelAberto).toBe(true);
    window.history.pushState({}, "", "/despensa");
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(t.loja.ler().painelAberto).toBe(false);
  });

  it("na página da conversa, abrir só preenche a caixa", () => {
    window.history.replaceState(null, "", "/conversa");
    caminhoAtual.mockReturnValue("/conversa");
    const t = comLoja(<Abridor pedido={{ rascunho: "Oi" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(t.loja.ler().painelAberto).toBe(false);
    expect(t.loja.ler().caixa.texto).toBe("Oi");
  });

  it("no celular, trocar de página fecha a folha; no computador, o painel fica", () => {
    const t = lojaDeTeste();
    const { rerender } = comLoja(<Abridor />, t);
    act(() => t.loja.definirPainel(true));
    caminhoAtual.mockReturnValue("/receitas");
    rerender(
      <ProvedorDeToasts>
        <ProvedorDaConversa loja={t.loja}>
          <Abridor />
        </ProvedorDaConversa>
      </ProvedorDeToasts>,
    );
    expect(t.loja.ler().painelAberto).toBe(false);

    definirMidia(TELA_LARGA, true);
    act(() => t.loja.definirPainel(true));
    caminhoAtual.mockReturnValue("/cozinha");
    rerender(
      <ProvedorDeToasts>
        <ProvedorDaConversa loja={t.loja}>
          <Abridor />
        </ProvedorDaConversa>
      </ProvedorDeToasts>,
    );
    expect(t.loja.ler().painelAberto).toBe(true);

    caminhoAtual.mockReturnValue("/conversa");
    rerender(
      <ProvedorDeToasts>
        <ProvedorDaConversa loja={t.loja}>
          <Abridor />
        </ProvedorDaConversa>
      </ProvedorDeToasts>,
    );
    expect(t.loja.ler().painelAberto).toBe(false);
  });

  it("fora do provedor, nada quebra", () => {
    function Solto() {
      const { abrir, abrirDaPagina, fechar } = useConversa();
      return (
        <button
          type="button"
          onClick={() => {
            abrir({ rascunho: "x" });
            abrirDaPagina();
            fechar();
          }}
        >
          Solto
        </button>
      );
    }
    render(<Solto />);
    fireEvent.click(screen.getByRole("button", { name: "Solto" }));
    expect(push).not.toHaveBeenCalled();
  });

  it("sem loja de fora, o provedor cria a dele", () => {
    render(
      <ProvedorDaConversa>
        <Abridor />
      </ProvedorDaConversa>,
    );
    expect(screen.getByText("fechada quieta 0")).toBeInTheDocument();
  });
});

describe("abrir pela página", () => {
  function Entrada() {
    const aoClicar = useEntradaDaConversa();
    return (
      <a href="/conversa" onClick={aoClicar}>
        Conversar
      </a>
    );
  }

  it("leva o contexto da página; um contexto mais preciso da mesma página fica", () => {
    const t = comLoja(<Entrada />);
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().caixa.contexto).toEqual({ tela: "despensa", tipo: "tela", id: "despensa", rotulo: "Despensa" });
    act(() => t.loja.definirContexto({ tela: "despensa", tipo: "ingrediente", id: "alho", rotulo: "Alho" }));
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().caixa.contexto?.id).toBe("alho");

    // Noutra página, o contexto passa a ser o dela.
    window.history.replaceState(null, "", "/receitas");
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().caixa.contexto).toMatchObject({ tela: "receitas", tipo: "tela" });

    // A mesma tela de novo: nada muda.
    const antes = t.loja.ler().caixa;
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().caixa.contexto).toBe(antes.contexto);
  });

  it("na página de um item, o contexto é o item", () => {
    window.history.replaceState(null, "", "/despensa/alcaparras");
    const t = comLoja(
      <main>
        <h1>Alcaparras</h1>
        <Entrada />
      </main>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }));
    expect(t.loja.ler().caixa.contexto).toEqual({ tela: "despensa", tipo: "ingrediente", id: "alcaparras", rotulo: "Alcaparras" });
  });

  it("Ctrl, Shift ou o botão do meio seguem o link", () => {
    const t = comLoja(<Entrada />);
    fireEvent.click(screen.getByRole("link", { name: "Conversar" }), { ctrlKey: true });
    expect(t.loja.ler().painelAberto).toBe(false);
    const evento = { button: 1, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };
    expect(cliqueSimples(evento as never)).toBe(false);
    expect(cliqueSimples({ ...evento, button: 0 } as never)).toBe(true);
    expect(cliqueSimples({ ...evento, button: 0, altKey: true } as never)).toBe(false);
  });
});

describe("o que o provedor acompanha", () => {
  it("resposta que chega com a conversa fechada vira não lida, e o título da aba avisa", async () => {
    const t = lojaDeTeste();
    await t.loja.abrirConversa("cv-1");
    comLoja(<Abridor />, t);
    document.title = "Despensa | Sabor da Maria";
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    expect(document.title).toBe(`${PREFIXO_RESPONDENDO}Despensa | Sabor da Maria`);
    act(() => {
      t.emitir({ seq: 1, turno_id: "t-1", tipo: "texto.final", texto: "Olá.", retirados: 0 });
      t.emitir({ seq: 2, turno_id: "t-1", tipo: "turno.concluido" });
    });
    expect(screen.getByText("fechada quieta 1")).toBeInTheDocument();
    expect(document.title).toBe("(1) Despensa | Sabor da Maria");

    // O Next troca o título a cada página: o prefixo volta junto.
    await act(async () => {
      const titulo = document.createElement("title");
      titulo.textContent = "Receitas | Sabor da Maria";
      document.head.appendChild(titulo);
      document.title = "Receitas | Sabor da Maria";
      await esperarPromessas();
    });
    expect(document.title).toBe("(1) Receitas | Sabor da Maria");

    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(screen.getByText("aberta quieta 0")).toBeInTheDocument();
    expect(document.title).toBe("Receitas | Sabor da Maria");
  });

  it("a aba voltou à vista com o painel aberto: nada é não lido", () => {
    const t = comLoja(<Abridor />);
    act(() => t.loja.definirPainel(true));
    const visibilidade = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    visibilidade.mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(t.loja.ler().naoLidas).toBe(0);
    visibilidade.mockRestore();
  });

  it("sem internet, a loja sabe; quando volta, também", () => {
    const t = comLoja(<Abridor />);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(t.loja.ler().online).toBe(false);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(t.loja.ler().online).toBe(true);
  });

  it("recarregou com uma resposta rodando: o selo acende sem ela abrir a conversa", async () => {
    vi.useFakeTimers();
    const t = lojaDeTeste({ listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1", { respondendo: true })] }) });
    comLoja(<Abridor />, t);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(t.transporte.ler).toHaveBeenCalledWith("cv-1");
  });

  it("os avisos da loja viram toast", async () => {
    const t = lojaDeTeste({ criar: async () => Promise.reject(new Error("caiu")) });
    comLoja(<Abridor />, t);
    await act(async () => {
      await t.loja.novaConversa();
    });
    expect(await screen.findByText("Não consegui falar com o sistema agora. Confira a internet e tente de novo em instantes.")).toBeInTheDocument();
    expect(t.loja.ler().aviso).toBeNull();
  });

  it("estado.alterado atualiza as telas: a sincronização refaz a leitura da página", async () => {
    const falso = transporteFalso({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1")] }),
      ler: async (id: string) => ({
        ...conversaVazia(id),
        turno_em_andamento: { turno_id: "t-1", estado: "em_andamento", ultimo_seq: 1, iniciado_texto: "hoje" },
      }),
    });
    render(
      <ProvedorDeSincronizacao espera={0}>
        <ProvedorDaConversa transporte={falso.transporte}>
          <Abridor />
        </ProvedorDaConversa>
      </ProvedorDeSincronizacao>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    await waitFor(() => expect(falso.assinaturas).toHaveLength(1));
    act(() => falso.emitir({ seq: 1, turno_id: "t-1", tipo: "estado.alterado", recursos: ["despensa", "orcamento"] }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  });
});

describe("BotaoConversa", () => {
  it("fora da conversa, é o link flutuante que abre o painel com a página", () => {
    const t = comLoja(<BotaoConversa />);
    const link = screen.getByRole("link", { name: "Conversar" });
    expect(link).toHaveAttribute("href", "/conversa");
    expect(link.className).toContain("lg:inline-flex");
    fireEvent.click(link);
    expect(t.loja.ler().painelAberto).toBe(true);
    expect(t.loja.ler().caixa.contexto?.tela).toBe("despensa");
    // Aberto, ele se esconde (sem sair do lugar, para o foco voltar a ele).
    expect(screen.queryByRole("link", { name: "Conversar" })).toBeNull();
    expect(document.querySelector("a[data-abre-conversa]")).toHaveAttribute("hidden");
  });

  it.each(["/conversa", "/conversa/cv-7f3a"])("em %s, some", (caminho) => {
    caminhoAtual.mockReturnValue(caminho);
    const { container } = render(<BotaoConversa />);
    expect(container).toBeEmptyDOMElement();
  });

  it("o selo diz o que acontece para o leitor de tela", () => {
    expect(avisoDoSelo(true, 3)).toBe("o agente está respondendo");
    expect(avisoDoSelo(false, 1)).toBe("1 resposta nova");
    expect(avisoDoSelo(false, 2)).toBe("2 respostas novas");
    expect(avisoDoSelo(false, 0)).toBeNull();
  });

  it("com respostas novas, mostra quantas", async () => {
    const t = lojaDeTeste();
    await t.loja.abrirConversa("cv-1");
    comLoja(<BotaoConversa />, t);
    await act(async () => {
      await t.loja.enviar("Oi");
    });
    expect(screen.getByRole("link", { name: "Conversar: o agente está respondendo" })).toBeInTheDocument();
    act(() => t.emitir({ seq: 1, turno_id: "t-1", tipo: "turno.concluido" }));
    expect(screen.getByRole("link", { name: "Conversar: 1 resposta nova" })).toBeInTheDocument();
  });
});

describe("BotaoPerguntar", () => {
  it("leva a pergunta do card, com o contexto, e nunca envia sozinho", async () => {
    const t = comLoja(
      <BotaoPerguntar
        rascunho="O que eu posso fazer com peito de frango?"
        contexto={{ tela: "despensa", tipo: "ingrediente", id: "peito-de-frango", rotulo: "Peito de frango" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Perguntar" }));
    expect(t.loja.ler().painelAberto).toBe(true);
    expect(t.loja.ler().caixa).toMatchObject({
      texto: "O que eu posso fazer com peito de frango?",
      contexto: { id: "peito-de-frango", rotulo: "Peito de frango" },
    });
    await esperarPromessas();
    expect(t.transporte.enviar).not.toHaveBeenCalled();
  });

  it("aceita o texto e a aparência de quem usa", () => {
    comLoja(<BotaoPerguntar rascunho="x" rotulo="Responder no chat" variante="primario" tamanho="lg" larguraTotal />);
    const botao = screen.getByRole("button", { name: "Responder no chat" });
    expect(botao.className).toContain("bg-marca-fundo");
    expect(botao.className).toContain("w-full");
  });
});
