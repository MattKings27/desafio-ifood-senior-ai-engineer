/**
 * Preferências: a engrenagem abre a folha; tema, tamanho do texto e movimento
 * valem na hora e ficam guardados; os passos do agente abertos ou não;
 * apagar todas as conversas com confirmação; baixar os dados (e a rota que
 * ainda não existe); restaurar os dados da planilha, com confirmação, aviso e
 * todas as telas refeitas; e quem responde na conversa.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/despensa",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const sincronizacao = vi.hoisted(() => ({ avisar: vi.fn() }));
vi.mock("@/lib/dados/sincronizacao", async (original) => ({
  ...(await original<typeof import("@/lib/dados/sincronizacao")>()),
  useSincronizacao: () => ({ avisar: sincronizacao.avisar, assinar: () => () => {} }),
}));

import { ProvedorDeMovimento } from "@/componentes/compartilhados/Movimento";
import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import { ProvedorDaConversa } from "@/componentes/conversa/ProvedorDaConversa";
import { MENSAGENS } from "@/lib/api/base";
import type { RestauracaoDosDados } from "@/lib/api/dados";
import { CHAVE_DO_TEMA } from "@/lib/tema";
import { contrato } from "@/teste/fixturas";
import { esperarPromessas, lojaDeTeste, resumo } from "@/teste/conversa";
import type { LojaDeTeste } from "@/teste/conversa";

import {
  COMO_CONFERE,
  EXPLICACAO_DO_MINIMALISTA,
  EXPLICACAO_DO_TEMA,
  O_QUE_FICA_NA_RESTAURACAO,
  Preferencias,
  TEXTO_DA_RESTAURACAO,
  TEXTO_DO_DOWNLOAD_AUSENTE,
} from "./Preferencias";

let rede: ReturnType<typeof vi.fn>;

beforeEach(() => {
  rede = vi.fn();
  vi.stubGlobal("fetch", rede);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.removeAttribute("data-texto");
  document.documentElement.removeAttribute("data-movimento");
});

async function montar(t: LojaDeTeste | null = lojaDeTeste()) {
  const engrenagem = <Preferencias />;
  const resultado = render(
    <ProvedorDeToasts>{t ? <ProvedorDaConversa loja={t.loja}>{engrenagem}</ProvedorDaConversa> : engrenagem}</ProvedorDeToasts>,
  );
  const botao = screen.getByRole("button", { name: "Preferências" });
  expect(botao).toHaveAttribute("aria-haspopup", "dialog");
  expect(botao).toHaveAttribute("aria-expanded", "false");
  await act(async () => {
    fireEvent.click(botao);
    await esperarPromessas();
  });
  const folha = screen.getByRole("dialog", { name: "Preferências" });
  return { ...resultado, botao, folha };
}

describe("a engrenagem", () => {
  it("abre a folha com as quatro seções, sem violação do axe", async () => {
    const { folha, botao, container } = await montar();
    expect(botao).toHaveAttribute("aria-expanded", "true");
    for (const secao of ["Aparência", "Conversa", "Seus dados", "Sobre o agente"]) {
      expect(within(folha).getByRole("heading", { level: 3, name: secao })).toBeInTheDocument();
    }
    expect(await axe(container)).toHaveNoViolations();
    fireEvent.click(within(folha).getByRole("button", { name: "Fechar" }));
    expect(folha).not.toHaveAttribute("open");
  });
});

describe("Aparência", () => {
  it("o tema vale na hora, fica guardado e explica o que faz", async () => {
    const { folha } = await montar();
    expect(within(folha).getByRole("radio", { name: "Automático" })).toBeChecked();
    expect(within(folha).getByText(EXPLICACAO_DO_TEMA.automatico)).toBeInTheDocument();
    fireEvent.click(within(folha).getByRole("radio", { name: "Escuro" }));
    expect(document.documentElement).toHaveAttribute("data-tema", "escuro");
    expect(localStorage.getItem(CHAVE_DO_TEMA)).toBe("escuro");
    expect(within(folha).getByText(EXPLICACAO_DO_TEMA.escuro)).toBeInTheDocument();
    fireEvent.click(within(folha).getByRole("radio", { name: "Claro" }));
    expect(document.documentElement).toHaveAttribute("data-tema", "claro");
  });

  it("texto grande e movimento reduzido marcam o <html>", async () => {
    const { folha } = await montar();
    expect(within(folha).getByText(/O tamanho de sempre/)).toBeInTheDocument();
    fireEvent.click(within(folha).getByRole("radio", { name: "Grande" }));
    expect(document.documentElement).toHaveAttribute("data-texto", "grande");
    expect(localStorage.getItem("texto")).toBe("grande");
    expect(within(folha).getByText("Letras, botões e espaços ficam maiores em todas as telas.")).toBeInTheDocument();
    expect(within(folha).getByText(/Faz o que o aparelho/)).toBeInTheDocument();
    fireEvent.click(within(folha).getByRole("radio", { name: "Reduzir" }));
    expect(document.documentElement).toHaveAttribute("data-movimento", "reduzir");
    expect(within(folha).getByText("Sem animações: as trocas de tela acontecem direto.")).toBeInTheDocument();
  });

  it("o modo minimalista é um interruptor, desligado de começo, que marca o <html> e fica guardado", async () => {
    const { folha } = await montar();
    const interruptor = within(folha).getByRole("switch", { name: "Modo minimalista" });
    expect(interruptor).not.toBeChecked();
    expect(interruptor).toHaveAccessibleDescription(EXPLICACAO_DO_MINIMALISTA);
    fireEvent.click(interruptor);
    expect(interruptor).toBeChecked();
    expect(document.documentElement).toHaveAttribute("data-minimalista", "ligado");
    expect(localStorage.getItem("minimalista")).toBe("ligado");
    fireEvent.click(interruptor);
    expect(interruptor).not.toBeChecked();
    expect(document.documentElement).toHaveAttribute("data-minimalista", "desligado");
    expect(localStorage.getItem("minimalista")).toBe("desligado");
  });

  it("o provedor de movimento acompanha a escolha", () => {
    localStorage.setItem("movimento", "reduzir");
    render(
      <ProvedorDeMovimento>
        <p>tela</p>
      </ProvedorDeMovimento>,
    );
    expect(screen.getByText("tela")).toBeInTheDocument();
  });
});

describe("Conversa", () => {
  it("o interruptor dos passos do agente", async () => {
    const { folha } = await montar();
    const interruptor = within(folha).getByRole("switch", { name: "Mostrar o que o agente fez em cada resposta" });
    expect(interruptor).not.toBeChecked();
    fireEvent.click(interruptor);
    expect(localStorage.getItem("passos-da-consultora")).toBe("abertos");
    expect(interruptor).toBeChecked();
    fireEvent.click(interruptor);
    expect(localStorage.getItem("passos-da-consultora")).toBe("recolhidos");
  });

  it("apagar todas pede confirmação, apaga uma a uma e avisa", async () => {
    const t = lojaDeTeste({ listar: vi.fn().mockResolvedValue({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] }) as never });
    const { folha } = await montar(t);
    fireEvent.click(within(folha).getByRole("button", { name: "Apagar todas as conversas" }));
    let confirmacao = screen.getByRole("alertdialog", { name: "Apagar todas as conversas?" });
    fireEvent.click(within(confirmacao).getByRole("button", { name: "Cancelar" }));
    expect(t.transporte.apagar).not.toHaveBeenCalled();

    fireEvent.click(within(folha).getByRole("button", { name: "Apagar todas as conversas" }));
    confirmacao = screen.getByRole("alertdialog", { name: "Apagar todas as conversas?" });
    t.transporte.listar.mockResolvedValueOnce({ atual: "cv-1", conversas: [resumo("cv-1"), resumo("cv-2")] });
    t.transporte.listar.mockResolvedValue({ atual: null, conversas: [] });
    await act(async () => {
      fireEvent.click(within(confirmacao).getByRole("button", { name: "Apagar todas" }));
      await esperarPromessas(10);
    });
    expect(t.transporte.apagar.mock.calls.map(([id]) => id)).toEqual(["cv-1", "cv-2"]);
    expect(await screen.findByText("Apaguei todas as conversas.")).toBeInTheDocument();
    await waitFor(() => expect(within(folha).getByText("Não há nenhuma conversa guardada agora.")).toBeInTheDocument());
    const botao = within(folha).getByRole("button", { name: "Apagar todas as conversas" });
    expect(botao).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(botao);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("se apagar falhar, a loja avisa e a folha não diz que apagou", async () => {
    const t = lojaDeTeste({
      listar: async () => ({ atual: "cv-1", conversas: [resumo("cv-1")] }),
      apagar: async () => Promise.reject(new Error("caiu")),
    });
    const { folha } = await montar(t);
    fireEvent.click(within(folha).getByRole("button", { name: "Apagar todas as conversas" }));
    await act(async () => {
      fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Apagar todas" }));
      await esperarPromessas(10);
    });
    expect(screen.queryByText("Apaguei todas as conversas.")).toBeNull();
  });
});

describe("Seus dados", () => {
  it("baixa a despensa em texto", async () => {
    rede.mockResolvedValueOnce(new Response("DESPENSA", { status: 200 }));
    const { folha } = await montar();
    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: "Baixar a despensa em texto" }));
      await esperarPromessas(10);
    });
    expect(rede.mock.calls[0]?.[0]).toBe("/motor/despensa/planilha.txt");
    expect(await within(folha).findByText("Pronto: despensa-da-dona-maria.txt foi para os arquivos baixados.")).toBeInTheDocument();
  });

  it("a cópia de tudo que ainda não existe diz isso com calma; a rede caída também", async () => {
    rede
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }))
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }));
    const { folha } = await montar();
    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: "Baixar tudo" }));
      await esperarPromessas(10);
    });
    expect(await within(folha).findByText(TEXTO_DO_DOWNLOAD_AUSENTE)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: "Baixar tudo" }));
      await esperarPromessas(10);
    });
    expect(await within(folha).findByText("Não consegui baixar agora. Confira a internet e tente de novo.")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(folha).getByRole("button", { name: "Baixar a despensa em texto" }));
      await esperarPromessas(10);
    });
    expect(await within(folha).findByText("Não encontrei esse arquivo agora. Tente de novo mais tarde.")).toBeInTheDocument();
  });
});

describe("Restaurar os dados da planilha", () => {
  const RESTAURACAO = contrato<RestauracaoDosDados>("restauracao.json");
  const envelope = (dados: unknown) =>
    new Response(JSON.stringify({ ok: true, dados, erro: null, categoria: null, pergunta: null }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  it("pede confirmação dizendo o que volta e o que fica; restaura, avisa e refaz todas as telas", async () => {
    rede.mockResolvedValueOnce(envelope(RESTAURACAO));
    const t = lojaDeTeste();
    const esquecer = vi.spyOn(t.loja, "esquecerConversas");
    const { folha } = await montar(t);
    fireEvent.click(within(folha).getByRole("button", { name: "Restaurar os dados da planilha" }));
    const confirmacao = screen.getByRole("alertdialog", { name: "Restaurar os dados da planilha?" });
    expect(within(confirmacao).getByText(TEXTO_DA_RESTAURACAO)).toBeInTheDocument();
    expect(within(confirmacao).getByText(O_QUE_FICA_NA_RESTAURACAO)).toBeInTheDocument();
    expect(rede).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(within(confirmacao).getByRole("button", { name: "Restaurar" }));
      await esperarPromessas(10);
    });
    const [url, init] = rede.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/motor/dados/restaurar");
    expect(JSON.parse(String(init.body))).toMatchObject({ confirmar: true });
    expect(await screen.findByText(RESTAURACAO.texto)).toBeInTheDocument();
    expect(sincronizacao.avisar).toHaveBeenCalledWith(RESTAURACAO.recursos);
    expect(esquecer).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("cancelar não restaura; sem a rede, diz isso, e as telas não se refazem", async () => {
    rede.mockRejectedValueOnce(new TypeError("fetch failed"));
    const { folha } = await montar();
    fireEvent.click(within(folha).getByRole("button", { name: "Restaurar os dados da planilha" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancelar" }));
    expect(rede).not.toHaveBeenCalled();
    fireEvent.click(within(folha).getByRole("button", { name: "Restaurar os dados da planilha" }));
    await act(async () => {
      fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Restaurar" }));
      await esperarPromessas(10);
    });
    expect(await screen.findByText(MENSAGENS.rede)).toBeInTheDocument();
    expect(sincronizacao.avisar).not.toHaveBeenCalled();
  });
});

describe("Sobre o agente", () => {
  it("diz quem responde, pelo estado do chat, e como cada número é conferido", async () => {
    const t = lojaDeTeste({ estadoDoChat: async () => ({ disponivel: true, modelo: "claude-opus-5-5" }) });
    const { folha } = await montar(t);
    expect(await within(folha).findByText(/Claude Opus 5\.5, um modelo de inteligência artificial da Anthropic/)).toBeInTheDocument();
    for (const frase of COMO_CONFERE) expect(within(folha).getByText(frase)).toBeInTheDocument();
  });

  it("fora do ar, diz; sem o modelo, uma frase neutra", async () => {
    const t = lojaDeTeste({ estadoDoChat: async () => ({ disponivel: false }) });
    const { folha } = await montar(t);
    expect(await within(folha).findByText("O agente está fora do ar agora. As outras telas continuam funcionando.")).toBeInTheDocument();
    expect(within(folha).getByText(/Quem conversa com a senhora é um modelo de inteligência artificial/)).toBeInTheDocument();
  });

  it("fora do provedor da conversa, a folha abre sem a seção da conversa", async () => {
    const { folha } = await montar(null);
    expect(within(folha).queryByRole("heading", { name: "Conversa" })).toBeNull();
    expect(within(folha).getByText(/Quem conversa com a senhora é um modelo/)).toBeInTheDocument();
  });
});
