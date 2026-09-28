"use client";

/**
 * Os limites da rotina: quantas bocas, quantas horas ela cozinha de uma vez
 * (em horas, com vírgula: "1,5"; o motor guarda minutos), quantas porções por
 * leva, espaço na geladeira, aparelhos fortes ligados juntos e o botijão de
 * reserva.
 *
 * Número tem + e −, a unidade ao lado e o "Não sei", que é resposta dela (e
 * não "ainda não perguntei"). O gás é Sim / Não / Não sei. Cada mudança grava
 * 300 ms depois do último toque. A faixa (de 1 a 8 bocas…) vem da API: número
 * fora dela não é enviado, e o campo diz qual é a faixa.
 */

import { ChatCircleDots, Question } from "@phosphor-icons/react/dist/ssr";
import { useId, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { EntradaNumero } from "@/componentes/compartilhados/Campos";
import { Card } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import { definirRestricao } from "@/lib/acoes/cozinha";
import type { ImpactoDaMudanca, RespostaDaCozinha, Restricao } from "@/lib/api/perfil";
import { formatarNumero } from "@/lib/formato";

import { NotaDoImpacto, TextoDaGravacao } from "./ItemDaCozinha";
import { useGravacaoAdiada } from "./useGravacaoAdiada";

/** O nome de cada limite na tela; um campo novo da API aparece pela pergunta. */
export const ROTULO_DO_LIMITE: Readonly<Record<string, string>> = {
  bocas_fogao: "Bocas do fogão",
  tempo_max_por_fornada_min: "Horas cozinhando de uma vez",
  porcoes_por_fornada: "Porções por leva",
  espaco_geladeira_litros: "Espaço livre na geladeira",
  energia_aparelhos_simultaneos: "Aparelhos fortes ligados juntos",
  tem_gas_sobrando: "Botijão de gás de reserva",
};

type ValorNaTela = number | boolean | "nao_sei" | null;

/** O valor da API na tela: `null` com "não sei" é "não sei"; `null` sem ele, ainda não perguntado. */
export function valorNaTela(restricao: Restricao): ValorNaTela {
  if (restricao.valor !== null) return restricao.valor;
  return restricao.nao_sei ? "nao_sei" : null;
}

function Situacao({ restricao, valor }: { restricao: Restricao; valor: ValorNaTela }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {valor === "nao_sei" ? <Chip tom="neutro">A senhora disse que não sabe</Chip> : null}
      {valor === null ? <Chip tom="neutro">Ainda não perguntei</Chip> : null}
      {restricao.atualizado_por === "conversa" ? (
        <Chip tom="info" icone={<ChatCircleDots size={14} weight="fill" />}>
          Atualizado pela conversa{restricao.atualizado_texto ? `, ${restricao.atualizado_texto}` : ""}
        </Chip>
      ) : null}
    </div>
  );
}

function useLimite(campo: string, restricao: Restricao, aoGravar?: (texto: string) => void) {
  const [impacto, setImpacto] = useState<ImpactoDaMudanca | null>(null);
  const gravacao = useGravacaoAdiada<ValorNaTela, RespostaDaCozinha>(
    valorNaTela(restricao),
    (valor) => definirRestricao(campo, valor === "nao_sei" ? null : valor),
    {
      aoGravar: (dados) => {
        setImpacto(dados.impacto);
        aoGravar?.(`${ROTULO_DO_LIMITE[campo] ?? restricao.pergunta}: ${dados.impacto.texto}`);
      },
    },
  );
  return { gravacao, impacto };
}

