"use client";

/**
 * Os cards da despensa na conversa: o resumo (quanto ela pagou, onde está o
 * dinheiro parado, a pendência), um ingrediente, e o orçamento das compras.
 *
 * Os dados são os das rotas (`/api/visao-geral`, `/api/despensa/itens/{id}`,
 * `/api/orcamento`), mas podem vir só com o mínimo, e o preço de um item pode
 * vir `null` (item que ela já tinha sem preço, cobertura sem o peso da
 * embalagem): cada campo é lido com cuidado, e o que falta aparece como valor
 * desconhecido, nunca como R$ 0,00.
 */

import { ArrowRight, Basket, ChatCircleDots, Wallet } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

import { Barra } from "@/componentes/compartilhados/Barra";
import { Botao } from "@/componentes/compartilhados/Botao";
import { Chip } from "@/componentes/compartilhados/Chip";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import { rascunhos } from "@/lib/conversa/perguntas";

import { useAcoesDaConversa } from "../useAcoesDaConversa";
import { dinheiro, imagem, num, obj, objetos, rotaInterna, str } from "./leitura";
import type { PropsDoCartao } from "./Moldura";
import { LinhaDoCartao, MolduraDoCartao, useDadosDoCartao } from "./Moldura";

export function LinkDoCartao({ href, children }: { href: string; children: string }) {
  return (
    <Link
      href={href}
      className="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 text-sm font-semibold text-marca hover:bg-marca/10"
    >
      {children}
      <ArrowRight size={16} weight="bold" aria-hidden="true" />
    </Link>
  );
}

/* -------------------------------------------------------------------------- */
/* despensa_resumo                                                             */
/* -------------------------------------------------------------------------- */

