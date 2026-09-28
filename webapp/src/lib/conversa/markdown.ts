/**
 * O Markdown leve do agente, desenhado em nós React.
 *
 * A instrução fixa da web deixa o agente usar **negrito**, *itálico*,
 * listas com "-" e parágrafos curtos (ver o `INSTRUCAO_DA_WEB` do backend).
 * Este renderizador entende exatamente isso, mais links http e https. Todo o
 * resto cai para texto: título vira uma linha em negrito, tabela e código
 * aparecem como foram escritos, e nada vira HTML. Não existe
 * `dangerouslySetInnerHTML` aqui: todo texto vai como texto, então um
 * `<script>` no meio da resposta é só um texto com sinais de menor e maior.
 *
 * Três peças especiais atravessam o Markdown sem se perder:
 * - o sentinela (U+E000), que vira o brilho "R$ ···" do valor em conferência;
 * - "[valor retirado]", o que o backend tirou do texto final, que vira um chip;
 * - no texto final, cada valor em reais, que ganha algarismos tabulares.
 */

import type { ReactNode } from "react";
import { createElement, Fragment } from "react";

import { SENTINELA } from "./mascara";

export type NoEmLinha =
  | { tipo: "texto"; texto: string }
  | { tipo: "negrito"; filhos: NoEmLinha[] }
  | { tipo: "italico"; filhos: NoEmLinha[] }
  | { tipo: "link"; href: string; filhos: NoEmLinha[] }
  | { tipo: "valor" }
  | { tipo: "retirado" }
  | { tipo: "dinheiro"; texto: string }
  | { tipo: "quebra" };

export type Bloco =
  | { tipo: "paragrafo"; filhos: NoEmLinha[] }
  | { tipo: "lista"; itens: NoEmLinha[][] };

export type OpcoesDoMarkdown = {
  /** Marca cada valor em reais (só no texto final, que já foi conferido). */
  destacarDinheiro?: boolean;
};

/* -------------------------------------------------------------------------- */
/* Endereços                                                                   */
/* -------------------------------------------------------------------------- */

