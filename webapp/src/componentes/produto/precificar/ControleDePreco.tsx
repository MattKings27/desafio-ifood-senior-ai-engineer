"use client";

/**
 * "E se a senhora cobrar…": o controle de preço.
 *
 * Os limites e o passo vêm da API (`controle{min, max, passo}`), e cada
 * parada pergunta à API o que acontece naquele preço (`/preco-em`): a tela não
 * multiplica nada. Começa no mínimo sem prejuízo, e não em um dos caminhos,
 * para não dar a entender que um deles é o recomendado.
 */

import { Info } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useEffect, useId, useState } from "react";

import { Card } from "@/componentes/compartilhados/Card";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import { ErroDoMotor } from "@/lib/api/base";
import type { PontoPreco, TabelaPrecos } from "@/lib/api/preco";
import { precoDeHoje } from "@/lib/api/preco";
import { porcentagem, textoParaEla } from "@/lib/formato";

/** Espera antes de perguntar: um pedido por parada, não um por pixel arrastado. */
export const PAUSA_DO_CONTROLE_MS = 120;

function Metrica({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-xs text-apagado">{rotulo}</dt>
      <dd className="numero font-semibold text-tinta">{valor}</dd>
    </div>
  );
}

export function ControleDePreco({
  tabela,
  ponto,
  aoMudarPonto,
}: {
  tabela: TabelaPrecos;
  ponto: PontoPreco | null;
  aoMudarPonto: (ponto: PontoPreco | null) => void;
}) {
  const id = useId();
  const { controle } = tabela;
  const [preco, setPreco] = useState(controle.min.valor);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vale = true;
    const agendado = setTimeout(() => {
      precoDeHoje.precoEm(tabela.prato, preco).then(
        (novo) => {
          if (!vale) return;
          setErro(null);
          aoMudarPonto(novo);
        },
        (causa: unknown) => {
          if (!vale) return;
          const mensagem = causa instanceof ErroDoMotor ? causa.message : null;
          setErro(textoParaEla(mensagem, "Não consegui fazer a conta desse preço. Tente de novo."));
        },
      );
    }, PAUSA_DO_CONTROLE_MS);
    return () => {
      vale = false;
      clearTimeout(agendado);
    };
  }, [preco, tabela.prato, aoMudarPonto]);

  const atual = ponto && ponto.preco.valor === preco ? ponto : null;

  return (
    <Card aria-labelledby={`${id}-titulo`}>
      <TituloSecao
        id={`${id}-titulo`}
        titulo="E se a senhora cobrar outro preço?"
        apoio="Arraste para ver o que muda. Quem decide o preço é a senhora."
      />
      <label htmlFor={`${id}-preco`} className="text-sm font-semibold text-tinta">
        Preço de uma porção
      </label>
      <input
        id={`${id}-preco`}
        type="range"
        min={controle.min.valor}
        max={controle.max.valor}
        step={controle.passo}
        value={preco}
        onChange={(evento) => setPreco(Number(evento.target.value))}
        aria-valuetext={atual ? atual.preco.texto : "calculando o preço"}
        className="mt-2 h-11 w-full cursor-pointer accent-marca focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-marca"
      />
      <div className="mt-1 flex justify-between gap-2 text-xs text-apagado">
        <span className="numero">mínimo sem prejuízo {controle.min.texto}</span>
        <span className="numero">{controle.max.texto}</span>
      </div>

      {erro ? (
        <p role="alert" className="mt-4 text-sm font-medium text-perigo">
          {erro}
        </p>
      ) : atual ? (
        <div
          aria-live="polite"
          className={clsx(
            "mt-4 rounded-md border p-4",
            atual.da_prejuizo ? "border-perigo/30 bg-perigo/5" : "border-sucesso/30 bg-sucesso/5",
          )}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <Valor dinheiro={atual.preco} tamanho="xl" />
            <div className="text-right">
              <p className="text-xs text-apagado">lucro por porção</p>
              <Valor dinheiro={atual.lucro} tamanho="lg" tom={atual.da_prejuizo ? "negativo" : "positivo"} />
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <Metrica rotulo="taxa" valor={atual.taxa.texto} />
            <Metrica rotulo="chega para a senhora" valor={atual.recebe.texto} />
            <Metrica rotulo="ingrediente no preço" valor={porcentagem(atual.food_cost)} />
            <Metrica rotulo="sobra do preço" valor={porcentagem(atual.margem)} />
          </dl>
          <Derivacao className="mt-2">{atual.explicacao}</Derivacao>
        </div>
      ) : (
        <p role="status" className="mt-4 text-sm text-apagado">
          Fazendo a conta…
        </p>
      )}

      <p className="mt-3 flex items-start gap-1.5 text-xs text-apagado">
        <Info size={14} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
        Cada valor é calculado de novo a cada parada, a partir da planilha da senhora.
      </p>
    </Card>
  );
}
