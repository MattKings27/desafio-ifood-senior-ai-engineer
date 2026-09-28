"use client";

/**
 * Preferências: a engrenagem no canto direito do cabeçalho, em toda largura.
 *
 * Abre uma folha com o que é dela decidir:
 * - **Aparência**: tema (Claro, Escuro, Automático), tamanho do texto,
 *   movimento e o modo minimalista. Fica guardado neste aparelho e vale antes
 *   da primeira pintura (o script do `<head>`), então nada pisca ao abrir a
 *   página.
 * - **Conversa**: mostrar ou não o que o agente fez em cada resposta, e
 *   apagar todas as conversas, com confirmação.
 * - **Seus dados**: baixar a despensa em texto e uma cópia de tudo, e
 *   restaurar os dados da planilha (com confirmação: tudo volta ao começo, a
 *   plataforma guarda uma cópia antes, e as receitas lidas e as fotos ficam).
 * - **Sobre o agente**: quem responde, e como cada número é conferido.
 *
 * O ícone da engrenagem não depende de nenhuma escolha: o cabeçalho sai igual
 * do servidor e do navegador, sem trocar de ícone depois de carregar.
 */

import {
  ArrowCounterClockwise,
  CircleHalf,
  CloudSlash,
  DownloadSimple,
  GearSix,
  Moon,
  ShieldCheck,
  Sun,
  Trash,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useEffect, useId, useState } from "react";

import { Botao, BotaoIcone } from "@/componentes/compartilhados/Botao";
import { DialogoDeConfirmacao } from "@/componentes/compartilhados/Dialogo";
import { Folha } from "@/componentes/compartilhados/Folha";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import { useToast } from "@/componentes/compartilhados/Toast";
import { useLojaOpcional, useSeletor } from "@/componentes/conversa/useLoja";
import { ErroDoMotor } from "@/lib/api/base";
import { dados } from "@/lib/api/dados";
import type { ResultadoDoDownload } from "@/lib/baixar";
import { baixarDaApi } from "@/lib/baixar";
import type { Loja } from "@/lib/conversa/loja";
import { fraseDoModelo } from "@/lib/conversa/modelo";
import { novoIdCliente } from "@/lib/dados/id";
import { useSincronizacao } from "@/lib/dados/sincronizacao";
import { textoParaEla } from "@/lib/formato";
import { MINIMALISTA, MOVIMENTO, PASSOS_DA_CONSULTORA, TAMANHO_DO_TEXTO, definirPreferenciaDe } from "@/lib/preferencias";
import type { PreferenciaDeMovimento, TamanhoDoTexto } from "@/lib/preferencias";
import type { PreferenciaDeTema } from "@/lib/tema";
import { definirPreferencia } from "@/lib/tema";
import { useMinimalista, usePreferencia, usePreferenciaDeTema } from "@/lib/usePreferencias";

/* -------------------------------------------------------------------------- */
/* Textos                                                                      */
/* -------------------------------------------------------------------------- */

const OPCOES_DE_TEMA: readonly { valor: PreferenciaDeTema; rotulo: string; icone: ReactNode }[] = [
  { valor: "claro", rotulo: "Claro", icone: <Sun size={18} weight="bold" /> },
  { valor: "escuro", rotulo: "Escuro", icone: <Moon size={18} weight="bold" /> },
  { valor: "automatico", rotulo: "Automático", icone: <CircleHalf size={18} weight="bold" /> },
];

export const EXPLICACAO_DO_TEMA: Readonly<Record<PreferenciaDeTema, string>> = {
  claro: "Fica sempre clara, não importa o horário.",
  escuro: "Fica sempre escura, não importa o horário.",
  automatico: "Segue o celular ou o computador da senhora: escurece quando ele escurecer.",
};

const OPCOES_DE_TEXTO: readonly { valor: TamanhoDoTexto; rotulo: string }[] = [
  { valor: "normal", rotulo: "Normal" },
  { valor: "grande", rotulo: "Grande" },
];

const OPCOES_DE_MOVIMENTO: readonly { valor: PreferenciaDeMovimento; rotulo: string }[] = [
  { valor: "sistema", rotulo: "Seguir o aparelho" },
  { valor: "reduzir", rotulo: "Reduzir" },
];

export const EXPLICACAO_DO_MINIMALISTA =
  "Os cards ficam sem as contas e as telas com menos texto; o detalhe de cada item continua completo.";

export const TEXTO_DO_DOWNLOAD_AUSENTE =
  "A cópia completa ainda não está pronta por aqui. Por enquanto, a senhora pode baixar a despensa em texto.";

export const TEXTO_DA_RESTAURACAO =
  "Tudo volta a ser como na planilha: a despensa e os preços, os itens que a senhora acrescentou ou tirou, as compras e os R$ 80,00, as respostas sobre a cozinha, os gostos e as notas, o cardápio, as respostas sobre as receitas e as conversas.";

