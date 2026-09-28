/**
 * Os cards da grade de receitas, como numa vitrine de classificados: a foto
 * quadrada em cima, o nome, o site e o tempo, o selo na língua dela (com o que
 * tem, ou comprando quanto), o quanto usa da despensa e o que falta comprar.
 * O card inteiro é o link para a receita; a pontuação, quando ela já avaliou,
 * fica sobre a foto, e no ranking também a posição. A receita que se apoia no
 * que toda cozinha tem, sem ela ter confirmado, traz a nota "Confirme a cozinha".
 *
 * O card de "Falta uma resposta sua" é largo: a foto pequena ao lado do nome, e
 * uma pergunta de cada vez, com a resposta ali mesmo embaixo, por cima do link
 * do card: primeiro se ela gosta de fazer o prato; se gosta, a da cozinha
 * (equipamento, técnica ou rotina) que segura a receita. Nele nada é cortado: o
 * nome, o site e a pergunta quebram linha, sem reticências.
 *
 * No modo minimalista, os dois ficam com o essencial: a foto, o nome, o selo e
 * o que falta numa linha. O site, o "usa 3 de 4" e os preços de referência
 * somem; a pergunta fica numa linha, com o "Responder" (`PerguntaRecolhida`).
 * A conta inteira continua no detalhe da receita.
 */

import { CheckCircle, Question, SealQuestion, ShoppingCartSimple, Star } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

import { AcimaDoLink, CardLink } from "@/componentes/compartilhados/Card";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { PerguntaRecolhida } from "@/componentes/compartilhados/RespostaRecolhida";
import type { CodigoDoSelo, ItemDaGrade, SeloDaReceita } from "@/lib/api/receitas";

import { IconeDoPrato, tomDaFoto } from "./aparencia";
import { PerguntaDoGosto } from "./GostoDaGrade";
import { comoResponder } from "./perguntas";
import { PerguntaEmLinha } from "./RespostaInline";
import { CLASSES_DO_TOM, TOM_DA_COZINHA, semQuebrarValor } from "./textos";
import { ValorDeReferencia } from "./ValorDeReferencia";

const ICONE_DO_SELO: Readonly<Record<CodigoDoSelo, ReactNode>> = {
  com_o_que_tem: <CheckCircle size={16} weight="fill" />,
  comprando: <ShoppingCartSimple size={16} weight="fill" />,
  falta_resposta: <Question size={16} weight="fill" />,
};

/** "TudoGostoso · 35 min"; a receita que ela ditou não tem site. */
function origemDa(item: Pick<ItemDaGrade, "site" | "tempo_texto">): string {
  return [item.site ?? "Receita da senhora", item.tempo_texto].filter(Boolean).join(" · ");
}

/** O selo em cor e ícone, como a linha de preço de um anúncio. O texto é o da API. */
export function SeloDaGrade({ selo, className }: { selo: SeloDaReceita; className?: string }) {
  const tom = CLASSES_DO_TOM[TOM_DA_COZINHA[selo.codigo]];
  return (
    <p className={clsx("flex items-start gap-1.5 text-[0.8125rem] font-semibold leading-snug", tom.texto, className)}>
      <span aria-hidden="true" className="mt-px inline-flex shrink-0">
        {ICONE_DO_SELO[selo.codigo]}
      </span>
      <span className="min-w-0">{semQuebrarValor(selo.texto)}</span>
    </p>
  );
}

/**
 * "Confirme a cozinha": a receita dá para fazer, mas se apoia no que toda
 * cozinha tem e ela ainda não confirmou. A aba não muda; o aceite vai pedir.
 */
export function NotaDaCozinha({ nota }: { nota: string }) {
  return (
    <p className="flex items-start gap-1.5 text-xs font-semibold text-atencao">
      <SealQuestion size={15} weight="fill" aria-hidden="true" className="mt-px shrink-0" />
      <span className="min-w-0">{nota}</span>
    </p>
  );
}

function Pontuacao({ texto }: { texto: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-superficie px-2 py-0.5 text-xs font-bold text-tinta shadow-cartao">
      <Star size={13} weight="fill" aria-hidden="true" className="text-atencao" />
      <span className="numero">{texto}</span>
      <span className="sr-only"> de pontuação</span>
    </span>
  );
}

function FotoDoCard({ item, posicao, prioridade }: { item: ItemDaGrade; posicao?: number; prioridade: boolean }) {
  return (
    <div className="relative overflow-hidden">
      <ImagemComFallback
        src={item.imagem?.url}
        alt=""
        proporcao="1/1"
        tipo="receita"
        prioridade={prioridade}
        icone={<IconeDoPrato nome={item.nome} tamanho={48} />}
        classeDoFundo={tomDaFoto(item.slug)}
        classeDaImagem="transition-transform duration-lenta ease-padrao group-hover:scale-[1.04]"
      />
      {posicao !== undefined ? (
        <span className="absolute top-2 left-2 inline-flex min-w-7 items-center justify-center rounded-full bg-tinta px-2 py-0.5 text-xs font-bold text-superficie">
          <span className="numero">{posicao}º</span>
          <span className="sr-only"> lugar no ranking</span>
        </span>
      ) : null}
      {item.pontuacao ? (
        <span className="absolute top-2 right-2">
          <Pontuacao texto={item.pontuacao.texto} />
        </span>
      ) : null}
    </div>
  );
}

