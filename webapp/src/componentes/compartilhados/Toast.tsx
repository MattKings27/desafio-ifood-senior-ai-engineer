"use client";

/**
 * Avisos passageiros (toast): "Anotei o creme de leite", "Não salvou".
 *
 * As duas regiões vivas existem desde o começo, vazias: um leitor de tela só
 * anuncia o que entra numa região que já estava lá. Sucesso e informação vão
 * na região educada (`status`); erro vai na `alert`, que interrompe.
 *
 * Um aviso com ação ("Desfazer") fica mais tempo, e nenhum some enquanto o
 * ponteiro ou o foco estão nele: o tempo para ler e agir é dela.
 */

import { CheckCircle, Info, WarningCircle, X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { BotaoIcone } from "./Botao";
import { AnimatePresence, ComMovimento, DURACAO, m } from "./Movimento";

export type TomDoAviso = "sucesso" | "erro" | "info";

export type PedidoDeAviso = {
  texto: string;
  tom?: TomDoAviso;
  acao?: { rotulo: string; aoClicar: () => void };
  /** Quanto tempo fica na tela. Padrão: 5 s; com ação, 10 s; erro, 8 s. */
  duracaoMs?: number;
};

type Aviso = Required<Pick<PedidoDeAviso, "texto" | "tom">> &
  Pick<PedidoDeAviso, "acao"> & { id: number; duracaoMs: number };

type ValorDosAvisos = {
  mostrar: (pedido: PedidoDeAviso) => number;
  fechar: (id: number) => void;
};

const SEM_PROVEDOR: ValorDosAvisos = { mostrar: () => -1, fechar: () => {} };

const Contexto = createContext<ValorDosAvisos>(SEM_PROVEDOR);

/** `mostrar` e `fechar`. Fora do provedor, não faz nada (útil em testes isolados). */
export function useToast(): ValorDosAvisos {
  return useContext(Contexto);
}

function duracaoPadrao(pedido: PedidoDeAviso): number {
  if (pedido.duracaoMs) return pedido.duracaoMs;
  if (pedido.acao) return 10_000;
  if (pedido.tom === "erro") return 8_000;
  return 5_000;
}

/** Quantos avisos cabem de uma vez. O mais antigo sai quando chega um novo. */
const MAXIMO = 3;

export function ProvedorDeToasts({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const proximo = useRef(1);

  const fechar = useCallback((id: number) => {
    setAvisos((atuais) => atuais.filter((aviso) => aviso.id !== id));
  }, []);

  const mostrar = useCallback((pedido: PedidoDeAviso) => {
    const id = proximo.current;
    proximo.current += 1;
    const aviso: Aviso = {
      id,
      texto: pedido.texto,
      tom: pedido.tom ?? "info",
      acao: pedido.acao,
      duracaoMs: duracaoPadrao(pedido),
    };
    setAvisos((atuais) => [...atuais, aviso].slice(-MAXIMO));
    return id;
  }, []);

  const valor = useMemo(() => ({ mostrar, fechar }), [mostrar, fechar]);

  return (
    <Contexto.Provider value={valor}>
      {children}
      <RegiaoDeToasts avisos={avisos} fechar={fechar} />
    </Contexto.Provider>
  );
}

function RegiaoDeToasts({ avisos, fechar }: { avisos: Aviso[]; fechar: (id: number) => void }) {
  const educados = avisos.filter((aviso) => aviso.tom !== "erro");
  const urgentes = avisos.filter((aviso) => aviso.tom === "erro");
  return (
    <ComMovimento>
      <div
        className={clsx(
          "pointer-events-none fixed inset-x-0 z-50 flex flex-col items-center gap-2 px-4",
          // No celular, acima da barra inferior; no computador, no canto.
          "bottom-[calc(var(--altura-barra-inferior)+env(safe-area-inset-bottom)+0.75rem)]",
          "lg:inset-x-auto lg:bottom-6 lg:left-6 lg:items-start lg:px-0",
        )}
      >
        <div role="status" aria-live="polite" className="flex w-full flex-col items-center gap-2 lg:items-start">
          <AnimatePresence initial={false}>
            {educados.map((aviso) => (
              <CaixaDoAviso key={aviso.id} aviso={aviso} fechar={fechar} />
            ))}
          </AnimatePresence>
        </div>
        <div role="alert" className="flex w-full flex-col items-center gap-2 lg:items-start">
          <AnimatePresence initial={false}>
            {urgentes.map((aviso) => (
              <CaixaDoAviso key={aviso.id} aviso={aviso} fechar={fechar} />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </ComMovimento>
  );
}

const ICONE: Record<TomDoAviso, ReactNode> = {
  sucesso: <CheckCircle size={22} weight="fill" className="text-sucesso" />,
  erro: <WarningCircle size={22} weight="fill" className="text-perigo" />,
  info: <Info size={22} weight="fill" className="text-info" />,
};

function CaixaDoAviso({ aviso, fechar }: { aviso: Aviso; fechar: (id: number) => void }) {
  const [pausado, setPausado] = useState(false);

  useEffect(() => {
    if (pausado) return;
    const relogio = setTimeout(() => fechar(aviso.id), aviso.duracaoMs);
    return () => clearTimeout(relogio);
  }, [aviso.id, aviso.duracaoMs, fechar, pausado]);

  return (
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8, transition: { duration: DURACAO.rapida } }}
      transition={{ duration: DURACAO.padrao }}
      onMouseEnter={() => setPausado(true)}
      onMouseLeave={() => setPausado(false)}
      onFocus={() => setPausado(true)}
      onBlur={() => setPausado(false)}
      className={clsx(
        "pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-lg border border-borda",
        "bg-superficie p-3 pl-4 text-texto shadow-flutuante",
      )}
    >
      <span aria-hidden="true" className="mt-0.5 shrink-0">
        {ICONE[aviso.tom]}
      </span>
      <p className="min-w-0 flex-1 py-0.5 text-base">{aviso.texto}</p>
      {aviso.acao ? (
        <button
          type="button"
          onClick={() => {
            aviso.acao?.aoClicar();
            fechar(aviso.id);
          }}
          className="-my-1 min-h-11 shrink-0 rounded-sm px-2 text-sm font-bold text-marca hover:bg-marca/10"
        >
          {aviso.acao.rotulo}
        </button>
      ) : null}
      <BotaoIcone rotulo="Fechar o aviso" className="-my-1.5 -mr-1.5" onClick={() => fechar(aviso.id)}>
        <X size={18} weight="bold" />
      </BotaoIcone>
    </m.div>
  );
}