export const O_QUE_FICA_NA_RESTAURACAO =
  "As receitas que eu já li continuam na grade, com as fotos. Antes de restaurar, eu guardo uma cópia de tudo.";

export const COMO_CONFERE: readonly string[] = [
  "Todo número sai da conta feita com a sua planilha, não da cabeça do agente.",
  "Enquanto o agente escreve, os valores ficam escondidos. Eles aparecem quando a conta é conferida, e um valor que nenhuma conta sustenta sai da resposta.",
  "Antes de um preço entrar no cardápio, uma segunda conta, feita por outro caminho, confere o resultado. Se as duas não baterem, o preço espera.",
];

/* -------------------------------------------------------------------------- */
/* Peças                                                                       */
/* -------------------------------------------------------------------------- */

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="border-t border-borda pt-5 first:border-t-0 first:pt-0">
      <h3 id={id} className="font-titulo text-base font-bold text-tinta">
        {titulo}
      </h3>
      <div className="mt-3 space-y-5">{children}</div>
    </section>
  );
}

function Explicacao({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-sm text-apagado">{children}</p>;
}

/** Um interruptor de verdade: `checkbox` com `role="switch"`, nome e explicação. */
function Interruptor({
  rotulo,
  descricao,
  ligado,
  aoMudar,
}: {
  rotulo: string;
  descricao: string;
  ligado: boolean;
  aoMudar: (ligado: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="group">
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={ligado}
        aria-describedby={`${id}-descricao`}
        onChange={(evento) => aoMudar(evento.target.checked)}
        className="sr-only"
      />
      <label htmlFor={id} className="flex min-h-11 cursor-pointer items-start justify-between gap-4">
        <span className="min-w-0 pt-0.5 text-sm font-semibold text-tinta">{rotulo}</span>
        <span
          aria-hidden="true"
          className={clsx(
            "relative mt-0.5 inline-flex h-7 w-12 shrink-0 items-center rounded-full border-2 transition-colors duration-rapida",
            "group-has-[:focus-visible]:outline-2 group-has-[:focus-visible]:outline-offset-2 group-has-[:focus-visible]:outline-marca",
            ligado ? "border-tinta bg-tinta" : "border-borda-campo bg-superficie",
          )}
        >
          <span
            className={clsx(
              "inline-block size-5 rounded-full shadow-cartao transition-transform duration-rapida",
              ligado ? "translate-x-5.5 bg-superficie" : "translate-x-0.5 bg-borda-campo",
            )}
          />
        </span>
      </label>
      <p id={`${id}-descricao`} className="pr-16 text-sm text-apagado">
        {descricao}
      </p>
    </div>
  );
}

type EstadoDoDownload = { estado: "parado" } | { estado: "baixando" } | ({ estado: "feito" } & ResultadoDoDownload);

function BotaoDeDownload({
  rotulo,
  caminho,
  nomePadrao,
  explicacao,
  seAusente,
}: {
  rotulo: string;
  caminho: string;
  nomePadrao: string;
  explicacao: string;
  /** O que dizer quando a rota não existe (404). */
  seAusente?: string;
}) {
  const [situacao, setSituacao] = useState<EstadoDoDownload>({ estado: "parado" });
  const baixar = async () => {
    setSituacao({ estado: "baixando" });
    setSituacao({ estado: "feito", ...(await baixarDaApi(caminho, nomePadrao)) });
  };
  const resultado = situacao.estado === "feito" ? situacao : null;
  return (
    <div>
      <Botao
        variante="terciario"
        tamanho="sm"
        icone={<DownloadSimple size={18} weight="bold" />}
        carregando={situacao.estado === "baixando"}
        rotuloCarregando="Preparando o arquivo…"
        onClick={() => void baixar()}
      >
        {rotulo}
      </Botao>
      <Explicacao>{explicacao}</Explicacao>
      <p role="status" className={clsx("text-sm", resultado ? "mt-1" : "sr-only", resultado?.ok ? "text-sucesso" : "text-perigo")}>
        {resultado
          ? resultado.ok
            ? `Pronto: ${resultado.nome} foi para os arquivos baixados.`
            : resultado.categoria === "ausente" && seAusente
              ? seAusente
              : resultado.categoria === "ausente"
                ? "Não encontrei esse arquivo agora. Tente de novo mais tarde."
                : "Não consegui baixar agora. Confira a internet e tente de novo."
          : ""}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Seções                                                                      */
/* -------------------------------------------------------------------------- */

function Aparencia() {
  const tema = usePreferenciaDeTema();
  const texto = usePreferencia(TAMANHO_DO_TEXTO);
  const movimento = usePreferencia(MOVIMENTO);
  const minimalista = useMinimalista();
  return (
    <Secao titulo="Aparência">
      <div>
        <Segmentado legenda="Tema" orientacao="vertical" opcoes={OPCOES_DE_TEMA} valor={tema} aoMudar={definirPreferencia} />
        <Explicacao>{EXPLICACAO_DO_TEMA[tema]}</Explicacao>
      </div>
      <div>
        <Segmentado
          legenda="Tamanho do texto"
          opcoes={OPCOES_DE_TEXTO}
          valor={texto}
          aoMudar={(valor) => definirPreferenciaDe(TAMANHO_DO_TEXTO, valor)}
        />
        <Explicacao>
          {texto === "grande"
            ? "Letras, botões e espaços ficam maiores em todas as telas."
            : "O tamanho de sempre. Grande deixa letras, botões e espaços maiores em todas as telas."}
        </Explicacao>
      </div>
      <div>
        <Segmentado
          legenda="Movimento"
          orientacao="vertical"
          opcoes={OPCOES_DE_MOVIMENTO}
          valor={movimento}
          aoMudar={(valor) => definirPreferenciaDe(MOVIMENTO, valor)}
        />
        <Explicacao>
          {movimento === "reduzir"
            ? "Sem animações: as trocas de tela acontecem direto."
            : "Faz o que o aparelho da senhora pede. Reduzir tira as animações."}
        </Explicacao>
      </div>
      <Interruptor
        rotulo="Modo minimalista"
        descricao={EXPLICACAO_DO_MINIMALISTA}
        ligado={minimalista}
        aoMudar={(ligado) => definirPreferenciaDe(MINIMALISTA, ligado ? "ligado" : "desligado")}
      />
      <p className="text-sm text-apagado">Estas escolhas ficam guardadas neste aparelho.</p>
    </Secao>
  );
}

function ConversaDaConsultora({ loja }: { loja: Loja }) {
  const passos = usePreferencia(PASSOS_DA_CONSULTORA);
  const lista = useSeletor(loja, (estado) => estado.lista);
  const [confirmando, setConfirmando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const { mostrar } = useToast();

  useEffect(() => {
    void loja.carregarLista();
  }, [loja]);

  const semConversas = lista.carregamento === "pronta" && lista.conversas.length === 0;
  const apagar = async () => {
    setApagando(true);
    const apagou = await loja.apagarTodas();
    setApagando(false);
    setConfirmando(false);
    if (apagou) mostrar({ texto: "Apaguei todas as conversas.", tom: "sucesso" });
  };

  return (
    <Secao titulo="Conversa">
      <Interruptor
        rotulo="Mostrar o que o agente fez em cada resposta"
        descricao="Os passos de cada resposta aparecem abertos, sem precisar tocar em Ver o que eu fiz."
        ligado={passos === "abertos"}
        aoMudar={(ligado) => definirPreferenciaDe(PASSOS_DA_CONSULTORA, ligado ? "abertos" : "recolhidos")}
      />
      <div>
        <Botao
          variante="terciario"
          tamanho="sm"
          icone={<Trash size={18} weight="bold" />}
          className="text-perigo"
          aria-disabled={semConversas || undefined}
          onClick={() => {
            if (!semConversas) setConfirmando(true);
          }}
        >
          Apagar todas as conversas
        </Botao>
        <Explicacao>
          {semConversas
            ? "Não há nenhuma conversa guardada agora."
            : "O que a senhora anotou na despensa, na cozinha e no cardápio continua lá."}
        </Explicacao>
      </div>
      <DialogoDeConfirmacao
        aberto={confirmando}
        titulo="Apagar todas as conversas?"
        descricao="As conversas somem da lista e não voltam. O que a senhora anotou na despensa, na cozinha e no cardápio continua lá."
        rotuloConfirmar="Apagar todas"
        perigoso
        carregando={apagando}
        aoConfirmar={() => void apagar()}
        aoCancelar={() => setConfirmando(false)}
      />
    </Secao>
  );
}

/** "Restaurar os dados da planilha": pede confirmação, e todas as telas se refazem. */
function RestaurarOsDados({ loja }: { loja: Loja | null }) {
  const [confirmando, setConfirmando] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [clique, setClique] = useState<string | null>(null);
  const { mostrar } = useToast();
  const { avisar } = useSincronizacao();

  const restaurar = async () => {
    // A mesma chave enquanto o diálogo está aberto: o reenvio do clique não restaura duas vezes.
    const chave = clique ?? novoIdCliente();
    setClique(chave);
    setRestaurando(true);
    try {
      const feito = await dados.restaurar(chave);
      loja?.esquecerConversas();
      avisar(feito.recursos);
      setConfirmando(false);
      setClique(null);
      mostrar({ texto: feito.texto, tom: "sucesso" });
    } catch (causa) {
      const mensagem = causa instanceof ErroDoMotor ? causa.message : null;
      mostrar({ texto: textoParaEla(mensagem, "Não consegui restaurar agora. Tente de novo."), tom: "erro" });
    } finally {
      setRestaurando(false);
    }
  };

  return (
    <div>
      <Botao
        variante="terciario"
        tamanho="sm"
        icone={<ArrowCounterClockwise size={18} weight="bold" />}
        className="text-perigo"
        onClick={() => setConfirmando(true)}
      >
        Restaurar os dados da planilha
      </Botao>
      <Explicacao>Volta tudo ao começo, como estava na planilha que a senhora entregou.</Explicacao>
      <DialogoDeConfirmacao
        aberto={confirmando}
        titulo="Restaurar os dados da planilha?"
        descricao={
          <>
            <span className="block">{TEXTO_DA_RESTAURACAO}</span>
            <span className="mt-2 block">{O_QUE_FICA_NA_RESTAURACAO}</span>
          </>
        }
        rotuloConfirmar="Restaurar"
        perigoso
        carregando={restaurando}
        aoConfirmar={() => void restaurar()}
        aoCancelar={() => {
          setConfirmando(false);
          setClique(null);
        }}
      />
    </div>
  );
}

function SeusDados({ loja }: { loja: Loja | null }) {
  return (
    <Secao titulo="Seus dados">
      <BotaoDeDownload
        rotulo="Baixar a despensa em texto"
        caminho="/despensa/planilha.txt"
        nomePadrao="despensa-da-dona-maria.txt"
        explicacao="A planilha como o agente lê, com o que a senhora mudou por aqui."
      />
      <BotaoDeDownload
        rotulo="Baixar tudo"
        caminho="/exportacao"
        nomePadrao="sabor-da-maria-dados.json"
        explicacao="Uma cópia de tudo o que está guardado: despensa, cozinha, receitas, cardápio e conversas."
        seAusente={TEXTO_DO_DOWNLOAD_AUSENTE}
      />
      <RestaurarOsDados loja={loja} />
    </Secao>
  );
}

function SobreAConsultora({ loja }: { loja: Loja | null }) {
  return (
    <Secao titulo="Sobre o agente">
      {loja ? <QuemResponde loja={loja} /> : <p className="text-base text-texto">{fraseDoModelo(null)}</p>}
      <div>
        <h4 className="flex items-center gap-2 text-sm font-semibold text-tinta">
          <ShieldCheck size={18} weight="bold" aria-hidden="true" className="text-sucesso" />
          Como cada número é conferido
        </h4>
        <ul className="mt-2 space-y-2 text-sm text-texto">
          {COMO_CONFERE.map((frase) => (
            <li key={frase} className="flex gap-2">
              <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-apagado" />
              <span>{frase}</span>
            </li>
          ))}
        </ul>
      </div>
    </Secao>
  );
}

function QuemResponde({ loja }: { loja: Loja }) {
  const disponibilidade = useSeletor(loja, (estado) => estado.disponibilidade);
  useEffect(() => {
    void loja.verificarDisponibilidade();
  }, [loja]);
  return (
    <div>
      <p className="text-base text-texto">{fraseDoModelo(disponibilidade.modelo)}</p>
      {disponibilidade.conferida && !disponibilidade.disponivel ? (
        <p className="mt-1 flex items-center gap-1.5 text-sm text-atencao">
          <CloudSlash size={16} weight="bold" aria-hidden="true" />
          O agente está fora do ar agora. As outras telas continuam funcionando.
        </p>
      ) : null}
    </div>
  );
}

export function ConteudoDasPreferencias() {
  const loja = useLojaOpcional();
  return (
    <div className="space-y-6 pb-2">
      <Aparencia />
      {loja ? <ConversaDaConsultora loja={loja} /> : null}
      <SeusDados loja={loja} />
      <SobreAConsultora loja={loja} />
    </div>
  );
}

/** A engrenagem e a folha. */
export function Preferencias({ className }: { className?: string }) {
  const [aberta, setAberta] = useState(false);
  return (
    <>
      <BotaoIcone
        rotulo="Preferências"
        aria-haspopup="dialog"
        aria-expanded={aberta}
        className={clsx("text-texto", aberta && "bg-tinta/8", className)}
        onClick={() => setAberta(true)}
      >
        <GearSix size={22} weight="bold" />
      </BotaoIcone>
      <Folha aberto={aberta} aoFechar={() => setAberta(false)} titulo="Preferências" lado="auto">
        {aberta ? <ConteudoDasPreferencias /> : null}
      </Folha>
    </>
  );
}
