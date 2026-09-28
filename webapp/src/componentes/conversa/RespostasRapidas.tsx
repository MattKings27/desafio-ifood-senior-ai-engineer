"use client";

/**
 * Os chips de resposta rápida, logo acima da caixa de texto.
 *
 * Quem manda neles, nesta ordem (plano, 9.4): as sugestões que o backend
 * mandou no fim da última resposta; as tiradas do último card dela; e, se
 * nada disso veio, as de começo de conversa da página em que ela está. Um
 * chip manda a mensagem na hora (com a ação, quando vem de um card), junto do
 * contexto do chip "Vendo: …".
 */

import clsx from "clsx";

import type { OpcaoSugerida } from "@/lib/api/conversa";
import type { EstadoDaConversa } from "@/lib/conversa/estado";
import { ultimaResposta } from "@/lib/conversa/estado";
import { chipsDoCartao, sugestoesDaTela } from "@/lib/conversa/sugestoes";

import { useLojaDaConversa, useSeletor } from "./useLoja";

/** As opções da vez, pela ordem de quem manda. No máximo quatro. */
export function opcoesDaVez(conversa: EstadoDaConversa, caminho: string | null | undefined): readonly OpcaoSugerida[] {
  if (conversa.sugestoes.length > 0) return conversa.sugestoes.slice(0, 4);
  const resposta = ultimaResposta(conversa);
  if (resposta?.estado === "concluido") {
    const ultimoCartao = resposta.cartoes.at(-1);
    const doCartao = ultimoCartao ? chipsDoCartao(ultimoCartao) : [];
    if (doCartao.length > 0) return doCartao.slice(0, 4);
  }
  return sugestoesDaTela(caminho).slice(0, 4);
}

export function RespostasRapidas({ caminho, className }: { caminho: string | null | undefined; className?: string }) {
  const loja = useLojaDaConversa();
  const conversa = useSeletor(loja, (estado) => estado.conversa);
  const online = useSeletor(loja, (estado) => estado.online);
  const disponivel = useSeletor(loja, (estado) => estado.disponibilidade.disponivel);

  const pronta = conversa.carregamento === "pronto" && conversa.itens.length > 0;
  if (!pronta || conversa.turno || !online || !disponivel) return null;
  const opcoes = opcoesDaVez(conversa, caminho);
  if (opcoes.length === 0) return null;

  return (
    <div role="group" aria-label="Sugestões de resposta" className={clsx("flex flex-wrap gap-2", className)}>
      {opcoes.map((opcao) => (
        <button
          key={`${opcao.rotulo}-${opcao.texto}`}
          type="button"
          title={opcao.texto === opcao.rotulo ? undefined : opcao.texto}
          onClick={() => void loja.enviarSugestao(opcao)}
          className={clsx(
            "inline-flex min-h-11 max-w-full items-center rounded-full border border-borda-campo/60 bg-superficie px-4",
            "text-sm font-semibold text-tinta transition-colors duration-rapida hover:border-tinta hover:bg-secao",
          )}
        >
          <span className="truncate">{opcao.rotulo}</span>
        </button>
      ))}
    </div>
  );
}
