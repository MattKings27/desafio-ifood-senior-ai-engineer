/**
 * O custo de uma porção, linha a linha, com a conta de cada ingrediente. As
 * linhas somam o total mostrado (a API arredonda cada uma para isso), e a
 * barra de cada linha é a parte dela no custo, que também vem pronta.
 */

import { Barra } from "@/componentes/compartilhados/Barra";
import { Card } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import { ListaExpansivel } from "@/componentes/compartilhados/ListaExpansivel";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { CMV } from "@/lib/api/preco";
import { porcentagem } from "@/lib/formato";

export function CustoDaPorcao({ custo }: { custo: CMV }) {
  return (
    <Card aria-labelledby="titulo-do-custo">
      <TituloSecao
        id="titulo-do-custo"
        titulo={`Custo de uma porção de ${custo.prato}`}
        apoio={
          custo.rendimento_original > 1
            ? `A receita rende ${custo.rendimento_original} porções; os valores já são de uma só.`
            : undefined
        }
        acao={custo.e_faixa ? <Chip tom="atencao">entre dois valores</Chip> : undefined}
      />
      <ListaExpansivel
        itens={custo.linhas}
        visiveis={6}
        chave={(linha) => linha.ingrediente}
        className="space-y-3"
        descricaoDoResto="ingredientes"
        renderizar={(linha) => (
          <div>
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate text-sm font-medium text-tinta">{linha.ingrediente}</span>
              <Valor dinheiro={linha.custo} tamanho="sm" />
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <Barra
                fracao={linha.fracao}
                tom={linha.fracao > 0.3 ? "atencao" : "marca"}
                rotulo={`${linha.ingrediente} no custo da porção`}
                valorTexto={porcentagem(linha.fracao)}
              />
              <span className="numero w-10 shrink-0 text-right text-xs text-apagado">{porcentagem(linha.fracao)}</span>
            </div>
            <Derivacao>{linha.derivacao}</Derivacao>
          </div>
        )}
      />
      <div className="mt-4 border-t border-borda pt-3">
        {custo.e_faixa ? (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-bold">Total</span>
              <span className="numero font-bold text-tinta">
                entre {custo.minimo.texto} e {custo.maximo.texto}
              </span>
            </div>
            <Derivacao>
              A diferença vem de medida caseira, como xícara, que muda de uma pessoa para outra. No preço eu uso{" "}
              {custo.maximo.texto}, para não faltar.
            </Derivacao>
          </>
        ) : (
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-bold">Total</span>
            <Valor dinheiro={custo.total} tamanho="lg" tom="marca" />
          </div>
        )}
      </div>
      {custo.itens_a_gosto.length > 0 ? (
        <Derivacao className="mt-2">A gosto, com custo pequeno mas contado: {custo.itens_a_gosto.join(", ")}.</Derivacao>
      ) : null}
    </Card>
  );
}
