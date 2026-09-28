"use client";

/**
 * A pergunta da cozinha que segura uma receita, com a resposta ali mesmo: no
 * card de "Falta uma resposta sua", no painel que libera receitas, no início e
 * no detalhe da receita. Só a cozinha é pergunta (ver `./perguntas`): o
 * equipamento e a técnica (tem, não tem, não sei), os limites da rotina (um
 * número, ou sim e não); o que não dá para responder com um toque ou um número
 * vai para a conversa, com o rascunho pronto. Pergunta de outro assunto não
 * aparece.
 *
 * Depois da resposta, a Server Action refaz a rota: a receita muda de aba (ou
 * a pergunta some do detalhe) e o aviso diz o que mudou.
 */

import { Question } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { FormEvent } from "react";
import { useId, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Campo, EntradaNumero } from "@/componentes/compartilhados/Campos";
import { BotaoPerguntar } from "@/componentes/conversa";
import type { ErroDaAcao } from "@/lib/acoes/base";
import { responderLimiteDaCozinha } from "@/lib/acoes/receitas";
import type { EntradaDaPergunta, PerguntaDaReceita } from "@/lib/api/receitas";
import { useAcao } from "@/lib/dados/useAcao";

import { GrupoDeOpcoes } from "./GrupoDeOpcoes";
import { PerguntaDePosse } from "./PerguntaDePosse";
import { comoResponder } from "./perguntas";
import { comMaiuscula, rascunhoDaPergunta } from "./textos";

type Receita = { slug: string; nome: string };

/** O motivo da API como frase: maiúscula no começo e um ponto no fim. */
function frase(texto: string): string {
  const limpo = comMaiuscula(texto.trim().replace(/[.!]+$/, ""));
  return `${limpo}.`;
}

function ErroEmLinha({ erro, aviso }: { erro: ErroDaAcao | null; aviso?: string | null }) {
  const texto = aviso ?? (erro ? (erro.pergunta ?? erro.mensagem) : null);
  if (!texto) return null;
  return (
    <p role="alert" className="mt-1.5 text-sm font-medium text-perigo">
      {texto}
    </p>
  );
}

/* -------------------------------------------------------------------------- */
/* Número: as bocas do fogão, as horas cozinhando de uma vez                   */
/* -------------------------------------------------------------------------- */

function RespostaDeNumero({
  entrada,
  idDaPergunta,
  pendente,
  erro,
  aoResponder,
  aoNaoSaber,
}: {
  entrada: EntradaDaPergunta;
  idDaPergunta: string;
  pendente: boolean;
  erro: ErroDaAcao | null;
  aoResponder: (valor: number) => void;
  aoNaoSaber?: () => void;
}) {
  const [valor, setValor] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const unidade = entrada.unidade ?? "";
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null) {
      setAviso(unidade ? `Escreva o número de ${unidade}.` : "Escreva o número.");
      return;
    }
    setAviso(null);
    aoResponder(valor);
  };
  return (
    <form onSubmit={enviar} noValidate>
      <div className="flex flex-wrap items-end gap-2">
        <Campo rotulo={unidade ? comMaiuscula(unidade) : "Resposta"} className="min-w-0 flex-1 basis-32">
          <EntradaNumero
            valor={valor}
            aoMudar={(novo) => {
              setValor(novo);
              setAviso(null);
            }}
            casas={entrada.casas ?? 0}
            min={entrada.min}
            max={entrada.max}
            aria-describedby={idDaPergunta}
            invalido={Boolean(aviso)}
          />
        </Campo>
        <Botao type="submit" tamanho="sm" className="h-12" carregando={pendente} rotuloCarregando="Anotando…">
          Responder
        </Botao>
        {aoNaoSaber ? (
          <Botao variante="texto" tamanho="sm" className="h-12" onClick={() => !pendente && aoNaoSaber()}>
            Não sei
          </Botao>
        ) : null}
      </div>
      <ErroEmLinha erro={erro} aviso={aviso} />
    </form>
  );
}

