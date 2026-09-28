/**
 * Contraste WCAG dos tokens de cor, nos dois temas.
 *
 * Existe porque "passa AA" dito a olho é opinião, e dito por conta é fato. O
 * teste que usa este módulo lê o `globals.css` de verdade, então um token
 * trocado sem pensar no contraste fica vermelho no CI antes de chegar à tela.
 *
 * A fórmula é a da luminância relativa do WCAG 2.2. As tintas (os chips usam a
 * cor semântica a 10% sobre a superfície) são compostas em sRGB, que é como o
 * navegador pinta uma cor com transparência sobre outra.
 */

export type Rgb = readonly [number, number, number];

export type TemaDeCor = "claro" | "escuro";

/** Nome do token sem o prefixo `--color-` → valor hexadecimal. */
export type Tokens = Readonly<Record<string, string>>;

export function hexParaRgb(hex: string): Rgb {
  const limpo = hex.trim().replace(/^#/, "");
  const cheio =
    limpo.length === 3
      ? limpo
          .split("")
          .map((c) => c + c)
          .join("")
      : limpo;
  if (!/^[0-9a-fA-F]{6}$/.test(cheio)) {
    throw new Error(`cor inválida: ${hex}`);
  }
  return [0, 2, 4].map((i) => parseInt(cheio.slice(i, i + 2), 16)) as unknown as Rgb;
}

function canalLinear(canal: number): number {
  const v = canal / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

export function luminancia([r, g, b]: Rgb): number {
  return 0.2126 * canalLinear(r) + 0.7152 * canalLinear(g) + 0.0722 * canalLinear(b);
}

function comoRgb(cor: Rgb | string): Rgb {
  return typeof cor === "string" ? hexParaRgb(cor) : cor;
}

/** Razão de contraste entre duas cores, de 1 a 21. A ordem não importa. */
export function contraste(a: Rgb | string, b: Rgb | string): number {
  const [clara, escura] = [luminancia(comoRgb(a)), luminancia(comoRgb(b))].sort((x, y) => y - x) as [
    number,
    number,
  ];
  return (clara + 0.05) / (escura + 0.05);
}

/** A cor `frente` com opacidade `alfa`, pintada sobre `fundo`. */
export function compor(frente: Rgb | string, fundo: Rgb | string, alfa: number): Rgb {
  const f = comoRgb(frente);
  const b = comoRgb(fundo);
  return [0, 1, 2].map((i) => alfa * f[i]! + (1 - alfa) * b[i]!) as unknown as Rgb;
}

/* -------------------------------------------------------------------------- */
/* Leitura do globals.css                                                      */
/* -------------------------------------------------------------------------- */

/** O corpo do primeiro bloco `{…}` que começa em `seletor`, contando chaves. */
function corpoDoBloco(css: string, seletor: string): string {
  const inicio = css.indexOf(seletor);
  if (inicio < 0) throw new Error(`bloco não encontrado: ${seletor}`);
  const abre = css.indexOf("{", inicio);
  let profundidade = 0;
  for (let i = abre; i < css.length; i += 1) {
    if (css[i] === "{") profundidade += 1;
    if (css[i] === "}") {
      profundidade -= 1;
      if (profundidade === 0) return css.slice(abre + 1, i);
    }
  }
  throw new Error(`bloco sem fim: ${seletor}`);
}

function tokensDe(corpo: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const [, nome, valor] of corpo.matchAll(/--color-([\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
    tokens[nome!] = valor!.toLowerCase();
  }
  return tokens;
}

export type TokensDosTemas = {
  claro: Tokens;
  /** O que vale com `data-tema="escuro"`: o claro sobrescrito pelo bloco escuro. */
  escuro: Tokens;
  /** Só o que o bloco escuro redeclara, para conferir que tudo troca. */
  redeclaradosNoEscuro: Tokens;
  /** O plano B sem JavaScript, pela media query. Tem que ser igual ao escuro. */
  escuroSemScript: Tokens;
};

export function lerTokens(cssComComentarios: string): TokensDosTemas {
  // Sem os comentários, um seletor citado em prosa não é confundido com o bloco.
  const css = cssComComentarios.replace(/\/\*[\s\S]*?\*\//g, "");
  const claro = tokensDe(corpoDoBloco(css, "@theme"));
  const redeclarados = tokensDe(corpoDoBloco(css, ':root[data-tema="escuro"]'));
  const semScript = tokensDe(corpoDoBloco(css, ':root:not([data-tema="claro"])'));
  return {
    claro,
    escuro: { ...claro, ...redeclarados },
    redeclaradosNoEscuro: redeclarados,
    escuroSemScript: semScript,
  };
}

/* -------------------------------------------------------------------------- */
/* Os pares que a interface usa                                                */
/* -------------------------------------------------------------------------- */

/** Um fundo: um token puro, ou uma tinta (token com opacidade) sobre outro. */
export type Fundo = string | { tinta: string; alfa: number; sobre: string };

export type Par = {
  /** Onde o par aparece, nas palavras de quem desenha a tela. */
  uso: string;
  frente: string;
  fundo: Fundo;
  /** 4,5 para texto; 3 para borda de campo, anel de foco e barra. */
  minimo: 4.5 | 3;
};

const SEMANTICAS = [
  ["sucesso", "Dá pra fazer, lucro"],
  ["atencao", "Falta saber"],
  ["perigo", "Não dá, prejuízo"],
  ["info", "Dá, comprando"],
] as const;

export const PARES: readonly Par[] = [
  { uso: "Texto corrido sobre o cartão", frente: "texto", fundo: "superficie", minimo: 4.5 },
  { uso: "Texto corrido sobre o fundo da página", frente: "texto", fundo: "fundo", minimo: 4.5 },
  { uso: "Texto sobre a faixa creme", frente: "texto", fundo: "creme", minimo: 4.5 },
  { uso: "Chip neutro", frente: "texto", fundo: "secao", minimo: 4.5 },
  { uso: "Texto sobre a tinta de alerta", frente: "texto", fundo: "tinta-clara", minimo: 4.5 },
  { uso: "Títulos e valores sobre o cartão", frente: "tinta", fundo: "superficie", minimo: 4.5 },
  { uso: "Títulos sobre o fundo da página", frente: "tinta", fundo: "fundo", minimo: 4.5 },
  { uso: "Texto de apoio sobre o cartão", frente: "apagado", fundo: "superficie", minimo: 4.5 },
  { uso: "Texto de apoio sobre o fundo", frente: "apagado", fundo: "fundo", minimo: 4.5 },
  { uso: "Texto de apoio sobre a seção", frente: "apagado", fundo: "secao", minimo: 4.5 },
  { uso: "Texto de apoio sobre o creme", frente: "apagado", fundo: "creme", minimo: 4.5 },
  { uso: "Texto de apoio sobre a superfície 2", frente: "apagado", fundo: "superficie-2", minimo: 4.5 },
  { uso: "Link e botão secundário sobre o cartão", frente: "marca", fundo: "superficie", minimo: 4.5 },
  { uso: "Link sobre o fundo da página", frente: "marca", fundo: "fundo", minimo: 4.5 },
  { uso: "Link sobre a superfície 2", frente: "marca", fundo: "superficie-2", minimo: 4.5 },
  { uso: "Botão principal e Conversar", frente: "sobre-marca", fundo: "marca-fundo", minimo: 4.5 },
  {
    uso: "Botão principal com o ponteiro em cima",
    frente: "sobre-marca",
    fundo: "marca-fundo-escura",
    minimo: 4.5,
  },
  { uso: "Botão de perigo (tirar, apagar)", frente: "superficie", fundo: "perigo", minimo: 4.5 },
  { uso: "Opção escolhida (segmentado, filtro)", frente: "superficie", fundo: "tinta", minimo: 4.5 },
  {
    uso: "Chip da marca",
    frente: "marca-escura",
    fundo: { tinta: "marca", alfa: 0.1, sobre: "superficie" },
    minimo: 4.5,
  },
  ...SEMANTICAS.flatMap(([tom, uso]): Par[] => [
    { uso: `${uso}: texto sobre o cartão`, frente: tom, fundo: "superficie", minimo: 4.5 },
    { uso: `${uso}: texto sobre o fundo`, frente: tom, fundo: "fundo", minimo: 4.5 },
    {
      uso: `${uso}: chip sobre o cartão`,
      frente: tom,
      fundo: { tinta: tom, alfa: 0.1, sobre: "superficie" },
      minimo: 4.5,
    },
    {
      uso: `${uso}: chip sobre o fundo`,
      frente: tom,
      fundo: { tinta: tom, alfa: 0.1, sobre: "fundo" },
      minimo: 4.5,
    },
  ]),
  { uso: "Borda de campo de formulário", frente: "borda-campo", fundo: "superficie", minimo: 3 },
  { uso: "Anel de foco sobre o fundo", frente: "marca", fundo: "fundo", minimo: 3 },
  { uso: "Barra de proporção sobre o trilho", frente: "marca", fundo: "borda", minimo: 3 },
];

function cor(tokens: Tokens, nome: string): string {
  const valor = tokens[nome];
  if (!valor) throw new Error(`token sem valor: ${nome}`);
  return valor;
}

export function resolverFundo(tokens: Tokens, fundo: Fundo): Rgb {
  if (typeof fundo === "string") return hexParaRgb(cor(tokens, fundo));
  return compor(cor(tokens, fundo.tinta), cor(tokens, fundo.sobre), fundo.alfa);
}

export function razaoDoPar(tokens: Tokens, par: Par): number {
  return contraste(cor(tokens, par.frente), resolverFundo(tokens, par.fundo));
}

/** "4,58:1", como o DESIGN.md escreve. Trunca, para nunca arredondar para cima. */
export function formatarRazao(razao: number): string {
  const truncada = Math.floor(razao * 100) / 100;
  return `${truncada.toFixed(2).replace(".", ",")}:1`;
}

function descreverFundo(fundo: Fundo): string {
  return typeof fundo === "string"
    ? `\`${fundo}\``
    : `\`${fundo.tinta}\` a ${Math.round(fundo.alfa * 100)}% sobre \`${fundo.sobre}\``;
}

/** A tabela do DESIGN.md, gerada dos tokens: o texto e a conta não divergem. */
export function tabelaDeContraste(temas: TokensDosTemas): string {
  const linhas = [
    "| Onde | Frente | Fundo | Claro | Escuro | Mínimo |",
    "|---|---|---|---|---|---|",
  ];
  for (const par of PARES) {
    linhas.push(
      `| ${par.uso} | \`${par.frente}\` | ${descreverFundo(par.fundo)} | ` +
        `${formatarRazao(razaoDoPar(temas.claro, par))} | ` +
        `${formatarRazao(razaoDoPar(temas.escuro, par))} | ` +
        `${String(par.minimo).replace(".", ",")}:1 |`,
    );
  }
  return linhas.join("\n");
}
