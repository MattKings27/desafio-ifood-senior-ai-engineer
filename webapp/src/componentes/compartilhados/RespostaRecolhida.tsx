"use client";

/**
 * O "Responder" do modo minimalista: a pergunta fica numa linha, e a resposta
 * (o formulário) abre ali mesmo quando ela toca. Fora do modo, o botão não
 * aparece e a resposta fica à vista, como sempre.
 *
 * Quem esconde e mostra é a variante `minimalista:` do CSS: o servidor e o
 * navegador desenham o mesmo, e o script do `<head>` marca o modo antes da
 * primeira pintura, então nada pula depois de carregar.
 */

import { CaretDown } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useId, useState } from "react";

import { Botao } from "./Botao";

/** Aberta ou recolhida, o id que o botão controla e a classe de quem fica recolhido. */
export function useRespostaRecolhida() {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  return {
    id,
    aberta,
    alternar: () => setAberta((antes) => !antes),
    /** Recolhida, a resposta some no modo minimalista; aberta, aparece. Fora do modo, sempre aparece. */
    classeDaResposta: aberta ? undefined : "minimalista:hidden",
  };
}

/** O botão "Responder", que só aparece no modo minimalista. */
export function BotaoResponder({
  aberta,
  controla,
  aoAlternar,
  descritoPor,
  className,
}: {
  aberta: boolean;
  /** O id da resposta que ele abre e recolhe. */
  controla: string;
  aoAlternar: () => void;
  /** O id do texto da pergunta: com mais de um "Responder" na tela, o leitor de tela diz qual. */
  descritoPor?: string;
  className?: string;
}) {
  return (
    <span className={clsx("hidden shrink-0 minimalista:inline-flex", className)}>
      <Botao
        variante="secundario"
        tamanho="sm"
        aria-expanded={aberta}
        aria-controls={controla}
        aria-describedby={descritoPor}
        iconeDepois={
          <CaretDown
            size={16}
            weight="bold"
            className={clsx("transition-transform duration-rapida", aberta && "rotate-180")}
          />
        }
        onClick={aoAlternar}
      >
        Responder
      </Botao>
    </span>
  );
}

/**
 * A pergunta numa linha, com o Responder ao lado, e a resposta embaixo, que
 * abre quando ela toca: isso no modo minimalista. Fora dele, só a resposta
 * (que já traz a pergunta inteira), como sempre.
 */
export function PerguntaRecolhida({
  pergunta,
  icone,
  className,
  children,
}: {
  pergunta: string;
  /** O ícone antes da pergunta, escondido do leitor de tela. */
  icone: ReactNode;
  className?: string;
  /** A resposta: o cartão com a pergunta inteira e o formulário. */
  children: ReactNode;
}) {
  const { id, aberta, alternar, classeDaResposta } = useRespostaRecolhida();
  const idDaLinha = useId();
  return (
    <div className={className}>
      {/* `contain: inline-size`: a pergunta inteira numa linha não alarga quem está em volta; ela corta com reticências. */}
      <div className="hidden items-center gap-2 [contain:inline-size] minimalista:flex">
        <p
          id={idDaLinha}
          className={clsx(
            "flex min-w-0 flex-1 items-center gap-1.5 text-sm font-semibold text-tinta",
            // Aberta, a pergunta inteira aparece logo abaixo: a linha curta sai.
            aberta && "invisible",
          )}
        >
          <span aria-hidden="true" className="inline-flex shrink-0">
            {icone}
          </span>
          <span className="truncate">{pergunta}</span>
        </p>
        <BotaoResponder aberta={aberta} controla={id} aoAlternar={alternar} descritoPor={idDaLinha} />
      </div>
      <div id={id} className={clsx("minimalista:mt-2", classeDaResposta)}>
        {children}
      </div>
    </div>
  );
}
