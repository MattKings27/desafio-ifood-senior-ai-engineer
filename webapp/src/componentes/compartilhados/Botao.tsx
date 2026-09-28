"use client";

/**
 * Botão e botão só de ícone.
 *
 * O primário é o único elemento que usa o vermelho cheio da marca como fundo
 * (`marca-fundo`, #EB0033 nos dois temas). O resto da tela usa a marca só em
 * texto, ícone e foco. Todo botão tem pelo menos 44 px de altura.
 *
 * `carregando` não desabilita o botão de verdade: um botão `disabled` perde o
 * foco, e quem usa teclado ou leitor de tela fica sem saber onde está. Ele
 * fica `aria-disabled`, ignora o clique e mostra o giro.
 *
 * É um módulo de cliente porque o botão cuida do próprio clique. O link com
 * cara de botão (`BotaoLink`) não precisa, e mora em `BotaoLink.tsx`.
 */

import { CircleNotch } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ComponentPropsWithoutRef, MouseEvent, ReactNode } from "react";

import { unirClasses } from "./classes";
import type { Aparencia } from "./estilosDoBotao";
import { BASE_DO_BOTAO, Conteudo, VARIANTES_DO_BOTAO, classesDoBotao } from "./estilosDoBotao";

export type { Aparencia, TamanhoBotao, VarianteBotao } from "./estilosDoBotao";
export { classesDoBotao } from "./estilosDoBotao";

export type PropsDoBotao = ComponentPropsWithoutRef<"button"> &
  Aparencia & {
    carregando?: boolean;
    /** O texto enquanto carrega (ex.: "Salvando…"). Sem ele, fica o texto normal. */
    rotuloCarregando?: string;
  };

export function Botao({
  variante,
  tamanho,
  larguraTotal,
  icone,
  iconeDepois,
  carregando = false,
  rotuloCarregando,
  className,
  children,
  onClick,
  type = "button",
  "aria-disabled": ariaDisabled,
  ...resto
}: PropsDoBotao) {
  const aoClicar = (evento: MouseEvent<HTMLButtonElement>) => {
    if (carregando) {
      evento.preventDefault();
      return;
    }
    onClick?.(evento);
  };

  return (
    <button
      type={type}
      className={unirClasses(classesDoBotao({ variante, tamanho, larguraTotal }), className)}
      aria-busy={carregando || undefined}
      aria-disabled={carregando || ariaDisabled || undefined}
      onClick={aoClicar}
      {...resto}
    >
      <Conteudo
        icone={
          carregando ? <CircleNotch size={18} weight="bold" className="animate-spin" /> : icone
        }
        iconeDepois={carregando ? undefined : iconeDepois}
      >
        {carregando && rotuloCarregando ? rotuloCarregando : children}
      </Conteudo>
    </button>
  );
}

export type PropsDoBotaoIcone = Omit<ComponentPropsWithoutRef<"button">, "children"> & {
  /** O nome do botão, que o leitor de tela anuncia. Obrigatório: não há texto. */
  rotulo: string;
  children: ReactNode;
  variante?: "terciario" | "texto" | "primario";
  tamanho?: "sm" | "md";
};

/** Botão quadrado só com ícone (fechar, limpar a busca). 44 px no mínimo. */
export function BotaoIcone({
  rotulo,
  children,
  variante = "texto",
  tamanho = "sm",
  className,
  type = "button",
  ...resto
}: PropsDoBotaoIcone) {
  return (
    <button
      type={type}
      aria-label={rotulo}
      title={rotulo}
      className={unirClasses(
        clsx(
          BASE_DO_BOTAO,
          tamanho === "sm" ? "size-11" : "size-12",
          variante === "primario"
            ? VARIANTES_DO_BOTAO.primario
            : variante === "terciario"
              ? VARIANTES_DO_BOTAO.terciario
              : "bg-transparent text-texto hover:bg-secao",
        ),
        className,
      )}
      {...resto}
    >
      <span aria-hidden="true" className="inline-flex">
        {children}
      </span>
    </button>
  );
}
