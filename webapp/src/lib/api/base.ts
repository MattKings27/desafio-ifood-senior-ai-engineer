/**
 * O transporte até a API: envelope, categorias de erro, tempo limite.
 *
 * Regra que organiza esta pasta: **a interface não calcula nada.** Todo valor
 * em reais vem da API já resolvido, com o texto em pt-BR junto. Fazer a conta
 * aqui criaria um segundo lugar onde o número pode estar errado, e o segundo
 * lugar é sempre o que ninguém testa.
 *
 * Cada domínio tem o seu arquivo (`despensa.ts`, `receitas.ts`…). Este guarda
 * só o que todos compartilham.
 */

export type Dinheiro = {
  /** Número para desenhar gráfico, ordenar e filtrar. Nunca para formatar nem somar. */
  valor: number;
  /** Texto já em pt-BR: `R$ 1.234,56`. É isto que aparece na tela. */
  texto: string;
};

/** Imagem sempre servida pela API (`/motor/imagens/<chave>`), com o crédito. */
export type Imagem = { url: string; credito: string } | null;

/** O único endereço de foto que a interface carrega: chave hexadecimal da API. */
export const ENDERECO_DE_IMAGEM = /^\/motor\/imagens\/[0-9a-f]{8,64}$/;

/** Só o que a API serve é foto. Qualquer outro endereço é "sem foto". */
export function ehImagemDaApi(src: string | null | undefined): src is string {
  return typeof src === "string" && ENDERECO_DE_IMAGEM.test(src);
}

/**
 * O que fazer depois de um erro depende da categoria:
 * - `dado`: falta uma informação, e vem a pergunta que destrava;
 * - `regra`: recusa deliberada (ex.: preço antes de confirmar que dá pra fazer);
 * - `uso`: o pedido não bate com o que a API espera;
 * - `ausente`: o item, a receita ou a conversa não existe (404);
 * - `tempo`: a resposta não chegou a tempo;
 * - `rede`: não houve conversa com a API (fora do ar, conexão, 5xx).
 */
export type CategoriaDeErro = "dado" | "regra" | "uso" | "ausente" | "tempo" | "rede";

/** O envelope que a API sempre devolve: sucesso e erro com a mesma forma. */
export type Envelope<T> = {
  ok: boolean;
  dados: T | null;
  erro: string | null;
  categoria: CategoriaDeErro | null;
  /** Presente quando a API recusou por falta de dado: é a pergunta a fazer. */
  pergunta: string | null;
};

/** O tempo que uma leitura comum espera antes de desistir. */
export const TEMPO_LIMITE_PADRAO_MS = 15_000;

/** As mensagens que ela lê quando a culpa é do caminho, não do pedido. */
export const MENSAGENS = {
  rede: "Não consegui falar com o sistema agora. Confira a internet e tente de novo em instantes.",
  tempo: "A resposta demorou demais para chegar. Tente de novo.",
  uso: "O pedido saiu incompleto. Confira o que foi preenchido e tente de novo.",
  ausente: "Não encontrei o que a senhora procurou. Pode ter sido tirado.",
  semMotivo: "O sistema recusou sem dizer o motivo.",
} as const;

/**
 * Erro da API, já com a categoria que diz o que fazer a seguir.
 *
 * `message` é sempre texto que pode ir para a tela dela. O detalhe técnico,
 * quando existe, fica em `detalhe`, para o console e para quem investiga.
 */
export class ErroDoMotor extends Error {
  constructor(
    message: string,
    readonly categoria: CategoriaDeErro,
    readonly pergunta?: string,
    readonly detalhe?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ErroDoMotor";
  }
}

/**
 * No navegador vale o proxy do Next (`/motor/*` → API), que evita CORS e
 * mantém origem única. No servidor não existe origem relativa, então falamos
 * direto com a API. Resolver isso aqui deixa o resto do código indiferente a
 * onde está rodando.
 */
