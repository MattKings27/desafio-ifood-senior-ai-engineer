/**
 * Por que o preço não é só o custo, e três caminhos de preço lado a lado.
 *
 * Nenhum é marcado como recomendado: os três têm o mesmo peso na tela, e quem
 * escolhe o posicionamento do próprio negócio é ela. Cada um traz a conta
 * inteira: a taxa, o que chega para ela e o lucro.
 */

import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { useId } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Card } from "@/componentes/compartilhados/Card";
import { Chip } from "@/componentes/compartilhados/Chip";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { Cenario, TabelaPrecos } from "@/lib/api/preco";
import { porcentagem } from "@/lib/formato";

function CartaoDoCenario({
  cenario,
  aoEscolher,
  ocupado,
  idDoBloqueio,
}: {
  cenario: Cenario;
  aoEscolher: (preco: number) => void;
  ocupado: boolean;
  idDoBloqueio?: string;
}) {
  const id = useId();
  return (
    <Card como="article" aria-labelledby={`${id}-nome`} className="flex h-full flex-col">
      <h3 id={`${id}-nome`} className="font-bold text-tinta">
        {cenario.nome}
      </h3>
      <p className="mt-0.5 text-sm text-apagado">{cenario.descricao}</p>
      <p className="mt-3">
        <Valor dinheiro={cenario.preco} tamanho="xl" />
      </p>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-apagado">Taxa da plataforma (10%)</dt>
          <dd className="numero">{cenario.taxa.texto}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-apagado">Chega para a senhora</dt>
          <dd className="numero font-semibold">{cenario.recebe.texto}</dd>
        </div>
        <div className="flex justify-between gap-2 border-t border-borda pt-1.5">
          <dt className="font-semibold">Lucro por porção</dt>
          <dd>
            <Valor dinheiro={cenario.lucro} tamanho="sm" tom="positivo" />
          </dd>
        </div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        <Chip>o ingrediente é {porcentagem(cenario.food_cost)} do preço</Chip>
        <Chip>sobra {porcentagem(cenario.margem)} do preço</Chip>
      </div>
      <Derivacao className="mb-3 pt-3">{cenario.explicacao}</Derivacao>
      <Botao
        variante="secundario"
        tamanho="md"
        larguraTotal
        className="mt-auto aria-disabled:opacity-50"
        disabled={ocupado}
        aria-disabled={idDoBloqueio ? true : undefined}
        aria-describedby={idDoBloqueio}
        onClick={() => {
          if (!idDoBloqueio) aoEscolher(cenario.preco.valor);
        }}
      >
        Vou cobrar {cenario.preco.texto}
      </Botao>
    </Card>
  );
}

export function CenariosDePreco({
  tabela,
  aoEscolher,
  ocupado = false,
  idDoBloqueio,
}: {
  tabela: TabelaPrecos;
  /** Ela escolheu cobrar o preço de um dos caminhos (o número da API, sem conta). */
  aoEscolher: (preco: number) => void;
  ocupado?: boolean;
  /** Enquanto o aceite espera (a cozinha a confirmar), o id do que falta: o "Vou cobrar" fica desabilitado e diz por quê. */
  idDoBloqueio?: string;
}) {
  return (
    <div className="space-y-4">
      <Card tom="creme" aria-labelledby="titulo-da-taxa">
        <div className="flex items-start gap-3">
          <ArrowRight size={20} weight="bold" aria-hidden="true" className="mt-0.5 shrink-0 text-marca" />
          <div>
            <h2 id="titulo-da-taxa" className="font-bold text-tinta">
              Por que o preço não é só o custo mais o lucro
            </h2>
            <p className="mt-1 text-sm text-texto">{tabela.explicacao_da_taxa}</p>
          </div>
        </div>
      </Card>
      <section aria-labelledby="titulo-dos-caminhos">
        <TituloSecao
          id="titulo-dos-caminhos"
          titulo="Três caminhos de preço"
          apoio="Nenhum é recomendação: quem escolhe é a senhora."
        />
        <ul className="grid gap-4 md:grid-cols-3">
          {tabela.cenarios.map((cenario) => (
            <li key={cenario.nome} className="min-w-0">
              <CartaoDoCenario cenario={cenario} aoEscolher={aoEscolher} ocupado={ocupado} idDoBloqueio={idDoBloqueio} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
