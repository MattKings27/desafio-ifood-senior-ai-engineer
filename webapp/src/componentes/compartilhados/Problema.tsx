"use client";

/**
 * O que deu errado, dito do jeito dela, e o que fazer.
 *
 * O título vem da **categoria**, não da mensagem: "Não consegui falar com o
 * sistema" (rede), "Demorou demais" (tempo), "Não encontrei" (ausente), "Falta
 * uma informação" (dado). `dado` vem com a pergunta que destrava e é tratado
 * como pergunta, não como falha. `regra` é uma recusa deliberada, e dizer
 * "erro" seria mentir sobre o que aconteceu.
 *
 * Nenhum texto técnico chega a ela: código de estado, caminho de arquivo,
 * mensagem em inglês ou jargão caem para a frase padrão da categoria.
 */

import {
  ArrowClockwise,
  Clock,
  HandPalm,
  MagnifyingGlass,
  Question,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useTransition } from "react";

import type { CategoriaDeErro } from "@/lib/api/base";

import { Botao } from "./Botao";
import { TITULO_DO_PROBLEMA, textoDoProblema } from "./textosDoProblema";

const ICONE: Record<CategoriaDeErro, ReactNode> = {
  rede: <WifiSlash size={22} weight="duotone" />,
  tempo: <Clock size={22} weight="duotone" />,
  ausente: <MagnifyingGlass size={22} weight="duotone" />,
  dado: <Question size={22} weight="fill" />,
  regra: <HandPalm size={22} weight="duotone" />,
  uso: <WarningCircle size={22} weight="duotone" />,
};

const ICONE_DE_TENTAR = <ArrowClockwise size={18} weight="bold" />;

/** Refaz a leitura da página: o server component busca de novo na API. */
function BotaoDeRecarregar() {
  const router = useRouter();
  const [refazendo, iniciar] = useTransition();
  return (
    <Botao
      variante="terciario"
      tamanho="sm"
      icone={ICONE_DE_TENTAR}
      carregando={refazendo}
      onClick={() => iniciar(() => router.refresh())}
    >
      Tentar de novo
    </Botao>
  );
}

export function Problema({
  categoria = "rede",
  mensagem,
  pergunta,
  titulo,
  aoTentarDeNovo,
  recarregar = false,
  acao,
  nivelTitulo,
  anunciar = "status",
  className,
}: {
  categoria?: CategoriaDeErro;
  /** A mensagem da API. Só aparece se for texto para ela. */
  mensagem?: string;
  pergunta?: string;
  /** Troca o título da categoria quando a tela sabe dizer melhor. */
  titulo?: string;
  aoTentarDeNovo?: () => void;
  /** Mostra "Tentar de novo" que refaz a leitura da página (server component). */
  recarregar?: boolean;
  /** Outra saída além de tentar de novo (ex.: um link para a lista). */
  acao?: ReactNode;
  /** Com título de página (ex.: `error.tsx`), o título vira um cabeçalho. */
  nivelTitulo?: 1 | 2 | 3;
  /** `alert` para o que acabou de dar errado por causa de um clique dela. */
  anunciar?: "status" | "alert";
  className?: string;
}) {
  const ehPergunta = categoria === "dado";
  const Titulo = nivelTitulo ? (`h${nivelTitulo}` as const) : "p";
  const temSaida = Boolean(aoTentarDeNovo) || recarregar || Boolean(acao);

  return (
    <div
      role={anunciar}
      className={clsx(
        "flex gap-3 rounded-lg border p-4 sm:p-5",
        ehPergunta ? "border-info/30 bg-info/5" : "border-borda bg-superficie",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={clsx("mt-0.5 shrink-0", ehPergunta ? "text-info" : "text-atencao")}
      >
        {ICONE[categoria]}
      </span>
      <div className="min-w-0 flex-1">
        <Titulo className="text-base font-bold text-tinta">
          {titulo ?? TITULO_DO_PROBLEMA[categoria]}
        </Titulo>
        <p className="mt-1 text-base text-texto">{textoDoProblema(categoria, mensagem, pergunta)}</p>
        {temSaida ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {aoTentarDeNovo ? (
              <Botao variante="terciario" tamanho="sm" icone={ICONE_DE_TENTAR} onClick={aoTentarDeNovo}>
                Tentar de novo
              </Botao>
            ) : recarregar ? (
              <BotaoDeRecarregar />
            ) : null}
            {acao}
          </div>
        ) : null}
      </div>
    </div>
  );
}
