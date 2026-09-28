/**
 * Sincronização entre superfícies: vários avisos viram um refresh só, depois
 * da espera, e cada assinante é chamado uma vez com o que mudou.
 */

import { act, render } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import type { OuvinteDeRecursos, Recurso } from "./sincronizacao";
import { ProvedorDeSincronizacao, useAoMudar, useSincronizacao } from "./sincronizacao";

type Controle = ReturnType<typeof useSincronizacao>;

function Captura({ aoMontar }: { aoMontar: (controle: Controle) => void }) {
  const controle = useSincronizacao();
  useEffect(() => {
    aoMontar(controle);
  }, [controle, aoMontar]);
  return null;
}

function montar(espera?: number) {
  let controle!: Controle;
  const tela = render(
    <ProvedorDeSincronizacao espera={espera}>
      <Captura aoMontar={(c) => (controle = c)} />
    </ProvedorDeSincronizacao>,
  );
  return { ...tela, controle: () => controle };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  refresh.mockClear();
});

describe("ProvedorDeSincronizacao", () => {
  it("junta os avisos numa espera de 250 ms e faz um refresh só", () => {
    const { controle } = montar();
    act(() => {
      controle().avisar(["despensa"]);
      controle().avisar(["orcamento"]);
    });
    act(() => vi.advanceTimersByTime(249));
    expect(refresh).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("avisa cada assinante uma vez, com o conjunto que mudou; `*` escuta tudo", () => {
    const { controle } = montar(100);
    const daDespensa = vi.fn();
    const deTudo = vi.fn();
    const doCardapio = vi.fn();
    act(() => {
      controle().assinar("despensa", daDespensa);
      controle().assinar("orcamento", daDespensa);
      controle().assinar("*", deTudo);
      controle().assinar("cardapio", doCardapio);
      controle().avisar(["despensa", "orcamento"]);
    });
    act(() => vi.advanceTimersByTime(100));
    expect(daDespensa).toHaveBeenCalledOnce();
    expect(daDespensa).toHaveBeenCalledWith(["despensa", "orcamento"]);
    expect(deTudo).toHaveBeenCalledOnce();
    expect(doCardapio).not.toHaveBeenCalled();
  });

  it("cancelar a assinatura para de avisar", () => {
    const { controle } = montar(10);
    const ouvinte = vi.fn();
    let cancelar = () => {};
    act(() => {
      cancelar = controle().assinar("receitas", ouvinte);
    });
    cancelar();
    act(() => {
      controle().avisar(["receitas"]);
      vi.advanceTimersByTime(10);
    });
    expect(ouvinte).not.toHaveBeenCalled();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("aviso vazio não faz nada", () => {
    const { controle } = montar(10);
    act(() => {
      controle().avisar([]);
      vi.advanceTimersByTime(50);
    });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("sair da tela no meio da espera não faz refresh depois", () => {
    const { controle, unmount } = montar(10);
    act(() => controle().avisar(["perfil"]));
    unmount();
    act(() => vi.advanceTimersByTime(50));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("fora do provedor, avisar e assinar não fazem nada", () => {
    let controle!: Controle;
    render(<Captura aoMontar={(c) => (controle = c)} />);
    expect(() => controle.avisar(["despensa"])).not.toThrow();
    expect(controle.assinar("despensa", () => {})()).toBeUndefined();
  });
});

function Assinante({ recursos, ouvinte }: { recursos: Recurso | readonly Recurso[]; ouvinte: OuvinteDeRecursos }) {
  useAoMudar(recursos, ouvinte);
  return null;
}

describe("useAoMudar", () => {
  it("chama o ouvinte mais recente quando um dos recursos muda", () => {
    let controle!: Controle;
    const primeiro = vi.fn();
    const segundo = vi.fn();
    const { rerender } = render(
      <ProvedorDeSincronizacao espera={5}>
        <Captura aoMontar={(c) => (controle = c)} />
        <Assinante recursos={["despensa", "orcamento"]} ouvinte={primeiro} />
      </ProvedorDeSincronizacao>,
    );
    rerender(
      <ProvedorDeSincronizacao espera={5}>
        <Captura aoMontar={(c) => (controle = c)} />
        <Assinante recursos={["despensa", "orcamento"]} ouvinte={segundo} />
      </ProvedorDeSincronizacao>,
    );
    act(() => {
      controle.avisar(["orcamento", "despensa"]);
      vi.advanceTimersByTime(5);
    });
    expect(primeiro).not.toHaveBeenCalled();
    expect(segundo).toHaveBeenCalledOnce();
  });

  it("aceita um recurso só, e para de ouvir ao desmontar", () => {
    let controle!: Controle;
    const ouvinte = vi.fn();
    const { rerender } = render(
      <ProvedorDeSincronizacao espera={5}>
        <Captura aoMontar={(c) => (controle = c)} />
        <Assinante recursos="cardapio" ouvinte={ouvinte} />
      </ProvedorDeSincronizacao>,
    );
    act(() => {
      controle.avisar(["cardapio"]);
      vi.advanceTimersByTime(5);
    });
    expect(ouvinte).toHaveBeenCalledOnce();

    rerender(
      <ProvedorDeSincronizacao espera={5}>
        <Captura aoMontar={(c) => (controle = c)} />
      </ProvedorDeSincronizacao>,
    );
    act(() => {
      controle.avisar(["cardapio"]);
      vi.advanceTimersByTime(5);
    });
    expect(ouvinte).toHaveBeenCalledOnce();
  });
});
