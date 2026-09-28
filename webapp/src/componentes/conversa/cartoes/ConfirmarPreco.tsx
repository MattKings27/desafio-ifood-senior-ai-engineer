"use client";

/**
 * "Vou cobrar este": a confirmação antes de gravar o preço de um prato.
 *
 * Aceitar um preço é decisão dela e entra no cardápio, então passa por um
 * diálogo que busca a conta de novo no motor (`/preco-em`), com o preço
 * escolhido: quanto ela recebe depois da taxa, quanto sobra por porção e, se
 * for o caso, o aviso de prejuízo. Só com a conta nova na tela o botão manda
 * a ação `decidir`; o backend executa pelo portão antes de contar ao
 * agente, e o mesmo `id_cliente` nunca grava duas vezes.
 */

import { WarningCircle } from "@phosphor-icons/react/dist/ssr";
import { useEffect, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Dialogo } from "@/componentes/compartilhados/Dialogo";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { PontoPreco } from "@/lib/api/preco";
import { precoDeHoje } from "@/lib/api/preco";
import { rascunhos } from "@/lib/conversa/perguntas";
import { textoParaEla } from "@/lib/formato";

import { useAcoesDaConversa } from "../useAcoesDaConversa";
import { bool, dinheiro, str } from "./leitura";

export type PedidoDePreco = {
  prato: string;
  /** O número do preço, como veio do motor (vai na ação). */
  valor: number;
  /** O texto do preço, como veio do motor ("R$ 18,00"). */
  texto?: string | null;
};

type Conta =
  | { estado: "buscando" }
  | { estado: "pronta"; ponto: PontoPreco }
  | { estado: "falhou"; mensagem: string };

const FALHA_DA_CONTA = "Não consegui conferir a conta com esse preço agora. Tente de novo.";

function ConteudoDaConta({ conta, aoTentarDeNovo }: { conta: Conta; aoTentarDeNovo: () => void }) {
  if (conta.estado === "buscando") {
    return (
      <p role="status" className="text-base text-apagado">
        Conferindo a conta com esse preço…
      </p>
    );
  }
  if (conta.estado === "falhou") {
    return (
      <div role="alert" className="space-y-2">
        <p className="text-base text-texto">{conta.mensagem}</p>
        <Botao variante="terciario" tamanho="sm" onClick={aoTentarDeNovo}>
          Conferir de novo
        </Botao>
      </div>
    );
  }
  const { ponto } = conta;
  const recebe = dinheiro(ponto.recebe);
  const lucro = dinheiro(ponto.lucro);
  const prejuizo = bool(ponto.da_prejuizo) === true;
  const explicacao = str(ponto.explicacao);
  return (
    <div className="space-y-3">
      <dl className="divide-y divide-borda rounded-lg border border-borda">
        <div className="flex items-baseline justify-between gap-3 px-4 py-3">
          <dt className="text-base text-texto">A senhora recebe, depois da taxa</dt>
          <dd>
            <Valor dinheiro={recebe} tamanho="md" />
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3 px-4 py-3">
          <dt className="text-base text-texto">Sobra por porção</dt>
          <dd>
            <Valor dinheiro={lucro} tamanho="md" />
          </dd>
        </div>
      </dl>
      {prejuizo ? (
        <p className="flex items-start gap-2 rounded-lg border border-perigo/25 bg-perigo/10 px-3 py-2.5 text-base text-perigo">
          <WarningCircle size={20} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
          Com esse preço a senhora perde dinheiro em cada porção. A decisão é da senhora.
        </p>
      ) : null}
      {explicacao ? <Derivacao className="text-sm">{explicacao}</Derivacao> : null}
    </div>
  );
}

export function ConfirmarPreco({ pedido, aoFechar }: { pedido: PedidoDePreco | null; aoFechar: () => void }) {
  const acoes = useAcoesDaConversa();
  const [conta, setConta] = useState<Conta>({ estado: "buscando" });
  const [tentativa, setTentativa] = useState(0);

  const prato = pedido?.prato ?? null;
  const valor = pedido?.valor ?? null;

  useEffect(() => {
    if (prato === null || valor === null) return;
    let valendo = true;
    setConta({ estado: "buscando" });
    precoDeHoje
      .precoEm(prato, valor)
      .then((ponto) => {
        if (valendo) setConta({ estado: "pronta", ponto });
      })
      .catch((causa: unknown) => {
        if (!valendo) return;
        const mensagem = causa instanceof Error ? causa.message : undefined;
        setConta({ estado: "falhou", mensagem: textoParaEla(mensagem, FALHA_DA_CONTA) });
      });
    return () => {
      valendo = false;
    };
  }, [prato, valor, tentativa]);

  if (!pedido) return <Dialogo aberto={false} aoFechar={aoFechar} titulo="Cobrar este preço?" />;

  const precoTexto =
    (conta.estado === "pronta" ? dinheiro(conta.ponto.preco)?.texto : null) ?? str(pedido.texto) ?? "este preço";

  const confirmar = () => {
    if (conta.estado !== "pronta" || acoes.ocupada) return;
    acoes.enviar(rascunhos.vouCobrar(precoTexto, pedido.prato), {
      acao: { tipo: "decidir", prato: pedido.prato, decisao: "aceito", preco: pedido.valor },
    });
    aoFechar();
  };

  return (
    <Dialogo
      aberto
      aoFechar={aoFechar}
      titulo={`Cobrar ${precoTexto} por porção?`}
      descricao={
        <p>
          O prato <strong className="font-bold text-tinta">{pedido.prato}</strong> entra no cardápio com esse preço.
          A senhora pode mudar depois.
        </p>
      }
      acoes={
        <>
          <Botao variante="terciario" onClick={aoFechar}>
            Agora não
          </Botao>
          <Botao
            variante="primario"
            onClick={confirmar}
            aria-disabled={conta.estado !== "pronta" || acoes.ocupada || undefined}
            title={acoes.motivo ?? undefined}
          >
            Vou cobrar este
          </Botao>
        </>
      }
    >
      <ConteudoDaConta conta={conta} aoTentarDeNovo={() => setTentativa((n) => n + 1)} />
    </Dialogo>
  );
}
