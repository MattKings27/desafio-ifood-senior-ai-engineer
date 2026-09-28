"use client";

/**
 * Os cards de preço na conversa: o custo de uma porção, os três caminhos de
 * preço, a conta de um preço escolhido, o preço preliminar e a decisão que
 * entrou no cardápio.
 *
 * Nada aqui faz conta: cada valor é o `texto` da API, com a derivação ao
 * lado, e o número (`valor`) só segue na ação de aceitar um preço. Aceitar
 * passa pela confirmação, que busca a conta de novo antes de gravar
 * (`ConfirmarPreco`). Nenhum caminho de preço é marcado como recomendado:
 * quem escolhe é ela.
 */

import { Calculator, ChatCircleDots, ListChecks, Receipt, Tag } from "@phosphor-icons/react/dist/ssr";
import { useState } from "react";

import { Barra } from "@/componentes/compartilhados/Barra";
import { Botao } from "@/componentes/compartilhados/Botao";
import { Chip } from "@/componentes/compartilhados/Chip";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import { rascunhos } from "@/lib/conversa/perguntas";
import { porcentagem } from "@/lib/formato";

import { useAcoesDaConversa } from "../useAcoesDaConversa";
import { LinkDoCartao } from "./CartoesDaDespensa";
import type { PedidoDePreco } from "./ConfirmarPreco";
import { ConfirmarPreco } from "./ConfirmarPreco";
import type { Solto } from "./leitura";
import { bool, dinheiro, lista, num, obj, objetos, parametro, str } from "./leitura";
import type { PropsDoCartao } from "./Moldura";
import { LinhaDoCartao, MolduraDoCartao, useDadosDoCartao } from "./Moldura";

function rotaDaReceitaDoCartao(cartao: PropsDoCartao["cartao"], dados: Solto): string | null {
  const slug = str(dados.slug) ?? str(parametro(cartao, "slug"));
  return slug && /^[\w-]+$/.test(slug) ? `/receitas/${slug}` : null;
}

/** "Vou cobrar este": abre a confirmação com o preço que veio da API. */
function BotaoVouCobrar({ pedido, aoPedir }: { pedido: PedidoDePreco | null; aoPedir: (pedido: PedidoDePreco) => void }) {
  const acoes = useAcoesDaConversa();
  if (!pedido) return null;
  return (
    <Botao
      variante="secundario"
      tamanho="sm"
      larguraTotal
      icone={<Tag size={18} weight="bold" />}
      aria-disabled={acoes.ocupada || undefined}
      title={acoes.motivo ?? undefined}
      onClick={() => {
        if (!acoes.ocupada) aoPedir(pedido);
      }}
    >
      Vou cobrar este
    </Botao>
  );
}

/** Um valor dentro de um quadro de preço: o rótulo em cima e o valor embaixo, que cabe em quadro estreito. */
function ValorDoQuadro({ rotulo, dinheiro: valor }: { rotulo: string; dinheiro: unknown }) {
  return (
    <div>
      <p className="text-sm text-apagado">{rotulo}</p>
      <Valor dinheiro={dinheiro(valor)} tamanho="md" />
    </div>
  );
}

function pedidoDe(prato: string | null, preco: unknown): PedidoDePreco | null {
  const valor = dinheiro(preco);
  if (!prato || !valor || !Number.isFinite(valor.valor)) return null;
  return { prato, valor: valor.valor, texto: valor.texto };
}

/* -------------------------------------------------------------------------- */
/* custo_porcao                                                                */
/* -------------------------------------------------------------------------- */

