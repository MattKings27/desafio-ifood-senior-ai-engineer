"use client";

/**
 * O "corrigir" de um valor que a plataforma estabeleceu sem perguntar: o preço
 * do que falta comprar, o peso de uma medida pela tabela do IBGE, o rendimento
 * estimado pelo peso. Nada disso é pergunta: o valor já está na tela, dito como
 * estimado e com a fonte, e o link discreto abre o campo para ela pôr o dela,
 * que sempre vale mais. Cada correção vai pela rota de sempre: o preço para
 * `POST /api/preco-mercado`, o peso e o rendimento para a resposta da receita.
 */

import { PencilSimple } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { FormEvent } from "react";
import { useId, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Campo, Entrada, EntradaNumero, Selecao } from "@/componentes/compartilhados/Campos";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import type { ErroDaAcao } from "@/lib/acoes/base";
import { informarPrecoDoQueFalta, responderSobreAReceita } from "@/lib/acoes/receitas";
import { useAcao } from "@/lib/dados/useAcao";

import type { Correcao } from "./correcao";
import type { EntradaDaPergunta, LeiturasDoPeso } from "@/lib/api/receitas";
import { comMaiuscula, ondeFicou } from "./textos";

type Receita = { slug: string; nome: string };

/** O que o campo corrige, dito sem pergunta: "O preço de creme de leite", "O peso de 1 cebola". */
function tituloDa(correcao: Correcao): string {
  if (correcao.tipo === "preco") return `O preço de ${correcao.ingrediente} que a senhora paga`;
  if (correcao.tipo === "peso") return `O peso de ${correcao.campo} na cozinha da senhora`;
  return comMaiuscula(correcao.entrada.unidade ?? "o valor da senhora");
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
/* O preço do que falta comprar                                                */
/* -------------------------------------------------------------------------- */

function CorrigirPreco({ ingrediente, idDoTitulo }: { ingrediente: string; idDoTitulo: string }) {
  const [valor, setValor] = useState<number | null>(null);
  const [quantidade, setQuantidade] = useState<number | null>(1);
  const [unidade, setUnidade] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const { executar, pendente, erro } = useAcao(informarPrecoDoQueFalta, { sucesso: (dados) => dados.texto, avisarErro: false });
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null || quantidade === null || !unidade.trim()) {
      setAviso(`Escreva o preço de ${ingrediente} e por qual quantidade: 1 lata, 1 kg, 1 pacote.`);
      return;
    }
    setAviso(null);
    void executar([{ ingrediente, valor, quantidade, unidade }]);
  };
  return (
    <form onSubmit={enviar} noValidate aria-labelledby={idDoTitulo} className="space-y-3">
      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)] items-end gap-2">
        <Campo rotulo="Preço">
          <EntradaNumero valor={valor} aoMudar={setValor} prefixo="R$" casas={2} min={0} invalido={Boolean(aviso)} />
        </Campo>
        <Campo rotulo="Quantidade">
          <EntradaNumero valor={quantidade} aoMudar={setQuantidade} casas={2} min={0} />
        </Campo>
        <Campo rotulo="Medida">
          <Entrada value={unidade} onChange={(evento) => setUnidade(evento.target.value)} placeholder="lata, kg" autoComplete="off" />
        </Campo>
      </div>
      <Botao type="submit" tamanho="sm" carregando={pendente} rotuloCarregando="Anotando…">
        Salvar
      </Botao>
      <ErroEmLinha erro={erro} aviso={aviso} />
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* O peso de uma medida, e um número da receita (o rendimento)                  */
/* -------------------------------------------------------------------------- */

const UNIDADES_DO_PESO = [
  { valor: "g", rotulo: "g" },
  { valor: "kg", rotulo: "kg" },
] as const;

/** O número como vai para a API: vírgula decimal e sem ponto de milhar ("0,3", "1500"). */
function numeroDoPeso(valor: number): string {
  return String(valor).replace(".", ",");
}

function useRespostaDaReceita() {
  return useAcao(responderSobreAReceita, { sucesso: (dados) => ondeFicou(dados.nome, dados.cozinha), avisarErro: false });
}

