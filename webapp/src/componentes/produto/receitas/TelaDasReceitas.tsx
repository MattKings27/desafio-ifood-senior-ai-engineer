"use client";

/**
 * A tela de receitas: só as que a Dona Maria consegue fazer.
 *
 * As abas dizem o que a cozinha permite:
 *
 * - "Dá para fazer": com o que ela tem, ou comprando o que falta dentro do que
 *   resta do orçamento;
 * - "Falta uma resposta sua": cada receita com a pergunta da vez, e a resposta
 *   ali mesmo; respondida, a receita muda de aba;
 * - "Ranking": as que ela avaliou, pela pontuação.
 *
 * Dentro de cada aba, as seções dizem o que ela acha do prato: "Gosto de
 * fazer", "Ainda não me disse se gosta" (cada card pergunta, antes de qualquer
 * coisa da cozinha, se ela gosta de fazer) e, fechada no fim, "Não gosto de
 * fazer", com o "Mudei de ideia". A resposta muda a receita de seção na hora,
 * com o "Desfazer" no aviso (`ProvedorDoGosto`).
 *
 * Com nada para fazer ainda e receitas esperando resposta, o painel "Responda
 * e eu libero mais receitas" vem no alto de "Falta uma resposta sua", com as
 * perguntas da cozinha das receitas que ela gosta de fazer. E a tela nunca diz
 * "nada dá" quando a verdade é "ainda não confirmei": no alto de "Falta uma
 * resposta sua" e no lugar do vazio de "Dá para fazer" vai a frase da API
 * (`esperando_resposta`).
 *
 * O que a cozinha dela não permite não aparece em aba nenhuma. A aba e os
 * filtros moram na URL; as listas vêm da API, que filtra, conta e ordena: a da
 * aba e a das que ela não quer, com os mesmos filtros. Com o catálogo vazio, a
 * primeira visita já pede uma procura de receitas (`useDescoberta`).
 */

