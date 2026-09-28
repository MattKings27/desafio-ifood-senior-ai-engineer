"use client";

/**
 * A avaliação dela: gosta de fazer, as estrelas de cada categoria, as notas e
 * a pontuação que a API calcula com isso (com a conta, em "Como calculamos").
 *
 * Cada toque salva na hora e aparece já marcado; a pontuação e a posição no
 * ranking chegam com a página refeita pela Server Action. Se a API recusar, a
 * marcação volta sozinha e o aviso diz por quê. As notas se salvam sozinhas
 * uma pausa depois da última tecla (e ao sair do campo), sem refazer a página.
 */

import { CaretDown, Medal, Star } from "@phosphor-icons/react/dist/ssr";
import { useEffect, useId, useRef, useState } from "react";

import { AreaDeTexto, Campo } from "@/componentes/compartilhados/Campos";
import { Estrelas } from "@/componentes/compartilhados/Estrelas";
import type { EstadoDoSalvamento } from "@/componentes/compartilhados/IndicadorDeSalvamento";
import { IndicadorDeSalvamento } from "@/componentes/compartilhados/IndicadorDeSalvamento";
import { Derivacao } from "@/componentes/compartilhados/Valor";
import { anotarReceita, avaliarReceita } from "@/lib/acoes/receitas";
import type { AvaliacaoDaReceita as Avaliacao, AvaliacaoEnviada, CategoriaDeEstrela } from "@/lib/api/receitas";
import { useAcaoOtimista } from "@/lib/dados/useAcao";

import { GrupoDeOpcoes } from "./GrupoDeOpcoes";

export const CATEGORIAS: readonly { id: CategoriaDeEstrela; rotulo: string }[] = [
  { id: "sabor", rotulo: "Sabor" },
  { id: "facilidade", rotulo: "Facilidade de preparo" },
  { id: "tempo", rotulo: "Tempo de preparo" },
  { id: "entrega", rotulo: "Aguenta a entrega" },
  { id: "apelo", rotulo: "Apelo de venda" },
];

/** Uma pausa depois da última tecla e a nota se salva. */
export const PAUSA_DAS_NOTAS_MS = 800;

function aplicar(atual: Avaliacao, pedido: AvaliacaoEnviada): Avaliacao {
  return {
    ...atual,
    gosta: pedido.gosta !== undefined ? pedido.gosta : atual.gosta,
    estrelas: { ...atual.estrelas, ...pedido.estrelas },
  };
}

function Notas({ slug, inicial }: { slug: string; inicial: string }) {
  const [texto, setTexto] = useState(inicial);
  const [estado, setEstado] = useState<EstadoDoSalvamento>("ocioso");
  const [quando, setQuando] = useState<string | null>(null);
  const salvo = useRef(inicial);
  const relogio = useRef<ReturnType<typeof setTimeout>>(undefined);
  const ultimo = useRef(texto);

  useEffect(() => () => clearTimeout(relogio.current), []);

  const salvar = async (valor: string) => {
    clearTimeout(relogio.current);
    if (valor === salvo.current) return;
    setEstado("salvando");
    let resultado: Awaited<ReturnType<typeof anotarReceita>>;
    try {
      resultado = await anotarReceita(slug, valor);
    } catch {
      resultado = { ok: false, erro: { categoria: "rede", mensagem: "" } };
    }
    // Ela continuou escrevendo enquanto a nota ia: vale o que está no campo.
    if (ultimo.current !== valor) return;
    if (resultado.ok) {
      salvo.current = resultado.dados.notas;
      setQuando(resultado.dados.atualizado_texto);
      setEstado("salvo");
    } else {
      setEstado("erro");
    }
  };

  return (
    <div className="space-y-1.5">
      <Campo rotulo="Notas da senhora" dica="Se salvam sozinhas enquanto a senhora escreve.">
        <AreaDeTexto
          value={texto}
          minLinhas={3}
          maxLinhas={10}
          maxLength={2000}
          placeholder="Servir com farofa? Testar com açafrão?"
          onChange={(evento) => {
            const novo = evento.target.value;
            setTexto(novo);
            ultimo.current = novo;
            clearTimeout(relogio.current);
            relogio.current = setTimeout(() => void salvar(novo), PAUSA_DAS_NOTAS_MS);
          }}
          onBlur={() => void salvar(texto)}
        />
      </Campo>
      <IndicadorDeSalvamento estado={estado} quandoTexto={quando} aoTentarDeNovo={() => void salvar(texto)} />
    </div>
  );
}

