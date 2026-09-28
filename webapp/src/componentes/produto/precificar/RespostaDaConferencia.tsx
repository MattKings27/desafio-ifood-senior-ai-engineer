"use client";

/**
 * Responder a pergunta da conferência ali mesmo, sem sair da tela de preço.
 *
 * Cada pergunta tem o seu jeito (`formaDaConferencia`):
 * ter ou não ter um equipamento vai para o perfil da cozinha; o tempo no fogo
 * e o rendimento são da receita, e voltam para o formulário (a receita que ela
 * escreveu); o gosto vai para o gosto dela; o preço do que falta, para os
 * preços; o peso de uma linha ("Não sei quanto pesa um peito de frango") e o
 * item parecido ("É o seu miolo de alcatra?") vão para a receita guardada, e a
 * conferência seguinte mantém o que ela disse. Depois da resposta, a tela
 * confere de novo. "Não sei" não vira "não tenho".
 */

import type { FormEvent } from "react";
import { useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Campo, Entrada, EntradaNumero, Selecao } from "@/componentes/compartilhados/Campos";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import { BotaoPerguntar } from "@/componentes/conversa/BotaoPerguntar";
import { ErroDoMotor } from "@/lib/api/base";
import { cardapioDeHoje } from "@/lib/api/cardapio";
import { perfil } from "@/lib/api/perfil";
import type { RespostaDePosse } from "@/lib/api/perfil";
import { precoDeHoje } from "@/lib/api/preco";
import type { EntradaDaPergunta, LeiturasDoPeso, OpcaoDeResposta, PerguntaDaReceita } from "@/lib/api/receitas";
import { receitas } from "@/lib/api/receitas";
import { textoParaEla } from "@/lib/formato";

import { formaDaConferencia } from "./formaDaConferencia";
import { ID_DO_PREPARO } from "./FormularioDaReceita";

/** O que muda na receita que ela escreveu, quando a resposta é da receita. */
export type RespostaDaReceita = { tempo?: number; rende?: number };

type Props = {
  pergunta: PerguntaDaReceita;
  prato: string;
  /** A receita guardada que a conferência leu: é nela que o peso e o item parecido ficam. */
  receitaId?: string;
  /** Depois de gravar a resposta: a tela confere de novo. */
  aoResponder: () => void;
  /** A resposta é da própria receita: volta para o formulário, e a tela confere de novo. */
  aoResponderNaReceita: (resposta: RespostaDaReceita) => void;
};

function useEnvio(aoResponder: () => void) {
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const enviar = async (acao: () => Promise<unknown>) => {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
      aoResponder();
    } catch (causa) {
      const mensagem = causa instanceof ErroDoMotor ? (causa.pergunta ?? causa.message) : null;
      setErro(textoParaEla(mensagem, "Não consegui anotar a resposta. Tente de novo."));
    } finally {
      setOcupado(false);
    }
  };
  return { ocupado, erro, enviar };
}

function Erro({ texto }: { texto: string | null }) {
  return texto ? (
    <p role="alert" className="mt-1.5 text-sm font-medium text-perigo">
      {texto}
    </p>
  ) : null;
}

function Numero({
  entrada,
  rotulo,
  ocupado,
  aoResponder,
  aoNaoSaber,
}: {
  entrada: EntradaDaPergunta;
  rotulo: string;
  ocupado: boolean;
  aoResponder: (valor: number) => void;
  aoNaoSaber?: () => void;
}) {
  const [valor, setValor] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null) {
      setAviso(`Escreva o número de ${entrada.unidade ?? "vezes"}.`);
      return;
    }
    setAviso(null);
    aoResponder(valor);
  };
  return (
    <form noValidate onSubmit={enviar} className="flex flex-wrap items-end gap-2">
      <Campo rotulo={rotulo} erro={aviso} className="min-w-0 flex-1 basis-40">
        <EntradaNumero valor={valor} aoMudar={setValor} casas={entrada.casas ?? 0} min={entrada.min} max={entrada.max} invalido={Boolean(aviso)} />
      </Campo>
      <Botao type="submit" tamanho="sm" className="h-12" carregando={ocupado} rotuloCarregando="Anotando…">
        Responder
      </Botao>
      {aoNaoSaber ? (
        <Botao variante="texto" tamanho="sm" className="h-12" onClick={aoNaoSaber}>
          Não sei
        </Botao>
      ) : null}
    </form>
  );
}

function Escolhas<V extends string>({
  opcoes,
  ocupado,
  aoEscolher,
}: {
  opcoes: readonly { rotulo: string; valor: V }[];
  ocupado: boolean;
  aoEscolher: (valor: V) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {opcoes.map((opcao) => (
        <Botao key={opcao.valor} variante="terciario" tamanho="sm" disabled={ocupado} onClick={() => aoEscolher(opcao.valor)}>
          {opcao.rotulo}
        </Botao>
      ))}
    </div>
  );
}

