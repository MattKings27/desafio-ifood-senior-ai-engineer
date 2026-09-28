/**
 * Os ingredientes da receita contra a despensa dela: "A senhora tem" (quanto a
 * receita precisa, quanto ela tem e quanto sobra) ao lado de "Falta comprar"
 * (quanto custa a compra, se cabe no orçamento, e a conta). Embaixo, o que vai
 * a gosto, o que a receita diz que é opcional e as linhas que a leitura não
 * entendeu.
 *
 * Nada aqui é pergunta: peso, medida, quantidade e preço vêm pré-determinados,
 * da receita e da pesquisa, e aparecem como "Estimado", com a fonte e o
 * "corrigir" discreto, que abre o campo para o valor dela. Todo número é o
 * texto que a API mandou; a conta de cada compra aparece junto.
 */

import { CheckCircle, Question, ShoppingCartSimple } from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

import { Derivacao } from "@/componentes/compartilhados/Valor";
import type { DetalheDaReceita, IngredienteDaReceita, IngredienteQueFalta } from "@/lib/api/receitas";

import { correcaoDe } from "./correcao";
import { CorrigirValor } from "./CorrigirValor";
import { ValorDeReferencia } from "./ValorDeReferencia";

type Receita = { slug: string; nome: string };

/** O que ela tem; o parecido com um item dela também, sem a pergunta "é o seu?". */
const QUE_TEM = new Set(["tem", "tem_parte", "confirmar"]);

