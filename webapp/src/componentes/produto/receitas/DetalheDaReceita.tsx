/**
 * O detalhe de uma receita: a foto com o crédito e a página de onde ela veio,
 * se a cozinha dela dá conta (e por quê), o checklist de produção (tudo o que
 * precisa estar certo antes do aceite, com as respostas ali mesmo e o
 * "Confirmar a cozinha"), o que ela tem e o que falta comprar, o modo de
 * preparo com o que cada passo pede, a avaliação dela, o custo por porção e o
 * preço preliminar. "Pôr preço" leva à conversa, e só quando o checklist
 * libera o aceite.
 */

import {
  ArrowSquareOut,
  CaretLeft,
  CheckCircle,
  Clock,
  CookingPot,
  Prohibit,
  Question,
  ShoppingCartSimple,
  Users,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

import { Card } from "@/componentes/compartilhados/Card";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { BotaoPerguntar } from "@/componentes/conversa";
import type { Estimativa } from "@/lib/api/preco";
import type { CodigoDaCozinha, DetalheDaReceita as Receita } from "@/lib/api/receitas";

import { IconeDoPrato, tomDaFoto } from "./aparencia";
import { AvaliacaoDaReceita } from "./AvaliacaoDaReceita";
import { BotaoPorPreco } from "./BotaoPorPreco";
import { ChecklistDeProducaoDaReceita } from "./ChecklistDeProducao";
import type { CustoNaTela } from "./CustoDaReceita";
import { correcaoDe } from "./correcao";
import { CustoDaReceita, PrecoPreliminar } from "./CustoDaReceita";
import { IngredientesDaReceita } from "./IngredientesDaReceita";
import { PassosDaReceita } from "./PassosDaReceita";
import { CLASSES_DO_TOM, TOM_DA_COZINHA, permissaoDePreco } from "./textos";
import { ValorDeReferencia } from "./ValorDeReferencia";

const ICONE_DA_COZINHA: Readonly<Record<CodigoDaCozinha, ReactNode>> = {
  com_o_que_tem: <CheckCircle size={22} weight="fill" />,
  comprando: <ShoppingCartSimple size={22} weight="fill" />,
  falta_resposta: <Question size={22} weight="fill" />,
  nao_da: <Prohibit size={22} weight="bold" />,
};

function VereditoDaCozinha({ receita }: { receita: Receita }) {
  const { codigo, rotulo, motivo } = receita.veredito_da_cozinha;
  const tom = CLASSES_DO_TOM[TOM_DA_COZINHA[codigo]];
  return (
    <div className={clsx("rounded-lg border p-4", tom.caixa)}>
      <p className={clsx("flex items-center gap-2 text-base font-bold", tom.texto)}>
        <span aria-hidden="true" className="inline-flex shrink-0">
          {ICONE_DA_COZINHA[codigo]}
        </span>
        {rotulo}
      </p>
      <p className="mt-1 text-sm text-texto">{motivo}</p>
      {receita.avisos.length > 0 ? (
        <ul className="mt-3 space-y-2 border-t border-borda/60 pt-3">
          {receita.avisos.map((aviso) => (
            <li key={aviso.texto} className="flex items-start gap-2 text-sm text-texto">
              <WarningCircle size={18} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
              <span>{aviso.texto}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Fatos({ receita }: { receita: Receita }) {
  const ativo = receita.tempos.ativo_min;
  const fatos: [string, ReactNode, string][] = [];
  if (receita.tempo_texto) fatos.push(["tempo", <Clock key="i" size={18} weight="bold" />, `${receita.tempo_texto} no total`]);
  if (ativo !== null && ativo !== receita.tempos.total_min) {
    fatos.push(["ativo", <CookingPot key="i" size={18} weight="bold" />, `${ativo} min de fogo e trabalho`]);
  }
  if (receita.rendimento_texto) fatos.push(["rende", <Users key="i" size={18} weight="bold" />, `Rende ${receita.rendimento_texto}`]);
  if (fatos.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-texto">
      {fatos.map(([chave, icone, texto]) => (
        <li key={chave} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-flex text-apagado">
            {icone}
          </span>
          {texto}
        </li>
      ))}
    </ul>
  );
}

function Foto({ receita }: { receita: Receita }) {
  const { site, url, autor } = receita.fonte;
  return (
    <figure className="min-w-0">
      <div className="overflow-hidden rounded-lg">
        <ImagemComFallback
          src={receita.imagem?.url}
          alt=""
          proporcao="4/3"
          tipo="receita"
          prioridade
          icone={<IconeDoPrato nome={receita.nome} tamanho={72} />}
          classeDoFundo={tomDaFoto(receita.slug)}
        />
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-apagado">
        {receita.imagem?.credito ? <span>{receita.imagem.credito}</span> : null}
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="-mx-1 inline-flex min-h-11 items-center gap-1 rounded-sm px-1 text-sm font-semibold text-marca hover:underline"
          >
            Ver a receita {site ? `no ${site}` : "na página de origem"}
            <ArrowSquareOut size={16} weight="bold" aria-hidden="true" />
            <span className="sr-only"> (abre em outra aba)</span>
          </a>
        ) : null}
        {autor ? <span>Receita de {autor}</span> : null}
      </figcaption>
    </figure>
  );
}

function Secao({ id, titulo, apoio, children, className }: { id: string; titulo: string; apoio?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card como="section" aria-labelledby={id} className={className}>
      <TituloSecao id={id} titulo={titulo} apoio={apoio} />
      {children}
    </Card>
  );
}

export function DetalheDaReceita({
  receita,
  custo,
  estimativa,
}: {
  receita: Receita;
  custo: CustoNaTela;
  estimativa: Estimativa | null;
}) {
  const nosDados = { slug: receita.slug, nome: receita.nome };
  const jaPerguntados = new Set(
    receita.perguntas.filter((p) => p.tipo === "equipamento" || p.tipo === "tecnica").map((p) => p.campo),
  );
  const contexto = { tela: "receitas", tipo: "receita", id: receita.slug, rotulo: receita.nome };

  return (
    <article className="space-y-6">
      <Link
        href="/receitas"
        className="-mb-2 -ml-2 inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-sm font-semibold text-apagado hover:text-tinta"
      >
        <CaretLeft size={16} weight="bold" aria-hidden="true" />
        Receitas
      </Link>
      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <div className="lg:col-span-7">
          <Foto receita={receita} />
        </div>
        <div className="space-y-4 lg:col-span-5">
          <div>
            <p className="text-sm font-semibold text-apagado">{receita.fonte.site ?? "Receita que a senhora ditou"}</p>
            <h1 className="mt-1 font-titulo text-2xl leading-tight font-bold text-tinta sm:text-3xl">{receita.nome}</h1>
          </div>
          <Fatos receita={receita} />
          <VereditoDaCozinha receita={receita} />
          <BotaoPorPreco
            slug={receita.slug}
            nome={receita.nome}
            permissao={permissaoDePreco(receita)}
            aoLado={<BotaoPerguntar rascunho={receita.rascunho_chat} contexto={contexto} tamanho="md" />}
          />
        </div>
      </div>

      <Secao id="checklist" titulo={receita.checklist.titulo} apoio={receita.checklist.resumo}>
        <ChecklistDeProducaoDaReceita receita={nosDados} checklist={receita.checklist} />
      </Secao>

      <Secao
        id="ingredientes"
        titulo="Ingredientes"
        apoio={receita.rendimento_texto ? `Para ${receita.rendimento_texto}, contra a despensa da senhora.` : "Contra a despensa da senhora."}
      >
        {receita.rendimento?.estimado ? (
          <div className="mb-4">
            <ValorDeReferencia
              receita={nosDados}
              texto={`A receita não diz quantas porções rende: ${receita.rendimento.texto}. ${receita.rendimento.derivacao}.`}
              correcao={correcaoDe(receita.rendimento.pergunta)}
              oQue="o rendimento"
            />
          </div>
        ) : null}
        <IngredientesDaReceita receita={receita} />
      </Secao>

      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <div className="lg:col-span-7">
          <Secao id="preparo" titulo="Modo de preparo">
            <PassosDaReceita passos={receita.passos} requisitosDaReceita={receita.requisitos_da_receita} jaPerguntados={jaPerguntados} />
          </Secao>
        </div>
        <div className="space-y-6 lg:col-span-5">
          <Secao id="avaliacao" titulo="Avaliação da senhora">
            <AvaliacaoDaReceita
              slug={receita.slug}
              nome={receita.nome}
              avaliacao={receita.avaliacao}
              posicao={receita.posicao_no_ranking}
            />
          </Secao>
          <Secao id="custo" titulo="Custo por porção">
            <CustoDaReceita custo={custo} nome={receita.nome} contexto={contexto} />
          </Secao>
          {estimativa ? (
            <Secao id="preco-preliminar" titulo={estimativa.rotulo}>
              <PrecoPreliminar estimativa={estimativa} />
            </Secao>
          ) : null}
          {receita.respostas.length > 0 ? (
            <Secao id="respostas" titulo="O que a senhora já me disse">
              <ul className="space-y-2">
                {receita.respostas.map((resposta) => (
                  <li key={`${resposta.campo}-${resposta.quando_texto}`} className="text-sm text-texto">
                    {resposta.texto} <span className="text-apagado">({resposta.quando_texto})</span>
                  </li>
                ))}
              </ul>
            </Secao>
          ) : null}
        </div>
      </div>
    </article>
  );
}
