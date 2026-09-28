"use client";

/**
 * Campos de formulário.
 *
 * `Campo` liga o rótulo, a dica e o erro ao controle de dentro (ids,
 * `aria-describedby`, `aria-invalid`), sem quem usa precisar lembrar:
 *
 *     <Campo rotulo="Quanto pagou" dica="o total da nota" erro={erro}>
 *       <EntradaNumero valor={preco} aoMudar={setPreco} prefixo="R$" />
 *     </Campo>
 *
 * Texto de campo tem 16 px: abaixo disso o Safari do iPhone dá zoom ao tocar.
 * A borda do campo passa 3:1 contra a superfície (WCAG 1.4.11).
 */

import { CaretDown, MagnifyingGlass, Minus, Plus, WarningCircle, X } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type {
  ChangeEvent,
  ComponentPropsWithRef,
  FocusEvent,
  KeyboardEvent,
  ReactNode,
  Ref,
} from "react";
import { createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { formatarNumero, lerNumeroBR } from "@/lib/formato";

import { BotaoIcone } from "./Botao";
import { unirClasses } from "./classes";

/* -------------------------------------------------------------------------- */
/* Campo: rótulo, dica e erro                                                  */
/* -------------------------------------------------------------------------- */

type ContextoDoCampo = {
  id: string;
  descritoPor?: string;
  invalido: boolean;
  obrigatorio: boolean;
};

const ContextoCampo = createContext<ContextoDoCampo | null>(null);

/** O que um controle recebe do `Campo` em volta dele (se houver). */
function useLigacao(
  id: string | undefined,
  descritoPor: string | undefined,
  invalido: boolean | undefined,
  obrigatorio: boolean | undefined,
) {
  const campo = useContext(ContextoCampo);
  const juntos = [campo?.descritoPor, descritoPor].filter(Boolean).join(" ");
  return {
    id: id ?? campo?.id,
    "aria-describedby": juntos || undefined,
    "aria-invalid": invalido || campo?.invalido || undefined,
    required: obrigatorio ?? campo?.obrigatorio ?? undefined,
  };
}

export function Campo({
  rotulo,
  dica,
  erro,
  obrigatorio = false,
  opcional = false,
  rotuloVisivel = true,
  id,
  className,
  children,
}: {
  rotulo: ReactNode;
  dica?: ReactNode;
  /** Diz o que está errado e como consertar. */
  erro?: ReactNode;
  obrigatorio?: boolean;
  /** Escreve "(opcional)" ao lado do rótulo. */
  opcional?: boolean;
  rotuloVisivel?: boolean;
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  const gerado = useId();
  const idCampo = id ?? `campo${gerado}`;
  const idDica = dica ? `${idCampo}-dica` : undefined;
  const idErro = erro ? `${idCampo}-erro` : undefined;
  const descritoPor = [idErro, idDica].filter(Boolean).join(" ") || undefined;

  return (
    <ContextoCampo.Provider
      value={{ id: idCampo, descritoPor, invalido: Boolean(erro), obrigatorio }}
    >
      <div className={clsx("space-y-1.5", className)}>
        <label
          htmlFor={idCampo}
          className={rotuloVisivel ? "block text-sm font-semibold text-tinta" : "sr-only"}
        >
          {rotulo}
          {opcional ? <span className="font-normal text-apagado"> (opcional)</span> : null}
        </label>
        {children}
        {erro ? (
          <p id={idErro} className="flex items-start gap-1.5 text-sm font-medium text-perigo">
            <WarningCircle size={18} weight="fill" className="mt-px shrink-0" aria-hidden="true" />
            <span>{erro}</span>
          </p>
        ) : null}
        {dica ? (
          <p id={idDica} className="text-sm text-apagado">
            {dica}
          </p>
        ) : null}
      </div>
    </ContextoCampo.Provider>
  );
}

/* -------------------------------------------------------------------------- */
/* Controles                                                                   */
/* -------------------------------------------------------------------------- */

const CAIXA =
  "block w-full rounded-sm border border-borda-campo bg-superficie text-base text-tinta " +
  "placeholder:text-apagado transition-colors duration-rapida " +
  "hover:border-tinta/60 aria-invalid:border-perigo " +
  "disabled:cursor-not-allowed disabled:bg-secao disabled:text-apagado";

type PropsDaEntrada = ComponentPropsWithRef<"input"> & { invalido?: boolean };

export function Entrada({
  className,
  invalido,
  id,
  required,
  "aria-describedby": descritoPor,
  ...resto
}: PropsDaEntrada) {
  const ligacao = useLigacao(id, descritoPor, invalido, required);
  return <input className={unirClasses(clsx(CAIXA, "h-12 px-3"), className)} {...ligacao} {...resto} />;
}

function juntarRefs<T>(...refs: (Ref<T> | undefined)[]) {
  return (no: T | null) => {
    for (const ref of refs) {
      if (typeof ref === "function") ref(no);
      else if (ref) (ref as { current: T | null }).current = no;
    }
  };
}

type PropsDoNumero = Omit<
  ComponentPropsWithRef<"input">,
  "value" | "defaultValue" | "onChange" | "type" | "min" | "max" | "step"
> & {
  valor: number | null;
  aoMudar: (valor: number | null) => void;
  /** Casas decimais ao mostrar (0 para inteiros). */
  casas?: number;
  min?: number;
  max?: number;
  /** O quanto os botões − e + mudam. */
  passo?: number;
  /** Botões − e + dos lados, para quem não quer digitar. */
  comBotoes?: boolean;
  /** Antes do número (ex.: "R$"). */
  prefixo?: string;
  /** Depois do número (ex.: "bocas", "kg"). */
  unidade?: string;
  invalido?: boolean;
  /** Nome dos botões para o leitor de tela. */
  rotulos?: { menos: string; mais: string };
};

function comoTexto(valor: number | null, casas: number): string {
  return valor === null ? "" : formatarNumero(valor, casas);
}

/**
 * Número como ela escreve: vírgula decimal. Enquanto ela digita, o texto é
 * dela ("1," fica "1,"); ao sair do campo, o número é arrumado e preso aos
 * limites. Campo vazio é `null`, nunca zero.
 */
export function EntradaNumero({
  valor,
  aoMudar,
  casas = 2,
  min,
  max,
  passo = 1,
  comBotoes = false,
  prefixo,
  unidade,
  invalido,
  rotulos = { menos: "Diminuir", mais: "Aumentar" },
  className,
  id,
  required,
  disabled,
  onBlur,
  "aria-describedby": descritoPor,
  ...resto
}: PropsDoNumero) {
  const ligacao = useLigacao(id, descritoPor, invalido, required);
  const [texto, setTexto] = useState(() => comoTexto(valor, casas));

  // O valor mudou por fora (botão, outra tela): o texto acompanha. Enquanto o
  // texto dela já significa o mesmo número, ele fica como ela escreveu.
  useEffect(() => {
    setTexto((atual) => (lerNumeroBR(atual) === valor ? atual : comoTexto(valor, casas)));
  }, [valor, casas]);

  const limitar = (numero: number) => {
    let preso = numero;
    if (min !== undefined && preso < min) preso = min;
    if (max !== undefined && preso > max) preso = max;
    return Number(preso.toFixed(casas));
  };

  const aoDigitar = (evento: ChangeEvent<HTMLInputElement>) => {
    const novo = evento.target.value;
    setTexto(novo);
    if (novo.trim() === "") {
      aoMudar(null);
      return;
    }
    const numero = lerNumeroBR(novo);
    if (numero !== null) aoMudar(numero);
  };

  const aoSair = (evento: FocusEvent<HTMLInputElement>) => {
    const numero = lerNumeroBR(texto);
    if (numero === null) {
      // O que ficou escrito não é número ("1,", "abc"): volta ao último que era.
      setTexto(comoTexto(valor, casas));
    } else {
      const preso = limitar(numero);
      setTexto(comoTexto(preso, casas));
      if (preso !== valor) aoMudar(preso);
    }
    onBlur?.(evento);
  };

  const somar = (sinal: 1 | -1) => {
    const base = valor ?? min ?? 0;
    aoMudar(limitar(base + sinal * passo));
  };

  const entrada = (
    <div className="relative min-w-0 flex-1">
      {prefixo ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-base text-apagado"
        >
          {prefixo}
        </span>
      ) : null}
      <input
        type="text"
        inputMode={casas > 0 ? "decimal" : "numeric"}
        autoComplete="off"
        value={texto}
        onChange={aoDigitar}
        onBlur={aoSair}
        disabled={disabled}
        className={unirClasses(
          clsx(CAIXA, "numero h-12", prefixo ? "pl-10" : "pl-3", unidade ? "pr-16" : "pr-3"),
          className,
        )}
        {...ligacao}
        {...resto}
      />
      {unidade ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-apagado"
        >
          {unidade}
        </span>
      ) : null}
    </div>
  );

  if (!comBotoes) return entrada;
  return (
    <div className="flex items-center gap-2">
      <BotaoIcone
        rotulo={rotulos.menos}
        variante="terciario"
        disabled={disabled || (min !== undefined && valor !== null && valor <= min)}
        onClick={() => somar(-1)}
      >
        <Minus size={18} weight="bold" />
      </BotaoIcone>
      {entrada}
      <BotaoIcone
        rotulo={rotulos.mais}
        variante="terciario"
        disabled={disabled || (max !== undefined && valor !== null && valor >= max)}
        onClick={() => somar(1)}
      >
        <Plus size={18} weight="bold" />
      </BotaoIcone>
    </div>
  );
}