export function CartaoDespensaResumo({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const acoes = useAcoesDaConversa();
  const dados = obj(bruto) ?? {};
  const despensa = obj(obj(dados.kpis)?.despensa);
  const total = dinheiro(despensa?.total);
  const itensTexto = str(despensa?.texto);
  const parado = obj(dados.dinheiro_parado);
  const maiores = objetos(parado?.itens).slice(0, 3);
  const pendencia = objetos(dados.pendencias)[0] ?? null;
  const ingredienteDaPendencia = str(pendencia?.ingrediente);
  // O rascunho termina com espaço de propósito ("…tem "): ela completa com o peso.
  const doBackend = typeof pendencia?.rascunho_chat === "string" && pendencia.rascunho_chat.trim() ? pendencia.rascunho_chat : null;
  const rascunho = doBackend ?? (ingredienteDaPendencia ? rascunhos.embalagem(ingredienteDaPendencia) : null);

  return (
    <MolduraDoCartao
      sobretitulo="Sua despensa"
      icone={<Basket size={16} weight="bold" />}
      titulo="O que a senhora tem"
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={<LinkDoCartao href={rotaInterna(despensa?.rota) ?? "/despensa"}>Ver a despensa</LinkDoCartao>}
    >
      <div>
        <Valor dinheiro={total} tamanho="xl" />
        <p className="text-sm text-apagado">{itensTexto ? `pagos em ${itensTexto}` : "pagos na despensa"}</p>
      </div>
      {maiores.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold text-tinta">Onde está mais dinheiro parado</h4>
          <ul className="mt-1 divide-y divide-borda">
            {maiores.map((item, indice) => {
              const nome = str(item.nome) ?? "Ingrediente";
              const rota = rotaInterna(item.rota);
              return (
                <li key={str(item.id) ?? indice}>
                  <LinhaDoCartao
                    rotulo={
                      rota ? (
                        <Link href={rota} className="font-semibold text-tinta hover:underline">
                          {nome}
                        </Link>
                      ) : (
                        nome
                      )
                    }
                    valor={
                      <span className="flex items-baseline gap-2">
                        <Valor dinheiro={dinheiro(item.pago)} tamanho="md" />
                        {str(item.fracao_texto) ? (
                          <span className="numero text-sm text-apagado">{str(item.fracao_texto)}</span>
                        ) : null}
                      </span>
                    }
                  />
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {pendencia && str(pendencia.pergunta) ? (
        <div className="rounded-lg bg-info/5 p-3">
          <p className="text-base text-texto">{str(pendencia.pergunta)}</p>
          {str(pendencia.impacto_texto) ? (
            <p className="mt-0.5 text-sm text-apagado">{str(pendencia.impacto_texto)}</p>
          ) : null}
          {rascunho ? (
            <Botao
              variante="secundario"
              tamanho="sm"
              className="mt-2"
              icone={<ChatCircleDots size={18} weight="bold" />}
              onClick={() =>
                acoes.preencher(rascunho, {
                  tela: "conversa",
                  tipo: "pendencia",
                  ...(str(pendencia.id) ? { id: str(pendencia.id) as string } : {}),
                  ...(ingredienteDaPendencia ? { rotulo: ingredienteDaPendencia } : {}),
                })
              }
            >
              Responder
            </Botao>
          ) : null}
        </div>
      ) : null}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* ingrediente                                                                 */
/* -------------------------------------------------------------------------- */

export function CartaoIngredienteChat({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const nome = str(dados.nome) ?? "Ingrediente";
  const foto = imagem(dados.imagem);
  const unidade = str(dados.unidade_compra_rotulo) ?? str(dados.unidade);
  const rota = rotaInterna(dados.rota);
  const confianca = str(dados.confianca_rotulo);
  const usam = str(dados.receitas_que_usam_texto);

  return (
    <MolduraDoCartao
      sobretitulo="Ingrediente"
      icone={<Basket size={16} weight="bold" />}
      titulo={nome}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={rota ? <LinkDoCartao href={rota}>Ver na despensa</LinkDoCartao> : undefined}
    >
      <div className="flex gap-3">
        <div className="w-20 shrink-0 overflow-hidden rounded-lg">
          <ImagemComFallback src={foto?.url} alt="" proporcao="1/1" tipo="ingrediente" />
        </div>
        <div className="min-w-0 flex-1 text-base">
          {str(dados.estoque_texto) ? <p className="text-texto">Tem {str(dados.estoque_texto)}</p> : null}
          {str(dados.comprado_texto) ? <p className="text-sm text-apagado">Comprou {str(dados.comprado_texto)}</p> : null}
          {usam ? <p className="text-sm text-apagado">{usam}</p> : null}
        </div>
      </div>
      <div className="divide-y divide-borda">
        <LinhaDoCartao rotulo="Pagou" valor={<Valor dinheiro={dinheiro(dados.pago)} />} />
        <LinhaDoCartao
          rotulo={unidade ? `Custo por ${unidade}` : "Custo por unidade"}
          valor={<Valor dinheiro={dinheiro(dados.custo_unitario)} />}
          detalhe={str(dados.derivacao) ? <Derivacao>{str(dados.derivacao)}</Derivacao> : null}
        />
      </div>
      {confianca ? <Chip tom="neutro">{confianca}</Chip> : null}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* orcamento                                                                   */
/* -------------------------------------------------------------------------- */

export function CartaoOrcamento({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const restante = dinheiro(dados.restante);
  const inicial = dinheiro(dados.inicial);
  const fracao = num(dados.fracao_gasta) ?? num(dados.fracao_usada);
  const compras = objetos(dados.compras).slice(-3).reverse();
  const cabe = typeof dados.cabe === "boolean" ? dados.cabe : typeof dados.cabe_no_orcamento === "boolean" ? dados.cabe_no_orcamento : null;

  return (
    <MolduraDoCartao
      sobretitulo="Orçamento das compras"
      icone={<Wallet size={16} weight="bold" />}
      titulo="Quanto ainda sobra"
      selo={cabe === null ? undefined : cabe ? <Chip tom="sucesso">Cabe no orçamento</Chip> : <Chip tom="perigo">Não cabe no orçamento</Chip>}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={<LinkDoCartao href="/despensa#orcamento">Ver o orçamento</LinkDoCartao>}
    >
      <div>
        <Valor dinheiro={restante} tamanho="xl" />
        {inicial ? <p className="text-sm text-apagado">de {inicial.texto} para as compras</p> : null}
      </div>
      {fracao !== null ? (
        <Barra fracao={fracao} rotulo="Orçamento já usado" valorTexto={str(dados.texto) ?? undefined} />
      ) : null}
      {str(dados.texto) ? <p className="text-sm text-apagado">{str(dados.texto)}</p> : null}
      {compras.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold text-tinta">Últimas compras</h4>
          <ul className="mt-1 divide-y divide-borda">
            {compras.map((compra, indice) => (
              <li key={String(compra.id ?? indice)}>
                <LinhaDoCartao
                  rotulo={str(compra.descricao) ?? "Compra"}
                  valor={<Valor dinheiro={dinheiro(compra.valor)} />}
                  detalhe={
                    str(compra.quando_texto) ?? str(compra.quando) ? (
                      <span className="text-sm text-apagado">{str(compra.quando_texto) ?? str(compra.quando)}</span>
                    ) : null
                  }
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </MolduraDoCartao>
  );
}
