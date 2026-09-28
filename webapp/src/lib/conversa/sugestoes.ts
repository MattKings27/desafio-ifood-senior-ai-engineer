/**
 * As sugestões de resposta rápida e as de começo de conversa, por tela.
 *
 * A ordem de quem manda nos chips acima da caixa (plano, 9.4):
 * 1. as sugestões que o backend mandou no fim do último turno;
 * 2. as tiradas do último card da resposta (o mesmo catálogo do backend,
 *    `sugestoes_para`, para quando o turno não trouxe sugestão);
 * 3. as de começo de conversa da página em que ela está.
 */

import type { AcaoDoCartao, ContextoDaConversa, OpcaoSugerida } from "@/lib/api/conversa";
import type { CategoriaDeEstrela } from "@/lib/api/receitas";

import { ehTipoDeCartao } from "./cartoes";
import { emMinusculas } from "./perguntas";

export type Tela =
  | "inicio"
  | "despensa"
  | "receitas"
  | "cozinha"
  | "precificar"
  | "cardapio"
  | "historico"
  | "conversa";

const TELAS: readonly [string, Tela][] = [
  ["/despensa", "despensa"],
  ["/receitas", "receitas"],
  ["/cozinha", "cozinha"],
  ["/precificar", "precificar"],
  ["/cardapio", "cardapio"],
  ["/trilha", "historico"],
  ["/conversa", "conversa"],
];

