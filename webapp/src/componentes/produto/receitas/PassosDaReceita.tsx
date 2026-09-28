/**
 * O modo de preparo, passo a passo, com o que cada passo pede da cozinha dela
 * (o fogão, a panela de pressão, refogar) e os limites (5 min no fogo, mais
 * uma boca ao mesmo tempo). O que ainda não foi perguntado a ela tem a
 * resposta ali mesmo: Tenho, Não tenho, Não sei. Os passos vêm na ordem e com
 * o texto da página, e o nome de cada parte (a massa, a cobertura) fica em
 * cima do primeiro passo dela, como a página mostra.
 */

import {
  ArrowsLeftRight,
  Check,
  CheckCircle,
  Fire,
  Prohibit,
  Question,
  Timer,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

import type { LimiteDoPasso, Passo, Requisito } from "@/lib/api/receitas";

import { PerguntaDePosse } from "./PerguntaDePosse";

type Tom = "neutro" | "sucesso" | "info" | "atencao" | "perigo";

const TONS: Readonly<Record<Tom, string>> = {
  neutro: "border-borda bg-secao text-texto",
  sucesso: "border-sucesso/25 bg-sucesso/10 text-sucesso",
  info: "border-info/25 bg-info/10 text-info",
  atencao: "border-atencao/25 bg-atencao/10 text-atencao",
  perigo: "border-perigo/25 bg-perigo/10 text-perigo",
};

/** Uma etiqueta que quebra linha (o nome do requisito e o estado podem ser longos). */
function Etiqueta({ tom, icone, children }: { tom: Tom; icone: ReactNode; children: ReactNode }) {
  return (
    <li
      className={clsx(
        "inline-flex max-w-full items-start gap-1 rounded-md border px-2 py-1 text-xs leading-snug font-semibold",
        TONS[tom],
      )}
    >
      <span aria-hidden="true" className="mt-px inline-flex shrink-0">
        {icone}
      </span>
      <span className="min-w-0">{children}</span>
    </li>
  );
}

/** O estado dito para ela; o "suposto" vira o porquê de estar suposto. */
function estadoDoRequisito(requisito: Requisito): { tom: Tom; icone: ReactNode; texto: string } {
  if (requisito.substituto) return { tom: "info", icone: <ArrowsLeftRight size={14} weight="bold" />, texto: requisito.rotulo_estado };
  if (requisito.estado === "tem") {
    if (requisito.suposto) {
      return {
        tom: "neutro",
        icone: <Check size={14} weight="bold" />,
        texto: requisito.tipo === "tecnica" ? "toda cozinheira faz" : "toda cozinha tem",
      };
    }
    return { tom: "sucesso", icone: <CheckCircle size={14} weight="fill" />, texto: requisito.rotulo_estado };
  }
  if (requisito.estado === "nao_tem") return { tom: "perigo", icone: <Prohibit size={14} weight="bold" />, texto: requisito.rotulo_estado };
  return { tom: "atencao", icone: <Question size={14} weight="fill" />, texto: requisito.rotulo_estado };
}

function EtiquetaDoLimite({ limite }: { limite: LimiteDoPasso }) {
  return (
    <Etiqueta
      tom="neutro"
      icone={limite.tipo === "tempo" ? <Timer size={14} weight="bold" /> : <Fire size={14} weight="bold" />}
    >
      {limite.texto}
    </Etiqueta>
  );
}

/** Ainda não perguntado, e a conferência pergunta por ele: ela responde aqui. */
function perguntavel(requisito: Requisito): boolean {
  return (
    requisito.estado === "desconhecido" &&
    requisito.conferido &&
    !requisito.substituto &&
    (requisito.tipo === "equipamento" || requisito.tipo === "tecnica")
  );
}

function perguntaDoRequisito(requisito: Requisito): string {
  const nome = requisito.nome.toLocaleLowerCase("pt-BR");
  return requisito.tipo === "tecnica" ? `A senhora sabe ${nome}?` : `A senhora tem ${nome}?`;
}

function Requisitos({
  requisitos,
  limites = [],
  aPerguntar,
}: {
  requisitos: readonly Requisito[];
  limites?: readonly LimiteDoPasso[];
  /** Os requisitos que este trecho pergunta (cada um só no primeiro lugar em que aparece). */
  aPerguntar: readonly Requisito[];
}) {
  if (requisitos.length === 0 && limites.length === 0) return null;
  return (
    <>
      <ul className="flex flex-wrap gap-1.5">
        {requisitos.map((requisito) => {
          const estado = estadoDoRequisito(requisito);
          return (
            <Etiqueta key={`${requisito.tipo}-${requisito.id}`} tom={estado.tom} icone={estado.icone}>
              {requisito.nome}: {estado.texto}
            </Etiqueta>
          );
        })}
        {limites.map((limite) => (
          <EtiquetaDoLimite key={`${limite.tipo}-${limite.trecho}`} limite={limite} />
        ))}
      </ul>
      {/* A pergunta é a legenda do grupo: escrita uma vez, e o nome que o leitor de tela diz. */}
      {aPerguntar.map((requisito) => (
        <PerguntaDePosse
          key={requisito.id}
          lista={requisito.tipo === "tecnica" ? "tecnicas" : "equipamentos"}
          id={requisito.id}
          legenda={perguntaDoRequisito(requisito)}
          legendaVisivel
          className="max-w-sm"
        />
      ))}
    </>
  );
}

/**
 * Onde cada requisito ainda não perguntado é perguntado: só no primeiro passo
 * que o pede (e fora dos passos, se nenhum pede), e nunca o que a lista de
 * perguntas da receita já pergunta.
 */
function ondePerguntar(passos: readonly Passo[], daReceita: readonly Requisito[], jaPerguntados: ReadonlySet<string>) {
  const vistos = new Set(jaPerguntados);
  const escolher = (requisitos: readonly Requisito[]) =>
    requisitos.filter((requisito) => {
      if (!perguntavel(requisito) || vistos.has(requisito.id)) return false;
      vistos.add(requisito.id);
      return true;
    });
  const porPasso = passos.map((passo) => ({ passo, aPerguntar: escolher(passo.requisitos) }));
  return { porPasso, daReceita: escolher(daReceita) };
}

/**
 * O nome da parte da receita ("Massa", "Cobertura") em cima do primeiro passo
 * dela, como a página mostra; nada no passo que continua a mesma parte, nem no
 * que a página não põe numa parte com nome.
 */
export function abreSecao(passos: readonly Passo[], indice: number): string | null {
  const secao = passos[indice]?.secao ?? null;
  if (!secao) return null;
  return secao === (passos[indice - 1]?.secao ?? null) ? null : secao;
}

export function PassosDaReceita({
  passos,
  requisitosDaReceita,
  jaPerguntados,
}: {
  passos: readonly Passo[];
  requisitosDaReceita: readonly Requisito[];
  /** Os ids que a lista de perguntas já pergunta: aqui não repete o seletor. */
  jaPerguntados: ReadonlySet<string>;
}) {
  const perguntas = ondePerguntar(passos, requisitosDaReceita, jaPerguntados);
  return (
    <div className="space-y-5">
      {passos.length === 0 ? (
        <p className="text-sm text-texto">A página não trouxe o modo de preparo desta receita.</p>
      ) : (
        <ol className="space-y-5">
          {perguntas.porPasso.map(({ passo, aPerguntar }, indice) => {
            const secao = abreSecao(passos, indice);
            return (
              <li key={passo.ordem} className="space-y-3">
                {secao ? <h3 className="text-base font-bold text-tinta">{secao}</h3> : null}
                <div className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="numero flex size-8 shrink-0 items-center justify-center rounded-full bg-secao text-sm font-bold text-tinta"
                  >
                    {passo.ordem}
                  </span>
                  <div className="min-w-0 flex-1 space-y-2 pt-1">
                    <p className="text-base text-texto">
                      <span className="sr-only">Passo {passo.ordem}: </span>
                      {passo.texto}
                    </p>
                    <Requisitos requisitos={passo.requisitos} limites={passo.limites} aPerguntar={aPerguntar} />
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {requisitosDaReceita.length > 0 ? (
        <div className="space-y-2 rounded-lg bg-secao p-4">
          <h3 className="text-sm font-bold text-tinta">A receita também pede</h3>
          <Requisitos requisitos={requisitosDaReceita} aPerguntar={perguntas.daReceita} />
        </div>
      ) : null}
    </div>
  );
}
