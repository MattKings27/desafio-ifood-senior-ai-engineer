"use client";

/**
 * As páginas do histórico dos filtros de agora.
 *
 * A primeira vem do servidor, já filtrada pela URL. Trocar um filtro troca a
 * URL sem ir ao servidor (`useFiltrosNaUrl`), então a primeira página nova é
 * pedida daqui, pelo proxy, e a velha fica na tela (esmaecida) até ela
 * chegar. "Ver mais" pede a página seguinte pelo cursor e junta à de cima: o
 * dia que continua na página seguinte continua no mesmo grupo.
 */

import { useEffect, useRef, useState } from "react";

import type { CategoriaDeErro } from "@/lib/api/base";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { FiltrosDeAtividades, GrupoDeAtividades, PaginaDeAtividades } from "@/lib/api/atividades";
import { atividades } from "@/lib/api/atividades";

export type ErroDoHistorico = { categoria: CategoriaDeErro; mensagem: string };

function paraErro(causa: unknown): ErroDoHistorico {
  if (causa instanceof ErroDoMotor) return { categoria: causa.categoria, mensagem: causa.message };
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

/** Junta a página seguinte à de cima: o mesmo dia continua no mesmo grupo. */
export function juntarGrupos(
  antes: readonly GrupoDeAtividades[],
  depois: readonly GrupoDeAtividades[],
): GrupoDeAtividades[] {
  const juntos = antes.map((grupo) => ({ ...grupo, itens: [...grupo.itens] }));
  for (const grupo of depois) {
    const ultimo = juntos.at(-1);
    if (ultimo && ultimo.dia === grupo.dia) ultimo.itens.push(...grupo.itens);
    else juntos.push({ ...grupo, itens: [...grupo.itens] });
  }
  return juntos;
}

type Estado = {
  pagina: PaginaDeAtividades;
  chave: string;
  carregando: boolean;
  carregandoMais: boolean;
  erro: ErroDoHistorico | null;
};

export function useHistorico({
  inicial,
  chaveInicial,
  pedido,
  chave,
}: {
  inicial: PaginaDeAtividades;
  chaveInicial: string;
  pedido: FiltrosDeAtividades;
  chave: string;
}) {
  const [estado, setEstado] = useState<Estado>({
    pagina: inicial,
    chave: chaveInicial,
    carregando: false,
    carregandoMais: false,
    erro: null,
  });
  const [tentativa, setTentativa] = useState(0);
  const carregada = useRef({ chave: chaveInicial, tentativa: 0 });
  const atual = useRef(pedido);
  const emCurso = useRef<AbortController | null>(null);

  useEffect(() => {
    atual.current = pedido;
  });

  // Um filtro mudou (ou ela pediu de novo): a primeira página é pedida daqui.
  useEffect(() => {
    if (chave === carregada.current.chave && tentativa === carregada.current.tentativa) return;
    emCurso.current?.abort();
    const controle = new AbortController();
    emCurso.current = controle;
    setEstado((antes) => ({ ...antes, carregando: true, erro: null }));
    atividades.listar(atual.current, { signal: controle.signal }).then(
      (pagina) => {
        if (controle.signal.aborted) return;
        carregada.current = { chave, tentativa };
        setEstado({ pagina, chave, carregando: false, carregandoMais: false, erro: null });
      },
      (causa: unknown) => {
        if (controle.signal.aborted) return;
        carregada.current = { chave, tentativa };
        setEstado((antes) => ({ ...antes, carregando: false, erro: paraErro(causa) }));
      },
    );
    return () => controle.abort();
  }, [chave, tentativa]);

  const verMais = async () => {
    const cursor = estado.pagina.proximo_cursor;
    if (!cursor || estado.carregandoMais) return;
    setEstado((antes) => ({ ...antes, carregandoMais: true, erro: null }));
    try {
      const seguinte = await atividades.listar({ ...atual.current, cursor });
      setEstado((antes) => ({
        ...antes,
        carregandoMais: false,
        pagina: { ...seguinte, grupos: juntarGrupos(antes.pagina.grupos, seguinte.grupos) },
      }));
    } catch (causa) {
      setEstado((antes) => ({ ...antes, carregandoMais: false, erro: paraErro(causa) }));
    }
  };

  return {
    ...estado,
    /** A lista na tela ainda é de outro filtro (chegando a nova). */
    desatualizada: estado.chave !== chave,
    verMais,
    tentarDeNovo: () => setTentativa((n) => n + 1),
  };
}