/** A tela de um caminho: "/despensa/alcaparras" → "despensa"; "/" → "inicio". */
export function telaDoCaminho(caminho: string | null | undefined): Tela {
  const limpo = (caminho ?? "/").split(/[?#]/)[0] ?? "/";
  for (const [prefixo, tela] of TELAS) {
    if (limpo === prefixo || limpo.startsWith(`${prefixo}/`)) return tela;
  }
  return limpo === "/" ? "inicio" : "conversa";
}

/** O nome de cada tela, como ela lê no menu (e no chip "Vendo: Despensa"). */
export const ROTULO_DA_TELA: Readonly<Record<Tela, string>> = {
  inicio: "Início",
  despensa: "Despensa",
  receitas: "Receitas",
  cozinha: "Cozinha",
  precificar: "Pôr preço",
  cardapio: "Cardápio",
  historico: "Histórico",
  conversa: "Conversa",
};

/** O contexto de "de onde ela abriu": a tela, quando não é a própria conversa. */
export function contextoDaTela(caminho: string | null | undefined): ContextoDaConversa | undefined {
  const tela = telaDoCaminho(caminho);
  if (tela === "conversa") return undefined;
  return { tela, tipo: "tela", id: tela, rotulo: ROTULO_DA_TELA[tela] };
}

/** As páginas de detalhe que dizem, pelo endereço, o que ela está olhando. */
const DETALHES: Readonly<Record<string, { tela: Tela; tipo: string }>> = {
  despensa: { tela: "despensa", tipo: "ingrediente" },
  receitas: { tela: "receitas", tipo: "receita" },
};

/**
 * O contexto da página inteira: numa página de detalhe
 * (`/despensa/arroz-branco-tipo-1`), o item que ela está olhando, com o nome
 * que a página mostra no título; nas outras, a tela. O backend confere o id e
 * usa o nome dele: o rótulo daqui serve só para o chip "Vendo: …".
 */
export function contextoDaPagina(
  caminho: string | null | undefined,
  tituloDaPagina?: string | null,
): ContextoDaConversa | undefined {
  const daTela = contextoDaTela(caminho);
  if (!daTela) return undefined;
  const partes = ((caminho ?? "/").split(/[?#]/)[0] ?? "/").split("/").filter(Boolean);
  const detalhe = partes.length === 2 ? DETALHES[partes[0] ?? ""] : undefined;
  if (!detalhe) return daTela;
  let id: string;
  try {
    id = decodeURIComponent(partes[1] ?? "");
  } catch {
    return daTela;
  }
  const titulo = tituloDaPagina?.replace(/\s+/g, " ").trim();
  return {
    tela: detalhe.tela,
    tipo: detalhe.tipo,
    id,
    rotulo: titulo && titulo.length <= 120 ? titulo : (daTela.rotulo ?? ROTULO_DA_TELA[detalhe.tela]),
  };
}

/** O que o chip de contexto mostra: o rótulo, ou o nome da tela. */
export function rotuloDoContexto(contexto: ContextoDaConversa): string {
  const rotulo = contexto.rotulo?.trim();
  if (rotulo) return rotulo;
  const tela = contexto.tela as Tela;
  return ROTULO_DA_TELA[tela] ?? "esta tela";
}

const COMECOS: Readonly<Record<Tela, readonly OpcaoSugerida[]>> = {
  inicio: [
    { rotulo: "Por onde eu começo?", texto: "Por onde eu começo?" },
    { rotulo: "O que dá pra fazer?", texto: "O que dá pra fazer com o que eu já tenho?" },
    { rotulo: "Dinheiro parado", texto: "Onde está o meu dinheiro parado na despensa?" },
  ],
  despensa: [
    { rotulo: "Dinheiro parado", texto: "Onde está o meu dinheiro parado na despensa?" },
    { rotulo: "Receitas com o que tenho", texto: "Que receitas aproveitam o que está parado na despensa?" },
    { rotulo: "Quanto sobra do orçamento?", texto: "Quanto ainda sobra do orçamento das compras?" },
  ],
  receitas: [
    { rotulo: "O que dá pra fazer hoje?", texto: "Quais receitas dão pra fazer hoje, com o que eu tenho?" },
    { rotulo: "Outra receita", texto: "Me mostra outra receita com o que eu tenho." },
    { rotulo: "Qual aproveita mais?", texto: "Qual das receitas aproveita mais o que eu tenho?" },
  ],
  cozinha: [
    { rotulo: "O que falta saber?", texto: "O que ainda falta saber da minha cozinha?" },
    { rotulo: "Sem forno", texto: "Sem forno, o que eu consigo fazer?" },
  ],
  precificar: [
    { rotulo: "Quanto cobrar?", texto: "Quanto eu cobro por porção?" },
    { rotulo: "A taxa do aplicativo", texto: "Me explica como a taxa do aplicativo entra no preço." },
  ],
  cardapio: [
    { rotulo: "Como está o cardápio?", texto: "Como ficou o meu cardápio?" },
    { rotulo: "Mudar um preço", texto: "Quero mudar o preço de um prato." },
  ],
  historico: [{ rotulo: "O que já decidimos?", texto: "O que a gente já decidiu até agora?" }],
  conversa: [
    { rotulo: "O que dá pra fazer?", texto: "O que dá pra fazer com o que eu já tenho?" },
    { rotulo: "Quanto cobrar?", texto: "Quanto eu devo cobrar pelos meus pratos?" },
    { rotulo: "Dinheiro parado", texto: "Onde está o meu dinheiro parado na despensa?" },
    { rotulo: "Montar o cardápio", texto: "Me ajuda a montar o meu cardápio?" },
  ],
};

/** As sugestões de começo de conversa da tela em que ela está. */
export function sugestoesDaTela(caminho: string | null | undefined): readonly OpcaoSugerida[] {
  return COMECOS[telaDoCaminho(caminho)];
}

/* -------------------------------------------------------------------------- */
/* Validação do que vem de fora                                                */
/* -------------------------------------------------------------------------- */

function objeto(valor: unknown): Record<string, unknown> | null {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor)
    ? (valor as Record<string, unknown>)
    : null;
}

function textoCurto(valor: unknown, maximo: number): string | null {
  if (typeof valor !== "string") return null;
  const limpo = valor.replace(/\s+/g, " ").trim();
  return limpo && limpo.length <= maximo ? limpo : null;
}

/** Uma ação de botão vinda do backend, se tiver a forma de uma das três. */
export function acaoValida(bruta: unknown): AcaoDoCartao | undefined {
  const acao = objeto(bruta);
  if (!acao) return undefined;
  if (acao.tipo === "responder") {
    const { tipo_pergunta, campo, resposta, receita_id } = acao;
    if (typeof tipo_pergunta === "string" && typeof campo === "string" && typeof resposta === "string") {
      const daReceita = typeof receita_id === "string" && receita_id ? { receita_id } : {};
      return { tipo: "responder", tipo_pergunta, campo, resposta, ...daReceita };
    }
    return undefined;
  }
  if (acao.tipo === "decidir") {
    const { prato, decisao, preco } = acao;
    if (typeof prato !== "string" || typeof decisao !== "string") return undefined;
    if (preco !== undefined && (typeof preco !== "number" || !Number.isFinite(preco))) return undefined;
    return preco === undefined ? { tipo: "decidir", prato, decisao } : { tipo: "decidir", prato, decisao, preco };
  }
  if (acao.tipo === "avaliar" && typeof acao.receita_id === "string") {
    return avaliacaoValida(acao.receita_id, acao);
  }
  return undefined;
}

const CATEGORIAS_DE_ESTRELA: readonly CategoriaDeEstrela[] = ["sabor", "facilidade", "tempo", "entrega", "apelo"];

/** A avaliação de uma receita: só o que tem a forma certa segue (estrela de 1 a 5, ou `null`). */
function avaliacaoValida(receita_id: string, acao: Record<string, unknown>): AcaoDoCartao {
  const valida: AcaoDoCartao & { tipo: "avaliar" } = { tipo: "avaliar", receita_id };
  if (typeof acao.gosta === "boolean" || acao.gosta === null) valida.gosta = acao.gosta;
  if (typeof acao.notas === "string") valida.notas = acao.notas;
  const estrelas = objeto(acao.estrelas);
  if (estrelas) {
    const dadas: Partial<Record<CategoriaDeEstrela, number | null>> = {};
    for (const categoria of CATEGORIAS_DE_ESTRELA) {
      const valor = estrelas[categoria];
      if (valor === null || (typeof valor === "number" && Number.isInteger(valor) && valor >= 1 && valor <= 5)) {
        dadas[categoria] = valor;
      }
    }
    valida.estrelas = dadas;
  }
  return valida;
}

/** As opções de resposta rápida válidas (rótulo e texto curtos), no máximo quatro. */
export function opcoesValidas(brutas: unknown): OpcaoSugerida[] {
  if (!Array.isArray(brutas)) return [];
  const validas: OpcaoSugerida[] = [];
  for (const bruta of brutas) {
    const opcao = objeto(bruta);
    const rotulo = textoCurto(opcao?.rotulo, 60);
    const texto = textoCurto(opcao?.texto, 500);
    if (!opcao || !rotulo || !texto) continue;
    const acao = acaoValida(opcao.acao);
    validas.push(acao ? { rotulo, texto, acao } : { rotulo, texto });
    if (validas.length === 4) break;
  }
  return validas;
}

/* -------------------------------------------------------------------------- */
/* Chips tirados do último card                                                */
/* -------------------------------------------------------------------------- */

const QUANTO_COBRAR: OpcaoSugerida = { rotulo: "Quanto cobrar?", texto: "Quanto eu cobro por porção?" };
const OUTRO_PRECO: OpcaoSugerida = { rotulo: "Quero outro preço", texto: "Quero ver a conta com outro preço." };

const FIXAS: Readonly<Record<string, readonly OpcaoSugerida[]>> = {
  cenarios: [OUTRO_PRECO, { rotulo: "Vou pensar", texto: "Vou pensar um pouco antes de decidir o preço." }],
  custo_porcao: [QUANTO_COBRAR],
  receita: [
    { rotulo: "Dá pra eu fazer?", texto: "Dá pra eu fazer essa receita?" },
    { rotulo: "Outra receita", texto: "Me mostra outra receita com o que eu tenho." },
  ],
  comparacao: [{ rotulo: "Qual aproveita mais?", texto: "Qual delas aproveita mais o que eu tenho?" }],
  despensa_resumo: [
    { rotulo: "Receitas com isso", texto: "Que receitas aproveitam o que está parado na despensa?" },
  ],
  decisao: [{ rotulo: "Ver o cardápio", texto: "Como ficou o meu cardápio?" }],
  orcamento: [{ rotulo: "O que dá pra comprar?", texto: "O que dá pra comprar com o que sobrou?" }],
  preco_preliminar: [{ rotulo: "Refinar a conta", texto: "Vamos refinar essa estimativa?" }],
};

type CartaoParaChips = { tipo: string; dados: unknown; ref?: { parametros?: Record<string, unknown> } };

/** As respostas rápidas que um card sugere (o mesmo catálogo do backend). */
export function chipsDoCartao(cartao: CartaoParaChips | null | undefined): OpcaoSugerida[] {
  if (!cartao || !ehTipoDeCartao(cartao.tipo)) return [];
  const dados = objeto(cartao.dados) ?? {};
  switch (cartao.tipo) {
    case "pergunta":
      return opcoesValidas(dados.opcoes);
    case "ponto_de_preco": {
      const { prato, preco } = cartao.ref?.parametros ?? {};
      if (typeof prato === "string" && typeof preco === "number") {
        return [
          {
            rotulo: "Vou cobrar este preço",
            texto: "Vou cobrar este preço.",
            acao: { tipo: "decidir", prato, decisao: "aceito", preco },
          },
          OUTRO_PRECO,
        ];
      }
      return [OUTRO_PRECO];
    }
    case "viabilidade":
      return dados.pode_precificar === true ? [QUANTO_COBRAR] : [];
    case "ingrediente": {
      const nome = textoCurto(dados.nome, 80);
      return nome ? [{ rotulo: "Receitas com ele", texto: `Que receitas usam ${emMinusculas(nome)}?` }] : [];
    }
    default:
      return [...(FIXAS[cartao.tipo] ?? [])];
  }
}