function Coluna({
  titulo,
  icone,
  tom,
  children,
}: {
  titulo: string;
  icone: ReactNode;
  tom: "sucesso" | "info";
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-borda bg-superficie p-4">
      <h3 className="flex items-center gap-2 text-base font-bold text-tinta">
        <span aria-hidden="true" className={clsx("inline-flex", tom === "sucesso" ? "text-sucesso" : "text-info")}>
          {icone}
        </span>
        {titulo}
      </h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

/** Precisa, tem e sobra lado a lado; o que não veio da API não aparece. */
function Medidas({ ingrediente }: { ingrediente: IngredienteDaReceita }) {
  const medidas: [string, string][] = [["Precisa", ingrediente.precisa.texto]];
  if (ingrediente.tem) medidas.push(["Tem", ingrediente.tem.texto]);
  if (ingrediente.sobra) medidas.push(["Sobra", ingrediente.sobra.texto]);
  return (
    <dl className="mt-1 grid grid-cols-3 gap-x-3 gap-y-0.5 text-sm">
      {medidas.map(([rotulo, texto]) => (
        <div key={rotulo} className="min-w-0">
          <dt className="text-xs text-apagado">{rotulo}</dt>
          <dd className="numero text-texto">{texto}</dd>
        </div>
      ))}
    </dl>
  );
}

function ChipDoOrcamento({ cabe }: { cabe: boolean | null | undefined }) {
  if (cabe === undefined) return null;
  const [texto, classe] =
    cabe === null
      ? ["Ainda sem preço", "border-atencao/25 bg-atencao/10 text-atencao"]
      : cabe
        ? ["Cabe no orçamento", "border-sucesso/25 bg-sucesso/10 text-sucesso"]
        : ["Passa do orçamento", "border-perigo/25 bg-perigo/10 text-perigo"];
  return (
    <span className={clsx("inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold", classe)}>{texto}</span>
  );
}

function ItemQueFalta({
  receita,
  ingrediente,
  daCompra,
}: {
  receita: Receita;
  ingrediente: IngredienteDaReceita;
  daCompra: IngredienteQueFalta | undefined;
}) {
  const semPreco = daCompra ? !daCompra.preco_conhecido : ingrediente.compra?.cabe === null;
  const correcao = { tipo: "preco", ingrediente: ingrediente.nome } as const;
  return (
    <li className="py-3 first:pt-1 last:pb-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="font-medium text-tinta">{ingrediente.nome}</span>
        <ChipDoOrcamento cabe={ingrediente.compra ? ingrediente.compra.cabe : undefined} />
      </div>
      <p className="numero mt-0.5 text-sm text-texto">
        Precisa {ingrediente.precisa.texto}
        {ingrediente.compra ? <>. Compra: {ingrediente.compra.texto}</> : null}
      </p>
      {daCompra && daCompra.preco_conhecido ? <Derivacao>{daCompra.derivacao}</Derivacao> : null}
      {daCompra?.referencia ? (
        <ValorDeReferencia
          receita={receita}
          texto={daCompra.referencia.texto}
          fonte={daCompra.referencia.site}
          url={daCompra.referencia.url}
          precos={daCompra.referencia}
          correcao={correcao}
          oQue={`o preço de ${ingrediente.nome}`}
        />
      ) : null}
      {semPreco ? <CorrigirValor receita={receita} correcao={correcao} oQue={`o preço de ${ingrediente.nome}`} className="mt-1" /> : null}
    </li>
  );
}

export function IngredientesDaReceita({ receita }: { receita: DetalheDaReceita }) {
  const nosDados = { slug: receita.slug, nome: receita.nome };
  const tem = receita.ingredientes.filter((i) => QUE_TEM.has(i.situacao));
  const falta = receita.ingredientes.filter((i) => i.situacao === "falta" || (i.situacao === "tem_parte" && i.compra));
  const aGosto = receita.ingredientes.filter((i) => i.situacao === "a_gosto");
  const compra = receita.falta_comprar;
  const daCompra = (nome: string) => compra.itens.find((item) => item.nome === nome);

  return (
    <div className="space-y-4 @container">
      <div className="grid gap-4 @2xl:grid-cols-2">
        <Coluna titulo="A senhora tem" icone={<CheckCircle size={20} weight="fill" />} tom="sucesso">
          {tem.length === 0 ? (
            <p className="text-sm text-texto">Nenhum ingrediente desta receita está na despensa.</p>
          ) : (
            <ul className="divide-y divide-borda">
              {tem.map((ingrediente, indice) => (
                // A salsinha e a cebolinha saem do mesmo cheiro-verde dela: a posição desempata.
                <li key={`${indice}-${ingrediente.nome}-${ingrediente.item_id ?? ""}`} className="py-3 first:pt-1 last:pb-1">
                  <p className="font-medium text-tinta">{ingrediente.nome}</p>
                  <Medidas ingrediente={ingrediente} />
                  {ingrediente.medida_de_referencia ? (
                    <ValorDeReferencia
                      receita={nosDados}
                      texto={`${ingrediente.medida_de_referencia.texto}.`}
                      fonte="IBGE"
                      url={ingrediente.medida_de_referencia.url}
                      correcao={correcaoDe(ingrediente.medida_de_referencia.pergunta)}
                      oQue={`o peso de ${ingrediente.nome.toLocaleLowerCase("pt-BR")}`}
                    />
                  ) : null}
                  {ingrediente.situacao === "confirmar" ? (
                    <p className="mt-1 text-sm text-texto-secundario">Parecido com um item da despensa da senhora.</p>
                  ) : null}
                  {ingrediente.situacao === "tem_parte" ? (
                    <p className="mt-1 text-sm font-medium text-atencao">Tem só uma parte: o resto está em Falta comprar.</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Coluna>

        <Coluna titulo="Falta comprar" icone={<ShoppingCartSimple size={20} weight="fill" />} tom="info">
          {falta.length === 0 ? (
            <p className="text-sm text-texto">Nada a comprar. A senhora tem tudo o que a receita pede.</p>
          ) : (
            <>
              <ul className="divide-y divide-borda">
                {falta.map((ingrediente, indice) => (
                  <ItemQueFalta
                    key={`${indice}-${ingrediente.nome}`}
                    receita={nosDados}
                    ingrediente={ingrediente}
                    daCompra={daCompra(ingrediente.nome)}
                  />
                ))}
              </ul>
              <div className="mt-3 border-t border-borda pt-3">
                {compra.custo ? (
                  <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="text-sm text-apagado">A compra toda</span>
                    <span className="numero text-lg font-bold text-tinta">{compra.custo.texto}</span>
                  </p>
                ) : null}
                <p className={clsx("text-sm", compra.cabe_no_orcamento === false ? "text-perigo" : "text-texto-secundario")}>
                  {compra.texto.charAt(0).toLocaleUpperCase("pt-BR") + compra.texto.slice(1)}.
                </p>
              </div>
            </>
          )}
        </Coluna>
      </div>

      {aGosto.length > 0 || receita.opcionais.length > 0 ? (
        <dl className="space-y-2 rounded-lg bg-secao p-4 text-sm">
          {aGosto.length > 0 ? (
            <div>
              <dt className="font-semibold text-tinta">Vai a gosto</dt>
              <dd className="text-texto">
                {aGosto.map((i) => (i.tem ? `${i.nome} (a senhora tem ${i.tem.texto})` : i.nome)).join(", ")}.
              </dd>
            </div>
          ) : null}
          {receita.opcionais.length > 0 ? (
            <div>
              <dt className="font-semibold text-tinta">Opcional</dt>
              <dd className="text-texto">
                {receita.opcionais.map((o) => `${o.nome}: ${o.texto}`).join("; ")}. Fica fora da conta e da compra.
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {receita.linhas_nao_entendidas.length > 0 ? (
        <div className="rounded-lg border border-atencao/25 bg-atencao/10 p-4">
          <h3 className="flex items-center gap-2 text-base font-bold text-tinta">
            <Question size={20} weight="fill" aria-hidden="true" className="text-atencao" />
            Não consegui ler
          </h3>
          <ul className="mt-2 space-y-1">
            {receita.linhas_nao_entendidas.map((linha) => (
              <li key={linha.texto} className="text-sm text-texto">
                A receita diz: <q className="font-semibold text-tinta">{linha.texto}</q>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