export function CartaoDeReceita({
  item,
  posicao,
  acao,
  prioridade = false,
  nivelTitulo = 3,
}: {
  item: ItemDaGrade;
  /** A posição no ranking, quando a lista é o ranking inteiro. */
  posicao?: number;
  /** Uma ação que fica por cima do link do card (a pergunta do gosto, "Mudei de ideia"). */
  acao?: ReactNode;
  /** As primeiras fotos da tela carregam já. */
  prioridade?: boolean;
  /** Dentro de uma seção ("Gosto de fazer"), o nome do card é um nível abaixo do título dela. */
  nivelTitulo?: 3 | 4;
}) {
  return (
    <CardLink
      href={item.rota}
      titulo={item.nome}
      nivelTitulo={nivelTitulo}
      como="article"
      densidade="nenhuma"
      className="group flex h-full flex-col overflow-hidden"
      classeDoTitulo="line-clamp-2 px-3 pt-3 sm:px-3.5"
      midia={<FotoDoCard item={item} posicao={posicao} prioridade={prioridade} />}
    >
      <div className="flex flex-1 flex-col gap-1.5 px-3 pt-1 pb-3 sm:px-3.5 sm:pb-3.5">
        <p className="truncate text-xs text-apagado minimalista:hidden">{origemDa(item)}</p>
        <SeloDaGrade selo={item.selo} />
        {item.nota_da_cozinha ? <NotaDaCozinha nota={item.nota_da_cozinha} /> : null}
        <p className="text-xs text-texto minimalista:hidden">{item.usa_texto}</p>
        <p className="text-xs text-apagado minimalista:truncate">{semQuebrarValor(item.falta_texto)}</p>
        <PrecosDeReferencia item={item} />
        {acao ? <AcimaDoLink className="mt-auto pt-1.5">{acao}</AcimaDoLink> : null}
      </div>
    </CardLink>
  );
}

/** O que falta comprar com preço estimado: o texto com a fonte, e o "corrigir" discreto. */
function PrecosDeReferencia({ item }: { item: ItemDaGrade }) {
  if (!item.referencias || item.referencias.length === 0) return null;
  const receita = { slug: item.slug, nome: item.nome };
  return (
    <AcimaDoLink className="minimalista:hidden">
      {item.referencias.map((referencia) => (
        <ValorDeReferencia
          key={referencia.ingrediente}
          receita={receita}
          texto={referencia.texto}
          fonte={referencia.site}
          url={referencia.url}
          precos={referencia}
          correcao={{ tipo: "preco", ingrediente: referencia.ingrediente }}
          oQue={`o preço de ${referencia.ingrediente}`}
        />
      ))}
    </AcimaDoLink>
  );
}

/**
 * A pergunta da vez no card de quem espera uma resposta: o gosto primeiro; com
 * o gosto dito, a da cozinha; e o que falta, quando não há o que ela responda.
 */
function PerguntaDaVez({ item }: { item: ItemDaGrade }) {
  if (item.gosta === null) {
    return (
      <AcimaDoLink className="col-span-2 mt-3">
        <PerguntaDoGosto item={item} />
      </AcimaDoLink>
    );
  }
  const pergunta = item.pergunta;
  if (pergunta && comoResponder(pergunta).tipo !== "nenhuma") {
    return (
      <AcimaDoLink className="col-span-2 mt-3">
        <PerguntaRecolhida pergunta={pergunta.texto} icone={<Question size={16} weight="fill" className="text-atencao" />}>
          <PerguntaEmLinha receita={{ slug: item.slug, nome: item.nome }} pergunta={pergunta} />
        </PerguntaRecolhida>
      </AcimaDoLink>
    );
  }
  return <p className="col-span-2 mt-3 text-sm text-texto-secundario minimalista:truncate">{item.falta_texto}</p>;
}

/** O card de quem espera uma resposta: largo, com a pergunta da vez e a resposta ali mesmo. */
export function CartaoPendente({ item, nivelTitulo = 3 }: { item: ItemDaGrade; nivelTitulo?: 3 | 4 }) {
  return (
    <CardLink
      href={item.rota}
      titulo={item.nome}
      nivelTitulo={nivelTitulo}
      como="article"
      densidade="nenhuma"
      className="grid h-full grid-cols-[5rem_minmax(0,1fr)] content-start gap-x-3 p-3 sm:grid-cols-[6rem_minmax(0,1fr)] sm:p-4"
      classeDoTitulo="self-end break-words"
      midia={
        <div className="row-span-2 self-start overflow-hidden rounded-md">
          <ImagemComFallback
            src={item.imagem?.url}
            alt=""
            proporcao="1/1"
            tipo="receita"
            icone={<IconeDoPrato nome={item.nome} tamanho={32} />}
            classeDoFundo={tomDaFoto(item.slug)}
          />
        </div>
      }
    >
      <div className="min-w-0 space-y-0.5 self-start text-xs minimalista:hidden">
        <p className="break-words text-apagado">{origemDa(item)}</p>
        <p className="text-texto">{item.usa_texto}</p>
      </div>
      <PerguntaDaVez item={item} />
    </CardLink>
  );
}
