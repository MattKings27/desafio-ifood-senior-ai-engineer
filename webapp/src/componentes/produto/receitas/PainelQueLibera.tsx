"use client";

/**
 * "Responda e eu libero mais receitas": com a cozinha nova, nenhuma receita dá
 * para fazer ainda, e todas esperam uma resposta dela. O painel junta essas
 * perguntas pelo que perguntam (a API manda prontas, em
 * `receitas.json#perguntas_que_liberam`), as que mexem em mais receitas
 * primeiro, e cada uma se responde ali mesmo, com o mesmo componente dos cards
 * de "Falta uma resposta sua".
 *
 * A contagem é a que a API escreveu, sem exagero: "libera 3 receitas" só
 * quando as três não esperam por mais nada; senão, "ajuda a liberar". Ao lado,
 * quantas delas usam só o que ela tem (`sem_compra_texto`), também da API.
 *
 * O gosto vem antes da cozinha: o painel só traz a pergunta da cozinha
 * (equipamento, técnica, rotina) que segura alguma receita que ela disse que
 * gosta de fazer. Pergunta de outro assunto (peso, medida, preço) nunca entra.
 */

import { LockKeyOpen } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useId } from "react";

import { Card } from "@/componentes/compartilhados/Card";
import type { PerguntaQueLibera } from "@/lib/api/receitas";

import { daCozinha } from "./perguntas";
import { RespostaInline } from "./RespostaInline";
import { comMaiuscula } from "./textos";

/** "Frango com alcaparras e Salmão", "A, B e mais 2". */
function quais(nomes: readonly string[]): string {
  if (nomes.length <= 2) return nomes.join(" e ");
  const mais = nomes.length - 2;
  return `${nomes.slice(0, 2).join(", ")} e ${mais === 1 ? "mais 1" : `mais ${mais}`}`;
}

function PerguntaDoPainel({ grupo }: { grupo: PerguntaQueLibera }) {
  const id = useId();
  const idDaPergunta = `libera${id}`;
  const { pergunta } = grupo;
  const libera = grupo.liberadas > 0;
  return (
    <li className="min-w-0 rounded-md border border-borda bg-superficie p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className={clsx(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold",
            libera ? "border-sucesso/25 bg-sucesso/10 text-sucesso" : "border-info/25 bg-info/10 text-info",
          )}
        >
          {comMaiuscula(grupo.texto)}
        </span>
        {grupo.sem_compra_texto ? (
          <span className="inline-flex items-center rounded-full border border-sucesso/25 bg-sucesso/10 px-2 py-0.5 text-xs font-semibold text-sucesso">
            {comMaiuscula(grupo.sem_compra_texto)}
          </span>
        ) : null}
        <span className="min-w-0 text-xs text-apagado minimalista:hidden">{quais(grupo.nomes)}</span>
      </div>
      <p id={idDaPergunta} className="mt-2 text-sm font-semibold text-tinta">
        {pergunta.texto}
      </p>
      {pergunta.motivo ? (
        <p className="mt-0.5 text-xs text-texto-secundario minimalista:hidden">
          {comMaiuscula(pergunta.motivo.replace(/[.!]+$/, ""))}.
        </p>
      ) : null}
      <div className="mt-3">
        <RespostaInline
          receita={{ slug: grupo.slugs[0] ?? "", nome: grupo.nomes[0] ?? "" }}
          pergunta={pergunta}
          idDaPergunta={idDaPergunta}
        />
      </div>
    </li>
  );
}

export function PainelQueLibera({
  perguntas,
  curtidas,
}: {
  perguntas: readonly PerguntaQueLibera[];
  /** As receitas que ela disse que gosta de fazer: só a pergunta que segura uma delas entra. */
  curtidas: ReadonlySet<string>;
}) {
  const id = useId();
  const daVez = perguntas.filter((grupo) => daCozinha(grupo.pergunta) && grupo.slugs.some((slug) => curtidas.has(slug)));
  if (daVez.length === 0) return null;
  const idDoTitulo = `painel${id}`;
  return (
    <Card como="section" tom="creme" aria-labelledby={idDoTitulo}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-superficie text-marca shadow-cartao"
        >
          <LockKeyOpen size={22} weight="duotone" />
        </span>
        <div className="min-w-0">
          <h2 id={idDoTitulo} className="text-lg font-bold text-tinta">
            Responda e eu libero mais receitas
          </h2>
          <p className="mt-0.5 text-sm text-texto minimalista:hidden">
            Nenhuma receita está confirmada ainda. Cada resposta aqui vale para todas as receitas que esperam por ela.
          </p>
        </div>
      </div>
      <ol className="mt-4 grid gap-3 lg:grid-cols-2">
        {daVez.map((grupo) => (
          <PerguntaDoPainel key={`${grupo.pergunta.assunto}-${grupo.pergunta.campo}-${grupo.slugs.join(",")}`} grupo={grupo} />
        ))}
      </ol>
    </Card>
  );
}
