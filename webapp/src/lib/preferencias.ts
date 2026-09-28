/**
 * As preferências dela, guardadas neste navegador: o tamanho do texto, o
 * movimento da tela, o modo minimalista e como a conversa mostra o que o
 * agente fez. O tema mora em `tema.ts`, com a mesma ideia.
 *
 * O tamanho do texto, o movimento e o modo minimalista mudam a tela inteira,
 * então valem antes da primeira pintura: o script do `<head>`
 * (`SCRIPT_DA_APARENCIA`) marca `data-tema`, `data-texto`, `data-movimento` e
 * `data-minimalista` no `<html>`, e o CSS faz o resto. Sem isso, a página
 * abriria no tamanho normal e pularia para o grande depois de carregar.
 *
 * Este arquivo não usa React: o script sai de um server component. O gancho
 * que o React lê fica em `lib/usePreferencias.ts`.
 */

import { SCRIPT_DO_TEMA } from "./tema";

export type TamanhoDoTexto = "normal" | "grande";
export type PreferenciaDeMovimento = "sistema" | "reduzir";
export type PassosDaConsultora = "recolhidos" | "abertos";
export type ModoMinimalista = "desligado" | "ligado";

/** Uma preferência: onde fica guardada, o que aceita e o que vale sem escolha. */
export type Preferencia<V extends string> = {
  chave: string;
  valores: readonly V[];
  padrao: V;
  /** O atributo do `<html>` que carrega a escolha, quando ela muda a tela inteira. */
  atributo?: string;
};

export const TAMANHO_DO_TEXTO: Preferencia<TamanhoDoTexto> = {
  chave: "texto",
  valores: ["normal", "grande"],
  padrao: "normal",
  atributo: "data-texto",
};

export const MOVIMENTO: Preferencia<PreferenciaDeMovimento> = {
  chave: "movimento",
  valores: ["sistema", "reduzir"],
  padrao: "sistema",
  atributo: "data-movimento",
};

/** Os passos de cada resposta ("Ver o que eu fiz") começam abertos ou recolhidos. */
export const PASSOS_DA_CONSULTORA: Preferencia<PassosDaConsultora> = {
  chave: "passos-da-consultora",
  valores: ["recolhidos", "abertos"],
  padrao: "recolhidos",
};

/**
 * Modo minimalista: os cards das listas escondem as contas e as telas ficam
 * com menos texto. Quem esconde é o CSS, pela variante `minimalista:` do
 * Tailwind (ver `globals.css`); o detalhe de cada item não usa a variante, e
 * continua com tudo.
 */
export const MINIMALISTA: Preferencia<ModoMinimalista> = {
  chave: "minimalista",
  valores: ["desligado", "ligado"],
  padrao: "desligado",
  atributo: "data-minimalista",
};

const DA_TELA_INTEIRA = [TAMANHO_DO_TEXTO, MOVIMENTO, MINIMALISTA] as const;

const CHAVES: ReadonlySet<string> = new Set(
  [TAMANHO_DO_TEXTO, MOVIMENTO, MINIMALISTA, PASSOS_DA_CONSULTORA].map((p) => p.chave),
);

/* -------------------------------------------------------------------------- */
/* O script do <head>                                                          */
/* -------------------------------------------------------------------------- */

/** `v=g("texto");d.setAttribute("data-texto",(v==="grande")?v:"normal");` */
function trechoDoScript(preferencia: Preferencia<string>): string {
  const escolhas = preferencia.valores
    .filter((valor) => valor !== preferencia.padrao)
    .map((valor) => `v===${JSON.stringify(valor)}`)
    .join("||");
  return (
    `v=g(${JSON.stringify(preferencia.chave)});` +
    `d.setAttribute(${JSON.stringify(preferencia.atributo)},(${escolhas})?v:${JSON.stringify(preferencia.padrao)});`
  );
}

/**
 * O script que roda antes da primeira pintura: o do tema, e depois o tamanho
 * do texto, o movimento e o modo minimalista. É uma string porque roda antes
 * do React existir, e cada leitura fica protegida (armazenamento bloqueado
 * vale como o padrão).
 */
export const SCRIPT_DA_APARENCIA =
  SCRIPT_DO_TEMA +
  "(function(){try{var d=document.documentElement,v,g=function(k){try{return localStorage.getItem(k)}catch(e){return null}};" +
  DA_TELA_INTEIRA.map(trechoDoScript).join("") +
  "}catch(e){}})();";

/* -------------------------------------------------------------------------- */
/* Leitura, gravação e aplicação                                               */
/* -------------------------------------------------------------------------- */

export function lerPreferenciaDe<V extends string>(preferencia: Preferencia<V>): V {
  try {
    const guardada = window.localStorage.getItem(preferencia.chave);
    return preferencia.valores.find((valor) => valor === guardada) ?? preferencia.padrao;
  } catch {
    return preferencia.padrao;
  }
}

function marcar(preferencia: Preferencia<string>, valor: string) {
  if (!preferencia.atributo) return;
  const raiz = document.documentElement;
  if (raiz.getAttribute(preferencia.atributo) !== valor) raiz.setAttribute(preferencia.atributo, valor);
}

/** Marca no `<html>` o tamanho do texto, o movimento e o modo minimalista guardados. */
export function aplicarAparencia(): void {
  for (const preferencia of DA_TELA_INTEIRA) marcar(preferencia, lerPreferenciaDe<string>(preferencia));
}

const ouvintes = new Set<() => void>();
let desligar: (() => void) | null = null;

function avisar() {
  for (const ouvinte of [...ouvintes]) ouvinte();
}

function ligar(): () => void {
  // Outra aba mudou: esta acompanha, para as duas não discordarem.
  const aoMudarOutraAba = (evento: StorageEvent) => {
    if (evento.key !== null && !CHAVES.has(evento.key)) return;
    aplicarAparencia();
    avisar();
  };
  window.addEventListener("storage", aoMudarOutraAba);
  return () => window.removeEventListener("storage", aoMudarOutraAba);
}

/** Assina as mudanças de preferência (desta aba ou de outra). */
export function assinarPreferencias(ouvinte: () => void): () => void {
  ouvintes.add(ouvinte);
  desligar ??= ligar();
  return () => {
    ouvintes.delete(ouvinte);
    if (ouvintes.size === 0 && desligar) {
      desligar();
      desligar = null;
    }
  };
}

/** Grava a escolha, aplica na tela (quando é da tela inteira) e avisa quem assina. */
export function definirPreferenciaDe<V extends string>(preferencia: Preferencia<V>, valor: V): void {
  try {
    window.localStorage.setItem(preferencia.chave, valor);
  } catch {
    // Sem armazenamento, a escolha vale só nesta visita. Não é motivo de erro.
  }
  marcar(preferencia, valor);
  avisar();
}
