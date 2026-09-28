"use client";

/**
 * Pôr preço num prato, na ordem em que tem que acontecer: a conferência (dá
 * pra fazer?), o custo de uma porção, os três caminhos de preço e o controle,
 * e a decisão dela.
 *
 * A tela não conhece atalho: se a conferência não libera, nenhum preço é
 * pedido. E não faz conta: os limites do controle, o custo, a taxa e o lucro
 * vêm da API. Responder uma pergunta da conferência confere de novo; a do
 * tempo no fogo e a do rendimento voltam para a receita que ela escreveu.
 * "Vou cobrar" grava a decisão, e o cardápio (e o início) se refazem com o
 * prato, com os números da API. Antes dele, o aceite pede a cozinha confirmada:
 * a pergunta, uma só, aparece em cima dos caminhos, e o "Vou cobrar" espera.
 */

import { useId, useRef, useState } from "react";

import { Card } from "@/componentes/compartilhados/Card";
import { Esqueleto } from "@/componentes/compartilhados/Esqueleto";
import { Problema } from "@/componentes/compartilhados/Problema";
import { CabecalhoDaPagina } from "@/componentes/compartilhados/Titulos";
import type { CategoriaDeErro } from "@/lib/api/base";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import type { DecisaoRegistrada } from "@/lib/api/cardapio";
import { cardapio } from "@/lib/api/cardapio";
import type { Avaliacao, CMV, PontoPreco, TabelaPrecos } from "@/lib/api/preco";
import { precoDeHoje } from "@/lib/api/preco";
import type { ReceitaGuardada } from "@/lib/api/receitas";
import { novoIdCliente } from "@/lib/dados/id";
import { useSincronizacao } from "@/lib/dados/sincronizacao";
import { textoParaEla } from "@/lib/formato";

import { CenariosDePreco } from "./CenariosDePreco";
import { ConferenciaDoPrato, IngredientesDoPrato } from "./ConferenciaDoPrato";
import { ConfirmarACozinhaNoPreco } from "./ConfirmarACozinhaNoPreco";
import { ControleDePreco } from "./ControleDePreco";
import { CustoDaPorcao } from "./CustoDaPorcao";
import { DecisaoDoPreco } from "./DecisaoDoPreco";
import { FormularioDaReceita } from "./FormularioDaReceita";
import type { Rascunho } from "./rascunho";
import { rascunhoDe, receitaDo } from "./rascunho";
import type { RespostaDaReceita } from "./RespostaDaConferencia";

type Resultado = { avaliacao: Avaliacao; custo: CMV | null; precos: TabelaPrecos | null };

type ErroDaTela = { categoria: CategoriaDeErro; mensagem: string; pergunta?: string };

