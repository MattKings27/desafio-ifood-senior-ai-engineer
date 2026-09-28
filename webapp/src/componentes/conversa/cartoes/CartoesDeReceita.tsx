"use client";

/**
 * Os cards de receita na conversa: a receita que o agente leu, se dá para
 * fazer (o que a senhora tem, o que falta e as perguntas), a comparação das
 * que dão, e a avaliação que ela deu.
 *
 * Os dados são os das rotas (`/api/receitas/{slug}`, `/api/receitas?aba=`,
 * `/api/receitas/{slug}/avaliacao`), lidos com cuidado: um campo que falta
 * some da tela, nunca vira zero. O que a tela mostra de dinheiro é sempre o
 * `texto` que veio da API.
 */

import { ArrowSquareOut, BookOpenText, ChatCircleDots, CheckCircle, Heart, ListChecks, Question, Star, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import Link from "next/link";

import { Botao } from "@/componentes/compartilhados/Botao";
import type { TomDoChip } from "@/componentes/compartilhados/Chip";
import { Chip, SeloVeredito } from "@/componentes/compartilhados/Chip";
import { Estrelas } from "@/componentes/compartilhados/Estrelas";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { OpcaoSugerida } from "@/lib/api/conversa";
import { rascunhos, textoDaOpcao } from "@/lib/conversa/perguntas";
import { acaoValida } from "@/lib/conversa/sugestoes";

import { useAcoesDaConversa } from "../useAcoesDaConversa";
import { LinkDoCartao } from "./CartoesDaDespensa";
import type { Solto } from "./leitura";
import { bool, dinheiro, imagem, num, obj, objetos, parametro, rotaInterna, str, urlExterna, veredito } from "./leitura";
import type { PropsDoCartao } from "./Moldura";
import { LinhaDoCartao, MolduraDoCartao, useDadosDoCartao } from "./Moldura";

/* -------------------------------------------------------------------------- */
/* Peças                                                                       */
/* -------------------------------------------------------------------------- */

/** O selo de uma receita na grade (`selo.codigo` → tom). */
export const TOM_DO_SELO: Readonly<Record<string, TomDoChip>> = {
  com_o_que_tem: "sucesso",
  comprando: "info",
  falta_resposta: "atencao",
  nao_da: "perigo",
};

/** A rota da receita na tela: a que veio nos dados, ou a do slug. */
function rotaDaReceita(dados: Solto, cartao: PropsDoCartao["cartao"]): string | null {
  const slug = str(dados.slug) ?? str(parametro(cartao, "slug"));
  return rotaInterna(dados.rota) ?? (slug && /^[\w-]+$/.test(slug) ? `/receitas/${slug}` : null);
}

function SeloDaReceita({ dados }: { dados: Solto }) {
  const tecnico = veredito(dados.veredito);
  if (!tecnico) return null;
  return <SeloVeredito veredito={tecnico} rotulo={str(dados.veredito_rotulo) ?? undefined} />;
}

/** Um botão de resposta: manda a mensagem (com a ação, quando tem) na hora. */
function BotaoDeResposta({ opcao }: { opcao: OpcaoSugerida }) {
  const acoes = useAcoesDaConversa();
  return (
    <Botao
      variante="secundario"
      tamanho="sm"
      aria-disabled={acoes.ocupada || undefined}
      title={acoes.motivo ?? undefined}
      onClick={() => {
        if (!acoes.ocupada) acoes.enviar(opcao.texto, opcao.acao ? { acao: opcao.acao } : undefined);
      }}
    >
      {opcao.rotulo}
    </Botao>
  );
}

/**
 * As opções de uma pergunta, na forma do card (`{rotulo, texto, acao}`) ou da
 * receita (`{rotulo, resposta}`). A pergunta do item parecido ("É o seu miolo
 * de alcatra?") é da própria receita: a ação leva o `receita_id`, e a resposta
 * fica gravada nela.
 */
export function opcoesDaPergunta(pergunta: Solto, receitaId?: string | null): OpcaoSugerida[] {
  const tipo = str(pergunta.tipo);
  const campo = str(pergunta.campo);
  const daReceita = str(pergunta.assunto) === "mesmo_ingrediente" && receitaId ? { receita_id: receitaId } : {};
  return objetos(pergunta.opcoes).flatMap((opcao): OpcaoSugerida[] => {
    const rotulo = str(opcao.rotulo);
    if (!rotulo) return [];
    const texto = textoDaOpcao({ rotulo, texto: opcao.texto });
    const acao = acaoValida(opcao.acao);
    if (acao) return [{ rotulo, texto, acao }];
    const resposta = str(opcao.resposta);
    if (resposta && resposta !== "nao_sei" && tipo && campo) {
      return [{ rotulo, texto, acao: { tipo: "responder", tipo_pergunta: tipo, campo, resposta, ...daReceita } }];
    }
    return [{ rotulo, texto }];
  });
}

/** Uma pergunta que destrava a receita: com botões, ou com "Responder" que abre a caixa. */
function PerguntaDaReceita({ pergunta, receita }: { pergunta: Solto; receita: { id: string | null; nome: string } }) {
  const acoes = useAcoesDaConversa();
  const texto = str(pergunta.texto) ?? str(pergunta.pergunta);
  if (!texto) return null;
  const opcoes = opcoesDaPergunta(pergunta, receita.id);
  return (
    <div className="rounded-lg bg-atencao/10 p-3">
      <p className="flex items-start gap-2 text-base text-texto">
        <Question size={18} weight="fill" aria-hidden="true" className="mt-1 shrink-0 text-atencao" />
        <span>{texto}</span>
      </p>
      {str(pergunta.motivo) ? <p className="mt-1 pl-6 text-sm text-apagado">{str(pergunta.motivo)}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2 pl-6">
        {opcoes.length > 0 ? (
          opcoes.map((opcao) => <BotaoDeResposta key={opcao.rotulo} opcao={opcao} />)
        ) : (
          <Botao
            variante="secundario"
            tamanho="sm"
            icone={<ChatCircleDots size={18} weight="bold" />}
            onClick={() =>
              acoes.preencher("", {
                tela: "receitas",
                tipo: "receita",
                ...(receita.id ? { id: receita.id } : {}),
                rotulo: receita.nome,
              })
            }
          >
            Responder
          </Botao>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* receita                                                                     */
/* -------------------------------------------------------------------------- */

export function CartaoReceitaChat({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const acoes = useAcoesDaConversa();
  const dados = obj(bruto) ?? {};
  const nome = str(dados.nome) ?? str(parametro(cartao, "prato")) ?? "Receita";
  const slug = str(dados.slug) ?? str(parametro(cartao, "slug"));
  const foto = imagem(dados.imagem);
  const fonte = obj(dados.fonte);
  const site = str(fonte?.site) ?? str(dados.site);
  const endereco = urlExterna(fonte?.url);
  const rota = rotaDaReceita(dados, cartao);
  const pontuacao = str(obj(obj(dados.avaliacao)?.pontuacao)?.texto) ?? str(obj(dados.pontuacao)?.texto);
  const detalhes = [str(dados.tempo_texto), str(dados.rendimento_texto)].filter((d): d is string => d !== null);

  return (
    <MolduraDoCartao
      sobretitulo={site ? `Receita de ${site}` : "Receita"}
      icone={<BookOpenText size={16} weight="bold" />}
      titulo={nome}
      selo={<SeloDaReceita dados={dados} />}
      midia={
        foto ? (
          <ImagemComFallback src={foto.url} alt="" proporcao="16/9" tipo="receita" credito={foto.credito} />
        ) : undefined
      }
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={
        <>
          {rota ? <LinkDoCartao href={rota}>Ver a receita</LinkDoCartao> : null}
          {endereco ? (
            <a
              href={endereco}
              target="_blank"
              rel="noopener noreferrer"
              className="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
            >
              {site ? `Abrir no ${site}` : "Abrir a página da receita"}
              <ArrowSquareOut size={16} weight="bold" aria-hidden="true" />
              <span className="sr-only"> (abre em outra aba)</span>
            </a>
          ) : null}
        </>
      }
    >
      {detalhes.length > 0 || pontuacao ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-apagado">
          {detalhes.map((detalhe, indice) => (
            <span key={`${indice}-${detalhe}`}>{detalhe}</span>
          ))}
          {pontuacao ? (
            <span className="inline-flex items-center gap-1">
              <Star size={14} weight="fill" aria-hidden="true" className="text-atencao" />
              nota {pontuacao}
            </span>
          ) : null}
        </p>
      ) : null}
      {str(fonte?.autor) ? <p className="text-sm text-apagado">Receita de {str(fonte?.autor)}</p> : null}
      {str(dados.resumo) ? <p className="text-base text-texto">{str(dados.resumo)}</p> : null}
      <Botao
        variante="secundario"
        tamanho="sm"
        icone={<ChatCircleDots size={18} weight="bold" />}
        aria-disabled={acoes.ocupada || undefined}
        title={acoes.motivo ?? undefined}
        onClick={() => {
          if (acoes.ocupada) return;
          acoes.enviar(rascunhos.podeFazer(nome), {
            contexto: { tela: "receitas", tipo: "receita", ...(slug ? { id: slug } : {}), rotulo: nome },
          });
        }}
      >
        Dá pra eu fazer?
      </Botao>
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* viabilidade                                                                 */
/* -------------------------------------------------------------------------- */

const SITUACOES_QUE_TEM = new Set(["tem", "tem_parte"]);

export function CartaoViabilidade({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const nome = str(dados.nome) ?? str(parametro(cartao, "prato")) ?? "Receita";
  const slug = str(dados.slug) ?? str(parametro(cartao, "slug"));
  const rota = rotaDaReceita(dados, cartao);
  const ingredientes = objetos(dados.ingredientes);
  const tem = ingredientes.filter((i) => SITUACOES_QUE_TEM.has(str(i.situacao) ?? ""));
  const falta = ingredientes.filter((i) => str(i.situacao) === "falta");
  const nomesCom = (situacao: string) =>
    ingredientes
      .filter((i) => str(i.situacao) === situacao)
      .map((i) => str(i.nome))
      .filter((nome): nome is string => nome !== null);
  const outros = [
    { rotulo: "Vai a gosto", nomes: nomesCom("a_gosto") },
    { rotulo: "Opcional", nomes: nomesCom("opcional") },
    { rotulo: "Não consegui ler", nomes: nomesCom("nao_entendi") },
    { rotulo: "Falta a senhora confirmar", nomes: nomesCom("confirmar") },
  ].filter((grupo) => grupo.nomes.length > 0);
  const comprar = obj(dados.falta_comprar);
  const cabe = bool(comprar?.cabe_no_orcamento);
  const perguntas = objetos(dados.perguntas);
  const avisos = objetos(dados.avisos).filter((aviso) => str(aviso.texto));

  return (
    <MolduraDoCartao
      sobretitulo="Dá pra fazer?"
      icone={<ListChecks size={16} weight="bold" />}
      titulo={nome}
      selo={<SeloDaReceita dados={dados} />}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={rota ? <LinkDoCartao href={rota}>Ver a receita</LinkDoCartao> : undefined}
    >
      {str(dados.resumo) ? <p className="text-base text-texto">{str(dados.resumo)}</p> : null}
      {tem.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold text-tinta">A senhora tem</h4>
          <ul className="mt-1 divide-y divide-borda">
            {tem.map((ingrediente, indice) => {
              const precisa = str(obj(ingrediente.precisa)?.texto);
              const temTexto = str(obj(ingrediente.tem)?.texto);
              const sobra = str(obj(ingrediente.sobra)?.texto);
              return (
                // Dois ingredientes da receita podem sair do mesmo item dela (a salsinha
                // e a cebolinha, do cheiro-verde): a chave leva a posição junto.
                <li key={`${indice}-${str(ingrediente.item_id) ?? ""}`} className="flex items-start gap-1.5 py-1.5">
                  <CheckCircle size={16} weight="fill" aria-hidden="true" className="mt-1 shrink-0 text-sucesso" />
                  {/* Estreito (o painel no celular), o quanto precisa desce para baixo do nome. */}
                  <div className="min-w-0 flex-1">
                    <div className="@md:flex @md:items-baseline @md:justify-between @md:gap-3">
                      <span className="block text-base text-texto">{str(ingrediente.nome) ?? "Ingrediente"}</span>
                      {precisa ? <span className="numero block text-sm text-apagado @md:text-right">{precisa}</span> : null}
                    </div>
                    {temTexto ? (
                      <p className="text-sm text-apagado">
                        tem {temTexto}
                        {sobra ? `, sobram ${sobra}` : ""}
                      </p>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {falta.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold text-tinta">Falta comprar</h4>
          <ul className="mt-1 divide-y divide-borda">
            {falta.map((ingrediente, indice) => (
              <li key={`${str(ingrediente.nome)}-${indice}`}>
                <LinhaDoCartao
                  rotulo={str(ingrediente.nome) ?? "Ingrediente"}
                  valor={<span className="numero text-sm text-texto">{str(obj(ingrediente.compra)?.texto) ?? str(obj(ingrediente.precisa)?.texto) ?? ""}</span>}
                />
              </li>
            ))}
          </ul>
          {str(comprar?.texto) ? (
            <p className={clsx("mt-1 text-sm", cabe === false ? "text-perigo" : "text-apagado")}>{str(comprar?.texto)}</p>
          ) : null}
        </div>
      ) : null}
      {outros.length > 0 ? (
        <ul className="space-y-0.5 text-sm text-apagado">
          {outros.map((grupo) => (
            <li key={grupo.rotulo}>
              <span className="font-semibold text-texto">{grupo.rotulo}:</span> {grupo.nomes.join(", ")}.
            </li>
          ))}
        </ul>
      ) : null}
      {avisos.map((aviso, indice) => (
        <p key={`${indice}-${str(aviso.texto) ?? ""}`} className="flex items-start gap-2 text-sm text-texto">
          <WarningCircle size={18} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0 text-atencao" />
          {str(aviso.texto)}
        </p>
      ))}
      {perguntas.map((pergunta, indice) => (
        <PerguntaDaReceita key={`${indice}-${str(pergunta.campo) ?? ""}`} pergunta={pergunta} receita={{ id: slug, nome }} />
      ))}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* comparacao                                                                  */
/* -------------------------------------------------------------------------- */

/** Quantas receitas o card mostra; o resto está na tela de Receitas. */
export const RECEITAS_NA_COMPARACAO = 4;

export function CartaoComparacao({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const itens = objetos(dados.itens ?? dados.receitas);
  const mostradas = itens.slice(0, RECEITAS_NA_COMPARACAO);
  const restante = dinheiro(dados.orcamento_restante);
  const descoberta = str(obj(dados.descoberta)?.texto);
  // Com receitas esperando resposta, a verdade é "ainda não confirmei", não "nada dá".
  const espera = str(obj(dados.esperando_resposta)?.texto);

  return (
    <MolduraDoCartao
      sobretitulo="Receitas que dão"
      icone={<BookOpenText size={16} weight="bold" />}
      titulo={itens.length === 1 ? "1 receita para a senhora" : `${itens.length} receitas para a senhora`}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={<LinkDoCartao href="/receitas">{itens.length > mostradas.length ? "Ver todas as receitas" : "Ver as receitas"}</LinkDoCartao>}
    >
      {mostradas.length > 0 ? (
        <ul className="space-y-2">
          {mostradas.map((item, indice) => {
            const nome = str(item.nome) ?? "Receita";
            const rota = rotaInterna(item.rota);
            const selo = obj(item.selo);
            const foto = imagem(item.imagem);
            const pontuacao = str(obj(item.pontuacao)?.texto) ?? str(obj(item.nota)?.texto);
            const tecnico = veredito(item.veredito);
            return (
              <li key={str(item.slug) ?? indice} className="flex gap-3 rounded-lg border border-borda p-2">
                <div className="w-16 shrink-0 overflow-hidden rounded-md">
                  <ImagemComFallback src={foto?.url} alt="" proporcao="1/1" tipo="receita" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-tinta">
                    {rota ? (
                      <Link href={rota} className="hover:underline">
                        {nome}
                      </Link>
                    ) : (
                      nome
                    )}
                  </p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    {str(selo?.texto) ? (
                      <Chip tom={TOM_DO_SELO[str(selo?.codigo) ?? ""] ?? "neutro"}>{str(selo?.texto)}</Chip>
                    ) : tecnico ? (
                      <SeloVeredito veredito={tecnico} rotulo={str(item.veredito_rotulo) ?? undefined} />
                    ) : null}
                    {pontuacao ? <span className="numero text-sm text-apagado">nota {pontuacao}</span> : null}
                  </div>
                  {str(item.usa_texto) ? <p className="mt-0.5 text-sm text-apagado">{str(item.usa_texto)}</p> : null}
                  {str(item.falta_texto) ? <p className="text-sm text-apagado">{str(item.falta_texto)}</p> : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : espera ? (
        <div className="space-y-1">
          <p className="text-base text-texto">Nenhuma receita confirmada ainda.</p>
          <p className="text-sm text-texto">{espera}</p>
        </div>
      ) : (
        <p className="text-base text-texto">Nenhuma receita dá para fazer agora.</p>
      )}
      {restante ? (
        <LinhaDoCartao rotulo="Sobra do orçamento" valor={<Valor dinheiro={restante} />} />
      ) : null}
      {descoberta ? <p className="text-sm text-apagado">{descoberta}</p> : null}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* avaliacao_da_receita                                                        */
/* -------------------------------------------------------------------------- */

/** As categorias de estrela, na ordem e com os nomes da tela (contratos/web/LEIA.md). */
export const CATEGORIAS_DA_AVALIACAO: readonly { id: string; rotulo: string }[] = [
  { id: "sabor", rotulo: "Sabor" },
  { id: "facilidade", rotulo: "Facilidade de preparo" },
  { id: "tempo", rotulo: "Tempo de preparo" },
  { id: "entrega", rotulo: "Aguenta a entrega" },
  { id: "apelo", rotulo: "Apelo de venda" },
];

export function CartaoAvaliacaoDaReceita({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const avaliacao = obj(dados.avaliacao) ?? {};
  const nome = str(dados.nome) ?? str(parametro(cartao, "prato")) ?? "Receita";
  const gosta = bool(avaliacao.gosta);
  const estrelas = obj(avaliacao.estrelas) ?? {};
  const pontuacao = obj(avaliacao.pontuacao);
  const posicao = num(dados.posicao_no_ranking);
  const rota = rotaDaReceita(dados, cartao);

  return (
    <MolduraDoCartao
      sobretitulo="A avaliação da senhora"
      icone={<Star size={16} weight="bold" />}
      titulo={nome}
      selo={
        gosta === null ? (
          <Chip tom="neutro">Ainda não disse se gosta</Chip>
        ) : gosta ? (
          <Chip tom="sucesso" icone={<Heart size={14} weight="fill" />}>
            Gosta de fazer
          </Chip>
        ) : (
          <Chip tom="neutro">Não quer fazer</Chip>
        )
      }
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={rota ? <LinkDoCartao href={rota}>Ver a receita</LinkDoCartao> : undefined}
    >
      {str(dados.texto) ? <p className="text-base text-texto">{str(dados.texto)}</p> : null}
      <ul className="divide-y divide-borda">
        {CATEGORIAS_DA_AVALIACAO.map(({ id, rotulo }) => {
          const nota = num(estrelas[id]);
          return (
            <li key={id}>
              <LinhaDoCartao
                rotulo={rotulo}
                valor={
                  nota === null ? (
                    <span className="text-sm text-apagado">sem nota</span>
                  ) : (
                    <Estrelas legenda={rotulo} valor={nota} somenteLeitura tamanho="sm" className="text-atencao" />
                  )
                }
              />
            </li>
          );
        })}
      </ul>
      {pontuacao && str(pontuacao.texto) ? (
        <div>
          <LinhaDoCartao
            rotulo="Pontuação"
            valor={<span className="numero text-lg font-bold text-tinta">{str(pontuacao.texto)}</span>}
            detalhe={str(pontuacao.derivacao) ? <Derivacao>{str(pontuacao.derivacao)}</Derivacao> : null}
          />
          {posicao !== null ? <p className="text-sm text-apagado">{posicao}º lugar no ranking da senhora</p> : null}
        </div>
      ) : null}
      {str(avaliacao.notas) ? (
        <p className="rounded-lg bg-secao px-3 py-2 text-sm text-texto">
          <span className="font-semibold">Anotação: </span>
          {str(avaliacao.notas)}
        </p>
      ) : null}
    </MolduraDoCartao>
  );
}
