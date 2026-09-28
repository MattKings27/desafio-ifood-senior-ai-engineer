/**
 * Como as coisas aparecem para ela: números de controle, palavras, busca.
 *
 * Regra que organiza este arquivo: **a interface não calcula dinheiro.** Todo
 * valor em reais chega pronto da API, com o `texto` em pt-BR. O que existe aqui
 * é o que sobra para a tela fazer: escrever o rótulo de um controle (os limites
 * de um preço, uma porcentagem), ler o que ela digita com vírgula, comparar
 * valores já recebidos para ordenar, e garantir que nenhum jargão chegue a ela.
 */

import type { Dinheiro } from "@/lib/api/base";

/* -------------------------------------------------------------------------- */
/* Números                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Um valor em reais escrito como no Brasil ("R$ 15,00"). Só para rótulo de
 * controle, como os limites do preço: todo valor que vem de conta chega pronto
 * da API, com o texto dela.
 */
export function reais(valor: number): string {
  return `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Percentual em pt-BR. Não é dinheiro: é a fração que a API mandou. */
export function porcentagem(fracao: number, casas = 0): string {
  return `${(fracao * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  })}%`;
}

/** Um número como ela escreve: vírgula decimal, ponto de milhar. */
export function formatarNumero(numero: number, casasMaximas = 2): string {
  return numero.toLocaleString("pt-BR", { maximumFractionDigits: casasMaximas });
}

/**
 * Lê o que ela digitou. "1,5" é um e meio; "1.234,56" tem ponto de milhar;
 * "1.5", que o teclado do celular às vezes oferece, também é um e meio; e
 * "1.500" é mil e quinhentos. Qualquer outra coisa é `null`, nunca zero: zero
 * digitado e campo em branco são respostas diferentes.
 */
export function lerNumeroBR(texto: string): number | null {
  let limpo = texto.replace(/R\$/gi, "").replace(/\s+/g, "").trim();
  if (limpo === "") return null;

  if (limpo.includes(",")) {
    limpo = limpo.replace(/\./g, "").replace(",", ".");
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) {
    limpo = limpo.replace(/\./g, "");
  }
  if (!/^-?(\d+(\.\d+)?|\.\d+)$/.test(limpo)) return null;
  const numero = Number(limpo);
  return Number.isFinite(numero) ? numero : null;
}

/**
 * Ordena dinheiro já recebido, sem conta: só compara. O que não tem valor vai
 * para o fim, que é onde "ainda não sei o preço" deve ficar numa lista.
 */
export function compararDinheiro(
  a: Dinheiro | null | undefined,
  b: Dinheiro | null | undefined,
): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  if (a.valor < b.valor) return -1;
  if (a.valor > b.valor) return 1;
  return 0;
}

/* -------------------------------------------------------------------------- */
/* Viabilidade                                                                 */
/* -------------------------------------------------------------------------- */

export type Veredito = "APTO" | "APTO COM COMPRA" | "FALTA INFO" | "BLOQUEADO";

/** O que ela lê no lugar do valor técnico. A API manda o mesmo em `veredito_rotulo`. */
export const ROTULO_DO_VEREDITO: Readonly<Record<Veredito, string>> = {
  APTO: "Dá pra fazer",
  "APTO COM COMPRA": "Dá, comprando",
  "FALTA INFO": "Falta saber",
  BLOQUEADO: "Não dá",
};

export type TomSemantico = "sucesso" | "info" | "atencao" | "perigo";

export const TOM_DO_VEREDITO: Readonly<Record<Veredito, TomSemantico>> = {
  APTO: "sucesso",
  "APTO COM COMPRA": "info",
  "FALTA INFO": "atencao",
  BLOQUEADO: "perigo",
};

/** Cor semântica de um veredito. Nunca o vermelho da marca, que é de ação, não de bloqueio. */
export function corDoVeredito(veredito: Veredito): {
  texto: string;
  fundo: string;
  rotulo: string;
} {
  const tom = TOM_DO_VEREDITO[veredito];
  return { texto: `text-${tom}`, fundo: `bg-${tom}/10`, rotulo: ROTULO_DO_VEREDITO[veredito] };
}

/* -------------------------------------------------------------------------- */
/* Linguagem com ela                                                           */
/* -------------------------------------------------------------------------- */

/** Uma palavra inteira, com acento contando como letra. */
function palavra(padrao: string, bandeiras = "u"): RegExp {
  return new RegExp(`(?<![\\p{L}\\p{N}_])(?:${padrao})(?![\\p{L}\\p{N}_])`, bandeiras);
}

/**
 * O jargão que nunca chega à tela dela. `APTO`, `FALTA INFO` e `BLOQUEADO` só
 * em maiúsculas, que é a forma do valor técnico; o resto em qualquer caixa.
 */
export const PALAVRAS_PROIBIDAS: readonly { palavra: string; padrao: RegExp }[] = [
  { palavra: "motor", padrao: palavra("motor", "iu") },
  { palavra: "portão", padrao: palavra("port[ãa]o", "iu") },
  { palavra: "APTO", padrao: palavra("APTO") },
  { palavra: "FALTA INFO", padrao: palavra("FALTA INFO") },
  { palavra: "BLOQUEADO", padrao: palavra("BLOQUEADO") },
  { palavra: "veredito", padrao: palavra("veredito", "iu") },
  { palavra: "CMV", padrao: palavra("CMV") },
  { palavra: "food cost", padrao: palavra("food[\\s-]?cost", "iu") },
  { palavra: "append-only", padrao: palavra("append[\\s-]?only", "iu") },
  { palavra: "make api", padrao: palavra("make\\s+api", "iu") },
];

/** As palavras proibidas que aparecem no texto, na ordem da lista. */
export function encontrarJargao(texto: string): string[] {
  return PALAVRAS_PROIBIDAS.filter(({ padrao }) => padrao.test(texto)).map(({ palavra: p }) => p);
}

const SINAIS_TECNICOS: readonly RegExp[] = [
  // Código de estado HTTP dito como tal, não "500 g de farinha".
  /\b(?:HTTP|status|respondeu|c[óo]digo)\s*:?\s*[1-5]\d\d\b/i,
  /\b(?:Errno|Traceback|Exception|TypeError|SyntaxError|ECONN\w*|ENOTFOUND|ETIMEDOUT|EPIPE)\b/,
  /\b(?:fetch failed|failed|error|invalid|not found|cannot|unexpected|undefined|null|NaN)\b/i,
  /\b(?:localhost|127\.0\.0\.1|https?:\/\/)/i,
  // Caminho de arquivo: "/srv/dados/…", ".estado/auditoria.jsonl". Não "1/2 xícara".
  /(?:^|[\s'"(])(?:\.{1,2})?\/[\w.-]+\/[\w./-]*/,
  /\b[\w-]+\/[\w./-]*\.[a-z]{2,5}\b/,
  // Identificador de programa: `pode_precificar`, `avaliar_receita`.
  /\b[a-z]+_[a-z_]+\b/,
  /[`{}<>[\]]/,
];

