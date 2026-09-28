"use client";

/**
 * O checklist de produção de uma receita: tudo o que precisa estar certo antes
 * de ela aceitar o prato, grupo por grupo (equipamentos, técnicas, rotina,
 * ingredientes e o que a plataforma pré-determinou), numa lista de cima para
 * baixo, com o estado de cada item em ícone grande e em palavras.
 *
 * Nada aqui é decidido pela tela: o estado, a origem, o que falta para aceitar
 * e a pergunta de confirmar a cozinha vêm prontos da API. A tela só escolhe
 * como responder a pergunta da cozinha de cada item (a mesma resposta ali
 * mesmo das outras perguntas da receita) e junta o que toda cozinha tem numa
 * ação só, "Confirmar a cozinha", que grava tudo de uma vez. O que a plataforma
 * pré-determinou (porções, pesos, preços) aparece como "Estimado", com a fonte
 * e o "corrigir" discreto; peso, medida, quantidade e preço nunca são pergunta.
 */

import { CheckCircle, Info, Prohibit, Question, SealQuestion } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useId } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Chip } from "@/componentes/compartilhados/Chip";
import { confirmarSupostos } from "@/lib/acoes/cozinha";
import { responderSobreACozinha } from "@/lib/acoes/receitas";
import type {
  ChecklistDeProducao,
  ConfirmarACozinha as Confirmacao,
  GrupoDoChecklist,
  ItemDoChecklist,
  PerguntaDaReceita,
  StatusDoChecklist,
} from "@/lib/api/receitas";
import { useAcao } from "@/lib/dados/useAcao";

import { correcaoDe } from "./correcao";
import { CorrigirValor } from "./CorrigirValor";
import { comoResponder } from "./perguntas";
import { RespostaInline } from "./RespostaInline";
import type { TomDaSituacao } from "./textos";
import { comMaiuscula } from "./textos";

type Receita = { slug: string; nome: string };

/** O tom de cada estado: o que libera em verde, o pré-determinado em azul, o que espera em amarelo. */
export const TOM_DO_STATUS: Readonly<Record<StatusDoChecklist, TomDaSituacao>> = {
  confirmado: "sucesso",
  pre_determinado: "info",
  suposto: "atencao",
  falta_saber: "atencao",
  nao_da: "perigo",
};

const COR_DO_ICONE: Readonly<Record<TomDaSituacao, string>> = {
  sucesso: "text-sucesso",
  info: "text-info",
  atencao: "text-atencao",
  perigo: "text-perigo",
};

const ICONE_DO_STATUS: Readonly<Record<StatusDoChecklist, ReactNode>> = {
  confirmado: <CheckCircle size={28} weight="fill" />,
  pre_determinado: <Info size={28} weight="fill" />,
  suposto: <SealQuestion size={28} weight="fill" />,
  falta_saber: <Question size={28} weight="fill" />,
  nao_da: <Prohibit size={28} weight="bold" />,
};

/**
 * "Confirmar a cozinha": a pergunta, uma só, com o que ela confirma, e um toque
 * que grava tudo. A página se refaz com a resposta (a ação refaz a rota).
 */
export function ConfirmarACozinha({
  confirmacao,
  aoConfirmar,
  pendente,
}: {
  confirmacao: Confirmacao;
  aoConfirmar: () => void;
  pendente: boolean;
}) {
  const id = useId();
  const idDaPergunta = `confirmar${id}`;
  return (
    <div role="group" aria-labelledby={idDaPergunta} className="rounded-lg border border-atencao/30 bg-atencao/10 p-4">
      <p id={idDaPergunta} className="flex items-start gap-2 text-base font-semibold text-tinta">
        <SealQuestion size={24} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
        <span>{confirmacao.pergunta}</span>
      </p>
      <ul aria-label="O que a senhora confirma" className="mt-3 flex flex-wrap gap-2 pl-8">
        {confirmacao.itens.map((item) => (
          <li key={`${item.tipo}-${item.id}`}>
            <Chip>{item.nome}</Chip>
          </li>
        ))}
      </ul>
      <div className="mt-3 pl-8">
        <Botao
          icone={<CheckCircle size={20} weight="bold" />}
          carregando={pendente}
          rotuloCarregando="Anotando…"
          onClick={aoConfirmar}
        >
          Confirmar a cozinha
        </Botao>
        <p className="mt-2 text-sm text-texto-secundario">Se faltar algum, toque em Não tenho no item, aqui embaixo.</p>
      </div>
    </div>
  );
}

