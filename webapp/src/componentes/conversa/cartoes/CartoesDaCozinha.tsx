"use client";

/**
 * Os cards da cozinha na conversa: a pergunta da vez (com os botões que já
 * respondem) e a cozinha depois que ela respondeu.
 *
 * Os botões da pergunta mandam a resposta como ação (`responder`): o backend
 * anota pela conferência antes de o agente falar, e o mesmo pedido nunca
 * anota duas vezes. "Não sei" vai só como texto: não é "não tenho", e quem
 * decide o que fazer com a dúvida é o agente.
 */

import { CookingPot, Question } from "@phosphor-icons/react/dist/ssr";

import { Barra } from "@/componentes/compartilhados/Barra";
import { Botao } from "@/componentes/compartilhados/Botao";
import type { TomDoChip } from "@/componentes/compartilhados/Chip";
import { Chip } from "@/componentes/compartilhados/Chip";
import { comMaiuscula } from "@/lib/conversa/atividades";

import { useAcoesDaConversa } from "../useAcoesDaConversa";
import { LinkDoCartao } from "./CartoesDaDespensa";
import { opcoesDaPergunta } from "./CartoesDeReceita";
import type { Solto } from "./leitura";
import { bool, lista, num, obj, objetos, parametro, str } from "./leitura";
import type { PropsDoCartao } from "./Moldura";
import { LinhaDoCartao, MolduraDoCartao, useDadosDoCartao } from "./Moldura";

/* -------------------------------------------------------------------------- */
/* pergunta                                                                    */
/* -------------------------------------------------------------------------- */