function LimiteDeNumero({
  campo,
  restricao,
  aoGravar,
}: {
  campo: string;
  restricao: Restricao;
  aoGravar?: (texto: string) => void;
}) {
  const id = useId();
  const [foraDaFaixa, setForaDaFaixa] = useState<string | null>(null);
  const { gravacao, impacto } = useLimite(campo, restricao, aoGravar);
  const numero = typeof gravacao.valor === "number" ? gravacao.valor : null;
  const rotulo = ROTULO_DO_LIMITE[campo] ?? restricao.pergunta;
  const unidade = restricao.unidade ?? "";

  const mudar = (valor: number | null) => {
    // Campo apagado não é "não sei": só o botão diz isso.
    if (valor === null) return;
    const { min, max } = restricao;
    if ((min !== undefined && valor < min) || (max !== undefined && valor > max)) {
      const [de, ate] = [min, max].map((limite) => (limite === undefined ? "" : formatarNumero(limite)));
      setForaDaFaixa(`Diga um número de ${de} a ${ate} ${unidade}.`.replace(/\s+\./, "."));
      return;
    }
    setForaDaFaixa(null);
    gravacao.mudar(valor);
  };

  return (
    <li className="flex flex-col gap-2 py-4">
      <label htmlFor={`${id}-numero`} className="text-base font-semibold text-tinta">
        {rotulo}
      </label>
      <p id={`${id}-pergunta`} className="text-sm text-apagado">
        {restricao.pergunta}
      </p>
      <Situacao restricao={restricao} valor={gravacao.valor} />
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1 basis-56">
          <EntradaNumero
            id={`${id}-numero`}
            aria-describedby={foraDaFaixa ? `${id}-pergunta ${id}-faixa` : `${id}-pergunta`}
            invalido={foraDaFaixa !== null}
            valor={numero}
            aoMudar={mudar}
            casas={restricao.casas ?? 0}
            passo={restricao.passo ?? 1}
            min={restricao.min}
            max={restricao.max}
            unidade={unidade}
            comBotoes
            rotulos={{ menos: `Menos: ${rotulo}`, mais: `Mais: ${rotulo}` }}
          />
        </div>
        <Botao
          variante={gravacao.valor === "nao_sei" ? "secundario" : "terciario"}
          tamanho="md"
          aria-pressed={gravacao.valor === "nao_sei"}
          icone={<Question size={18} weight="bold" />}
          onClick={() => {
            setForaDaFaixa(null);
            gravacao.mudar("nao_sei");
          }}
        >
          Não sei
        </Botao>
      </div>
      {foraDaFaixa ? (
        <p id={`${id}-faixa`} className="text-sm font-medium text-perigo">
          {foraDaFaixa}
        </p>
      ) : null}
      <TextoDaGravacao estado={gravacao.estado} />
      {impacto ? <NotaDoImpacto impacto={impacto} /> : null}
    </li>
  );
}

const SIM_NAO = [
  { valor: "sim", rotulo: "Sim" },
  { valor: "nao", rotulo: "Não" },
  { valor: "nao_sei", rotulo: "Não sei" },
] as const;

type OpcaoSimNao = (typeof SIM_NAO)[number]["valor"];

function LimiteDeSimNao({
  campo,
  restricao,
  aoGravar,
}: {
  campo: string;
  restricao: Restricao;
  aoGravar?: (texto: string) => void;
}) {
  const { gravacao, impacto } = useLimite(campo, restricao, aoGravar);
  const rotulo = ROTULO_DO_LIMITE[campo] ?? restricao.pergunta;
  const marcado: OpcaoSimNao | null =
    gravacao.valor === true ? "sim" : gravacao.valor === false ? "nao" : gravacao.valor === "nao_sei" ? "nao_sei" : null;

  return (
    <li className="flex flex-col gap-2 py-4">
      <Segmentado<OpcaoSimNao>
        legenda={rotulo}
        opcoes={SIM_NAO}
        valor={marcado}
        aoMudar={(opcao) => gravacao.mudar(opcao === "sim" ? true : opcao === "nao" ? false : "nao_sei")}
        className="sm:max-w-md"
      />
      <p className="text-sm text-apagado">{restricao.pergunta}</p>
      <Situacao restricao={restricao} valor={gravacao.valor} />
      <TextoDaGravacao estado={gravacao.estado} />
      {impacto ? <NotaDoImpacto impacto={impacto} /> : null}
    </li>
  );
}

export function LimitesDaRotina({
  restricoes,
  aoGravar,
  className,
}: {
  restricoes: Readonly<Record<string, Restricao>>;
  aoGravar?: (texto: string) => void;
  className?: string;
}) {
  return (
    <Card aria-labelledby="titulo-dos-limites" className={className}>
      <h2 id="titulo-dos-limites" className="text-lg font-bold text-tinta">
        Limites da rotina
      </h2>
      <p className="text-sm text-apagado">Gás, geladeira, tempo e energia: o que a rotina da senhora aguenta.</p>
      <ul className="mt-2 divide-y divide-borda">
        {Object.entries(restricoes).map(([campo, restricao]) =>
          restricao.tipo === "sim_nao" ? (
            <LimiteDeSimNao key={campo} campo={campo} restricao={restricao} aoGravar={aoGravar} />
          ) : (
            <LimiteDeNumero key={campo} campo={campo} restricao={restricao} aoGravar={aoGravar} />
          ),
        )}
      </ul>
    </Card>
  );
}
