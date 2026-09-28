"use client";

/**
 * Peças de filtro de lista: chips de escolha, os filtros ativos, o botão que
 * abre a folha de filtros e a ordenação.
 *
 * Os chips são caixas de marcar (ou rádios, na escolha única) nativas, num
 * `fieldset`: o teclado e o leitor de tela funcionam sem reescrever nada. Os
 * chips quebram linha; nada rola de lado.
 */

import { Check, FunnelSimple, X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useId } from "react";

import { Botao } from "./Botao";
import { Selecao } from "./Campos";

export type OpcaoDeFiltro<V extends string> = { valor: V; rotulo: string; contagem?: number };

export function FiltroChips<V extends string>({
  legenda,
  opcoes,
  selecionados,
  aoMudar,
  multiplo = true,
  legendaVisivel = false,
  nome,
  className,
}: {
  legenda: string;
  opcoes: readonly OpcaoDeFiltro<V>[];
  selecionados: readonly V[];
  aoMudar: (selecionados: V[]) => void;
  /** `false`: escolha única (rádios). */
  multiplo?: boolean;
  legendaVisivel?: boolean;
  nome?: string;
  className?: string;
}) {
  const gerado = useId();
  const grupo = nome ?? `filtro${gerado}`;

  const alternar = (valor: V) => {
    if (!multiplo) {
      aoMudar([valor]);
      return;
    }
    aoMudar(
      selecionados.includes(valor)
        ? selecionados.filter((atual) => atual !== valor)
        : [...selecionados, valor],
    );
  };

  return (
    <fieldset className={clsx("min-w-0", className)}>
      <legend className={legendaVisivel ? "mb-2 text-sm font-semibold text-tinta" : "sr-only"}>
        {legenda}
      </legend>
      <div className="flex flex-wrap gap-2">
        {opcoes.map((opcao) => {
          const marcado = selecionados.includes(opcao.valor);
          return (
            <label key={opcao.valor} className="relative">
              <input
                type={multiplo ? "checkbox" : "radio"}
                name={grupo}
                value={opcao.valor}
                checked={marcado}
                onChange={() => alternar(opcao.valor)}
                className="peer sr-only"
              />
              <span
                className={clsx(
                  "inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-full border px-3.5 text-sm font-semibold",
                  "transition-colors duration-rapida",
                  "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marca",
                  marcado
                    ? "border-tinta bg-tinta text-superficie"
                    : "border-borda-campo/60 bg-superficie text-texto hover:bg-secao",
                )}
              >
                {marcado ? <Check size={14} weight="bold" aria-hidden="true" /> : null}
                {opcao.rotulo}
                {opcao.contagem !== undefined ? " " : null}
                {opcao.contagem !== undefined ? (
                  <span className={clsx("numero font-normal", marcado ? "text-superficie" : "text-apagado")}>
                    {opcao.contagem}
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export type FiltroAtivo = { id: string; rotulo: string; aoRemover: () => void };

/**
 * O que está filtrando agora, cada um com o ✕ para tirar. O resumo ("12 de 37
 * ingredientes") é anunciado quando muda, para quem não vê a lista encolher.
 */
export function ChipsAtivos({
  filtros,
  aoLimparTudo,
  resumo,
  className,
}: {
  filtros: readonly FiltroAtivo[];
  aoLimparTudo?: () => void;
  resumo?: string;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-wrap items-center gap-2", className)}>
      {resumo ? (
        <p role="status" className="mr-1 text-sm text-apagado">
          {resumo}
        </p>
      ) : null}
      {filtros.length > 0 ? (
        <ul aria-label="Filtros ativos" className="flex flex-wrap gap-2">
          {filtros.map((filtro) => (
            <li key={filtro.id}>
              <button
                type="button"
                onClick={filtro.aoRemover}
                aria-label={`${filtro.rotulo}: tirar este filtro`}
                className={clsx(
                  "inline-flex min-h-11 items-center gap-1.5 rounded-full border border-borda bg-secao py-1 pr-2.5 pl-3.5",
                  "text-sm font-semibold text-texto transition-colors duration-rapida hover:border-borda-campo",
                )}
              >
                {filtro.rotulo}
                <X size={14} weight="bold" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {aoLimparTudo && filtros.length > 1 ? (
        <button
          type="button"
          onClick={aoLimparTudo}
          className="min-h-11 rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
        >
          Limpar filtros
        </button>
      ) : null}
    </div>
  );
}

/** "Filtros (2)": abre a folha com os filtros que não cabem na barra. */
export function BotaoFiltros({
  quantidade,
  aoAbrir,
  aberto = false,
  className,
}: {
  quantidade: number;
  aoAbrir: () => void;
  aberto?: boolean;
  className?: string;
}) {
  return (
    <Botao
      variante="terciario"
      tamanho="sm"
      icone={<FunnelSimple size={18} weight="bold" />}
      aria-haspopup="dialog"
      aria-expanded={aberto}
      onClick={aoAbrir}
      className={className}
    >
      Filtros
      {quantidade > 0 ? " " : null}
      {quantidade > 0 ? (
        <>
          <span className="numero rounded-full bg-tinta px-1.5 text-xs font-bold text-superficie">
            {quantidade}
          </span>{" "}
          <span className="sr-only">ativos</span>
        </>
      ) : null}
    </Botao>
  );
}

export function Ordenacao<V extends string>({
  opcoes,
  valor,
  aoMudar,
  rotulo = "Ordenar por",
  className,
}: {
  opcoes: readonly { valor: V; rotulo: string }[];
  valor: V;
  aoMudar: (valor: V) => void;
  rotulo?: string;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={clsx("flex items-center gap-2", className)}>
      <label htmlFor={`ordem${id}`} className="shrink-0 text-sm text-apagado">
        {rotulo}
      </label>
      <Selecao
        id={`ordem${id}`}
        value={valor}
        onChange={(evento) => aoMudar(evento.target.value as V)}
        opcoes={opcoes}
        className="h-11 text-sm"
      />
    </div>
  );
}
