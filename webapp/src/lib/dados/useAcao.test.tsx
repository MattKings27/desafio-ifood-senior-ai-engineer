/**
 * O lado do navegador de uma escrita: pendente, aviso, valor otimista.
 *
 * As Server Actions são trocadas por funções comuns que devolvem `Resultado`:
 * o que se testa é o que a tela faz com a resposta, não a ida ao servidor.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import type { Resultado } from "@/lib/acoes/base";
import { MENSAGENS } from "@/lib/api/base";

import { novoIdCliente } from "./id";
import type { OpcoesDaAcao } from "./useAcao";
import { useAcao, useAcaoOtimista } from "./useAcao";

function adiado<T>() {
  let resolver!: (valor: T) => void;
  const promessa = new Promise<T>((r) => {
    resolver = r;
  });
  return { promessa, resolver };
}

function Botoes<T>({
  acao,
  opcoes,
  aoResultado,
}: {
  acao: (texto: string) => Promise<Resultado<T>>;
  opcoes?: OpcoesDaAcao<T>;
  aoResultado?: (r: Resultado<T>) => void;
}) {
  const { executar, pendente, erro, limparErro } = useAcao(acao, opcoes);
  return (
    <div>
      <button type="button" onClick={() => void executar("oi").then(aoResultado)}>
        Salvar
      </button>
      <button type="button" onClick={limparErro}>
        Limpar
      </button>
      <span data-testid="pendente">{String(pendente)}</span>
      <span data-testid="erro">{erro?.mensagem ?? ""}</span>
    </div>
  );
}

function montar(ui: React.ReactElement) {
  return render(<ProvedorDeToasts>{ui}</ProvedorDeToasts>);
}

describe("useAcao", () => {
  it("fica pendente enquanto a ação roda, e mostra o aviso de sucesso", async () => {
    const espera = adiado<Resultado<{ texto: string }>>();
    const acao = vi.fn(() => espera.promessa);
    const aoConcluir = vi.fn();
    montar(<Botoes acao={acao} opcoes={{ sucesso: (d) => d.texto, aoConcluir }} />);

    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByTestId("pendente")).toHaveTextContent("true");
    expect(acao).toHaveBeenCalledWith("oi");

    await act(async () => espera.resolver({ ok: true, dados: { texto: "Anotei o creme de leite." } }));
    expect(screen.getByTestId("pendente")).toHaveTextContent("false");
    expect(screen.getByRole("status")).toHaveTextContent("Anotei o creme de leite.");
    expect(aoConcluir).toHaveBeenCalledWith({ texto: "Anotei o creme de leite." });
  });

  it("aviso de sucesso fixo, e nenhum aviso quando não pedido", async () => {
    const { unmount } = montar(
      <Botoes acao={async () => ({ ok: true, dados: 1 })} opcoes={{ sucesso: "Salvo." }} />,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Salvar" })));
    expect(screen.getByRole("status")).toHaveTextContent("Salvo.");
    unmount();

    montar(<Botoes acao={async () => ({ ok: true, dados: 1 })} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Salvar" })));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("erro vira aviso na região de alerta, com a pergunta quando há", async () => {
    const aoFalhar = vi.fn();
    const aoResultado = vi.fn();
    montar(
      <Botoes
        acao={async () => ({
          ok: false,
          erro: { categoria: "dado", mensagem: "Falta o peso.", pergunta: "Quanto vem na embalagem?" },
        })}
        opcoes={{ aoFalhar }}
        aoResultado={aoResultado}
      />,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Salvar" })));
    expect(screen.getByRole("alert")).toHaveTextContent("Quanto vem na embalagem?");
    expect(screen.getByTestId("erro")).toHaveTextContent("Falta o peso.");
    expect(aoFalhar).toHaveBeenCalledWith(expect.objectContaining({ categoria: "dado" }));
    expect(aoResultado).toHaveBeenCalledWith(expect.objectContaining({ ok: false }));

    fireEvent.click(screen.getByRole("button", { name: "Limpar" }));
    expect(screen.getByTestId("erro")).toBeEmptyDOMElement();
  });

  it("sem aviso de erro quando a tela mesma mostra o erro", async () => {
    montar(
      <Botoes
        acao={async () => ({ ok: false, erro: { categoria: "uso", mensagem: "Confira." } })}
        opcoes={{ avisarErro: false }}
      />,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Salvar" })));
    expect(screen.getByRole("alert")).toBeEmptyDOMElement();
    expect(screen.getByTestId("erro")).toHaveTextContent("Confira.");
  });

  it("ação que lança (servidor fora, ação sumiu no deploy) vira erro de rede, não exceção", async () => {
    montar(
      <Botoes
        acao={async () => {
          throw new Error("Failed to find Server Action");
        }}
      />,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Salvar" })));
    expect(screen.getByRole("alert")).toHaveTextContent(MENSAGENS.rede);
  });
});

type Item = { id: string; nome: string };

function ListaOtimista({ acao }: { acao: (id: string) => Promise<Resultado<null>> }) {
  const [itens, setItens] = useState<Item[]>([
    { id: "a", nome: "Alcaparras" },
    { id: "b", nome: "Cebola" },
  ]);
  const { estado, executar, pendente } = useAcaoOtimista(
    itens,
    (atual: Item[], id: string) => atual.filter((item) => item.id !== id),
    async (id: string) => {
      const resultado = await acao(id);
      // Como o refresh() da Server Action faria: a base nova chega junto.
      if (resultado.ok) setItens((atual) => atual.filter((item) => item.id !== id));
      return resultado;
    },
  );
  return (
    <div>
      <ul>
        {estado.map((item) => (
          <li key={item.id}>{item.nome}</li>
        ))}
      </ul>
      <button type="button" onClick={() => void executar("a")}>
        Tirar alcaparras
      </button>
      <span data-testid="pendente">{String(pendente)}</span>
    </div>
  );
}

describe("useAcaoOtimista", () => {
  it("some na hora e fica sumido quando a API confirma", async () => {
    const espera = adiado<Resultado<null>>();
    montar(<ListaOtimista acao={() => espera.promessa} />);

    fireEvent.click(screen.getByRole("button", { name: "Tirar alcaparras" }));
    expect(screen.queryByText("Alcaparras")).not.toBeInTheDocument();

    await act(async () => espera.resolver({ ok: true, dados: null }));
    expect(screen.queryByText("Alcaparras")).not.toBeInTheDocument();
    expect(screen.getByText("Cebola")).toBeInTheDocument();
  });

  it("volta sozinho quando a API recusa, e avisa", async () => {
    const espera = adiado<Resultado<null>>();
    montar(<ListaOtimista acao={() => espera.promessa} />);

    fireEvent.click(screen.getByRole("button", { name: "Tirar alcaparras" }));
    expect(screen.queryByText("Alcaparras")).not.toBeInTheDocument();

    await act(async () =>
      espera.resolver({ ok: false, erro: { categoria: "regra", mensagem: "Esse item entra num prato aceito." } }),
    );
    expect(screen.getByText("Alcaparras")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Esse item entra num prato aceito.");
    expect(screen.getByTestId("pendente")).toHaveTextContent("false");
  });
});

describe("novoIdCliente", () => {
  it("é único a cada chamada", () => {
    expect(novoIdCliente()).not.toBe(novoIdCliente());
  });

  it("sem randomUUID (contexto sem HTTPS) ainda gera um id", () => {
    vi.stubGlobal("crypto", {});
    try {
      expect(novoIdCliente()).toMatch(/^c-[0-9a-z]+-[0-9a-z]+$/);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
