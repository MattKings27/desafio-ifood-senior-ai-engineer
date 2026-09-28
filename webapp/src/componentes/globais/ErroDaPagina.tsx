"use client";

/**
 * A página que falhou ao abrir (o `error.tsx` de cada rota usa esta).
 *
 * Em produção o Next não passa a mensagem de um erro do servidor (ela pode ter
 * detalhe sensível), e mesmo que passasse ela não seria para a Dona Maria. A
 * tela diz o que aconteceu do jeito dela e oferece duas saídas: tentar de novo
 * (o `retry` do Next 16.3 busca a página de novo) ou voltar ao início.
 */

import { House } from "@phosphor-icons/react/dist/ssr";
import { useEffect } from "react";

import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Problema } from "@/componentes/compartilhados/Problema";

export type PropsDoErroDaRota = {
  error: Error & { digest?: string };
  retry: () => void;
};

export function ErroDaPagina({
  error,
  retry,
  titulo = "Não consegui abrir esta página",
}: PropsDoErroDaRota & { titulo?: string }) {
  useEffect(() => {
    // Para quem investiga: o digest casa com o log do servidor.
    console.error("a página não abriu", error.digest ?? error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl py-6">
      <Problema
        categoria="rede"
        titulo={titulo}
        nivelTitulo={1}
        anunciar="alert"
        aoTentarDeNovo={retry}
        acao={
          <BotaoLink href="/" variante="texto" tamanho="sm" icone={<House size={18} weight="bold" />}>
            Voltar ao início
          </BotaoLink>
        }
      />
    </div>
  );
}
