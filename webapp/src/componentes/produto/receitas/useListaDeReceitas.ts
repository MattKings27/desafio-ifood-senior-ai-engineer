"use client";

/**
 * A lista da aba e dos filtros de agora.
 *
 * A primeira vem do servidor, já filtrada pela URL. Trocar a aba ou um filtro
 * troca a URL sem ir ao servidor (`useFiltrosNaUrl`), então a lista nova é
 * pedida daqui, pelo proxy, e a velha fica na tela (esmaecida) até ela chegar.
 * Um pedido que ficou para trás é cancelado.
 *
 * Quando o servidor refaz a página (a Server Action que respondeu uma
 * pergunta, a conversa que mudou a despensa), a lista dele vale se for do
 * mesmo pedido que está na tela: ela é a mais nova. Ela entra já no render em
 * que chega, e não um depois: a resposta otimista do gosto termina nesse mesmo
 * render, e a receita não pode voltar à seção de antes por um instante.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { CategoriaDeErro } from "@/lib/api/base";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { FiltrosDeReceitas, ListaDeReceitas } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";

export type ErroDaLista = { categoria: CategoriaDeErro; mensagem: string; pergunta?: string };

export type EstadoDaLista = {
  lista: ListaDeReceitas;
  /** A chave do pedido que produziu `lista`. */
  chave: string;
  carregando: boolean;
  erro: ErroDaLista | null;
};

export function paraErro(causa: unknown): ErroDaLista {
  if (causa instanceof ErroDoMotor) {
    return { categoria: causa.categoria, mensagem: causa.message, ...(causa.pergunta ? { pergunta: causa.pergunta } : {}) };
  }
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

export function useListaDeReceitas({
  inicial,
  chaveInicial,
  pedido,
  chave,
}: {
  inicial: ListaDeReceitas;
  chaveInicial: string;
  pedido: FiltrosDeReceitas;
  chave: string;
}) {
  const [estado, setEstado] = useState<EstadoDaLista>({ lista: inicial, chave: chaveInicial, carregando: false, erro: null });
  const [tentativa, setTentativa] = useState(0);
  const [doServidor, setDoServidor] = useState(inicial);
  const atual = useRef({ chave, pedido });
  const carregada = useRef({ chave: chaveInicial, tentativa: 0 });
  const emCurso = useRef<AbortController | null>(null);

  useEffect(() => {
    atual.current = { chave, pedido };
  });

  // O servidor refez a página: a lista dele vale se for do pedido que está na
  // tela, e entra já neste render (o padrão de guardar o que veio antes).
  if (inicial !== doServidor) {
    setDoServidor(inicial);
    if (chaveInicial === chave) setEstado({ lista: inicial, chave: chaveInicial, carregando: false, erro: null });
  }

  // O pedido que estava indo para o mesmo lugar fica para trás.
  useEffect(() => {
    if (chaveInicial !== atual.current.chave) return;
    emCurso.current?.abort();
    carregada.current = { chave: chaveInicial, tentativa: carregada.current.tentativa };
  }, [inicial, chaveInicial]);

  // A aba ou um filtro mudou (ou ela pediu de novo): pede a lista daqui.
  useEffect(() => {
    if (chave === carregada.current.chave && tentativa === carregada.current.tentativa) return;
    emCurso.current?.abort();
    const controle = new AbortController();
    emCurso.current = controle;
    setEstado((antes) => ({ ...antes, carregando: true, erro: null }));
    receitas.listar(atual.current.pedido, { signal: controle.signal }).then(
      (lista) => {
        if (controle.signal.aborted) return;
        carregada.current = { chave, tentativa };
        setEstado({ lista, chave, carregando: false, erro: null });
      },
      (causa: unknown) => {
        if (controle.signal.aborted) return;
        carregada.current = { chave, tentativa };
        setEstado((antes) => ({ ...antes, carregando: false, erro: paraErro(causa) }));
      },
    );
    return () => controle.abort();
  }, [chave, tentativa]);

  const tentarDeNovo = useCallback(() => setTentativa((antes) => antes + 1), []);

  return { ...estado, tentarDeNovo };
}
