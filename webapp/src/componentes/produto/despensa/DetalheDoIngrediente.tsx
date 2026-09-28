"use client";

/**
 * A página de um ingrediente: a foto, a conta inteira (quanto tem, quanto
 * comprou, quanto pagou e o custo por quilo, litro ou unidade, com a derivação
 * sempre à vista e a confiança dela), as receitas que usam, as compras com os
 * R$ 80 e o histórico, com "Desfazer" na última mudança. O que a planilha não
 * diz não vira pergunta: ela corrige o valor pelo Editar.
 *
 * Ações: Editar (o nome não muda), "Acabou" (estoque zero), "Tirar da
 * despensa" (com confirmação; volta para a lista com o aviso e o "Desfazer")
 * e "Perguntar", que abre a conversa com o item como contexto.
 */

import {
  ArrowCounterClockwise,
  CookingPot,
  MagnifyingGlass,
  Package,
  PencilSimple,
  ShoppingCartSimple,
  Trash,
  TrayArrowDown,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState, useTransition } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Card, CardLink } from "@/componentes/compartilhados/Card";
import type { TomDoChip } from "@/componentes/compartilhados/Chip";
import { Chip, SeloVeredito } from "@/componentes/compartilhados/Chip";
import { DialogoDeConfirmacao } from "@/componentes/compartilhados/Dialogo";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import type { ItemDoTempo } from "@/componentes/compartilhados/ListaDoTempo";
import { ListaDoTempo } from "@/componentes/compartilhados/ListaDoTempo";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { useToast } from "@/componentes/compartilhados/Toast";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import { BotaoPerguntar } from "@/componentes/conversa/BotaoPerguntar";
import { corrigirItem, removerItem } from "@/lib/acoes/despensa";
import type { Imagem } from "@/lib/api/base";
import type {
  CategoriaParaEscolher,
  Confianca,
  DetalheDoItem,
  EventoDaDespensa,
  OrcamentoDaDespensa,
} from "@/lib/api/despensa";
import type { Veredito } from "@/lib/formato";
import { useAcao } from "@/lib/dados/useAcao";
import { novoIdCliente } from "@/lib/dados/id";

import { desfazerComAviso, useAvisoComDesfazer } from "./avisos";
import { FotoDoIngrediente } from "./FotoDoIngrediente";
import { FormularioDoItem } from "./FormularioDoItem";
import { ListaDeCompras } from "./ListaDeCompras";
import { comMaiuscula, semQuebrarNumero } from "./texto";

/** Uma receita que usa o item, venha do catálogo (a grade) ou das que ela está avaliando. */
export type ReceitaQueUsaNaTela = {
  slug: string;
  nome: string;
  imagem: Imagem;
  rota: string;
  usa_texto: string;
  /** O selo do catálogo ("Com o que a senhora tem", com o `codigo`), ou o veredito das avaliadas. */
  selo: { texto: string; codigo?: string; veredito?: Veredito };
};

const TOM_DA_CONFIANCA: Record<Confianca, TomDoChip> = {
  alta: "sucesso",
  media: "info",
  desconhecida: "atencao",
};

const CUSTO_POR: Record<string, string> = {
  kg: "Custo por quilo",
  L: "Custo por litro",
  un: "Custo por unidade",
};

const CANAL: Record<string, string> = {
  planilha: "na planilha",
  tela: "pela tela",
  conversa: "pela conversa",
};

function LinhaDaConta({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2.5">
      <dt className="text-sm text-apagado">{rotulo}</dt>
      <dd className="text-right text-base font-semibold text-tinta">{children}</dd>
    </div>
  );
}

