"use client";

/**
 * "De onde eu tirei isso": as fontes de uma resposta do agente.
 *
 * Cada chip é uma parte da plataforma que ele consultou (um item da despensa,
 * uma receita, a cozinha) e leva à tela que mostra aquilo; o que vem da base
 * de conhecimento culinário, sem tela própria, aparece como chip sem link. A
 * resposta que não tem fonte não ganha este card: quem não sabe diz que não
 * sabe.
 */

import { ArrowRight, BookBookmark, Books } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

import { objetos, obj, rotaInterna, str } from "./leitura";
import type { PropsDoCartao } from "./Moldura";
import { MolduraDoCartao, useDadosDoCartao } from "./Moldura";

export const TITULO_DAS_FONTES = "De onde eu tirei isso";

export function CartaoFontes({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const chips = objetos(dados.chips).filter((chip) => str(chip.rotulo));
  if (chips.length === 0) return null;

  return (
    <MolduraDoCartao
      sobretitulo="Fontes"
      icone={<Books size={16} weight="bold" />}
      titulo={str(dados.texto) ?? TITULO_DAS_FONTES}
      geradoTexto={geradoTexto}
    >
      <ul className="flex flex-wrap gap-2">
        {chips.map((chip, indice) => {
          const rotulo = str(chip.rotulo) as string;
          const rota = rotaInterna(chip.rota);
          return (
            <li key={`${rotulo}-${indice}`} className="max-w-full">
              {rota ? (
                <Link
                  href={rota}
                  className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-2xl border border-borda-campo/60 bg-superficie px-3.5 py-2 text-left text-sm font-semibold text-tinta transition-colors duration-rapida hover:border-tinta hover:bg-secao"
                >
                  <span>{rotulo}</span>
                  <ArrowRight size={14} weight="bold" aria-hidden="true" className="shrink-0 text-marca" />
                </Link>
              ) : (
                <span className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-2xl bg-secao px-3.5 py-2 text-sm text-texto">
                  <BookBookmark size={16} weight="bold" aria-hidden="true" className="shrink-0 text-apagado" />
                  <span>{rotulo}</span>
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </MolduraDoCartao>
  );
}
