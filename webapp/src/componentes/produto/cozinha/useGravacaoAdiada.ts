"use client";

/**
 * Gravar a escolha dela 300 ms depois do último toque.
 *
 * A tela muda na hora (o valor local), e a API só recebe o último valor de uma
 * sequência de toques: três cliques rápidos em "+" são uma gravação só, e andar
 * pelas opções de um grupo com as setas também. Se a API recusar, o valor volta
 * para o da página e o motivo aparece num aviso; com `avisarErro: false`, o
 * motivo fica em `erro`, para a tela escrever perto da pergunta. Se a página
 * sair antes dos 300 ms, o que estava esperando é gravado mesmo assim. Quando
 * a página volta da API com outro valor (a conversa mudou o item, ou a gravação
 * terminou), a tela acompanha, se não há nada esperando.
 */

import { useEffect, useRef, useState, useTransition } from "react";

import { useToast } from "@/componentes/compartilhados/Toast";
import type { ErroDaAcao, Resultado } from "@/lib/acoes/base";
import { MENSAGENS } from "@/lib/api/base";

export type EstadoDaGravacao = "ocioso" | "esperando" | "salvando" | "salvo" | "erro";

/** A espera entre o último toque e a gravação. */
export const ESPERA_DA_GRAVACAO_MS = 300;

async function semLancar<T>(trabalho: () => Promise<Resultado<T>>): Promise<Resultado<T>> {
  try {
    return await trabalho();
  } catch {
    return { ok: false, erro: { categoria: "rede", mensagem: MENSAGENS.rede } };
  }
}

export function useGravacaoAdiada<V, R>(
  doServidor: V,
  gravar: (valor: V) => Promise<Resultado<R>>,
  {
    espera = ESPERA_DA_GRAVACAO_MS,
    aoGravar,
    avisarErro = true,
  }: {
    espera?: number;
    aoGravar?: (dados: R) => void;
    /** Mostrar a recusa num aviso. Padrão: sim. */
    avisarErro?: boolean;
  } = {},
) {
  const toast = useToast();
  const [valor, setValor] = useState(doServidor);
  const [estado, setEstado] = useState<EstadoDaGravacao>("ocioso");
  const [erro, setErro] = useState<ErroDaAcao | null>(null);
  const [, iniciar] = useTransition();
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);
  const esperando = useRef<{ valor: V } | null>(null);
  const emVoo = useRef(0);
  const doServidorAtual = useRef(doServidor);
  const gravarAtual = useRef(gravar);
  const aoGravarAtual = useRef(aoGravar);

  useEffect(() => {
    gravarAtual.current = gravar;
    aoGravarAtual.current = aoGravar;
  });

  useEffect(() => {
    doServidorAtual.current = doServidor;
    if (!esperando.current && emVoo.current === 0) setValor(doServidor);
  }, [doServidor]);

  const salvar = (novo: V) => {
    esperando.current = null;
    relogio.current = null;
    emVoo.current += 1;
    setEstado("salvando");
    iniciar(async () => {
      const resultado = await semLancar(() => gravarAtual.current(novo));
      emVoo.current -= 1;
      if (resultado.ok) {
        setEstado("salvo");
        setErro(null);
        aoGravarAtual.current?.(resultado.dados);
        return;
      }
      setEstado("erro");
      setErro(resultado.erro);
      if (!esperando.current) setValor(doServidorAtual.current);
      if (avisarErro) toast.mostrar({ texto: resultado.erro.pergunta ?? resultado.erro.mensagem, tom: "erro" });
    });
  };

  const mudar = (novo: V) => {
    setValor(novo);
    setEstado("esperando");
    esperando.current = { valor: novo };
    if (relogio.current) clearTimeout(relogio.current);
    relogio.current = setTimeout(() => salvar(novo), espera);
  };

  // A página saiu com uma escolha esperando: grava assim mesmo, sem mexer na tela.
  useEffect(
    () => () => {
      if (relogio.current) clearTimeout(relogio.current);
      const pendente = esperando.current;
      if (pendente) void semLancar(() => gravarAtual.current(pendente.valor));
    },
    [],
  );

  return {
    valor,
    mudar,
    estado,
    /** A recusa da última gravação, enquanto nada novo espera ou está indo. */
    erro: estado === "erro" ? erro : null,
    tentarDeNovo: () => salvar(valor),
  };
}