export function CartaoCustoPorcao({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const prato = str(dados.prato) ?? str(parametro(cartao, "prato")) ?? "Prato";
  const faixa = bool(dados.e_faixa) === true;
  const minimo = dinheiro(dados.minimo);
  const maximo = dinheiro(dados.maximo);
  const aGosto = lista(dados.itens_a_gosto)
    .map(str)
    .filter((item): item is string => item !== null);
  const rota = rotaDaReceitaDoCartao(cartao, dados);

  return (
    <MolduraDoCartao
      sobretitulo="Custo de uma porção"
      icone={<Calculator size={16} weight="bold" />}
      titulo={prato}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={rota ? <LinkDoCartao href={rota}>Ver a receita</LinkDoCartao> : undefined}
    >
      <div>
        <Valor dinheiro={dinheiro(dados.total)} tamanho="xl" />
        <p className="text-sm text-apagado">
          {faixa && minimo && maximo ? `de ingrediente por porção, entre ${minimo.texto} e ${maximo.texto}` : "de ingrediente por porção"}
        </p>
      </div>
      {objetos(dados.linhas).length > 0 ? (
        <ul className="divide-y divide-borda">
          {objetos(dados.linhas).map((linha, indice) => {
            const ingrediente = str(linha.ingrediente) ?? "Ingrediente";
            const fracao = num(linha.fracao);
            return (
              <li key={`${ingrediente}-${indice}`}>
                <LinhaDoCartao
                  rotulo={
                    <span>
                      {ingrediente}
                      {str(linha.quantidade) ? <span className="text-sm text-apagado">, {str(linha.quantidade)}</span> : null}
                    </span>
                  }
                  valor={<Valor dinheiro={dinheiro(linha.custo)} />}
                  detalhe={
                    <>
                      {fracao !== null ? (
                        <Barra fracao={fracao} rotulo={`${ingrediente} no custo da porção`} espessura="sm" className="mt-1" />
                      ) : null}
                      {str(linha.derivacao) ? <Derivacao>{str(linha.derivacao)}</Derivacao> : null}
                    </>
                  }
                />
              </li>
            );
          })}
        </ul>
      ) : null}
      {aGosto.length > 0 ? (
        <p className="text-sm text-apagado">Fica de fora da conta, porque vai a gosto: {aGosto.join(", ")}.</p>
      ) : null}
      {str(dados.explicacao) ? <p className="text-base text-texto">{str(dados.explicacao)}</p> : null}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* cenarios                                                                    */
/* -------------------------------------------------------------------------- */

function Sensibilidade({ sensibilidade }: { sensibilidade: Solto }) {
  const variacao = num(sensibilidade.variacao_testada);
  const custoAntes = dinheiro(sensibilidade.cmv_original);
  const custoDepois = dinheiro(sensibilidade.cmv_com_alta);
  const lucroAntes = dinheiro(sensibilidade.lucro_original);
  const lucroDepois = dinheiro(sensibilidade.lucro_com_alta);
  const aindaDa = bool(sensibilidade.ainda_lucrativo);
  if (variacao === null || !custoAntes || !custoDepois || !lucroAntes || !lucroDepois) return null;
  return (
    <p className="rounded-lg bg-secao px-3 py-2 text-sm text-texto">
      Se o ingrediente subir {porcentagem(variacao)}, a porção passa de {custoAntes.texto} para {custoDepois.texto}, e a sobra do
      caminho do meio vai de {lucroAntes.texto} para {lucroDepois.texto}.{" "}
      {aindaDa === false ? "Aí passa a dar prejuízo." : aindaDa ? "Ainda dá lucro." : null}
    </p>
  );
}

export function CartaoCenarios({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const [pedido, setPedido] = useState<PedidoDePreco | null>(null);
  const dados = obj(bruto) ?? {};
  const prato = str(dados.prato) ?? str(parametro(cartao, "prato"));
  const cenarios = objetos(dados.cenarios);
  const sensibilidade = obj(dados.sensibilidade);

  return (
    <MolduraDoCartao
      sobretitulo="Caminhos de preço"
      icone={<Tag size={16} weight="bold" />}
      titulo={prato ?? "Caminhos de preço"}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={<LinkDoCartao href="/precificar">Ver no Pôr preço</LinkDoCartao>}
    >
      <div className="divide-y divide-borda">
        <LinhaDoCartao rotulo="Custo de uma porção" valor={<Valor dinheiro={dinheiro(dados.cmv)} />} />
        <LinhaDoCartao
          rotulo="Preço mínimo, com a taxa"
          valor={<Valor dinheiro={dinheiro(dados.preco_minimo)} />}
          detalhe={str(dados.explicacao_da_taxa) ? <Derivacao>{str(dados.explicacao_da_taxa)}</Derivacao> : null}
        />
      </div>
      <ul className="grid gap-2 @xl:grid-cols-3">
        {cenarios.map((cenario, indice) => {
          const nome = str(cenario.nome) ?? `Caminho ${indice + 1}`;
          return (
            <li key={`${indice}-${nome}`} className="flex flex-col gap-2 rounded-lg border border-borda p-3">
              <div>
                <p className="font-semibold text-tinta">{nome}</p>
                {str(cenario.descricao) ? <p className="text-sm text-apagado">{str(cenario.descricao)}</p> : null}
              </div>
              <Valor dinheiro={dinheiro(cenario.preco)} tamanho="lg" />
              <div className="space-y-1.5">
                <ValorDoQuadro rotulo="Chega para a senhora" dinheiro={cenario.recebe} />
                <ValorDoQuadro rotulo="Sobra por porção" dinheiro={cenario.lucro} />
              </div>
              {str(cenario.explicacao) ? <Derivacao>{str(cenario.explicacao)}</Derivacao> : null}
              <div className="mt-auto">
                <BotaoVouCobrar pedido={pedidoDe(prato, cenario.preco)} aoPedir={setPedido} />
              </div>
            </li>
          );
        })}
      </ul>
      {sensibilidade ? <Sensibilidade sensibilidade={sensibilidade} /> : null}
      <ConfirmarPreco pedido={pedido} aoFechar={() => setPedido(null)} />
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* ponto_de_preco                                                              */
/* -------------------------------------------------------------------------- */

export function CartaoPontoDePreco({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const [pedido, setPedido] = useState<PedidoDePreco | null>(null);
  const dados = obj(bruto) ?? {};
  const prato = str(parametro(cartao, "prato")) ?? str(dados.prato);
  const prejuizo = bool(dados.da_prejuizo) === true;

  return (
    <MolduraDoCartao
      sobretitulo="A conta desse preço"
      icone={<Receipt size={16} weight="bold" />}
      titulo={prato ?? "Preço"}
      selo={prejuizo ? <Chip tom="perigo">Dá prejuízo</Chip> : undefined}
      geradoTexto={geradoTexto}
      refazer={refazer}
    >
      <Valor dinheiro={dinheiro(dados.preco)} tamanho="xl" />
      <div className="divide-y divide-borda">
        <LinhaDoCartao rotulo="Fica com a plataforma" valor={<Valor dinheiro={dinheiro(dados.taxa)} />} />
        <LinhaDoCartao rotulo="Chega para a senhora" valor={<Valor dinheiro={dinheiro(dados.recebe)} />} />
        <LinhaDoCartao rotulo="Sobra por porção" valor={<Valor dinheiro={dinheiro(dados.lucro)} tom={prejuizo ? "negativo" : undefined} />} />
      </div>
      {str(dados.explicacao) ? <Derivacao>{str(dados.explicacao)}</Derivacao> : null}
      {str(dados.aviso) ? <p className="text-sm text-perigo">{str(dados.aviso)}</p> : null}
      <BotaoVouCobrar pedido={pedidoDe(prato, dados.preco)} aoPedir={setPedido} />
      <ConfirmarPreco pedido={pedido} aoFechar={() => setPedido(null)} />
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* preco_preliminar                                                            */
/* -------------------------------------------------------------------------- */

export function CartaoPrecoPreliminar({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const dados = obj(bruto) ?? {};
  const prato = str(dados.prato) ?? str(parametro(cartao, "prato")) ?? "Prato";
  const premissas = objetos(dados.premissas);
  // O que falta ela dizer, pelo nome da premissa ou da linha que a usa.
  const faltam = lista(obj(dados.sinais)?.faltam_parametros)
    .map(str)
    .filter((nome): nome is string => nome !== null)
    .map(
      (nome) =>
        str(premissas.find((premissa) => str(premissa.nome) === nome)?.rotulo) ??
        str(objetos(dados.linhas).find((linha) => lista(linha.premissas).includes(nome))?.rotulo),
    )
    .filter((rotulo): rotulo is string => rotulo !== null);
  const custo = obj(dados.custo_producao);
  const piso = obj(dados.piso);
  const rota = rotaDaReceitaDoCartao(cartao, dados);

  return (
    <MolduraDoCartao
      sobretitulo="Estimativa sem compromisso"
      icone={<Calculator size={16} weight="bold" />}
      titulo={prato}
      selo={<Chip tom="atencao">{str(dados.rotulo) ?? "Preço preliminar"}</Chip>}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={rota ? <LinkDoCartao href={rota}>Ver a receita</LinkDoCartao> : undefined}
    >
      {str(dados.texto) ? <p className="text-base text-texto">{str(dados.texto)}</p> : null}
      <ul className="divide-y divide-borda">
        {objetos(dados.linhas).map((linha, indice) => (
          <li key={str(linha.id) ?? indice}>
            <LinhaDoCartao
              rotulo={str(linha.rotulo) ?? "Custo"}
              valor={<Valor dinheiro={dinheiro(linha.valor)} semValor="falta saber" />}
              detalhe={str(linha.derivacao) ? <Derivacao>{str(linha.derivacao)}</Derivacao> : null}
            />
          </li>
        ))}
        {custo ? (
          <li>
            <LinhaDoCartao
              rotulo={<span className="font-semibold text-tinta">Custo de produção</span>}
              valor={<Valor dinheiro={dinheiro(custo)} />}
              detalhe={str(custo.derivacao) ? <Derivacao>{str(custo.derivacao)}</Derivacao> : null}
            />
          </li>
        ) : null}
        {piso ? (
          <li>
            <LinhaDoCartao
              rotulo={<span className="font-semibold text-tinta">Preço mínimo, com a taxa</span>}
              valor={<Valor dinheiro={dinheiro(piso)} />}
              detalhe={str(piso.derivacao) ? <Derivacao>{str(piso.derivacao)}</Derivacao> : null}
            />
          </li>
        ) : null}
      </ul>
      {objetos(dados.pontos).length > 0 ? (
        <ul className="grid gap-2 @xl:grid-cols-3">
          {objetos(dados.pontos).map((ponto, indice) => (
            <li key={str(ponto.nome) ?? indice} className="rounded-lg border border-borda p-3">
              <p className="font-semibold text-tinta">{str(ponto.nome) ?? `Preço ${indice + 1}`}</p>
              <Valor dinheiro={dinheiro(ponto.preco)} tamanho="lg" />
              <div className="mt-2 space-y-1.5">
                <ValorDoQuadro rotulo="Chega para a senhora" dinheiro={ponto.recebe} />
                <ValorDoQuadro rotulo="Sobra sobre o ingrediente" dinheiro={ponto.lucro} />
                {dinheiro(ponto.sobra_real) ? (
                  <ValorDoQuadro rotulo="Sobra depois do trabalho e do gás" dinheiro={ponto.sobra_real} />
                ) : null}
              </div>
              {str(ponto.derivacao) ? <Derivacao>{str(ponto.derivacao)}</Derivacao> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {faltam.length > 0 ? (
        <p className="text-sm text-atencao">Falta a senhora me dizer: {faltam.join(", ").toLowerCase()}.</p>
      ) : null}
      {str(dados.referencias_texto) ? <p className="text-sm text-apagado">{str(dados.referencias_texto)}</p> : null}
    </MolduraDoCartao>
  );
}

/* -------------------------------------------------------------------------- */
/* decisao                                                                     */
/* -------------------------------------------------------------------------- */

export function CartaoDecisao({ cartao, historico }: PropsDoCartao) {
  const { dados: bruto, geradoTexto, refazer } = useDadosDoCartao(cartao, historico);
  const acoes = useAcoesDaConversa();
  const dados = obj(bruto) ?? {};
  const pratos = objetos(dados.pratos);
  const nomeDoPrato = str(parametro(cartao, "prato"));
  const prato = pratos.find((p) => str(p.prato) === nomeDoPrato) ?? pratos[0] ?? null;
  const nome = str(prato?.prato) ?? nomeDoPrato ?? "Cardápio";
  const decisao = objetos(dados.historico).find((item) => str(item.prato) === nome) ?? null;
  const resumo = obj(dados.resumo);

  return (
    <MolduraDoCartao
      sobretitulo="No cardápio"
      icone={<ListChecks size={16} weight="bold" />}
      titulo={nome}
      selo={str(decisao?.tipo_rotulo) ? <Chip tom="sucesso">{str(decisao?.tipo_rotulo)}</Chip> : undefined}
      geradoTexto={geradoTexto}
      refazer={refazer}
      rodape={<LinkDoCartao href="/cardapio">Ver o cardápio</LinkDoCartao>}
    >
      {str(decisao?.texto_humano) ? <p className="text-base text-texto">{str(decisao?.texto_humano)}</p> : null}
      {prato ? (
        <div className="divide-y divide-borda">
          <LinhaDoCartao rotulo="Preço" valor={<Valor dinheiro={dinheiro(prato.preco)} tamanho="lg" />} />
          <LinhaDoCartao rotulo="Sobra por porção" valor={<Valor dinheiro={dinheiro(prato.lucro_porcao)} />} />
          <LinhaDoCartao rotulo="Custo de uma porção" valor={<Valor dinheiro={dinheiro(prato.custo_porcao)} />} />
        </div>
      ) : null}
      {str(resumo?.texto) ? (
        <p className="text-sm text-apagado">
          {[str(resumo?.texto), str(resumo?.margem_media_texto)].filter(Boolean).join(". ")}.
        </p>
      ) : null}
      <Botao
        variante="secundario"
        tamanho="sm"
        icone={<ChatCircleDots size={18} weight="bold" />}
        onClick={() => acoes.preencher(rascunhos.mudarPreco(nome), { tela: "cardapio", tipo: "prato", id: nome, rotulo: nome })}
      >
        Mudar preço
      </Botao>
    </MolduraDoCartao>
  );
}
