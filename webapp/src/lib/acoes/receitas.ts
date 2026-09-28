"use server";

/**
 * As escritas da tela de receitas, como Server Actions: trazer uma receita
 * pelo endereço, responder a pergunta que segura uma receita (a da própria
 * receita, a da cozinha ou o preço do que falta), avaliar e anotar.
 *
 * Todas devolvem `Resultado` e nunca lançam (ver `./base`). As que mudam a
 * grade refazem a rota na mesma ida e volta: a receita respondida sai de
 * "Falta uma resposta sua" e as contagens das abas mudam sem outro pedido. As
 * notas, que se salvam sozinhas enquanto ela escreve, não refazem a rota: o
 * texto dela não pode ser trocado no meio da digitação.
 *
 * O que volta é só o que a tela precisa para dizer o que aconteceu, não a
 * receita inteira: a tela nova chega pela própria rota refeita.
 */

import { api } from "@/lib/api";
import type { Imagem } from "@/lib/api/base";
import type { RespostaDePosse } from "@/lib/api/perfil";
import { precoDeHoje } from "@/lib/api/preco";
import type { AvaliacaoEnviada, RespostaDaAvaliacao, RespostaDasNotas, VereditoDaCozinha } from "@/lib/api/receitas";

import type { Resultado } from "./base";
import { executarAcao, falha } from "./base";

/** A receita trazida, do jeito que a folha de "Trazer uma receita" mostra. */
export type ReceitaTrazidaNaTela = {
  slug: string;
  nome: string;
  rota: string;
  imagem: Imagem;
  site: string | null;
  /** `false` quando o servidor já conhecia o endereço. */
  nova: boolean;
  cozinha: VereditoDaCozinha;
  gosta: boolean | null;
};

/** Para onde a receita foi depois de uma resposta dela. */
export type ReceitaRespondida = { slug: string; nome: string; cozinha: VereditoDaCozinha };

/** O que a API disse depois de uma resposta sobre a cozinha ou sobre um preço. */
export type TextoDaResposta = { texto: string };

export type PrecoDoQueFalta = {
  ingrediente: string;
  /** Quanto custa, em reais, como ela digitou. */
  valor: number;
  /** Por qual quantidade (1 lata, 0,5 kg), como ela digitou. */
  quantidade: number;
  unidade: string;
};

const ENDERECO = /^https?:\/\/[^\s/]+\.[^\s]+$/i;

export async function trazerReceita(url: string): Promise<Resultado<ReceitaTrazidaNaTela>> {
  const endereco = url.trim();
  if (!ENDERECO.test(endereco)) {
    return falha("uso", "Esse endereço não parece de uma página. Copie o endereço inteiro, que começa com https://.");
  }
  return executarAcao(async () => {
    const { receita, nova } = await api.receitas.trazer(endereco);
    return {
      slug: receita.slug,
      nome: receita.nome,
      rota: receita.rota,
      imagem: receita.imagem,
      site: receita.fonte.site,
      nova,
      cozinha: receita.veredito_da_cozinha,
      gosta: receita.avaliacao.gosta,
    };
  });
}

/**
 * A resposta a uma pergunta da própria receita: o tempo no fogo, o rendimento,
 * uma linha, ou o peso de uma linha (`porUnidade`: de uma unidade ou da linha inteira).
 */
export async function responderSobreAReceita(
  slug: string,
  campo: string,
  resposta: string,
  porUnidade?: boolean,
): Promise<Resultado<ReceitaRespondida>> {
  const texto = resposta.trim();
  if (!texto) return falha("uso", "Escreva a resposta antes de mandar.");
  return executarAcao(async () => {
    const corpo = porUnidade === undefined ? { campo, resposta: texto } : { campo, resposta: texto, por_unidade: porUnidade };
    const receita = await api.receitas.responder(slug, corpo);
    return { slug: receita.slug, nome: receita.nome, cozinha: receita.veredito_da_cozinha };
  });
}

/** Tem ou não tem (faz ou não faz) um equipamento ou uma técnica. "Não sei" também é resposta. */
export async function responderSobreACozinha(
  lista: "equipamentos" | "tecnicas",
  id: string,
  estado: RespostaDePosse,
): Promise<Resultado<TextoDaResposta>> {
  return executarAcao(async () => {
    const { impacto } = await api.perfil.definirPosse(lista, id, estado);
    return { texto: impacto.texto };
  });
}

/** Um limite da rotina (bocas do fogão, gás sobrando…). `null` é "não sei". */
export async function responderLimiteDaCozinha(
  campo: string,
  valor: number | boolean | null,
): Promise<Resultado<TextoDaResposta>> {
  return executarAcao(async () => {
    const { impacto } = await api.perfil.definirRestricao(campo, valor);
    return { texto: impacto.texto };
  });
}

/** Quanto custa o que falta comprar, e por qual quantidade. Um preço por ingrediente. */
export async function informarPrecoDoQueFalta(precos: readonly PrecoDoQueFalta[]): Promise<Resultado<TextoDaResposta>> {
  if (precos.length === 0) return falha("uso", "Diga quanto custa antes de mandar.");
  for (const preco of precos) {
    if (!(preco.valor > 0)) return falha("uso", `Diga quanto custa ${preco.ingrediente}.`);
    if (!(preco.quantidade > 0) || !preco.unidade.trim()) {
      return falha("uso", `Diga por qual quantidade é esse preço de ${preco.ingrediente}: 1 lata, 1 kg, 1 pacote.`);
    }
  }
  return executarAcao(async () => {
    const textos: string[] = [];
    for (const preco of precos) {
      const registrado = await precoDeHoje.registrarPreco(preco.ingrediente, preco.valor, {
        quantidade: preco.quantidade,
        unidade: preco.unidade.trim(),
      });
      textos.push(registrado.texto);
    }
    return { texto: textos.join(" ") };
  });
}

/** O gosto e as estrelas: só o que mudou (`null` apaga). */
export async function avaliarReceita(slug: string, avaliacao: AvaliacaoEnviada): Promise<Resultado<RespostaDaAvaliacao>> {
  return executarAcao(() => api.receitas.avaliar(slug, avaliacao));
}

/** As anotações dela. Salvam sozinhas: não refazem a rota. */
export async function anotarReceita(slug: string, texto: string): Promise<Resultado<RespostaDasNotas>> {
  return executarAcao(() => api.receitas.salvarNotas(slug, texto), { atualizar: false });
}