/** O texto tem cara de mensagem de programa, e não de gente? */
export function pareceTecnico(texto: string): boolean {
  return SINAIS_TECNICOS.some((sinal) => sinal.test(texto));
}

/**
 * O texto, se ele serve para ela; senão, a alternativa. A mensagem de uma
 * recusa vem da API e deveria vir limpa, mas a tela é a última porta: um erro
 * em inglês ou um caminho de arquivo nunca aparece como se fosse conversa.
 */
export function textoParaEla(texto: string | null | undefined, alternativa: string): string {
  const limpo = texto?.trim();
  if (!limpo) return alternativa;
  if (pareceTecnico(limpo) || encontrarJargao(limpo).length > 0) return alternativa;
  return limpo;
}

/* -------------------------------------------------------------------------- */
/* Busca                                                                       */
/* -------------------------------------------------------------------------- */

/** Minúsculas e sem acento: "Açafrão" e "acafrao" são a mesma busca. */
export function semAcento(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

/** Cada palavra do termo aparece no texto, em qualquer ordem e sem acento. */
export function casaComBusca(texto: string, termo: string): boolean {
  const alvo = semAcento(texto);
  return semAcento(termo)
    .split(/\s+/)
    .filter(Boolean)
    .every((parte) => alvo.includes(parte));
}