export function AvaliacaoDaReceita({
  slug,
  nome,
  avaliacao,
  posicao,
}: {
  slug: string;
  nome: string;
  avaliacao: Avaliacao;
  posicao: number | null;
}) {
  const id = useId();
  const [texto, setTexto] = useState<string | null>(null);
  const { estado, executar, erro } = useAcaoOtimista(avaliacao, aplicar, (pedido: AvaliacaoEnviada) => avaliarReceita(slug, pedido), {
    aoConcluir: (dados) => setTexto(dados.texto),
    avisarErro: false,
  });
  const gosta = estado.gosta === true ? "sim" : estado.gosta === false ? "nao" : null;
  const pontuacao = avaliacao.pontuacao;

  return (
    <div className="space-y-5">
      <div>
        <p id={`${id}-gosta`} className="mb-1.5 text-sm font-semibold text-tinta">
          Gosta de fazer?
        </p>
        <GrupoDeOpcoes
          idDoRotulo={`${id}-gosta`}
          opcoes={[
            { rotulo: "Sim", valor: "sim" },
            { rotulo: "Não", valor: "nao" },
          ]}
          escolhida={gosta}
          pendente={false}
          aoEscolher={(valor) => void executar({ gosta: valor === "sim" })}
          className="max-w-xs"
        />
      </div>

      <ul aria-label={`As estrelas de ${nome}`} className="divide-y divide-borda">
        {CATEGORIAS.map((categoria) => (
          <li key={categoria.id} className="pt-2 pb-0.5 first:pt-0">
            <span aria-hidden="true" className="block text-sm font-medium text-tinta">
              {categoria.rotulo}
            </span>
            <Estrelas
              legenda={categoria.rotulo}
              legendaVisivel={false}
              nome={`${categoria.id}${id}`}
              valor={estado.estrelas[categoria.id]}
              aoMudar={(nota) => void executar({ estrelas: { [categoria.id]: nota } })}
            />
          </li>
        ))}
      </ul>

      <div className="rounded-md bg-secao p-3">
        {pontuacao ? (
          <>
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm text-apagado">Pontuação</span>
              <span className="numero font-titulo text-3xl font-bold tracking-tight text-tinta">{pontuacao.texto}</span>
              <span className="text-sm text-apagado">de 100</span>
            </p>
            {posicao !== null ? (
              <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-tinta">
                <Medal size={18} weight="fill" aria-hidden="true" className="text-atencao" />
                {posicao}º lugar no ranking
              </p>
            ) : null}
            <details className="group mt-1">
              <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-sm text-sm font-semibold text-marca [&::-webkit-details-marker]:hidden">
                Como calculamos
                <CaretDown
                  size={14}
                  weight="bold"
                  aria-hidden="true"
                  className="transition-transform duration-padrao group-open:rotate-180"
                />
              </summary>
              <Derivacao className="mt-0 text-sm">{pontuacao.derivacao}</Derivacao>
            </details>
          </>
        ) : (
          <p className="flex items-start gap-2 text-sm text-texto">
            <Star size={18} weight="duotone" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
            Dê as estrelas que a pontuação aparece aqui, e a receita entra no ranking.
          </p>
        )}
        {erro ? (
          <p role="alert" className="mt-2 text-sm font-medium text-perigo">
            {erro.pergunta ?? erro.mensagem}
          </p>
        ) : texto ? (
          <p role="status" className="mt-2 text-sm text-texto-secundario">
            {texto}
          </p>
        ) : null}
      </div>

      <Notas slug={slug} inicial={avaliacao.notas} />
    </div>
  );
}