/** O endereço, se for http ou https absoluto; `null` para todo o resto (javascript:, data:, relativo). */
export function linkSeguro(endereco: string): string | null {
  const limpo = endereco.trim();
  if (!/^https?:\/\//i.test(limpo)) return null;
  try {
    const url = new URL(limpo);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Em linha                                                                    */
/* -------------------------------------------------------------------------- */

const RETIRADO = "[valor retirado]";
const LINK = /^\[([^\]\n]{1,300})\]\(([^()\s]{1,2000})\)/;
const URL_SOLTA = /^https?:\/\/[^\s<>"'`[\]()]+/i;
const PONTUACAO_FINAL = /[.,;:!?]+$/;
const DINHEIRO = /^[Rr]\$\s*(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)/;

/** O índice do `**` que fecha o negrito aberto em `inicio`, ou -1. */
function fimDoNegrito(texto: string, inicio: number): number {
  let busca = inicio + 2;
  while (busca < texto.length) {
    const fim = texto.indexOf("**", busca);
    if (fim === -1) return -1;
    const dentro = texto.slice(inicio + 2, fim);
    if (dentro.trim() !== "" && !/^\s/.test(dentro) && !/\s$/.test(dentro)) return fim;
    busca = fim + 1;
  }
  return -1;
}

/** O índice do `*` que fecha o itálico aberto em `inicio`, ou -1. */
function fimDoItalico(texto: string, inicio: number): number {
  if (/\s/.test(texto[inicio + 1] ?? " ")) return -1;
  for (let fim = inicio + 2; fim < texto.length; fim += 1) {
    if (texto[fim] !== "*") continue;
    if (texto[fim + 1] === "*") {
      fim += 1;
      continue;
    }
    if (!/\s/.test(texto[fim - 1] ?? " ")) return fim;
  }
  return -1;
}

function empurrarTexto(nos: NoEmLinha[], texto: string) {
  if (!texto) return;
  const partes = texto.split("\n");
  partes.forEach((parte, indice) => {
    if (indice > 0) nos.push({ tipo: "quebra" });
    if (!parte) return;
    const ultimo = nos.at(-1);
    if (ultimo?.tipo === "texto") ultimo.texto += parte;
    else nos.push({ tipo: "texto", texto: parte });
  });
}

/** O texto de um parágrafo ou item, em nós em linha. */
export function analisarEmLinha(texto: string, opcoes: OpcoesDoMarkdown = {}): NoEmLinha[] {
  const nos: NoEmLinha[] = [];
  let solto = "";
  const soltar = () => {
    empurrarTexto(nos, solto);
    solto = "";
  };

  let i = 0;
  while (i < texto.length) {
    const letra = texto[i] as string;
    const resto = texto.slice(i);

    if (letra === SENTINELA) {
      soltar();
      nos.push({ tipo: "valor" });
      i += 1;
      continue;
    }

    if (letra === "[") {
      if (resto.slice(0, RETIRADO.length).toLowerCase() === RETIRADO) {
        soltar();
        nos.push({ tipo: "retirado" });
        i += RETIRADO.length;
        continue;
      }
      const link = LINK.exec(resto);
      if (link) {
        soltar();
        const [inteiro, rotulo = "", endereco = ""] = link;
        const href = linkSeguro(endereco);
        const filhos = analisarEmLinha(rotulo, opcoes);
        if (href) nos.push({ tipo: "link", href, filhos });
        else nos.push(...filhos);
        i += inteiro.length;
        continue;
      }
    }

    if (letra === "*") {
      if (texto[i + 1] === "*") {
        const fim = fimDoNegrito(texto, i);
        if (fim !== -1) {
          soltar();
          nos.push({ tipo: "negrito", filhos: analisarEmLinha(texto.slice(i + 2, fim), opcoes) });
          i = fim + 2;
          continue;
        }
        solto += "**";
        i += 2;
        continue;
      }
      const fim = fimDoItalico(texto, i);
      if (fim !== -1) {
        soltar();
        nos.push({ tipo: "italico", filhos: analisarEmLinha(texto.slice(i + 1, fim), opcoes) });
        i = fim + 1;
        continue;
      }
    }

    if ((letra === "h" || letra === "H") && !/[\p{L}\p{N}]/u.test(texto[i - 1] ?? " ")) {
      const solta = URL_SOLTA.exec(resto);
      if (solta) {
        const endereco = solta[0].replace(PONTUACAO_FINAL, "");
        const href = linkSeguro(endereco);
        if (href) {
          soltar();
          nos.push({ tipo: "link", href, filhos: [{ tipo: "texto", texto: endereco }] });
          i += endereco.length;
          continue;
        }
      }
    }

    if (opcoes.destacarDinheiro && (letra === "R" || letra === "r") && texto[i + 1] === "$") {
      const valor = DINHEIRO.exec(resto);
      if (valor) {
        soltar();
        nos.push({ tipo: "dinheiro", texto: valor[0] });
        i += valor[0].length;
        continue;
      }
    }

    solto += letra;
    i += 1;
  }
  soltar();
  return nos;
}

/* -------------------------------------------------------------------------- */
/* Blocos                                                                      */
/* -------------------------------------------------------------------------- */

const ITEM = /^\s{0,3}[-*•]\s+(.*)$/;
const TITULO = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;
const REGUA = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const CONTINUACAO = /^\s{2,}\S/;

/** O texto inteiro em blocos: parágrafos (linhas quebradas dentro) e listas. */
export function analisarMarkdown(texto: string, opcoes: OpcoesDoMarkdown = {}): Bloco[] {
  const blocos: Bloco[] = [];
  let paragrafo: string[] = [];
  let lista: string[] | null = null;

  const fecharParagrafo = () => {
    if (paragrafo.length === 0) return;
    const filhos = analisarEmLinha(paragrafo.join("\n"), opcoes);
    if (filhos.length > 0) blocos.push({ tipo: "paragrafo", filhos });
    paragrafo = [];
  };
  const fecharLista = () => {
    if (lista && lista.length > 0) {
      blocos.push({ tipo: "lista", itens: lista.map((item) => analisarEmLinha(item, opcoes)) });
    }
    lista = null;
  };

  for (const linha of texto.replace(/\r\n?/g, "\n").split("\n")) {
    if (linha.trim() === "" || REGUA.test(linha)) {
      fecharParagrafo();
      fecharLista();
      continue;
    }
    const item = ITEM.exec(linha);
    if (item) {
      fecharParagrafo();
      (lista ??= []).push((item[1] ?? "").trim());
      continue;
    }
    const titulo = TITULO.exec(linha);
    if (titulo) {
      fecharParagrafo();
      fecharLista();
      blocos.push({ tipo: "paragrafo", filhos: [{ tipo: "negrito", filhos: analisarEmLinha(titulo[1] ?? "", opcoes) }] });
      continue;
    }
    if (lista !== null && CONTINUACAO.test(linha)) {
      const itens: string[] = lista;
      itens[itens.length - 1] = `${itens[itens.length - 1] ?? ""} ${linha.trim()}`;
      continue;
    }
    fecharLista();
    paragrafo.push(linha.trim());
  }
  fecharParagrafo();
  fecharLista();
  return blocos;
}

/* -------------------------------------------------------------------------- */
/* Nós React                                                                   */
/* -------------------------------------------------------------------------- */

export type PecasDoMarkdown = {
  /** O valor em conferência (o sentinela). */
  valor: (chave: string) => ReactNode;
  /** O chip de "valor retirado". */
  retirado: (chave: string) => ReactNode;
  /** Um valor em reais do texto final. Sem esta peça, fica como texto. */
  dinheiro?: (texto: string, chave: string) => ReactNode;
};

function emLinha(nos: NoEmLinha[], pecas: PecasDoMarkdown, prefixo: string): ReactNode[] {
  return nos.map((no, indice) => {
    const chave = `${prefixo}.${indice}`;
    switch (no.tipo) {
      case "texto":
        return createElement(Fragment, { key: chave }, no.texto);
      case "negrito":
        return createElement(
          "strong",
          { key: chave, className: "font-bold text-tinta" },
          emLinha(no.filhos, pecas, chave),
        );
      case "italico":
        return createElement("em", { key: chave }, emLinha(no.filhos, pecas, chave));
      case "link":
        return createElement(
          "a",
          {
            key: chave,
            href: no.href,
            target: "_blank",
            rel: "noopener noreferrer",
            className: "font-semibold break-words text-marca underline underline-offset-2 hover:no-underline",
          },
          ...emLinha(no.filhos, pecas, chave),
          createElement("span", { key: "externo", className: "sr-only" }, " (abre em outra aba)"),
        );
      case "valor":
        return pecas.valor(chave);
      case "retirado":
        return pecas.retirado(chave);
      case "dinheiro":
        return pecas.dinheiro ? pecas.dinheiro(no.texto, chave) : createElement(Fragment, { key: chave }, no.texto);
      case "quebra":
        return createElement("br", { key: chave });
    }
  });
}

/** Os blocos em nós React: `<p>`, `<ul>`, e as peças especiais no meio do texto. */
export function renderizarBlocos(blocos: Bloco[], pecas: PecasDoMarkdown): ReactNode[] {
  return blocos.map((bloco, indice) => {
    const chave = `b${indice}`;
    if (bloco.tipo === "lista") {
      return createElement(
        "ul",
        { key: chave, className: "list-disc space-y-1.5 pl-6 marker:text-apagado" },
        bloco.itens.map((item, n) =>
          createElement("li", { key: `${chave}.${n}`, className: "pl-1" }, emLinha(item, pecas, `${chave}.${n}`)),
        ),
      );
    }
    return createElement("p", { key: chave }, emLinha(bloco.filhos, pecas, chave));
  });
}

function planoEmLinha(nos: NoEmLinha[]): string {
  return nos
    .map((no) => {
      switch (no.tipo) {
        case "texto":
        case "dinheiro":
          return no.texto;
        case "negrito":
        case "italico":
        case "link":
          return planoEmLinha(no.filhos);
        case "valor":
          return "valor em conferência";
        case "retirado":
          return "valor retirado";
        case "quebra":
          return " ";
      }
    })
    .join("");
}

/**
 * O texto sem as marcas do Markdown, numa linha só: o que o leitor de tela
 * anuncia quando a resposta fica pronta.
 */
export function textoPlano(texto: string): string {
  return analisarMarkdown(texto)
    .map((bloco) => (bloco.tipo === "lista" ? bloco.itens.map(planoEmLinha).join("; ") : planoEmLinha(bloco.filhos)))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Atalho: o texto direto para nós React. */
export function renderizarMarkdown(
  texto: string,
  pecas: PecasDoMarkdown,
  opcoes: OpcoesDoMarkdown = {},
): ReactNode[] {
  return renderizarBlocos(analisarMarkdown(texto, opcoes), pecas);
}
