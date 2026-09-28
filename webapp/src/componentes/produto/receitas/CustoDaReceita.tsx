"use client";

/**
 * O custo de uma porção e o preço preliminar, quando a API libera.
 *
 * O custo passa pela conferência: receita que ainda não dá (ou que ela não
 * gosta de fazer) volta recusada, o porquê da API aparece no lugar, e ela pode
 * responder pela conversa. Cada linha mostra a conta que produziu o número. O
 * preço preliminar só aparece se a rota dele respondeu.
 *
 * O valor da hora e a embalagem de uma porção se mudam ali mesmo, embaixo da
 * linha que usa cada um: a tela grava pela API e pede a estimativa de novo.
 * Nenhum número é refeito aqui, e o valor gravado aparece como dela porque a
 * premissa volta da API com `origem: "dela"`.
 */

import { Calculator, CaretDown, PencilSimple, Receipt } from "@phosphor-icons/react/dist/ssr";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useId, useRef, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Campo, EntradaNumero } from "@/componentes/compartilhados/Campos";
import { Problema } from "@/componentes/compartilhados/Problema";
import { textoDoProblema } from "@/componentes/compartilhados/textosDoProblema";
import { Derivacao, Valor } from "@/componentes/compartilhados/Valor";
import type { ContextoDaConversa } from "@/componentes/conversa";
import { BotaoPerguntar } from "@/componentes/conversa";
import type { ErroDaAcao, Resultado } from "@/lib/acoes/base";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { Estimativa, LinhaDaEstimativa, Premissa } from "@/lib/api/preco";
import { preco } from "@/lib/api/preco";
import type { CustoDaPorcao } from "@/lib/api/receitas";
import { emMinusculas } from "@/lib/conversa/perguntas";
import { useAcao } from "@/lib/dados/useAcao";
import { lerNumeroBR } from "@/lib/formato";

import { comMaiuscula, semQuebrarValor } from "./textos";

export type CustoNaTela =
  | { tipo: "pronto"; custo: CustoDaPorcao }
  | { tipo: "recusado"; motivo: string }
  | { tipo: "falhou"; mensagem: string };

/** O que ela diria ao agente para destravar o custo: o rascunho, que ela mesma manda. */
function rascunhoDoCusto(nome: string): string {
  return `O que falta para eu saber o custo por porção de ${emMinusculas(nome)}?`;
}

