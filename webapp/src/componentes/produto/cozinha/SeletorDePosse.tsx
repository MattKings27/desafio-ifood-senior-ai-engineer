"use client";

/**
 * Tenho / Não tenho / Não sei (para técnica, Faço / Não faço / Não sei).
 *
 * É a resposta dela sobre um equipamento ou uma técnica, na tela da cozinha e
 * nos passos de uma receita. Nada marcado quer dizer que ela ainda não
 * respondeu, e isso inclui o suposto: marcar "Tenho" num item que ninguém
 * perguntou seria dizer que ela disse o que não disse. "Não sei" é resposta, e
 * fica marcado como "Não sei".
 *
 *     <SeletorDePosse tipo="tecnica" legenda="Molho béchamel" valor={respostaDoItem(item)} aoMudar={gravar} />
 */

import { Check, Question, X } from "@phosphor-icons/react/dist/ssr";

import type { OpcaoDoSegmentado } from "@/componentes/compartilhados/Segmentado";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import type { RespostaDePosse } from "@/lib/api/perfil";

export { respostaDoItem } from "@/lib/filtros/cozinha";

export type TipoDePosse = "equipamento" | "tecnica";

/** O ícone só aparece com espaço (a partir de 640 px): no celular, "Não tenho" inteiro vale mais. */
const ICONES = {
  tem: <Check size={16} weight="bold" className="hidden sm:block" />,
  nao_tem: <X size={16} weight="bold" className="hidden sm:block" />,
  nao_sei: <Question size={16} weight="bold" className="hidden sm:block" />,
} as const;

export const OPCOES_DE_POSSE: Readonly<Record<TipoDePosse, readonly OpcaoDoSegmentado<RespostaDePosse>[]>> = {
  equipamento: [
    { valor: "tem", rotulo: "Tenho", icone: ICONES.tem },
    { valor: "nao_tem", rotulo: "Não tenho", icone: ICONES.nao_tem },
    { valor: "nao_sei", rotulo: "Não sei", icone: ICONES.nao_sei },
  ],
  tecnica: [
    { valor: "tem", rotulo: "Faço", icone: ICONES.tem },
    { valor: "nao_tem", rotulo: "Não faço", icone: ICONES.nao_tem },
    { valor: "nao_sei", rotulo: "Não sei", icone: ICONES.nao_sei },
  ],
};

export function SeletorDePosse({
  tipo,
  legenda,
  valor,
  aoMudar,
  legendaVisivel = false,
  desabilitado = false,
  nome,
  className,
}: {
  tipo: TipoDePosse;
  /** O nome do item: é o que o leitor de tela anuncia ("Forno, Tenho, 1 de 3"). */
  legenda: string;
  /** `null` quando ela ainda não respondeu (o suposto também). */
  valor: RespostaDePosse | null;
  aoMudar: (resposta: RespostaDePosse) => void;
  legendaVisivel?: boolean;
  desabilitado?: boolean;
  nome?: string;
  className?: string;
}) {
  return (
    <Segmentado
      legenda={legenda}
      legendaVisivel={legendaVisivel}
      opcoes={OPCOES_DE_POSSE[tipo]}
      valor={valor}
      aoMudar={aoMudar}
      desabilitado={desabilitado}
      nome={nome}
      className={className}
    />
  );
}