function RespostaDoLimite({
  campo,
  entrada,
  comNaoSei,
  idDaPergunta,
}: {
  campo: string;
  entrada: EntradaDaPergunta;
  comNaoSei: boolean;
  idDaPergunta: string;
}) {
  const { executar, pendente, erro } = useAcao(responderLimiteDaCozinha, {
    sucesso: (dados) => dados.texto,
    avisarErro: false,
  });
  return (
    <RespostaDeNumero
      entrada={entrada}
      idDaPergunta={idDaPergunta}
      pendente={pendente}
      erro={erro}
      aoResponder={(valor) => void executar(campo, valor)}
      aoNaoSaber={comNaoSei ? () => void executar(campo, null) : undefined}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Sim ou não: o gás que sobra                                                 */
/* -------------------------------------------------------------------------- */

const SIM_NAO = [
  { rotulo: "Sim", valor: "sim" },
  { rotulo: "Não", valor: "nao" },
  { rotulo: "Não sei", valor: "nao_sei" },
] as const;

type SimNao = (typeof SIM_NAO)[number]["valor"];

function RespostaSimNao({ campo, idDaPergunta }: { campo: string; idDaPergunta: string }) {
  const [escolhida, setEscolhida] = useState<SimNao | null>(null);
  const { executar, pendente, erro } = useAcao(responderLimiteDaCozinha, {
    sucesso: (dados) => dados.texto,
    avisarErro: false,
  });
  return (
    <div>
      <GrupoDeOpcoes
        idDoRotulo={idDaPergunta}
        opcoes={SIM_NAO}
        escolhida={escolhida}
        pendente={pendente}
        aoEscolher={(valor) => {
          setEscolhida(valor);
          void executar(campo, valor === "nao_sei" ? null : valor === "sim");
        }}
      />
      <ErroEmLinha erro={erro} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* A pergunta, com a resposta do tipo certo                                    */
/* -------------------------------------------------------------------------- */

export function RespostaInline({
  receita,
  pergunta,
  idDaPergunta,
}: {
  receita: Receita;
  pergunta: PerguntaDaReceita;
  /** O id do texto da pergunta, que nomeia os botões e descreve os campos. */
  idDaPergunta: string;
}) {
  const forma = comoResponder(pergunta);
  switch (forma.tipo) {
    case "posse":
      // A pergunta já está escrita em cima; a legenda escondida dá o mesmo nome ao grupo.
      return <PerguntaDePosse lista={forma.lista} id={forma.id} legenda={pergunta.texto} />;
    case "limite":
      return <RespostaDoLimite campo={forma.campo} entrada={forma.entrada} comNaoSei={forma.comNaoSei} idDaPergunta={idDaPergunta} />;
    case "sim_nao":
      return <RespostaSimNao campo={forma.campo} idDaPergunta={idDaPergunta} />;
    case "nenhuma":
      return null;
    default:
      return (
        <BotaoPerguntar
          rotulo="Responder no chat"
          rascunho={rascunhoDaPergunta(receita.nome)}
          contexto={{ tela: "receitas", tipo: "receita", id: receita.slug, rotulo: receita.nome }}
        />
      );
  }
}

/** O bloco da pergunta da cozinha: o texto, o porquê e a resposta. A de outro assunto não aparece. */
export function PerguntaEmLinha({
  receita,
  pergunta,
  className,
}: {
  receita: Receita;
  pergunta: PerguntaDaReceita;
  className?: string;
}) {
  const id = useId();
  const idDaPergunta = `pergunta${id}`;
  if (comoResponder(pergunta).tipo === "nenhuma") return null;
  return (
    <div className={clsx("rounded-md border border-atencao/25 bg-atencao/10 p-3", className)}>
      <p id={idDaPergunta} className="flex items-start gap-2 text-sm font-semibold text-tinta">
        <Question size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
        <span>{pergunta.texto}</span>
      </p>
      {pergunta.motivo ? <p className="mt-1 pl-6 text-xs text-texto-secundario">{frase(pergunta.motivo)}</p> : null}
      <div className="mt-3">
        <RespostaInline receita={receita} pergunta={pergunta} idDaPergunta={idDaPergunta} />
      </div>
    </div>
  );
}