export function base(): string {
  if (typeof window !== "undefined") return "/motor";
  return `${process.env.MISE_API ?? "http://127.0.0.1:8777"}/api`;
}

type ValorDeConsulta = string | number | boolean | null | undefined | readonly (string | number)[];

/** Monta `?a=1&b=2`, pulando o vazio. Listas viram a chave repetida. */
export function consulta(parametros: Record<string, ValorDeConsulta>): string {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) {
    if (valor === undefined || valor === null || valor === "" || valor === false) continue;
    if (Array.isArray(valor)) {
      for (const item of valor) busca.append(chave, String(item));
      continue;
    }
    busca.set(chave, valor === true ? "true" : String(valor));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

export type OpcoesDoPedido = RequestInit & {
  /** Quanto esperar antes de desistir. Padrão: 15 s. `0` desliga o limite. */
  tempoLimiteMs?: number;
};

function sinalCom(
  tempoLimiteMs: number | undefined,
  doChamador: AbortSignal | null | undefined,
): { sinal?: AbortSignal; doLimite?: AbortSignal } {
  const limite = tempoLimiteMs ?? TEMPO_LIMITE_PADRAO_MS;
  const doLimite = limite > 0 ? AbortSignal.timeout(limite) : undefined;
  const sinais = [doChamador, doLimite].filter((s): s is AbortSignal => Boolean(s));
  if (sinais.length === 0) return {};
  if (sinais.length === 1) return { sinal: sinais[0], doLimite };
  return { sinal: AbortSignal.any(sinais), doLimite };
}

function categoriaDoStatus(status: number): CategoriaDeErro {
  if (status === 404) return "ausente";
  if (status === 408 || status === 504) return "tempo";
  if (status === 409 || status === 422 || (status >= 400 && status < 500)) return "uso";
  return "rede";
}

export function ehEnvelope(corpo: unknown): corpo is Envelope<unknown> {
  return typeof corpo === "object" && corpo !== null && "ok" in corpo && "dados" in corpo;
}

/** O `detail` do FastAPI (texto, ou a lista de erros de validação). */
function detalheDe(corpo: unknown): string | undefined {
  if (typeof corpo !== "object" || corpo === null || !("detail" in corpo)) return undefined;
  const { detail } = corpo as { detail: unknown };
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}

/** O corpo JSON da resposta, ou `null` quando não há JSON para ler. */
export async function lerCorpo(resposta: Response): Promise<unknown> {
  try {
    return await resposta.json();
  } catch {
    return null;
  }
}

/** Converte uma resposta de erro (status fora de 2xx) no ErroDoMotor certo. */
export async function erroDaResposta(resposta: Response): Promise<ErroDoMotor> {
  const corpo = await lerCorpo(resposta);
  const status = resposta.status;

  // A API nova responde erro de domínio no próprio envelope, com status HTTP.
  if (ehEnvelope(corpo) && (corpo.erro || corpo.categoria)) {
    const categoria = corpo.categoria ?? categoriaDoStatus(status);
    return new ErroDoMotor(
      corpo.erro ?? MENSAGENS.semMotivo,
      categoria,
      corpo.pergunta ?? undefined,
      `HTTP ${status}`,
      status,
    );
  }

  const categoria = categoriaDoStatus(status);
  const detalhe = [`HTTP ${status}`, detalheDe(corpo)].filter(Boolean).join(": ");
  const mensagem =
    categoria === "ausente"
      ? MENSAGENS.ausente
      : categoria === "tempo"
        ? MENSAGENS.tempo
        : categoria === "uso"
          ? MENSAGENS.uso
          : MENSAGENS.rede;
  return new ErroDoMotor(mensagem, categoria, undefined, detalhe, status);
}

function ehAborto(causa: unknown, nome: "TimeoutError" | "AbortError"): boolean {
  return typeof causa === "object" && causa !== null && (causa as { name?: unknown }).name === nome;
}

/**
 * O `fetch` com tempo limite e as falhas de caminho já traduzidas: tempo
 * esgotado vira `tempo`, sem conexão vira `rede`. O cancelamento pedido por
 * quem chamou (`signal`) volta como veio, para ser ignorado em silêncio.
 */
export async function buscar(caminho: string, opcoes: OpcoesDoPedido = {}): Promise<Response> {
  const { tempoLimiteMs, ...init } = opcoes;
  const { sinal, doLimite } = sinalCom(tempoLimiteMs, init.signal);
  try {
    return await fetch(`${base()}${caminho}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
      ...(sinal ? { signal: sinal } : {}),
    });
  } catch (causa) {
    if (doLimite?.aborted || ehAborto(causa, "TimeoutError")) {
      throw Object.assign(new ErroDoMotor(MENSAGENS.tempo, "tempo", undefined, String(causa)), {
        cause: causa,
      });
    }
    if (init.signal?.aborted || ehAborto(causa, "AbortError")) throw causa;
    // A causa original vai encadeada: sem ela, "não consegui falar" esconde se
    // foi DNS, recusa de conexão ou timeout.
    throw Object.assign(new ErroDoMotor(MENSAGENS.rede, "rede", undefined, String(causa)), {
      cause: causa,
    });
  }
}

/**
 * Faz o pedido e abre o envelope, guardando o status HTTP (o 201 de "criei
 * agora" e o 200 de "já existia" dizem coisas diferentes a ela). Qualquer
 * falha vira ErroDoMotor, com uma mensagem que pode ir para a tela.
 */
export async function pedirComStatus<T>(
  caminho: string,
  opcoes: OpcoesDoPedido = {},
): Promise<{ dados: T; status: number }> {
  const resposta = await buscar(caminho, opcoes);
  if (!resposta.ok) throw await erroDaResposta(resposta);

  const corpo = await lerCorpo(resposta);
  if (!ehEnvelope(corpo)) {
    throw new ErroDoMotor(MENSAGENS.rede, "rede", undefined, "resposta sem envelope", resposta.status);
  }
  const envelope = corpo as Envelope<T>;
  if (!envelope.ok || envelope.dados === null) {
    throw new ErroDoMotor(
      envelope.erro ?? MENSAGENS.semMotivo,
      envelope.categoria ?? "uso",
      envelope.pergunta ?? undefined,
      undefined,
      resposta.status,
    );
  }
  return { dados: envelope.dados, status: resposta.status };
}

/** Faz o pedido e devolve só os dados do envelope. */
export async function pedir<T>(caminho: string, opcoes: OpcoesDoPedido = {}): Promise<T> {
  return (await pedirComStatus<T>(caminho, opcoes)).dados;
}

/**
 * A API não atende este pedido aqui: a rota não existe (404), o caminho só
 * casa com uma rota de outro método (405) ou o recurso está desligado neste
 * ambiente (501, como a descoberta de receitas desligada). A tela troca a ação
 * por um caminho que já funciona, em vez de mostrar erro.
 */
export function ehRotaQueFalta(causa: unknown): boolean {
  return causa instanceof ErroDoMotor && (causa.status === 404 || causa.status === 405 || causa.status === 501);
}

/** Um corpo JSON para POST/PUT/PATCH. */
export function comCorpo(metodo: "POST" | "PUT" | "PATCH" | "DELETE", corpo?: unknown): RequestInit {
  return corpo === undefined ? { method: metodo } : { method: metodo, body: JSON.stringify(corpo) };
}

/** Texto puro (ex.: a planilha em TXT), sem envelope. */
export async function pedirTexto(caminho: string, opcoes: OpcoesDoPedido = {}): Promise<string> {
  const resposta = await buscar(caminho, opcoes);
  if (!resposta.ok) throw await erroDaResposta(resposta);
  return resposta.text();
}

/** O endereço de um fluxo de eventos (SSE) no navegador, com a retomada. */
export function urlDeEventos(caminho: string, desde?: number): string {
  return `/motor${caminho}${desde === undefined ? "" : consulta({ desde })}`;
}