/** O "Não tenho" (ou "Não faço") de um item que era suposto: grava só ele. */
function NaoTenho({ item }: { item: ItemDoChecklist }) {
  const { executar, pendente } = useAcao(responderSobreACozinha, { sucesso: (dados) => dados.texto });
  const lista = item.tipo === "tecnica" ? "tecnicas" : "equipamentos";
  const rotulo = item.tipo === "tecnica" ? "Não faço" : "Não tenho";
  return (
    <Botao
      variante="terciario"
      tamanho="sm"
      carregando={pendente}
      rotuloCarregando="Anotando…"
      aria-label={`${rotulo}: ${item.nome}`}
      onClick={() => void executar(lista, item.id, "nao_tem")}
    >
      {rotulo}
    </Botao>
  );
}

/** A pergunta da cozinha do item, com a resposta ali mesmo. A de outro assunto não aparece. */
function RespostaDoItem({ receita, pergunta }: { receita: Receita; pergunta: PerguntaDaReceita }) {
  const id = useId();
  const idDaPergunta = `pergunta${id}`;
  if (comoResponder(pergunta).tipo === "nenhuma") return null;
  return (
    <div className="mt-2">
      <p id={idDaPergunta} className="text-sm font-semibold text-tinta">
        {pergunta.texto}
      </p>
      <div className="mt-2">
        <RespostaInline receita={receita} pergunta={pergunta} idDaPergunta={idDaPergunta} />
      </div>
    </div>
  );
}

function ItemDaLista({ receita, item }: { receita: Receita; item: ItemDoChecklist }) {
  const tom = TOM_DO_STATUS[item.status];
  const pergunta = item.pergunta;
  const suposto = item.status === "suposto";
  // O detalhe que só repete a pergunta sai: ela lê a pergunta uma vez, junto da resposta.
  const detalhe = item.detalhe && item.detalhe !== pergunta?.texto ? item.detalhe : null;
  return (
    <li className="flex items-start gap-3 py-4">
      <span aria-hidden="true" className={clsx("mt-0.5 inline-flex shrink-0", COR_DO_ICONE[tom])}>
        {ICONE_DO_STATUS[item.status]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold [overflow-wrap:anywhere] text-tinta">{item.nome}</p>
        {detalhe ? <p className="mt-0.5 text-sm [overflow-wrap:anywhere] text-texto">{detalhe}</p> : null}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          <Chip tom={tom}>{item.status === "pre_determinado" ? "Estimado" : comMaiuscula(item.status_texto)}</Chip>
          {/* No suposto, o estado já diz de onde veio: "suposto: confirme". */}
          {suposto ? null : <span className="text-sm text-apagado">{comMaiuscula(item.origem_texto)}</span>}
        </div>
        {suposto && (item.tipo === "equipamento" || item.tipo === "tecnica") ? (
          <div className="mt-2">
            <NaoTenho item={item} />
          </div>
        ) : null}
        {pergunta && !suposto ? <RespostaDoItem receita={receita} pergunta={pergunta} /> : null}
        <CorrigirDoItem receita={receita} item={item} />
      </div>
    </li>
  );
}

/**
 * Um grupo do checklist: o título e a lista. Não é uma região da página (a
 * seção de ingredientes, mais abaixo, já tem esse nome): é um trecho da lista,
 * com o título como cabeçalho.
 */
/** O "corrigir" de um valor pré-determinado: fechado até ela abrir. */
function CorrigirDoItem({ receita, item }: { receita: Receita; item: ItemDoChecklist }) {
  const correcao = correcaoDe(item.editar);
  if (!correcao) return null;
  return <CorrigirValor receita={receita} correcao={correcao} oQue={`o valor de ${item.nome.toLocaleLowerCase("pt-BR")}`} className="mt-1" />;
}

function GrupoDaLista({ receita, grupo }: { receita: Receita; grupo: GrupoDoChecklist }) {
  return (
    <div className="border-t border-borda pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-base font-bold text-tinta">{grupo.titulo}</h3>
      {grupo.itens.length === 0 ? (
        <p className="py-3 text-sm text-texto-secundario">{grupo.vazio_texto}</p>
      ) : (
        <ul className="divide-y divide-borda/70">
          {grupo.itens.map((item) => (
            <ItemDaLista key={`${grupo.id}-${item.id}`} receita={receita} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function ChecklistDeProducaoDaReceita({ receita, checklist }: { receita: Receita; checklist: ChecklistDeProducao }) {
  const { executar, pendente } = useAcao(confirmarSupostos, { sucesso: (dados) => dados.texto });
  return (
    <div className="space-y-5">
      {checklist.confirmar_a_cozinha ? (
        <ConfirmarACozinha
          confirmacao={checklist.confirmar_a_cozinha}
          pendente={pendente}
          aoConfirmar={() => void executar({ receita: receita.slug })}
        />
      ) : null}
      {checklist.grupos.map((grupo) => (
        <GrupoDaLista key={grupo.id} receita={receita} grupo={grupo} />
      ))}
    </div>
  );
}