function Gosto({ prato, aoResponder }: { prato: string; aoResponder: () => void }) {
  const [impedimento, setImpedimento] = useState("");
  const { ocupado, erro, enviar } = useEnvio(aoResponder);
  return (
    <div className="space-y-2">
      <Campo rotulo="Algum impedimento?" opcional dica="Pode deixar em branco.">
        <Entrada value={impedimento} onChange={(evento) => setImpedimento(evento.target.value)} autoComplete="off" />
      </Campo>
      <Escolhas
        opcoes={[
          { rotulo: "Gosto de fazer", valor: "sim" },
          { rotulo: "Não gosto", valor: "nao" },
        ]}
        ocupado={ocupado}
        aoEscolher={(valor) => void enviar(() => cardapioDeHoje.registrarGosto(prato, valor === "sim", impedimento))}
      />
      <Erro texto={erro} />
    </div>
  );
}

const UNIDADES_DO_PESO = [
  { valor: "g", rotulo: "g" },
  { valor: "kg", rotulo: "kg" },
] as const;

/** O peso de uma linha cuja medida não se converte, em gramas ou quilos, de uma unidade ou da linha. */
function PesoDaLinha({
  receitaId,
  campo,
  pesoDe,
  aoResponder,
}: {
  receitaId: string;
  campo: string;
  pesoDe: LeiturasDoPeso | null;
  aoResponder: () => void;
}) {
  const [valor, setValor] = useState<number | null>(null);
  const [unidade, setUnidade] = useState<"g" | "kg">("g");
  const [de, setDe] = useState<"cada" | "tudo">("cada");
  const [aviso, setAviso] = useState<string | null>(null);
  const { ocupado, erro, enviar } = useEnvio(aoResponder);
  const mandar = (evento: FormEvent) => {
    evento.preventDefault();
    if (valor === null || valor <= 0) {
      setAviso("Escreva quanto pesa, por exemplo: 300 g.");
      return;
    }
    setAviso(null);
    const resposta = `${String(valor).replace(".", ",")} ${unidade}`;
    void enviar(() => receitas.responder(receitaId, { campo, resposta, por_unidade: de === "cada" }));
  };
  return (
    <form noValidate onSubmit={mandar} className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <Campo rotulo="Quanto pesa" erro={aviso} className="min-w-0 flex-1 basis-32">
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
      <Botao type="submit" tamanho="sm" className="h-12" carregando={ocupado} rotuloCarregando="Anotando…">
        Responder
      </Botao>
      <Erro texto={erro} />
    </form>
  );
}

/** "A receita pede alcatra. É o seu miolo de alcatra?": a resposta fica na receita. */
function MesmoItem({
  receitaId,
  campo,
  opcoes,
  aoResponder,
}: {
  receitaId: string;
  campo: string;
  opcoes: readonly OpcaoDeResposta[];
  aoResponder: () => void;
}) {
  const { ocupado, erro, enviar } = useEnvio(aoResponder);
  return (
    <div>
      <Escolhas
        opcoes={opcoes.map((opcao) => ({ rotulo: opcao.rotulo, valor: opcao.resposta }))}
        ocupado={ocupado}
        aoEscolher={(valor) => void enviar(() => receitas.responder(receitaId, { campo, resposta: valor }))}
      />
      <Erro texto={erro} />
    </div>
  );
}

type PrecoDigitado = { valor: number | null; quantidade: number | null; unidade: string };

function Precos({ ingredientes, aoResponder }: { ingredientes: readonly string[]; aoResponder: () => void }) {
  const [precos, setPrecos] = useState<PrecoDigitado[]>(() => ingredientes.map(() => ({ valor: null, quantidade: 1, unidade: "" })));
  const [aviso, setAviso] = useState<string | null>(null);
  const { ocupado, erro, enviar } = useEnvio(aoResponder);
  const mudar = (indice: number, parcial: Partial<PrecoDigitado>) =>
    setPrecos((atuais) => atuais.map((preco, i) => (i === indice ? { ...preco, ...parcial } : preco)));
  const mandar = (evento: FormEvent) => {
    evento.preventDefault();
    const faltando = precos.findIndex((p) => p.valor === null || p.quantidade === null || !p.unidade.trim());
    if (faltando >= 0) {
      setAviso(`Diga o preço de ${ingredientes[faltando]} e por qual quantidade: 1 lata, 1 kg, 1 pacote.`);
      return;
    }
    setAviso(null);
    void enviar(async () => {
      for (const [indice, preco] of precos.entries()) {
        await precoDeHoje.registrarPreco(ingredientes[indice] ?? "", preco.valor ?? 0, {
          quantidade: preco.quantidade ?? 1,
          unidade: preco.unidade.trim(),
        });
      }
    });
  };
  return (
    <form noValidate onSubmit={mandar} className="space-y-3">
      {ingredientes.map((ingrediente, indice) => (
        <fieldset key={ingrediente} className="min-w-0">
          <legend className="mb-1 text-sm font-semibold text-tinta">{ingrediente}</legend>
          <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)] items-end gap-2">
            <Campo rotulo="Preço">
              <EntradaNumero valor={precos[indice]?.valor ?? null} aoMudar={(valor) => mudar(indice, { valor })} prefixo="R$" casas={2} min={0} />
            </Campo>
            <Campo rotulo="Quantidade">
              <EntradaNumero valor={precos[indice]?.quantidade ?? null} aoMudar={(quantidade) => mudar(indice, { quantidade })} casas={2} min={0} />
            </Campo>
            <Campo rotulo="Medida">
              <Entrada
                value={precos[indice]?.unidade ?? ""}
                onChange={(evento) => mudar(indice, { unidade: evento.target.value })}
                placeholder="lata, kg"
                autoComplete="off"
              />
            </Campo>
          </div>
        </fieldset>
      ))}
      <Botao type="submit" tamanho="sm" carregando={ocupado} rotuloCarregando="Anotando…">
        Guardar o preço
      </Botao>
      <Erro texto={aviso ?? erro} />
    </form>
  );
}