export function DetalheDoIngrediente({
  detalhe,
  receitas,
  categorias,
  orcamento,
}: {
  detalhe: DetalheDoItem;
  receitas: readonly ReceitaQueUsaNaTela[];
  categorias: readonly CategoriaParaEscolher[];
  orcamento?: OrcamentoDaDespensa | null;
}) {
  const router = useRouter();
  const avisar = useAvisoComDesfazer();
  const [editando, setEditando] = useState(false);
  const [tirando, setTirando] = useState(false);
  const [idDeTirar] = useState(novoIdCliente);

  const acabou = useAcao(corrigirItem, { aoConcluir: (dados) => avisar(dados.texto, dados.evento) });
  const tirar = useAcao(removerItem, {
    aoConcluir: (dados) => {
      setTirando(false);
      router.push("/despensa");
      avisar(dados.texto, dados.evento);
    },
  });

  const contexto = { tela: "despensa", tipo: "ingrediente", id: detalhe.id, rotulo: detalhe.nome };
  const custoPor = CUSTO_POR[detalhe.unidade] ?? "Custo por unidade";

  return (
    <>
      <CabecalhoDaPagina
        voltar={{ href: "/despensa", rotulo: "Despensa" }}
        titulo={detalhe.nome}
        descricao={`${detalhe.categoria_rotulo} · ${comMaiuscula(detalhe.origem_rotulo)}`}
        acoes={
          <>
            <Botao variante="terciario" icone={<PencilSimple size={18} weight="bold" />} onClick={() => setEditando(true)}>
              Editar
            </Botao>
            {detalhe.estoque > 0 ? (
              <Botao
                variante="terciario"
                icone={<TrayArrowDown size={18} weight="bold" />}
                carregando={acabou.pendente}
                onClick={() => void acabou.executar(detalhe.id, { estoque: 0, id_cliente: novoIdCliente() })}
              >
                Acabou
              </Botao>
            ) : null}
            <Botao variante="terciario" icone={<Trash size={18} weight="bold" />} onClick={() => setTirando(true)}>
              Tirar da despensa
            </Botao>
            <BotaoPerguntar rascunho={detalhe.rascunho_chat} contexto={contexto} tamanho="md" />
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-12">
        <div className="overflow-hidden rounded-lg lg:col-span-5">
          <FotoDoIngrediente
            imagem={detalhe.imagem}
            categoria={detalhe.categoria}
            mostrarCredito
            prioridade
            grande
          />
        </div>
        <Card aria-labelledby="titulo-da-conta" className="lg:col-span-7">
          <h2 id="titulo-da-conta" className="text-lg font-bold text-tinta">
            A conta
          </h2>
          <dl className="mt-1 divide-y divide-borda">
            <LinhaDaConta rotulo="Tem agora">{detalhe.estoque_texto}</LinhaDaConta>
            <LinhaDaConta rotulo="Comprou">{detalhe.comprado_texto}</LinhaDaConta>
            <LinhaDaConta rotulo="Pagou">
              {detalhe.pago ? <Valor dinheiro={detalhe.pago} /> : <span className="text-atencao">A senhora ainda não disse</span>}
            </LinhaDaConta>
            <LinhaDaConta rotulo={custoPor}>
              {detalhe.custo_unitario ? (
                <Valor dinheiro={detalhe.custo_unitario} tamanho="lg" />
              ) : (
                <span className="text-atencao">Ainda não dá para saber</span>
              )}
            </LinhaDaConta>
          </dl>
          <Derivacao className="text-sm">{semQuebrarNumero(detalhe.derivacao)}</Derivacao>
          <div className="mt-3 flex flex-wrap gap-2">
            <Chip tom={TOM_DA_CONFIANCA[detalhe.confianca]}>{comMaiuscula(detalhe.confianca_rotulo)}</Chip>
            <Chip tom="neutro">{comMaiuscula(detalhe.fracao_texto)}</Chip>
            <Chip tom="neutro">{comMaiuscula(detalhe.receitas_que_usam_texto)}</Chip>
          </div>
        </Card>
      </div>

      <section aria-labelledby="titulo-das-receitas" className="mt-8">
        <h2 id="titulo-das-receitas" className="mb-3 text-lg font-bold text-tinta">
          Receitas que usam
        </h2>
        <ListaExpansivel
          itens={receitas}
          visiveis={4}
          chave={(receita) => receita.slug}
          descricaoDoResto="receitas"
          className="grid grid-cols-2 gap-3 md:grid-cols-4"
          classeDoItem="min-w-0"
          renderizar={(receita) => <CartaoDaReceita receita={receita} />}
          vazio={
            <EstadoVazio
              icone={<CookingPot size={24} weight="duotone" />}
              titulo="Nenhuma receita usa isso ainda"
              descricao={`Eu procuro receitas que aproveitam ${detalhe.nome.toLocaleLowerCase("pt-BR")}.`}
              acao={
                <BotaoLink
                  href={`/receitas?usa=${encodeURIComponent(detalhe.id)}`}
                  variante="secundario"
                  icone={<MagnifyingGlass size={18} weight="bold" />}
                >
                  Procurar receitas
                </BotaoLink>
              }
            />
          }
        />
      </section>

      {detalhe.compras.length > 0 ? (
        <section aria-labelledby="titulo-das-compras" className="mt-8">
          <h2 id="titulo-das-compras" className="flex items-center gap-2 text-lg font-bold text-tinta">
            <ShoppingCartSimple size={20} weight="bold" aria-hidden="true" />
            Compras com os complementos
          </h2>
          <Card tom="plano" className="mt-3 py-1 sm:py-1">
            <ListaDeCompras compras={detalhe.compras} />
          </Card>
        </section>
      ) : null}

      <section aria-labelledby="titulo-do-historico" className="mt-8">
        <h2 id="titulo-do-historico" className="mb-3 text-lg font-bold text-tinta">
          Histórico
        </h2>
        <Card tom="plano">
          <HistoricoDoItem historico={detalhe.historico} />
        </Card>
      </section>

      <FormularioDoItem
        pedido={editando ? { modo: "editar", item: detalhe } : null}
        aoFechar={() => setEditando(false)}
        categorias={categorias}
        orcamento={orcamento ?? null}
      />

      <DialogoDeConfirmacao
        aberto={tirando}
        titulo={`Tirar ${detalhe.nome.toLocaleLowerCase("pt-BR")} da despensa?`}
        descricao={
          detalhe.origem === "orcamento"
            ? "O que a senhora pagou volta para os complementos. Dá para desfazer logo depois."
            : "Dá para desfazer logo depois, no aviso ou no histórico."
        }
        rotuloConfirmar="Tirar da despensa"
        perigoso
        carregando={tirar.pendente}
        aoCancelar={() => setTirando(false)}
        aoConfirmar={() => void tirar.executar(detalhe.id, idDeTirar, { atualizar: false })}
      />
    </>
  );
}

function CartaoDaReceita({ receita }: { receita: ReceitaQueUsaNaTela }) {
  return (
    <CardLink
      href={receita.rota}
      titulo={receita.nome}
      densidade="nenhuma"
      className="flex h-full flex-col overflow-hidden"
      classeDoTitulo="px-3 pt-3 [overflow-wrap:anywhere]"
      midia={<ImagemComFallback src={receita.imagem?.url} alt="" tipo="receita" proporcao="4/3" />}
    >
      <div className="flex flex-1 flex-col gap-2 px-3 pt-1 pb-3">
        <p className="text-sm text-apagado">{receita.usa_texto}</p>
        <div className="mt-auto">
          {receita.selo.veredito ? (
            <SeloVeredito veredito={receita.selo.veredito} rotulo={receita.selo.texto} />
          ) : (
            <p
              className={clsx(
                "inline-block rounded-lg border px-2.5 py-1 text-xs leading-snug font-semibold",
                TOM_DO_SELO[receita.selo.codigo ?? ""] ?? TOM_DO_SELO.com_o_que_tem,
              )}
            >
              {semQuebrarNumero(receita.selo.texto)}
            </p>
          )}
        </div>
      </div>
    </CardLink>
  );
}

/** O selo do catálogo pede cor e quebra de linha: "Comprando R$ 6,00, cabe nos R$ 80,00" não cabe numa pílula. */
const TOM_DO_SELO: Record<string, string> = {
  com_o_que_tem: "border-sucesso/25 bg-sucesso/10 text-sucesso",
  comprando: "border-info/25 bg-info/10 text-info",
  falta_resposta: "border-atencao/25 bg-atencao/10 text-atencao",
};

const TOM_DO_EVENTO: Record<string, TomDoChip> = {
  planilha: "neutro",
  adicionar: "sucesso",
  corrigir: "info",
  remover: "perigo",
  restaurar: "sucesso",
};

const ICONE_DO_EVENTO: Record<string, ReactNode> = {
  planilha: <Package size={16} weight="bold" />,
  adicionar: <ShoppingCartSimple size={16} weight="bold" />,
  corrigir: <PencilSimple size={16} weight="bold" />,
  remover: <Trash size={16} weight="bold" />,
  restaurar: <ArrowCounterClockwise size={16} weight="bold" />,
};

export function HistoricoDoItem({ historico }: { historico: readonly EventoDaDespensa[] }) {
  // Do mais novo para o mais antigo: a última mudança, a que se desfaz, fica em cima.
  const itens: ItemDoTempo[] = [...historico].reverse().map((evento) => ({
    id: evento.id,
    texto: evento.texto,
    quandoTexto: evento.canal === "planilha" ? evento.quando_texto : `${evento.quando_texto}, ${CANAL[evento.canal] ?? evento.canal}`,
    tom: TOM_DO_EVENTO[evento.tipo] ?? "neutro",
    icone: ICONE_DO_EVENTO[evento.tipo],
    detalhe: evento.motivo ? `Motivo: ${evento.motivo}` : undefined,
    acao:
      evento.pode_desfazer && evento.id !== "planilha" ? (
        <BotaoDesfazer evento={evento.id} />
      ) : undefined,
  }));
  return <ListaDoTempo itens={itens} vazio={<p className="text-sm text-apagado">Nenhuma mudança ainda.</p>} />;
}

function BotaoDesfazer({ evento }: { evento: string }) {
  const toast = useToast();
  const [pendente, iniciar] = useTransition();
  return (
    <Botao
      variante="texto"
      tamanho="sm"
      className="-my-2"
      icone={<ArrowCounterClockwise size={16} weight="bold" />}
      carregando={pendente}
      onClick={() => iniciar(() => desfazerComAviso(evento, toast))}
    >
      Desfazer
    </Botao>
  );
}