type PropsDaArea = ComponentPropsWithRef<"textarea"> & {
  invalido?: boolean;
  minLinhas?: number;
  maxLinhas?: number;
};

/** Área de texto que cresce com o que ela escreve, até `maxLinhas`. */
export function AreaDeTexto({
  invalido,
  minLinhas = 3,
  maxLinhas = 12,
  className,
  id,
  required,
  value,
  onChange,
  ref,
  "aria-describedby": descritoPor,
  ...resto
}: PropsDaArea) {
  const ligacao = useLigacao(id, descritoPor, invalido, required);
  const interna = useRef<HTMLTextAreaElement | null>(null);

  const ajustar = () => {
    const area = interna.current;
    if (!area) return;
    const estilo = window.getComputedStyle(area);
    const linha = Number.parseFloat(estilo.lineHeight) || 24;
    const bordas =
      (Number.parseFloat(estilo.paddingTop) || 0) + (Number.parseFloat(estilo.paddingBottom) || 0);
    const maximo = linha * maxLinhas + bordas;
    area.style.height = "auto";
    const altura = Math.min(area.scrollHeight, maximo);
    area.style.height = `${altura}px`;
    area.style.overflowY = area.scrollHeight > maximo ? "auto" : "hidden";
  };

  useLayoutEffect(ajustar);

  return (
    <textarea
      ref={juntarRefs(ref, interna)}
      rows={minLinhas}
      value={value}
      onChange={(evento) => {
        onChange?.(evento);
        ajustar();
      }}
      className={unirClasses(clsx(CAIXA, "resize-none px-3 py-2.5 leading-6"), className)}
      {...ligacao}
      {...resto}
    />
  );
}