import { LinkSimple, ListChecks, MagnifyingGlass, Sparkle, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useMemo, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { Problema } from "@/componentes/compartilhados/Problema";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import { useConversa } from "@/componentes/conversa";
import type { EsperandoResposta, EstadoDaDescoberta, ItemDaGrade, ListaDeReceitas } from "@/lib/api/receitas";
import { contextoDaTela } from "@/lib/conversa/sugestoes";
import { useFiltrosNaUrl } from "@/lib/dados/useFiltrosNaUrl";

import { AbasDaGrade } from "./AbasDaGrade";
import { BarraDeFiltros } from "./BarraDeFiltros";
import type { AbaDaGrade } from "./filtros";
import {
  ESQUEMA_DAS_RECEITAS,
  FILTROS_DA_FOLHA,
  ROTULO_DA_ABA,
  chaveDoPedido,
  esquemaComAba,
  paraPedido,
  pedidoDasQueNaoQuer,
} from "./filtros";
import { PerguntaDoGosto, ProvedorDoGosto, useGostoDaGrade } from "./GostoDaGrade";
import type { ReceitasPorGosto } from "./gosto";
import { ROTULO_DA_SECAO, separarPorGosto } from "./gosto";
import { GradeDeReceitas, ListaPendente } from "./GradeDeReceitas";
import { PainelQueLibera } from "./PainelQueLibera";
import { SecaoAberta, SecaoNaoGosto } from "./SecoesDoGosto";
import { RASCUNHO_DA_DESCOBERTA, progressoDaDescoberta } from "./textos";
import { TrazerReceita } from "./TrazerReceita";
import { useDescoberta } from "./useDescoberta";
import type { ErroDaLista } from "./useListaDeReceitas";
import { useListaDeReceitas } from "./useListaDeReceitas";

/** Quantos cards "chegando" a procura mostra no fim da grade. */
const CHEGANDO = 4;

function FaixaDaDescoberta({ procura }: { procura: EstadoDaDescoberta }) {
  const procurando = procura.estado === "procurando";
  const deuErro = procura.estado === "erro";
  return (
    <div
      className={clsx(
        "flex items-start gap-2 rounded-md px-3 py-2.5 text-sm",
        deuErro ? "bg-tinta-clara text-texto" : "bg-creme text-texto",
      )}
    >
      <span aria-hidden="true" className={clsx("mt-px shrink-0", deuErro ? "text-perigo" : "text-marca")}>
        {deuErro ? (
          <WarningCircle size={18} weight="fill" />
        ) : (
          <Sparkle size={18} weight="fill" className={procurando ? "animate-pulse" : undefined} />
        )}
      </span>
      <p role="status" className="min-w-0">
        {procura.texto}
        {procurando && (procura.lidas > 0 || procura.encontradas > 0) ? (
          <span className="text-apagado"> {progressoDaDescoberta(procura.lidas, procura.encontradas)}.</span>
        ) : null}
      </p>
    </div>
  );
}

/** Quantas das que esperam resposta usam só o que ela tem, e o que falta ela dizer (texto da API). */
function ResumoDaEspera({ espera }: { espera: EsperandoResposta }) {
  return (
    <p className="flex items-start gap-2 rounded-md bg-creme px-3 py-2.5 text-sm text-texto minimalista:hidden">
      <ListChecks size={18} weight="bold" aria-hidden="true" className="mt-px shrink-0 text-marca" />
      <span className="min-w-0">{espera.texto}</span>
    </p>
  );
}

function Vazio({
  aba,
  comFiltros,
  contagens,
  espera,
  aoLimpar,
  aoIrPara,
  aoProcurar,
}: {
  aba: AbaDaGrade;
  comFiltros: boolean;
  contagens: ListaDeReceitas["contagens"];
  espera: EsperandoResposta | null;
  aoLimpar: () => void;
  aoIrPara: (aba: AbaDaGrade) => void;
  aoProcurar: (origem: HTMLElement | null) => void;
}) {
  if (comFiltros) {
    return (
      <EstadoVazio
        titulo="Nenhuma receita com esses filtros"
        descricao="Tire um filtro ou mude a busca para ver mais."
        icone={<MagnifyingGlass size={24} weight="duotone" />}
        acao={
          <Botao variante="terciario" tamanho="sm" onClick={aoLimpar}>
            Limpar filtros
          </Botao>
        }
      />
    );
  }
  if (aba === "falta_resposta") {
    return (
      <EstadoVazio
        titulo="Nenhuma receita esperando a senhora"
        descricao="Quando uma receita precisar de uma resposta sua, ela aparece aqui com a pergunta."
      />
    );
  }
  if (aba === "ranking") {
    return (
      <EstadoVazio
        titulo="A senhora ainda não avaliou nenhuma receita"
        descricao="Abra uma receita e dê as estrelas: a pontuação dela entra aqui, da maior para a menor."
      />
    );
  }
  const esperando = contagens.falta_resposta;
  return (
    <EstadoVazio
      titulo={esperando > 0 ? "Nenhuma receita confirmada ainda" : "Ainda não há receita que a senhora consiga fazer"}
      descricao={
        esperando > 0
          ? (espera?.texto ?? "Algumas receitas só esperam uma resposta sua para entrar aqui.")
          : "Procure receitas que aproveitam a sua despensa, ou traga uma receita pelo endereço."
      }
      acao={
        esperando > 0 ? (
          <Botao variante="terciario" tamanho="sm" onClick={() => aoIrPara("falta_resposta")}>
            Ver o que falta responder
          </Botao>
        ) : (
          <Botao variante="terciario" tamanho="sm" onClick={(evento) => aoProcurar(evento.currentTarget)}>
            Procurar receitas
          </Botao>
        )
      }
    />
  );
}

/**
 * O catálogo que ela vê está vazio: sem filtro nenhum, nenhuma receita em aba
 * nenhuma (as contagens da API seguem os filtros, então com filtro não dá para
 * saber).
 */
function semReceitaNenhuma(lista: ListaDeReceitas, comFiltros: boolean): boolean {
  return !comFiltros && Object.values(lista.contagens).every((quantas) => quantas === 0);
}

/** Uma lista vazia, do jeito que a API manda: para quem monta a tela sem as que ela não quer. */
function semNenhuma(de: ListaDeReceitas): ListaDeReceitas {
  return { ...de, aba: "nao_quer", itens: [] };
}

const perguntaDoGosto = (item: ItemDaGrade) => <PerguntaDoGosto item={item} className="mt-auto pt-1.5" />;

/**
 * As seções da aba: "Gosto de fazer" e "Ainda não me disse se gosta" abertas,
 * "Não gosto de fazer" fechada no fim. Em "Falta uma resposta sua", o card é o
 * largo, com a pergunta da vez; nas outras, o da grade, com a pergunta do gosto
 * em quem ainda não disse.
 */
function SecoesDaAba({
  aba,
  secoes,
  posicoes,
  esqueletos,
  erroDasQueNaoQuer,
  aoTentarDeNovo,
}: {
  aba: AbaDaGrade;
  secoes: ReceitasPorGosto;
  posicoes?: ReadonlyMap<string, number>;
  esqueletos: number;
  erroDasQueNaoQuer: ErroDaLista | null;
  aoTentarDeNovo: () => void;
}) {
  const { gosta, ainda_nao: aindaNao, nao_gosta: naoGosta } = secoes;
  const pendentes = aba === "falta_resposta";
  const lista = (itens: readonly ItemDaGrade[], rotulo: string, comPergunta: boolean, chegando = 0) =>
    pendentes ? (
      <ListaPendente itens={itens} rotulo={rotulo} nivelTitulo={4} />
    ) : (
      <GradeDeReceitas
        itens={itens}
        rotulo={rotulo}
        posicoes={posicoes}
        esqueletos={chegando}
        nivelTitulo={4}
        acaoDe={comPergunta ? perguntaDoGosto : undefined}
      />
    );
  const comAindaNao = aindaNao.length > 0 || esqueletos > 0;
  return (
    <div className="space-y-6">
      {gosta.length > 0 || comAindaNao ? (
        <SecaoAberta
          secao="gosta"
          quantas={gosta.length}
          apoio={
            gosta.length === 0
              ? "Nenhuma ainda. Diga em cada receita logo abaixo se a senhora gosta de fazer, e ela vem para cá."
              : pendentes
                ? "Falta só a resposta da cozinha, uma pergunta de cada vez."
                : undefined
          }
        >
          {gosta.length > 0 ? lista(gosta, ROTULO_DA_SECAO.gosta, false) : null}
        </SecaoAberta>
      ) : null}
      {comAindaNao ? (
        <SecaoAberta
          secao="ainda_nao"
          quantas={aindaNao.length}
          apoio="Antes de qualquer pergunta da cozinha, me diga se a senhora gosta de fazer cada prato."
        >
          {lista(aindaNao, ROTULO_DA_SECAO.ainda_nao, true, esqueletos)}
        </SecaoAberta>
      ) : null}
      <SecaoNaoGosto itens={naoGosta} erro={erroDasQueNaoQuer} aoTentarDeNovo={aoTentarDeNovo} />
    </div>
  );
}

/** A posição de cada receita no ranking inteiro, pela ordem que a API mandou. */
function posicoesDoRanking(itens: readonly ItemDaGrade[]): Map<string, number> {
  return new Map(itens.map((item, indice) => [item.slug, indice + 1]));
}

export function TelaDasReceitas(props: {
  inicial: ListaDeReceitas;
  chaveInicial: string;
  /** A aba em que a página abriu sem `aba` na URL (a do servidor), se não for a padrão. */
  abaPadrao?: AbaDaGrade;
  /** As que ela não quer, com os mesmos filtros (a página pede as duas juntas). */
  naoQuerInicial?: ListaDeReceitas;
  chaveDasQueNaoQuerInicial?: string;
}) {
  return (
    <ProvedorDoGosto>
      <Tela {...props} />
    </ProvedorDoGosto>
  );
}

function Tela({
  inicial,
  chaveInicial,
  abaPadrao,
  naoQuerInicial,
  chaveDasQueNaoQuerInicial,
}: {
  inicial: ListaDeReceitas;
  chaveInicial: string;
  abaPadrao?: AbaDaGrade;
  naoQuerInicial?: ListaDeReceitas;
  chaveDasQueNaoQuerInicial?: string;
}) {
  const esquema = useMemo(() => (abaPadrao ? esquemaComAba(abaPadrao) : ESQUEMA_DAS_RECEITAS), [abaPadrao]);
  const { filtros, definir, limpar } = useFiltrosNaUrl(esquema);
  const pedido = useMemo(() => paraPedido(filtros), [filtros]);
  const chave = chaveDoPedido(pedido);
  const { lista, carregando, erro, tentarDeNovo } = useListaDeReceitas({ inicial, chaveInicial, pedido, chave });
  const pedidoNaoQuer = useMemo(() => pedidoDasQueNaoQuer(pedido), [pedido]);
  const chaveNaoQuer = chaveDoPedido(pedidoNaoQuer);
  // Sem a lista das que ela não quer (quem monta a tela só com a da aba), uma vazia, a mesma a cada render.
  const naoQuerDoServidor = useMemo(() => naoQuerInicial ?? semNenhuma(inicial), [naoQuerInicial, inicial]);
  const naoQuer = useListaDeReceitas({
    inicial: naoQuerDoServidor,
    chaveInicial: chaveDasQueNaoQuerInicial ?? chaveNaoQuer,
    pedido: pedidoNaoQuer,
    chave: chaveNaoQuer,
  });
  const { mudancas } = useGostoDaGrade();
  const { abrir } = useConversa();
  const [trazendo, setTrazendo] = useState(false);
  const comFiltros = [pedido.q, pedido.usa, pedido.tempo_max, pedido.so_com_o_que_tenho, pedido.nota_min].some(
    (valor) => valor !== undefined,
  );
  const { procura, procurar } = useDescoberta(lista.descoberta, {
    semRota: (origem) => abrir({ rascunho: RASCUNHO_DA_DESCOBERTA, contexto: contextoDaTela("/receitas"), origem }),
    catalogoVazio: semReceitaNenhuma(lista, comFiltros),
  });

  const aba = filtros.aba;
  const limparFiltros = () => limpar(["q", ...FILTROS_DA_FOLHA]);
  const trocandoDeAba = lista.aba !== aba;
  const procurando = procura.estado === "procurando";
  const secoes = separarPorGosto(aba, lista.itens, naoQuer.lista.itens, mudancas);
  const naSecao = secoes.gosta.length + secoes.ainda_nao.length;

  const conteudo = (qual: AbaDaGrade) => {
    if (erro) {
      return <Problema categoria={erro.categoria} mensagem={erro.mensagem} pergunta={erro.pergunta} aoTentarDeNovo={tentarDeNovo} />;
    }
    if (trocandoDeAba) return <GradeDeReceitas itens={[]} rotulo={ROTULO_DA_ABA[qual]} esqueletos={CHEGANDO} />;
    const esqueletos = qual === "pode_fazer" && procurando ? CHEGANDO : 0;
    const secoesDaAba = (
      <SecoesDaAba
        aba={qual}
        secoes={secoes}
        posicoes={qual === "ranking" && !comFiltros && !pedido.ordem ? posicoesDoRanking(lista.itens) : undefined}
        esqueletos={esqueletos}
        erroDasQueNaoQuer={naoQuer.erro}
        aoTentarDeNovo={naoQuer.tentarDeNovo}
      />
    );
    if (naSecao === 0 && esqueletos === 0) {
      return (
        <div className="space-y-6">
          <Vazio
            aba={qual}
            comFiltros={comFiltros}
            contagens={lista.contagens}
            espera={lista.esperando_resposta}
            aoLimpar={limparFiltros}
            aoIrPara={(destino) => definir({ aba: destino })}
            aoProcurar={(origem) => void procurar(origem)}
          />
          {secoesDaAba}
        </div>
      );
    }
    if (qual === "falta_resposta") {
      const curtidas = new Set(secoes.gosta.map((item) => item.slug));
      return (
        <div className="space-y-5">
          {lista.contagens.pode_fazer === 0 ? (
            <PainelQueLibera perguntas={lista.perguntas_que_liberam} curtidas={curtidas} />
          ) : null}
          {lista.esperando_resposta ? <ResumoDaEspera espera={lista.esperando_resposta} /> : null}
          {secoesDaAba}
        </div>
      );
    }
    return secoesDaAba;
  };

  return (
    <div className="space-y-5">
      <CabecalhoDaPagina
        titulo="Receitas"
        descricao="Só as que a senhora consegue fazer: com o que tem, ou comprando o que falta dentro do orçamento."
        resumivel
        acoes={
          <div className="grid w-full grid-cols-1 gap-2 min-[420px]:grid-cols-2 sm:flex sm:w-auto">
            <Botao
              className="w-full sm:w-auto"
              icone={<Sparkle size={18} weight="fill" />}
              carregando={procurando}
              rotuloCarregando="Procurando…"
              onClick={(evento) => void procurar(evento.currentTarget)}
            >
              Procurar mais receitas
            </Botao>
            <Botao
              variante="secundario"
              className="w-full sm:w-auto"
              icone={<LinkSimple size={18} weight="bold" />}
              aria-haspopup="dialog"
              onClick={() => setTrazendo(true)}
            >
              Trazer uma receita
            </Botao>
          </div>
        }
      />

      {procura.texto ? <FaixaDaDescoberta procura={procura} /> : null}

      <BarraDeFiltros filtros={filtros} definir={definir} limpar={limparFiltros} quantas={lista.itens.length} />

      <AbasDaGrade ativa={aba} contagens={lista.contagens} aoTrocar={(destino) => definir({ aba: destino })}>
        <div
          aria-busy={carregando || undefined}
          className={clsx("@container transition-opacity duration-rapida", carregando && !trocandoDeAba && "opacity-60")}
        >
          {/* O título da aba, para quem navega pelos títulos: as seções são h3, os cards h4. */}
          <h2 className="sr-only">{ROTULO_DA_ABA[aba]}</h2>
          {conteudo(aba)}
        </div>
      </AbasDaGrade>

      <TrazerReceita aberta={trazendo} aoFechar={() => setTrazendo(false)} />
    </div>
  );
}