function Instrucao({ children, campo }: { children: string; campo?: string }) {
  return (
    <p className="text-sm text-texto">
      {children}{" "}
      {campo ? (
        <button
          type="button"
          onClick={() => document.getElementById(campo)?.focus()}
          className="-my-2 inline-flex min-h-11 items-center rounded-sm px-1 font-semibold text-marca underline-offset-4 hover:underline"
        >
          Ir para o campo
        </button>
      ) : null}
    </p>
  );
}

export function RespostaDaConferencia({ pergunta, prato, receitaId, aoResponder, aoResponderNaReceita }: Props) {
  const { ocupado, erro, enviar } = useEnvio(aoResponder);

  if (pergunta.tipo === "gosto") return <Gosto prato={prato} aoResponder={aoResponder} />;
  if (pergunta.campo === "modo_preparo") {
    return (
      <Instrucao campo={ID_DO_PREPARO}>
        Escreva como a senhora faz, passo a passo, no campo lá em cima, e confira de novo.
      </Instrucao>
    );
  }

  const noChat = (
    <BotaoPerguntar
      rotulo="Responder no chat"
      rascunho={`Sobre ${prato}: `}
      contexto={{ tela: "precificar", tipo: "pergunta", rotulo: pergunta.texto }}
    />
  );
  const forma = formaDaConferencia(pergunta);
  switch (forma.tipo) {
    case "posse":
      return (
        <div>
          <Escolhas
            opcoes={forma.opcoes.map((opcao) => ({ rotulo: opcao.rotulo, valor: opcao.estado }))}
            ocupado={ocupado}
            aoEscolher={(estado: RespostaDePosse) => void enviar(() => perfil.definirPosse(forma.lista, forma.id, estado))}
          />
          <Erro texto={erro} />
        </div>
      );
    case "receita":
      return (
        <Numero
          entrada={forma.entrada}
          rotulo={forma.campo === "tempo_cozimento_min" ? "Minutos no fogo" : "Porções"}
          ocupado={false}
          aoResponder={(valor) =>
            aoResponderNaReceita(forma.campo === "tempo_cozimento_min" ? { tempo: valor } : { rende: valor })
          }
        />
      );
    case "limite":
      return (
        <div>
          <Numero
            entrada={forma.entrada}
            rotulo={forma.entrada.unidade ? forma.entrada.unidade.charAt(0).toUpperCase() + forma.entrada.unidade.slice(1) : "Resposta"}
            ocupado={ocupado}
            aoResponder={(valor) => void enviar(() => perfil.definirRestricao(forma.campo, valor))}
            aoNaoSaber={forma.comNaoSei ? () => void enviar(() => perfil.definirRestricao(forma.campo, null)) : undefined}
          />
          <Erro texto={erro} />
        </div>
      );
    case "sim_nao":
      return (
        <div>
          <Escolhas
            opcoes={[
              { rotulo: "Sim", valor: "sim" },
              { rotulo: "Não", valor: "nao" },
              { rotulo: "Não sei", valor: "nao_sei" },
            ]}
            ocupado={ocupado}
            aoEscolher={(valor) =>
              void enviar(() => perfil.definirRestricao(forma.campo, valor === "nao_sei" ? null : valor === "sim"))
            }
          />
          <Erro texto={erro} />
        </div>
      );
    case "preco":
      return <Precos ingredientes={forma.ingredientes} aoResponder={aoResponder} />;
    case "peso":
      return receitaId ? (
        <PesoDaLinha receitaId={receitaId} campo={forma.campo} pesoDe={forma.pesoDe} aoResponder={aoResponder} />
      ) : (
        noChat
      );
    case "mesmo_item":
      return receitaId ? <MesmoItem receitaId={receitaId} campo={forma.campo} opcoes={forma.opcoes} aoResponder={aoResponder} /> : noChat;
    case "linha":
      return <Instrucao>Escreva na linha dessa receita, lá em cima, quanto vai (2 colheres de sopa, a gosto), e confira de novo.</Instrucao>;
    default:
      return noChat;
  }
}