function paraErro(causa: unknown): ErroDaTela {
  if (causa instanceof ErroDoMotor) {
    return { categoria: causa.categoria, mensagem: causa.message, ...(causa.pergunta ? { pergunta: causa.pergunta } : {}) };
  }
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

export function TelaDePorPreco({ inicial = null }: { inicial?: ReceitaGuardada | null }) {
  const [rascunho, setRascunho] = useState<Rascunho>(() => rascunhoDe(inicial));
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [conferindo, setConferindo] = useState(false);
  const [erro, setErro] = useState<ErroDaTela | null>(null);
  const [ponto, setPonto] = useState<PontoPreco | null>(null);
  const [decisao, setDecisao] = useState<{ registrada: DecisaoRegistrada | null; erro: string | null; ocupado: boolean }>({
    registrada: null,
    erro: null,
    ocupado: false,
  });
  const pedido = useRef(0);
  const { avisar } = useSincronizacao();
  const idDoBloqueio = `bloqueio${useId()}`;

  const conferir = async (atual: Rascunho = rascunho) => {
    const receita = receitaDo(atual);
    if (!receita) return;
    const este = ++pedido.current;
    setConferindo(true);
    setErro(null);
    setPonto(null);
    setDecisao({ registrada: null, erro: null, ocupado: false });
    try {
      const avaliacao = await precoDeHoje.avaliar(receita);
      // Só segue para o dinheiro se a conferência deixou: é a garantia do desafio
      // respeitada também pela tela.
      let custo: CMV | null = null;
      let precos: TabelaPrecos | null = null;
      if (avaliacao.pode_precificar) {
        custo = await precoDeHoje.cmv(receita);
        precos = await precoDeHoje.precos(custo.prato, custo.total.valor);
      }
      if (este === pedido.current) setResultado({ avaliacao, custo, precos });
    } catch (causa) {
      if (este === pedido.current) {
        setResultado(null);
        setErro(paraErro(causa));
      }
    } finally {
      if (este === pedido.current) setConferindo(false);
    }
  };

  const mudar = (parcial: Partial<Rascunho>) => setRascunho((antes) => ({ ...antes, ...parcial }));

  const responderNaReceita = (resposta: RespostaDaReceita) => {
    const novo = {
      ...rascunho,
      ...(resposta.tempo !== undefined ? { tempo: resposta.tempo } : {}),
      ...(resposta.rende !== undefined ? { rende: resposta.rende } : {}),
    };
    setRascunho(novo);
    void conferir(novo);
  };

  const decidir = async (escolha: "aceito" | "recusado" | "adiado", preco?: number) => {
    const prato = resultado?.precos?.prato ?? resultado?.avaliacao.prato;
    if (!prato) return;
    setDecisao({ registrada: null, erro: null, ocupado: true });
    try {
      const registrada = await cardapio.decidir({ prato, decisao: escolha, preco, id_cliente: novoIdCliente() });
      setDecisao({ registrada, erro: null, ocupado: false });
      // O prato entrou (ou saiu) do cardápio: as telas que mostram o cardápio se refazem.
      avisar(["cardapio", "receitas", "atividades", "visao-geral"]);
    } catch (causa) {
      const mensagem = causa instanceof ErroDoMotor ? (causa.pergunta ?? causa.message) : null;
      setDecisao({ registrada: null, erro: textoParaEla(mensagem, "Não consegui anotar a decisão. Tente de novo."), ocupado: false });
    }
  };

  const { avaliacao, custo, precos } = resultado ?? { avaliacao: null, custo: null, precos: null };
  // O preço aparece com a conferência liberada; o "Vou cobrar" espera também a cozinha confirmada.
  const esperaAceite = avaliacao !== null && !avaliacao.pode_aceitar;

  return (
    <div className="space-y-6">
      <CabecalhoDaPagina
        titulo="Pôr preço num prato"
        descricao="Primeiro eu confiro se a senhora consegue fazer o prato. O preço vem depois, com a conta aberta."
        className="mb-0"
      />

      <FormularioDaReceita rascunho={rascunho} aoMudar={mudar} aoConferir={() => void conferir()} conferindo={conferindo} />

      {conferindo && !avaliacao ? (
        <Card aria-hidden="true">
          <Esqueleto className="h-6 w-1/3" />
          <Esqueleto className="mt-3 h-4 w-full" />
          <Esqueleto className="mt-2 h-4 w-2/3" />
        </Card>
      ) : null}

      {erro ? (
        <Problema mensagem={erro.mensagem} categoria={erro.categoria} pergunta={erro.pergunta} aoTentarDeNovo={() => void conferir()} />
      ) : null}

      {avaliacao ? (
        <div className="space-y-4" aria-busy={conferindo || undefined}>
          <ConferenciaDoPrato
            avaliacao={avaliacao}
            aoResponder={() => void conferir()}
            aoResponderNaReceita={responderNaReceita}
          />
          <IngredientesDoPrato avaliacao={avaliacao} />
        </div>
      ) : null}

      {custo ? <CustoDaPorcao custo={custo} /> : null}

      {precos ? (
        <>
          {avaliacao && esperaAceite ? (
            <ConfirmarACozinhaNoPreco avaliacao={avaliacao} idDoMotivo={idDoBloqueio} aoMudar={() => void conferir()} />
          ) : null}
          <CenariosDePreco
            tabela={precos}
            aoEscolher={(preco) => void decidir("aceito", preco)}
            ocupado={decisao.ocupado}
            idDoBloqueio={esperaAceite ? idDoBloqueio : undefined}
          />
          <ControleDePreco key={precos.prato} tabela={precos} ponto={ponto} aoMudarPonto={setPonto} />
          <DecisaoDoPreco
            ponto={ponto}
            registrada={decisao.registrada}
            erro={decisao.erro}
            ocupado={decisao.ocupado}
            aoDecidir={(escolha, preco) => void decidir(escolha, preco)}
            idDoBloqueio={esperaAceite ? idDoBloqueio : undefined}
          />
        </>
      ) : null}
    </div>
  );
}
