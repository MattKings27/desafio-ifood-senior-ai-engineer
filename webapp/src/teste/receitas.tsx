/**
 * Apoio dos testes da tela de receitas: montar com os provedores de verdade
 * (avisos, sincronização e conversa, com a loja de teste; quem usa troca o
 * `next/navigation` por `@/teste/navegacao`), e os `Resultado` das Server
 * Actions, que nos testes são funções comuns.
 */

import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import { ProvedorDaConversa } from "@/componentes/conversa";
import { ProvedorDeSincronizacao } from "@/lib/dados/sincronizacao";
import type { ErroDaAcao, Resultado } from "@/lib/acoes/base";
import type { ItemDaGrade, ListaDeReceitas, PerguntaDaReceita } from "@/lib/api/receitas";

import { lojaDeTeste } from "./conversa";
import { contrato } from "./fixturas";

export function montar(ui: ReactElement) {
  const teste = lojaDeTeste();
  const envolver = (filho: ReactElement) => (
    <ProvedorDeToasts>
      <ProvedorDeSincronizacao>
        <ProvedorDaConversa loja={teste.loja}>{filho}</ProvedorDaConversa>
      </ProvedorDeSincronizacao>
    </ProvedorDeToasts>
  );
  const resultado = render(envolver(ui));
  return { ...resultado, loja: teste.loja, refazer: (novo: ReactElement) => resultado.rerender(envolver(novo)) };
}

export function deuCerto<T>(dados: T): Resultado<T> {
  return { ok: true, dados };
}

export function deuErrado(mensagem: string, extras: Partial<ErroDaAcao> = {}): Resultado<never> {
  return { ok: false, erro: { categoria: "uso", mensagem, ...extras } };
}

/** Uma promessa que o teste resolve quando quiser. */
export function adiado<T>() {
  let resolver!: (valor: T) => void;
  let rejeitar!: (motivo: unknown) => void;
  const promessa = new Promise<T>((r, j) => {
    resolver = r;
    rejeitar = j;
  });
  return { promessa, resolver, rejeitar };
}

export const LISTA = contrato<ListaDeReceitas>("receitas.json");
export const [ARROZ, FRANGO] = LISTA.itens as [ItemDaGrade, ItemDaGrade];

export const PERGUNTA_DO_TEMPO: PerguntaDaReceita = {
  tipo: "operacional",
  assunto: "tempo_cozimento",
  campo: "tempo_cozimento_min",
  texto: "Pelos passos não dá para saber quanto tempo a receita fica no fogo. Mais ou menos quantos minutos?",
  motivo: "a senhora tem 60 minutos por cozinhada",
  compras: [],
  opcoes: [],
  entrada: { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 },
  passos: [],
};

/** Uma pergunta da cozinha: um limite da rotina, respondido com um número. */
export const PERGUNTA_DAS_BOCAS: PerguntaDaReceita = {
  tipo: "operacional",
  assunto: "rotina",
  campo: "bocas_fogao",
  texto: "Seu fogão tem quantas bocas? Isso limita quantas panelas andam juntas.",
  motivo: "a receita usa duas panelas no fogo ao mesmo tempo",
  compras: [],
  opcoes: [{ rotulo: "Não sei", resposta: "nao_sei" }],
  entrada: { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 },
  passos: [],
};

/** Uma pergunta da cozinha: um equipamento, com as três respostas. */
export const PERGUNTA_DO_FORNO: PerguntaDaReceita = {
  tipo: "equipamento",
  assunto: "equipamento",
  campo: "forno",
  texto: "A senhora tem forno? Pode ser o do fogão mesmo, ou elétrico.",
  motivo: "a receita vai ao forno",
  compras: [],
  opcoes: [
    { rotulo: "Tenho", resposta: "sim" },
    { rotulo: "Não tenho", resposta: "nao" },
    { rotulo: "Não sei", resposta: "nao_sei" },
  ],
  entrada: null,
  passos: [3],
};

/** Perguntas que ela nunca responde: peso, preço, a linha que a leitura não entendeu e o item parecido. */
export const PERGUNTAS_QUE_NAO_SAO_DELA: readonly PerguntaDaReceita[] = [
  {
    tipo: "ingrediente",
    assunto: "medida",
    campo: "2 colheres de sopa de alcaparras",
    texto: "Não sei quanto pesa uma colher de sopa de alcaparras. Se a senhora souber, em gramas, eu calculo.",
    motivo: "sem o peso, não dá para saber quanto custa o prato",
    compras: [],
    opcoes: [],
    entrada: { tipo: "peso", unidade: "g", peso_de: { cada: "1 colher de sopa", tudo: "2 colheres de sopa" } },
    passos: [],
  },
  {
    tipo: "ingrediente",
    assunto: "preco_de_compra",
    campo: "creme de leite",
    texto: "Falta comprar: creme de leite. Quanto custa aí na sua região, e por qual quantidade?",
    motivo: "sem o preço não dá para saber se cabe no orçamento",
    compras: [{ ingrediente: "creme de leite", quantidade_texto: "1 caixa" }],
    opcoes: [],
    entrada: { tipo: "texto" },
    passos: [],
  },
  {
    tipo: "ingrediente",
    assunto: "linha_nao_lida",
    campo: "sal",
    texto: "Não entendi quanto vai de sal nessa receita, a senhora sabe?",
    motivo: "sem saber quanto vai, não dá para fechar o custo",
    compras: [],
    opcoes: [],
    entrada: { tipo: "texto" },
    passos: [],
  },
  {
    tipo: "ingrediente",
    assunto: "mesmo_ingrediente",
    campo: "500 g de alcatra",
    texto: "A receita pede alcatra. É o seu miolo de alcatra?",
    motivo: "a despensa tem um item parecido",
    compras: [],
    opcoes: [
      { rotulo: "É, sim", resposta: "sim" },
      { rotulo: "Não é", resposta: "nao" },
    ],
    entrada: null,
    passos: [],
  },
];

/** O que nenhuma tela escreve: a pergunta de peso, de preço, da linha e do item parecido. */
export const TEXTOS_QUE_NUNCA_APARECEM = [/quanto pesa/i, /Quanto custa/, /É o seu/, /Não entendi quanto vai/];

export function item(extras: Partial<ItemDaGrade> = {}): ItemDaGrade {
  return { ...ARROZ, ...extras };
}

export function lista(extras: Partial<ListaDeReceitas> = {}): ListaDeReceitas {
  return { ...LISTA, ...extras };
}
