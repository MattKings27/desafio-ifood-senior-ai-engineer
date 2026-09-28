"use client";

/**
 * Tem ou não tem (faz ou não faz) um equipamento ou uma técnica, respondido
 * ali mesmo: na pergunta que segura uma receita e no passo que pede algo que
 * ainda não foi perguntado.
 *
 * São as opções do `SeletorDePosse` da tela da cozinha, gravadas do mesmo
 * jeito: a escolha vai para o perfil da cozinha 300 ms depois do último toque,
 * então andar pelas opções com as setas manda só a última. Aqui, dentro do card
 * estreito, as opções ficam uma por linha quando não cabem lado a lado, e
 * "Não tenho" nunca vira "Não te…". A frase que volta (o que muda
 * nas receitas) aparece no aviso; a recusa fica escrita logo abaixo, perto da
 * pergunta, e o "Não sei" ganha a nota de que foi anotado.
 */

import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import { useToast } from "@/componentes/compartilhados/Toast";
import { OPCOES_DE_POSSE, useGravacaoAdiada } from "@/componentes/produto/cozinha";
import type { TextoDaResposta } from "@/lib/acoes/receitas";
import { responderSobreACozinha } from "@/lib/acoes/receitas";
import type { RespostaDePosse } from "@/lib/api/perfil";

export function PerguntaDePosse({
  lista,
  id,
  legenda,
  legendaVisivel = false,
  className,
}: {
  lista: "equipamentos" | "tecnicas";
  id: string;
  /** A pergunta ("A senhora tem batedeira?"): o nome do grupo para o leitor de tela. */
  legenda: string;
  /** A pergunta escrita em cima das opções, quando nenhum outro texto da tela a mostra. */
  legendaVisivel?: boolean;
  className?: string;
}) {
  const toast = useToast();
  const { valor, mudar, estado, erro } = useGravacaoAdiada<RespostaDePosse | null, TextoDaResposta>(
    null,
    (resposta) => responderSobreACozinha(lista, id, resposta ?? "nao_sei"),
    {
      avisarErro: false,
      aoGravar: (dados) => {
        if (dados.texto) toast.mostrar({ texto: dados.texto, tom: "sucesso" });
      },
    },
  );

  return (
    <div className={className}>
      <Segmentado
        legenda={legenda}
        legendaVisivel={legendaVisivel}
        opcoes={OPCOES_DE_POSSE[lista === "tecnicas" ? "tecnica" : "equipamento"]}
        valor={valor}
        aoMudar={mudar}
        orientacao="adaptavel"
      />
      {erro ? (
        <p role="alert" className="mt-1.5 text-sm font-medium text-perigo">
          {erro.pergunta ?? erro.mensagem}
        </p>
      ) : valor === "nao_sei" && estado === "salvo" ? (
        <p className="mt-1.5 text-sm text-texto-secundario">
          Anotei que a senhora não sabe. Quando souber, é só tocar na resposta.
        </p>
      ) : null}
    </div>
  );
}