export function CartaoPergunta({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto } = useDadosDoCartao(cartao, historico);
  const acoes = useAcoesDaConversa();
  const dados = obj(bruto) ?? {};
  const pergunta = str(dados.pergunta) ?? str(dados.texto);
  if (bool(dados.ha_pergunta) === false || !pergunta) {
    return (
      <MolduraDoCartao sobretitulo="Sua cozinha" icone={<CookingPot size={16} weight="bold" />} titulo="Nada a perguntar agora">
        <p className="text-base text-texto">Por enquanto, sei o que preciso da cozinha da senhora.</p>
      </MolduraDoCartao>
    );
  }
  const pratos = lista(dados.pratos_afetados)
    .map(str)
    .filter((prato): prato is string => prato !== null);
  const opcoes = opcoesDaPergunta(dados);

  return (
    <MolduraDoCartao
      sobretitulo="Preciso saber"
      icone={<Question size={16} weight="bold" />}
      titulo={pergunta}
      geradoTexto={geradoTexto}
    >
      {pratos.length > 0 ? (
        <p className="text-sm text-apagado">Vale para: {pratos.join(", ")}.</p>
      ) : str(dados.por_que_esta) ? (
        <p className="text-sm text-apagado">{comMaiuscula(str(dados.por_que_esta) as string)}.</p>
      ) : null}
      {opcoes.length > 0 ? (
        <div role="group" aria-label="Respostas" className="flex flex-wrap gap-2">
          {opcoes.map((opcao) => (
            <Botao
              key={opcao.rotulo}
              variante="secundario"
              tamanho="sm"
              aria-disabled={acoes.ocupada || undefined}
              title={acoes.motivo ?? opcao.texto}
              onClick={() => {
                if (!acoes.ocupada) acoes.enviar(opcao.texto, opcao.acao ? { acao: opcao.acao } : undefined);
              }}
            >
              {opcao.rotulo}
            </Botao>
          ))}
        </div>
      ) : (
        <Botao
          variante="secundario"
          tamanho="sm"
          onClick={() =>
            acoes.preencher("", {
              tela: "cozinha",
              tipo: str(dados.tipo) === "tecnica" ? "tecnica" : str(dados.tipo) === "restricao" ? "restricao" : "equipamento",
              ...(str(dados.campo) ? { id: str(dados.campo) as string } : {}),
            })
          }
        >
          Responder
        </Botao>
      )}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* cozinha_atualizada                                                          */
/* -------------------------------------------------------------------------- */

/** O que ela tem, dito para ela (o valor técnico do estado nunca aparece). */
export const ESTADO_NA_COZINHA: Readonly<Record<string, { texto: string; tom: TomDoChip }>> = {
  tem: { texto: "Tem", tom: "sucesso" },
  nao_tem: { texto: "Não tem", tom: "perigo" },
  desconhecido: { texto: "Não sei ainda", tom: "atencao" },
  nao_sei: { texto: "Não sei ainda", tom: "atencao" },
};

const ESTADO_DA_TECNICA: Readonly<Record<string, string>> = {
  tem: "Sabe fazer",
  nao_tem: "Não sabe fazer",
};

function itemMudado(dados: Solto, cartao: PropsDoCartao["cartao"]): { item: Solto; tecnica: boolean } | null {
  const campo = str(parametro(cartao, "campo"));
  const tipo = str(parametro(cartao, "tipo"));
  if (!campo) return null;
  const tecnica = tipo === "tecnica";
  const onde = tecnica ? objetos(dados.tecnicas) : [...objetos(dados.equipamentos), ...objetos(dados.tecnicas)];
  const item = onde.find((candidato) => str(candidato.id) === campo);
  return item ? { item, tecnica: tecnica || objetos(dados.tecnicas).includes(item) } : null;
}

export function CartaoCozinhaAtualizada({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const mudado = itemMudado(dados, cartao);
  const fracao = num(dados.fracao_respondida);
  const resumo = (str(dados.resumo) ?? "")
    .split("·")
    .map((parte) => parte.trim())
    .filter(Boolean);
  const estado = mudado ? str(mudado.item.estado) : null;
  const doEstado = estado ? ESTADO_NA_COZINHA[estado] : undefined;
  const afetadas = mudado ? num(mudado.item.receitas_afetadas) : null;

  return (
    <MolduraDoCartao
      sobretitulo="Sua cozinha"
      icone={<CookingPot size={16} weight="bold" />}
      titulo={mudado ? (str(mudado.item.nome) ?? "Cozinha atualizada") : "Cozinha atualizada"}
      selo={
        doEstado ? (
          <Chip tom={doEstado.tom}>{(mudado?.tecnica && estado ? ESTADO_DA_TECNICA[estado] : null) ?? doEstado.texto}</Chip>
        ) : undefined
      }
      geradoTexto={geradoTexto}
      rodape={<LinkDoCartao href="/cozinha">Ver a cozinha</LinkDoCartao>}
    >
      {mudado ? (
        <div className="text-sm text-apagado">
          {str(mudado.item.atualizado_por) === "conversa" ? <p>Anotado pela conversa{str(mudado.item.atualizado_texto) ? `, ${str(mudado.item.atualizado_texto)}` : ""}.</p> : null}
          {afetadas !== null && afetadas > 0 ? (
            <p>{afetadas === 1 ? "Isso muda 1 receita." : `Isso muda ${afetadas} receitas.`}</p>
          ) : null}
        </div>
      ) : null}
      {fracao !== null ? <Barra fracao={fracao} rotulo="Quanto da cozinha a senhora já respondeu" tom="sucesso" /> : null}
      {resumo.length > 0 ? (
        <ul className="space-y-0.5 text-sm text-texto">
          {resumo.map((parte, indice) => (
            <li key={`${indice}-${parte}`}>{parte}</li>
          ))}
        </ul>
      ) : null}
      {!mudado && objetos(dados.equipamentos).length > 0 ? (
        <ul className="divide-y divide-borda">
          {objetos(dados.equipamentos)
            .filter((item) => str(item.atualizado_por) === "conversa")
            .map((item, indice) => (
              <li key={`${indice}-${str(item.id) ?? ""}`}>
                <LinhaDoCartao
                  rotulo={str(item.nome) ?? "Equipamento"}
                  valor={<span className="text-sm text-apagado">{ESTADO_NA_COZINHA[str(item.estado) ?? ""]?.texto ?? ""}</span>}
                />
              </li>
            ))}
        </ul>
      ) : null}
    </MolduraDoCartao>
  );
}
