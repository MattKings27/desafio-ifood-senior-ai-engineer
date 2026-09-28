"use client";

/**
 * Tirar um prato do cardápio e desfazer, com o aviso que ela lê.
 *
 * Tirar mostra a frase da API e o "Desfazer" no próprio aviso, que volta o
 * prato ao que era (com o preço de antes). O desfazer do histórico usa a
 * mesma ação. Cada clique leva uma chave nova: o reenvio do mesmo clique não
 * grava duas vezes.
 */

import { useToast } from "@/componentes/compartilhados/Toast";
import { desfazerNoCardapio, tirarDoCardapio } from "@/lib/acoes/cardapio";
import { novoIdCliente } from "@/lib/dados/id";
import { useAcao } from "@/lib/dados/useAcao";

export function useMudancasNoCardapio() {
  const toast = useToast();
  const desfazer = useAcao(desfazerNoCardapio, { sucesso: (dados) => dados.texto });
  const tirar = useAcao(tirarDoCardapio);

  const voltarAtras = (prato: string) => desfazer.executar(prato, novoIdCliente());

  const tirarComDesfazer = async (prato: string) => {
    const resultado = await tirar.executar(prato, novoIdCliente());
    if (resultado.ok) {
      toast.mostrar({
        texto: resultado.dados.texto,
        tom: "sucesso",
        acao: { rotulo: "Desfazer", aoClicar: () => void voltarAtras(prato) },
      });
    }
    return resultado;
  };

  return {
    tirar: tirarComDesfazer,
    tirando: tirar.pendente,
    desfazer: (prato: string) => void voltarAtras(prato),
    desfazendo: desfazer.pendente,
  };
}