function CorrigirPeso({
  receita,
  campo,
  pesoDe,
  idDoTitulo,
}: {
  receita: Receita;
  campo: string;
  pesoDe: LeiturasDoPeso | null;
  idDoTitulo: string;
}) {
  const [valor, setValor] = useState<number | null>(null);
  const [unidade, setUnidade] = useState<"g" | "kg">("g");
  const [de, setDe] = useState<"cada" | "tudo">("cada");
  const [aviso, setAviso] = useState<string | null>(null);
  const { executar, pendente, erro } = useRespostaDaReceita();
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null || valor <= 0) {
      setAviso("Escreva o peso, por exemplo: 300 g.");
      return;
    }
    setAviso(null);
    // O valor de referência é o de uma unidade; "tudo" é o da linha inteira.
    void executar(receita.slug, campo, `${numeroDoPeso(valor)} ${unidade}`, de === "cada");
  };
  return (
    <form onSubmit={enviar} noValidate aria-labelledby={idDoTitulo} className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <Campo rotulo="Peso" className="min-w-0 flex-1 basis-32">
          <EntradaNumero valor={valor} aoMudar={setValor} casas={3} min={0} invalido={Boolean(aviso)} />
        </Campo>
        <Campo rotulo="Unidade" className="w-24 shrink-0">
          <Selecao value={unidade} onChange={(evento) => setUnidade(evento.target.value === "kg" ? "kg" : "g")} opcoes={UNIDADES_DO_PESO} />
        </Campo>
      </div>
      {pesoDe ? (
        <Segmentado
          legenda="Esse peso é de"
          opcoes={[
            { valor: "cada", rotulo: pesoDe.cada },
            { valor: "tudo", rotulo: pesoDe.tudo },
          ]}
          valor={de}
          aoMudar={setDe}
          orientacao="vertical"
        />
      ) : null}
      <Botao type="submit" tamanho="sm" carregando={pendente} rotuloCarregando="Anotando…">
        Salvar
      </Botao>
      <ErroEmLinha erro={erro} aviso={aviso} />
    </form>
  );
}

function CorrigirNumero({
  receita,
  campo,
  entrada,
  idDoTitulo,
}: {
  receita: Receita;
  campo: string;
  entrada: EntradaDaPergunta;
  idDoTitulo: string;
}) {
  const [valor, setValor] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const { executar, pendente, erro } = useRespostaDaReceita();
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null) {
      setAviso("Escreva o número.");
      return;
    }
    setAviso(null);
    void executar(receita.slug, campo, String(valor));
  };
  return (
    <form onSubmit={enviar} noValidate aria-labelledby={idDoTitulo}>
      <div className="flex flex-wrap items-end gap-2">
        <Campo rotulo={comMaiuscula(entrada.unidade ?? "número")} className="min-w-0 flex-1 basis-32">
          <EntradaNumero valor={valor} aoMudar={setValor} casas={0} min={entrada.min} max={entrada.max} invalido={Boolean(aviso)} />
        </Campo>
        <Botao type="submit" tamanho="sm" className="h-12" carregando={pendente} rotuloCarregando="Anotando…">
          Salvar
        </Botao>
      </div>
      <ErroEmLinha erro={erro} aviso={aviso} />
    </form>
  );
}

/**
 * O link discreto "corrigir" e, aberto, o campo do valor dela. O nome do botão
 * diz o que ele corrige ("corrigir o preço de creme de leite"), para quem usa
 * leitor de tela; na tela, só "corrigir".
 */
export function CorrigirValor({
  receita,
  correcao,
  oQue,
  className,
}: {
  receita: Receita;
  correcao: Correcao;
  /** O que o botão corrige, para o leitor de tela: "o preço de creme de leite". */
  oQue: string;
  className?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const id = useId();
  const idDoTitulo = `corrigir${id}`;
  return (
    <div className={clsx("text-xs", className)}>
      <button
        type="button"
        onClick={() => setAberto((antes) => !antes)}
        aria-expanded={aberto}
        className="inline-flex min-h-8 items-center gap-1 rounded-sm font-semibold text-texto-secundario underline underline-offset-2 hover:text-tinta"
      >
        <PencilSimple size={13} weight="bold" aria-hidden="true" />
        <span>
          corrigir <span className="sr-only">{oQue}</span>
        </span>
      </button>
      {aberto ? (
        <div className="mt-2 rounded-md bg-secao p-3">
          <p id={idDoTitulo} className="mb-2 text-sm font-semibold text-tinta">
            {tituloDa(correcao)}
          </p>
          {correcao.tipo === "preco" ? (
            <CorrigirPreco ingrediente={correcao.ingrediente} idDoTitulo={idDoTitulo} />
          ) : correcao.tipo === "peso" ? (
            <CorrigirPeso receita={receita} campo={correcao.campo} pesoDe={correcao.pesoDe} idDoTitulo={idDoTitulo} />
          ) : (
            <CorrigirNumero receita={receita} campo={correcao.campo} entrada={correcao.entrada} idDoTitulo={idDoTitulo} />
          )}
        </div>
      ) : null}
    </div>
  );
}