type Opcao = { valor: string; rotulo: string; desabilitada?: boolean };

type PropsDaSelecao = ComponentPropsWithRef<"select"> & {
  opcoes?: readonly Opcao[];
  invalido?: boolean;
};

/** A seleção nativa do sistema, com a seta desenhada por cima. */
export function Selecao({
  opcoes,
  invalido,
  className,
  children,
  id,
  required,
  "aria-describedby": descritoPor,
  ...resto
}: PropsDaSelecao) {
  const ligacao = useLigacao(id, descritoPor, invalido, required);
  return (
    <div className="relative">
      <select
        className={unirClasses(clsx(CAIXA, "h-12 cursor-pointer appearance-none pr-10 pl-3"), className)}
        {...ligacao}
        {...resto}
      >
        {opcoes?.map((opcao) => (
          <option key={opcao.valor} value={opcao.valor} disabled={opcao.desabilitada}>
            {opcao.rotulo}
          </option>
        ))}
        {children}
      </select>
      <CaretDown
        size={18}
        weight="bold"
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-3 my-auto text-apagado"
      />
    </div>
  );
}

type PropsDaBusca = Omit<ComponentPropsWithRef<"input">, "value" | "onChange" | "type"> & {
  valor: string;
  aoMudar: (valor: string) => void;
  /** O nome do campo. Fica escondido quando não há `Campo` em volta. */
  rotulo?: string;
};

/**
 * Busca de uma lista. Esc limpa; o botão ✕ também. Quem usa decide se filtra
 * na hora (lista já recebida) ou pede à API.
 */
export function Busca({
  valor,
  aoMudar,
  rotulo = "Buscar",
  placeholder,
  className,
  id,
  required,
  onKeyDown,
  "aria-describedby": descritoPor,
  ...resto
}: PropsDaBusca) {
  const campo = useContext(ContextoCampo);
  const gerado = useId();
  const ligacao = useLigacao(id ?? (campo ? undefined : `busca${gerado}`), descritoPor, undefined, required);
  const interna = useRef<HTMLInputElement | null>(null);

  const aoTeclar = (evento: KeyboardEvent<HTMLInputElement>) => {
    if (evento.key === "Escape" && valor !== "") {
      evento.preventDefault();
      aoMudar("");
    }
    onKeyDown?.(evento);
  };

  return (
    <div className={clsx("relative", className)}>
      {campo ? null : (
        <label htmlFor={ligacao.id} className="sr-only">
          {rotulo}
        </label>
      )}
      <MagnifyingGlass
        size={20}
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-3 my-auto text-apagado"
      />
      <input
        ref={interna}
        type="search"
        value={valor}
        placeholder={placeholder}
        onChange={(evento) => aoMudar(evento.target.value)}
        onKeyDown={aoTeclar}
        enterKeyHint="search"
        autoComplete="off"
        className={clsx(CAIXA, "h-12 pr-12 pl-10 [&::-webkit-search-cancel-button]:appearance-none")}
        {...ligacao}
        {...resto}
      />
      {valor !== "" ? (
        <BotaoIcone
          rotulo="Limpar a busca"
          className="absolute inset-y-0 right-0.5 my-auto"
          onClick={() => {
            aoMudar("");
            interna.current?.focus();
          }}
        >
          <X size={18} weight="bold" />
        </BotaoIcone>
      ) : null}
    </div>
  );
}
