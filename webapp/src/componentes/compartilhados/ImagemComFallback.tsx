"use client";

/**
 * Foto de receita, ingrediente ou prato, com proporção fixa e plano B.
 *
 * Só carrega imagem servida pela API (`/motor/imagens/<chave hex>`): a
 * interface nunca busca foto de outro endereço, e um `src` fora disso é
 * tratado como sem foto. É um `<img loading="lazy">` comum, não o otimizador
 * do Next, que com o curinga de antes virava um proxy aberto.
 *
 * Enquanto carrega, a caixa brilha; se a foto falhar (ou não existir), entra
 * um gradiente com o ícone do tipo. A proporção não muda em nenhum dos casos,
 * então a grade não pula.
 */

import { Basket, CookingPot, ForkKnife } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";

import { ehImagemDaApi } from "@/lib/api/base";

export type ProporcaoDaImagem = "1/1" | "4/3" | "16/9" | "3/2";
export type TipoDeImagem = "receita" | "ingrediente" | "prato";

const PROPORCOES: Record<ProporcaoDaImagem, string> = {
  "1/1": "aspect-square",
  "4/3": "aspect-[4/3]",
  "16/9": "aspect-video",
  "3/2": "aspect-[3/2]",
};

const ICONES: Record<TipoDeImagem, (tamanho: number) => ReactNode> = {
  receita: (tamanho) => <ForkKnife size={tamanho} weight="duotone" />,
  ingrediente: (tamanho) => <Basket size={tamanho} weight="duotone" />,
  prato: (tamanho) => <CookingPot size={tamanho} weight="duotone" />,
};

type Estado = "carregando" | "pronta" | "falhou";

export function ImagemComFallback({
  src,
  alt,
  proporcao = "4/3",
  tipo = "receita",
  credito,
  mostrarCredito = false,
  prioridade = false,
  icone,
  classeDoFundo,
  className,
  classeDaImagem,
}: {
  src: string | null | undefined;
  /** Vazio (`""`) quando o nome está ao lado da foto, como nos cartões. */
  alt: string;
  proporcao?: ProporcaoDaImagem;
  tipo?: TipoDeImagem;
  /** "Foto: Wikimedia Commons (CC BY-SA 4.0)". */
  credito?: string | null;
  /** Nas páginas de detalhe, o crédito aparece embaixo da foto. */
  mostrarCredito?: boolean;
  /** A foto do topo de uma página de detalhe: carrega já, sem esperar rolar. */
  prioridade?: boolean;
  /** Sem foto: um ícone no lugar do ícone do tipo (o do prato, por exemplo). */
  icone?: ReactNode;
  /** Sem foto: outro fundo no lugar do gradiente padrão (um tom por receita, para a grade variar). */
  classeDoFundo?: string;
  className?: string;
  classeDaImagem?: string;
}) {
  const valida = ehImagemDaApi(src);
  const [estado, setEstado] = useState<Estado>(valida ? "carregando" : "falhou");
  const imagem = useRef<HTMLImageElement | null>(null);

  // A foto pode ter carregado (ou falhado) antes de o React assumir a página:
  // o onLoad/onError daquela hora se perdeu. Confere o estado real ao montar.
  // Trocou a foto: recomeça do "carregando".
  useLayoutEffect(() => {
    if (!ehImagemDaApi(src)) {
      setEstado("falhou");
      return;
    }
    const no = imagem.current;
    if (no?.complete) setEstado(no.naturalWidth > 0 ? "pronta" : "falhou");
    else setEstado("carregando");
  }, [src]);

  const mostrarFoto = valida && estado !== "falhou";
  const caixa = (
    <div
      className={clsx(
        "relative w-full overflow-hidden bg-secao",
        PROPORCOES[proporcao],
        !mostrarCredito && className,
      )}
    >
      {mostrarFoto ? (
        <>
          {estado === "carregando" ? (
            <div aria-hidden="true" className="esqueleto animate-brilho absolute inset-0" />
          ) : null}
          <img
            ref={imagem}
            src={src}
            alt={alt}
            loading={prioridade ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={prioridade ? "high" : undefined}
            onLoad={() => setEstado("pronta")}
            onError={() => setEstado("falhou")}
            className={clsx(
              "absolute inset-0 size-full object-cover transition-opacity duration-padrao",
              estado === "pronta" ? "opacity-100" : "opacity-0",
              classeDaImagem,
            )}
          />
        </>
      ) : (
        <div
          role={alt ? "img" : undefined}
          aria-label={alt || undefined}
          aria-hidden={alt ? undefined : true}
          className={clsx(
            "absolute inset-0 flex items-center justify-center",
            classeDoFundo ?? "bg-linear-to-br from-creme to-secao text-apagado",
          )}
        >
          {icone ?? ICONES[tipo](proporcao === "16/9" ? 48 : 40)}
        </div>
      )}
    </div>
  );

  if (!mostrarCredito) return caixa;
  return (
    <figure className={className}>
      {caixa}
      {credito ? <figcaption className="mt-1.5 text-xs text-apagado">{credito}</figcaption> : null}
    </figure>
  );
}
