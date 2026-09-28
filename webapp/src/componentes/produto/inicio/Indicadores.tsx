/**
 * Os cinco números da tela inicial, cada um um cartão inteiro clicável que leva
 * à tela dele: a despensa, os R$ 80,00 (direto no painel do orçamento), as
 * receitas, o cardápio e a cozinha. O texto e a rota vêm da API: a tela não
 * soma, não formata e não inventa destino. No modo minimalista, cada um fica
 * com o nome e o número; a frase de apoio some.
 */

import type { Icon } from "@phosphor-icons/react";
import { Basket, BookOpenText, CookingPot, ListChecks, Wallet } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

import { Barra } from "@/componentes/compartilhados/Barra";
import { CardLink } from "@/componentes/compartilhados/Card";
import type { VisaoGeral } from "@/lib/api/visao-geral";

type Indicador = {
  chave: string;
  rotulo: string;
  Icone: Icon;
  rota: string;
  destaque: ReactNode;
  apoio?: ReactNode;
  rodape?: ReactNode;
};

function Numero({ children }: { children: ReactNode }) {
  return <p className="numero font-titulo text-2xl font-bold leading-tight text-tinta">{children}</p>;
}

function Frase({ children }: { children: ReactNode }) {
  return <p className="font-titulo text-lg font-bold leading-snug text-tinta">{children}</p>;
}

export function indicadoresDe(kpis: VisaoGeral["kpis"]): Indicador[] {
  const { despensa, orcamento, receitas, cardapio, cozinha } = kpis;
  return [
    {
      chave: "despensa",
      rotulo: "Despensa",
      Icone: Basket,
      rota: despensa.rota,
      destaque: <Numero>{despensa.total.texto}</Numero>,
      apoio: `pagos em ${despensa.texto}`,
    },
    {
      chave: "orcamento",
      rotulo: "Orçamento",
      Icone: Wallet,
      rota: orcamento.rota,
      destaque: <Numero>{orcamento.restante.texto}</Numero>,
      apoio: `restam dos ${orcamento.inicial.texto}; ${orcamento.texto}`,
    },
    {
      chave: "receitas",
      rotulo: "Receitas",
      Icone: BookOpenText,
      rota: receitas.rota,
      destaque: <Frase>{receitas.texto}</Frase>,
    },
    {
      chave: "cardapio",
      rotulo: "Cardápio",
      Icone: ListChecks,
      rota: cardapio.rota,
      destaque: <Frase>{cardapio.texto}</Frase>,
    },
    {
      chave: "cozinha",
      rotulo: "Cozinha",
      Icone: CookingPot,
      rota: cozinha.rota,
      destaque: <Frase>{cozinha.texto}</Frase>,
      rodape: (
        <Barra
          fracao={cozinha.fracao_respondida}
          tom="sucesso"
          espessura="sm"
          rotulo="Cozinha respondida pela senhora"
          valorTexto={cozinha.texto}
          className="mt-3"
        />
      ),
    },
  ];
}

export function Indicadores({ kpis }: { kpis: VisaoGeral["kpis"] }) {
  return (
    <section aria-labelledby="titulo-dos-numeros">
      <h2 id="titulo-dos-numeros" className="sr-only">
        Os números de agora
      </h2>
      <ul className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-5">
        {indicadoresDe(kpis).map(({ chave, rotulo, Icone, rota, destaque, apoio, rodape }) => (
          <li key={chave} className="min-w-0 last:min-[420px]:col-span-2 last:lg:col-span-1">
            <CardLink
              href={rota}
              titulo={rotulo}
              classeDoTitulo="flex items-center gap-2 text-sm font-semibold text-apagado"
              className="flex h-full flex-col gap-1"
              midia={
                <span aria-hidden="true" className="mb-1 inline-flex size-9 items-center justify-center rounded-full bg-marca/10 text-marca">
                  <Icone size={20} weight="bold" />
                </span>
              }
            >
              {destaque}
              {apoio ? <p className="text-sm text-apagado minimalista:hidden">{apoio}</p> : null}
              {rodape}
            </CardLink>
          </li>
        ))}
      </ul>
    </section>
  );
}