export function CustoDaReceita({ custo, nome, contexto }: { custo: CustoNaTela; nome: string; contexto: ContextoDaConversa }) {
  if (custo.tipo === "recusado") {
    return (
      <div className="space-y-3">
        <p className="flex items-start gap-2 text-sm text-texto">
          <Calculator size={20} weight="duotone" aria-hidden="true" className="mt-px shrink-0 text-apagado" />
          <span>{custo.motivo}</span>
        </p>
        <BotaoPerguntar rotulo="Responder no chat" rascunho={rascunhoDoCusto(nome)} contexto={contexto} />
      </div>
    );
  }
  if (custo.tipo === "falhou") {
    return (
      <p role="status" className="text-sm text-texto">
        {custo.mensagem}
      </p>
    );
  }
  const { total, linhas, itens_a_gosto: aGosto, e_faixa: eFaixa, minimo, maximo, rendimento_original: rendimento } = custo.custo;
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-baseline gap-x-2">
        <Valor dinheiro={total} tamanho="xl" />
        <span className="text-sm text-apagado">por porção</span>
      </p>
      {eFaixa ? (
        <p className="text-sm text-texto">
          Entre {minimo.texto} e {maximo.texto}, porque um dos pesos é estimado.
        </p>
      ) : null}
      <ul className="divide-y divide-borda">
        {linhas.map((linha) => (
          <li key={linha.ingrediente} className="py-2">
            <p className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 text-texto">
                {linha.ingrediente} <span className="numero text-apagado">({linha.quantidade})</span>
              </span>
              <Valor dinheiro={linha.custo} tamanho="sm" />
            </p>
            <Derivacao>{linha.derivacao}</Derivacao>
          </li>
        ))}
      </ul>
      {aGosto.length > 0 ? (
        <p className="text-sm text-texto-secundario">
          A gosto, com custo que quase não pesa: {aGosto.join(", ")}.
        </p>
      ) : null}
      <p className="text-xs text-apagado">A receita inteira rende {rendimento === 1 ? "1 porção" : `${rendimento} porções`}; os valores já são de uma.</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* As premissas: o que ela lê e o que ela muda                                 */
/* -------------------------------------------------------------------------- */

/** As premissas que ela muda ali mesmo, com o que o botão e o campo dizem. */
const EDITAVEIS: ReadonlyMap<string, { mudar: string; dizer: string; dica: string }> = new Map([
  [
    "valor_hora",
    { mudar: "Mudar o valor da hora", dizer: "Dizer o valor da hora", dica: "Quanto a senhora quer ganhar por uma hora de trabalho." },
  ],
  [
    "embalagem_por_porcao",
    {
      mudar: "Mudar o valor da embalagem",
      dizer: "Dizer quanto paga na embalagem",
      dica: "Quanto a senhora paga pela embalagem de uma porção.",
    },
  ],
]);

/** O que volta depois de gravar: a premissa e a estimativa refeita, ou por que a API não a refez. */
type Gravada = { premissa: Premissa; estimativa: Estimativa | null; erroDaConta: ErroDaAcao | null };

function paraErro(causa: unknown): ErroDaAcao {
  if (causa instanceof ErroDoMotor) {
    return { categoria: causa.categoria, mensagem: causa.message, ...(causa.pergunta ? { pergunta: causa.pergunta } : {}) };
  }
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

/**
 * Grava o valor dela e pede a estimativa de novo. Se a gravação passou e a
 * conta não voltou, o valor está gravado: a tela diz que a conta ficou para
 * depois, em vez de mostrar a antiga como se fosse a nova.
 */
async function mudarPremissa(slug: string, nome: string, valor: number): Promise<Resultado<Gravada>> {
  let premissa: Premissa;
  try {
    premissa = await preco.definirParametro(nome, valor);
  } catch (causa) {
    return { ok: false, erro: paraErro(causa) };
  }
  try {
    return { ok: true, dados: { premissa, estimativa: await preco.estimativa(slug), erroDaConta: null } };
  } catch (causa) {
    return { ok: true, dados: { premissa, estimativa: null, erroDaConta: paraErro(causa) } };
  }
}

/** A recusa da API como frase: maiúscula no começo e ponto no fim. */
function comoFrase(texto: string): string {
  const limpo = comMaiuscula(texto.trim());
  return /[.!?]$/.test(limpo) ? limpo : `${limpo}.`;
}

/** A premissa como ela lê: o valor e de onde ele vem (o que ela disse, a fonte, ou que ainda falta). */
function PremissaNaTela({ premissa }: { premissa: Premissa }) {
  const { rotulo, valor, fonte, fonte_url: endereco, atualizado_texto: quando } = premissa;
  const dela = premissa.origem === "dela" && valor !== null;
  return (
    <div className="min-w-0 text-sm">
      <p className="text-texto">
        {rotulo}:{" "}
        <span className="numero font-semibold text-tinta">{valor ? semQuebrarValor(valor.texto) : "a senhora ainda não disse"}</span>
        {dela ? (
          <>
            , a senhora disse
            {quando ? <span className="text-apagado"> ({quando})</span> : null}
          </>
        ) : null}
      </p>
      {!dela && fonte ? (
        <p className="text-xs text-apagado">
          {endereco ? (
            <a href={endereco} target="_blank" rel="noopener noreferrer" className="text-marca underline underline-offset-2">
              {fonte}
              <span className="sr-only"> (abre em outra aba)</span>
            </a>
          ) : (
            fonte
          )}
          {quando ? `, ${quando}` : ""}
        </p>
      ) : null}
    </div>
  );
}

/** A premissa embaixo da linha que a usa, com o botão que abre o campo para ela mudar. */
function PremissaEditavel({ premissa, slug, aoGravar }: { premissa: Premissa; slug: string; aoGravar: (gravada: Gravada) => void }) {
  const textos = EDITAVEIS.get(premissa.nome);
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const idDoBotao = useId();
  const entrada = useRef<HTMLInputElement>(null);
  const devolverFoco = useRef(false);
  const fechar = () => {
    devolverFoco.current = true;
    setEditando(false);
  };
  const { executar, pendente, erro, limparErro } = useAcao(mudarPremissa, {
    avisarErro: false,
    sucesso: ({ premissa: gravada, estimativa }) => (estimativa ? `Anotei ${gravada.valor?.texto ?? "o valor"} e refiz a conta.` : null),
    aoConcluir: (gravada) => {
      aoGravar(gravada);
      fechar();
    },
    aoFalhar: () => entrada.current?.focus(),
  });

  // Abrir leva ao campo; fechar (salvou, cancelou) devolve ao botão que abriu.
  useEffect(() => {
    if (editando) {
      entrada.current?.focus();
    } else if (devolverFoco.current) {
      devolverFoco.current = false;
      document.getElementById(idDoBotao)?.focus();
    }
  }, [editando, idDoBotao]);

  if (!textos) return null;

  const abrir = () => {
    setValor(premissa.valor?.valor ?? null);
    setAviso(null);
    limparErro();
    setEditando(true);
  };
  const cancelar = () => {
    if (pendente) return;
    limparErro();
    fechar();
  };
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (pendente) return;
    // Vale o que está escrito no campo, lido do jeito dela ("12,50"): é isso que ela vê e o que vai para a API.
    const escrito = entrada.current?.value.trim() ?? "";
    const numero = lerNumeroBR(escrito);
    if (numero === null) {
      setAviso(escrito ? "Escreva só o número, como 12,50." : "Escreva o valor em reais.");
      entrada.current?.focus();
      return;
    }
    setAviso(null);
    void executar(slug, premissa.nome, numero);
  };

  if (!editando) {
    return (
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-md bg-secao px-3 py-2">
        <PremissaNaTela premissa={premissa} />
        <Botao id={idDoBotao} variante="texto" tamanho="sm" icone={<PencilSimple size={18} weight="bold" />} onClick={abrir}>
          {premissa.valor ? textos.mudar : textos.dizer}
        </Botao>
      </div>
    );
  }

  const recusa = aviso ?? (erro?.categoria === "uso" ? comoFrase(textoDoProblema("uso", erro.mensagem, erro.pergunta)) : null);
  return (
    <form onSubmit={enviar} noValidate className="mt-2 space-y-3 rounded-md bg-secao p-3">
      <Campo rotulo={premissa.rotulo} dica={textos.dica} erro={recusa ? <span role="alert">{recusa}</span> : undefined}>
        <EntradaNumero
          ref={entrada}
          valor={valor}
          aoMudar={(novo) => {
            setValor(novo);
            setAviso(null);
            limparErro();
          }}
          onKeyDown={(evento) => {
            if (evento.key === "Escape") cancelar();
          }}
          prefixo="R$"
          casas={2}
        />
      </Campo>
      <div className="flex flex-wrap gap-2">
        <Botao type="submit" tamanho="sm" carregando={pendente} rotuloCarregando="Salvando…">
          Salvar
        </Botao>
        <Botao variante="terciario" tamanho="sm" onClick={cancelar}>
          Cancelar
        </Botao>
      </div>
      {erro && erro.categoria !== "uso" ? (
        <Problema categoria={erro.categoria} mensagem={erro.mensagem} pergunta={erro.pergunta} anunciar="alert" />
      ) : null}
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* O preço preliminar                                                          */
/* -------------------------------------------------------------------------- */

export function PrecoPreliminar({ estimativa: doServidor }: { estimativa: Estimativa }) {
  const router = useRouter();
  // A estimativa na tela: a do servidor, até ela mudar uma premissa aqui (aí
  // vale a que a API refez). Quando a página é refeita, vale a que chegou.
  const [estimativa, setEstimativa] = useState(doServidor);
  const [recebida, setRecebida] = useState(doServidor);
  // Gravou, mas a API não devolveu a conta nova: os números na tela são os de antes, e a tela diz por quê.
  const [contaAtrasada, setContaAtrasada] = useState<ErroDaAcao | null>(null);
  if (doServidor !== recebida) {
    setRecebida(doServidor);
    setEstimativa(doServidor);
    setContaAtrasada(null);
  }

  const refazer = async () => {
    try {
      setEstimativa(await preco.estimativa(estimativa.slug));
      setContaAtrasada(null);
    } catch (causa) {
      setContaAtrasada(paraErro(causa));
    }
  };
  const aoGravar = ({ estimativa: nova, erroDaConta }: Gravada) => {
    if (nova) setEstimativa(nova);
    setContaAtrasada(erroDaConta);
    // O resto da página e a cópia que o navegador guarda acompanham: voltar
    // para esta receita mostra a conta nova, não a de antes.
    router.refresh();
  };

  const premissas = new Map(estimativa.premissas.map((premissa) => [premissa.nome, premissa]));
  const naLinha = new Set<string>();
  /** As premissas que ela muda embaixo da linha, cada uma numa linha só. */
  const editaveisDa = (linha: LinhaDaEstimativa): Premissa[] =>
    linha.premissas.flatMap((nome) => {
      const premissa = premissas.get(nome);
      if (!premissa?.editavel || !EDITAVEIS.has(nome) || naLinha.has(nome)) return [];
      naLinha.add(nome);
      return [premissa];
    });
  const linhas = estimativa.linhas.map((linha) => ({ linha, editaveis: editaveisDa(linha) }));
  const outras = estimativa.premissas.filter((premissa) => !naLinha.has(premissa.nome));

  const contas = [
    ["Custo de produção", estimativa.custo_producao],
    ["O mínimo para não perder", estimativa.piso],
  ] as const;
  const faltaConfirmar = estimativa.sinais.falta_confirmar;
  return (
    <div className="space-y-4">
      {contaAtrasada ? (
        <Problema
          categoria={contaAtrasada.categoria}
          mensagem={contaAtrasada.mensagem}
          pergunta={contaAtrasada.pergunta}
          titulo="Anotei, mas não consegui refazer a conta"
          aoTentarDeNovo={() => void refazer()}
          anunciar="alert"
        />
      ) : null}
      <p className="text-sm text-texto">{estimativa.texto}</p>
      <ul className="divide-y divide-borda">
        {linhas.map(({ linha, editaveis }) => (
          <li key={linha.id} className="py-2">
            <p className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 text-texto">{linha.rotulo}</span>
              {linha.valor ? (
                <span className="numero font-semibold text-tinta">{linha.valor.texto}</span>
              ) : (
                <span className="text-sm font-semibold text-atencao">falta saber</span>
              )}
            </p>
            <Derivacao>{linha.derivacao}</Derivacao>
            {editaveis.map((premissa) => (
              <PremissaEditavel key={premissa.nome} premissa={premissa} slug={estimativa.slug} aoGravar={aoGravar} />
            ))}
          </li>
        ))}
      </ul>
      <dl className="space-y-2">
        {contas.map(([rotulo, conta]) =>
          conta ? (
            <div key={rotulo} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 text-sm">
              <dt className="font-semibold text-texto">{rotulo}</dt>
              <dd className="numero font-bold text-tinta">{conta.texto}</dd>
              <dd className="col-span-2">
                <Derivacao>{conta.derivacao}</Derivacao>
              </dd>
            </div>
          ) : null,
        )}
      </dl>
      {estimativa.pontos.length > 0 ? (
        <ul className="grid gap-2">
          {estimativa.pontos.map((ponto) => (
            <li key={ponto.nome} className="rounded-md border border-borda p-3">
              <p className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold text-tinta">{ponto.nome}</span>
                <span className="numero text-base font-bold text-tinta">{ponto.preco.texto}</span>
              </p>
              <p className="text-xs text-texto-secundario">{ponto.descricao}</p>
              <Derivacao>{ponto.derivacao}</Derivacao>
            </li>
          ))}
        </ul>
      ) : null}
      {faltaConfirmar.length > 0 ? (
        <div className="text-sm text-texto">
          <p className="font-semibold text-tinta">Ainda falta confirmar</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {faltaConfirmar.map((frase) => (
              <li key={frase}>{frase}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {outras.length > 0 ? (
        <details className="group">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-sm text-sm font-semibold text-marca [&::-webkit-details-marker]:hidden">
            De onde vêm os números
            <CaretDown size={14} weight="bold" aria-hidden="true" className="transition-transform duration-padrao group-open:rotate-180" />
          </summary>
          <ul className="space-y-2">
            {outras.map((premissa) => (
              <li key={premissa.nome}>
                <PremissaNaTela premissa={premissa} />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <p className="flex items-start gap-2 text-xs text-apagado">
        <Receipt size={16} weight="duotone" aria-hidden="true" className="mt-px shrink-0" />
        {estimativa.referencias_texto}
      </p>
    </div>
  );
}
