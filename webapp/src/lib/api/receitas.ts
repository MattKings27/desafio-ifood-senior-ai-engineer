/**
 * Receitas: a grade automática, o detalhe, a avaliação dela e a descoberta.
 *
 * As formas de hoje (`ReceitaGuardada`, `ReceitaDaWeb`…) continuam aqui
 * enquanto a tela de preço as lê. As do contrato v1 vêm de
 * `contratos/web/receitas.json`, `receita.json`, `custo.json`,
 * `avaliacao-escrita.json`, `notas-escrita.json`, `descoberta-inicio.json` e
 * `receitas-descoberta.jsonl`.
 */

import type { Dinheiro, Imagem, OpcoesDoPedido } from "./base";
import { comCorpo, consulta, pedir, pedirComStatus, urlDeEventos } from "./base";
import type { EstadoPosse } from "./perfil";
import type { LinhaCMV } from "./preco";
import type { Veredito } from "@/lib/formato";

/* -------------------------------------------------------------------------- */
/* Formas de hoje                                                              */
/* -------------------------------------------------------------------------- */

export type ReceitaEntrada = {
  nome: string;
  ingredientes: {
    texto: string;
    nome: string;
    quantidade?: number | null;
    medida?: string;
    opcional?: boolean;
  }[];
  rendimento_porcoes?: number;
  modo_preparo?: string[];
  tempo_preparo_min?: number | null;
  /** Quanto tempo fica no fogo (ou no forno, ou com o aparelho ligado), em minutos. */
  tempo_cozimento_min?: number | null;
  url?: string | null;
  fonte?: string | null;
};

export type ReceitaGuardada = {
  nome: string;
  rendimento_porcoes: number;
  rendimento_informado: boolean;
  modo_preparo: string[];
  /** O tempo no fogo que a receita diz (ou que ela disse), em minutos. */
  tempo_cozimento_min?: number | null;
  url: string | null;
  fonte: string | null;
  ingredientes: { texto: string; nome: string; quantidade: number | null; medida: string }[];
};

export type ReceitaDaWeb = {
  receita: ReceitaGuardada;
  procedencia: { url: string; fonte: string; citacao: string };
};

/* -------------------------------------------------------------------------- */
/* Contrato v1                                                                 */
/* -------------------------------------------------------------------------- */

/** As abas da lista. O que a cozinha dela não permite não entra em nenhuma. */
export type AbaDeReceitas = "pode_fazer" | "falta_resposta" | "ranking" | "nao_quer";
export type OrdemDeReceitas = "aproveitamento" | "pontuacao" | "compra" | "tempo" | "recentes";
export type OrigemDaReceita = "descoberta" | "url_dela" | "conversa" | "dita";

/** O selo do card da grade, na língua dela ("Com o que a senhora tem"). */
export type CodigoDoSelo = "com_o_que_tem" | "comprando" | "falta_resposta";
export type SeloDaReceita = { codigo: CodigoDoSelo; texto: string };

/** A pontuação dela (0 a 100), já calculada pela API. */
export type Pontuacao = { valor: number; texto: string };
export type PontuacaoComConta = Pontuacao & { derivacao: string };

export type OpcaoDeResposta = { rotulo: string; resposta: "sim" | "nao" | "nao_sei" | (string & {}) };

/**
 * As duas leituras do peso de uma linha que pede mais (ou menos) de uma
 * unidade: o de uma ("1 colher de sopa") e o da linha inteira ("2 colheres de sopa").
 */
export type LeiturasDoPeso = { cada: string; tudo: string };

/**
 * Como a tela pede a resposta: número com unidade e limites, texto, ou o peso
 * de uma linha cuja medida não se converte (`peso`, em gramas; `peso_de` é
 * `null` quando a linha pede uma unidade só).
 */
export type EntradaDaPergunta = {
  /** `horas` é o tempo por cozinhada, com vírgula ("1,5"). */
  tipo: "inteiro" | "horas" | "texto" | "peso" | (string & {});
  unidade?: string;
  min?: number;
  max?: number;
  /** Nas horas: de quanto em quanto o + e o − andam. */
  passo?: number;
  /** Nas horas: quantas casas depois da vírgula. */
  casas?: number;
  peso_de?: LeiturasDoPeso | null;
};

/** Do que a pergunta trata: a tela escolhe onde a resposta vai sem ler o texto. */
export type AssuntoDaPergunta =
  | "linha_nao_lida"
  | "preco_de_compra"
  | "preco_da_despensa"
  | "peso_da_embalagem"
  | "medida"
  | "mesmo_ingrediente"
  | "ingrediente"
  | "rendimento"
  | "tempo_cozimento"
  | "modo_preparo"
  | "equipamento"
  | "tecnica"
  | "rotina"
  | "gosto";

/** No preço do que falta comprar: o ingrediente e quanto falta dele ("240 ml"). */
export type CompraDaPergunta = { ingrediente: string; quantidade_texto: string };

export type PerguntaDaReceita = {
  tipo: string;
  assunto: AssuntoDaPergunta;
  campo: string;
  texto: string;
  motivo: string;
  /** Só no `preco_de_compra`; nas outras, vazio. */
  compras: CompraDaPergunta[];
  opcoes: OpcaoDeResposta[];
  entrada: EntradaDaPergunta | null;
  /** Os passos da receita que pedem o que a pergunta confere. */
  passos: number[];
};

/** Um card da grade (`receitas.json#itens[]`, também em `visao-geral.json`). */
export type ItemDaGrade = {
  slug: string;
  nome: string;
  imagem: Imagem;
  /** `null` na receita que ela ditou. */
  site: string | null;
  tempo_texto: string | null;
  selo: SeloDaReceita;
  usa_texto: string;
  falta_texto: string;
  pontuacao: Pontuacao | null;
  /** O que ela disse de fazer o prato: `null` enquanto ela não disse. */
  gosta: boolean | null;
  /** Só na aba `falta_resposta`: a pergunta, respondida ali mesmo. */
  pergunta: PerguntaDaReceita | null;
  /** O que falta comprar com preço de referência (não dito por ela), com a fonte. */
  referencias: PrecoDeReferencia[];
  /**
   * "Confirme a cozinha" quando a receita dá para fazer apoiada no que toda
   * cozinha tem e ela ainda não confirmou; `null` no resto. A aba não muda.
   */
  nota_da_cozinha: string | null;
  rota: string;
};

/**
 * O preço médio em São Paulo do que falta comprar: a média do quilo (do litro,
 * da unidade) em vários supermercados de São Paulo, cada um com o preço e o
 * endereço do produto. É referência, e o preço dela sempre vale mais
 * (`POST /api/preco-mercado`).
 */
export type PrecoDeReferencia = {
  ingrediente: string;
  /** "Preço médio em São Paulo: R$ 3,32 pela caixinha de 200 g (média de 6 mercados ...); a senhora pode corrigir." */
  texto: string;
  /** "R$ 3,32 pela caixinha de 200 g, preço médio em São Paulo, 27/09/2026" */
  preco_texto: string;
  /** O produto da embalagem que ela compra. */
  produto: string;
  /** "mercado de São Paulo" (a média), ou o mercado da fonte única. */
  site: string;
  url: string;
  data_texto: string;
  /** "Preço médio em São Paulo", ou "Preço em São Paulo" com uma fonte só. */
  titulo: string;
  /** "R$ 16,60 o quilo" */
  preco_medio_texto: string;
  /** "média de 6 mercados de São Paulo: R$ 14,95, R$ 16,45, ... o quilo, em 27/09/2026" */
  media_texto: string;
  /** Cada mercado de São Paulo, com o preço e o link do produto. */
  fontes: FonteDoPreco[];
};

/** O preço de um produto num supermercado de São Paulo, com o link da página. */
export type FonteDoPreco = {
  site: string;
  produto: string;
  /** "R$ 2,99 por 200 g", ou "R$ 8,99 o quilo" no vendido a peso. */
  preco_texto: string;
  /** "R$ 14,95 o quilo" */
  por_unidade_texto: string;
  url: string;
  data_texto: string;
  /** `false`: ficou mais de 50% longe da mediana e não entrou na média. */
  na_media: boolean;
};

/**
 * O rendimento nunca é pergunta: o da receita, ou a estimativa pelo peso dos
 * ingredientes e pelo peso de uma porção. `pergunta` (só na estimativa) é o campo
 * para ela mudar, na rota da receita (`rendimento_porcoes`).
 */
export type RendimentoDaReceita = {
  porcoes: number;
  estimado: boolean;
  texto: string;
  derivacao: string;
  pergunta: PerguntaDaReceita | null;
};

/** A medida da tabela do IBGE que fez a conta de uma linha, com o jeito de corrigir. */
export type MedidaDeReferencia = {
  texto: string;
  gramas: number;
  fonte: string;
  url: string;
  /** A pergunta do peso (assunto `medida`, `entrada` de peso): o peso dela vale mais. */
  pergunta: PerguntaDaReceita;
};

export type EstadoDaDescoberta = {
  estado: "parada" | "procurando" | "erro";
  lidas: number;
  encontradas: number;
  texto: string;
};

/**
 * Uma pergunta que segura receitas, junta pelo que pergunta: a mesma pergunta da
 * cozinha (ou o preço do mesmo ingrediente) vale para várias receitas.
 * `receitas` são as que esperam por ela; `liberadas`, as que ela libera sozinha;
 * `texto` é a contagem já escrita ("libera 3 receitas").
 */
export type PerguntaQueLibera = {
  pergunta: PerguntaDaReceita;
  receitas: number;
  liberadas: number;
  /** Das que esperam por ela, as que usam só o que a Dona Maria tem. */
  sem_compra: number;
  /** "7 delas usam só o que a senhora tem"; `null` quando nenhuma usa. */
  sem_compra_texto: string | null;
  nomes: string[];
  /** Na mesma ordem de `nomes`. */
  slugs: string[];
  rota: string;
  texto: string;
};

/**
 * Em que pé estão as receitas de "Falta uma resposta sua", pela despensa: as
 * que usam só o que ela tem e esperam só a resposta dela, as que pedem compra
 * e as que têm uma linha sem leitura. `texto` é a frase pronta da API.
 */
export type EsperandoResposta = {
  receitas: number;
  so_com_o_que_tem: number;
  precisa_comprar: number;
  linha_sem_leitura: number;
  /** As que usam só o que ela tem. */
  nomes: string[];
  /** Na mesma ordem de `nomes`. */
  slugs: string[];
  /** As perguntas da cozinha que seguram essas receitas, no meio da frase. */
  falta_dizer: string[];
  texto: string;
};

/**
 * As receitas que ficaram de fora só porque o preço de um ingrediente não se
 * achou em página de supermercado: o preço não se pergunta, e sem ele não dá
 * para confirmar que a compra cabe. `texto` é a frase pronta da API.
 */
export type SemPrecoNaInternet = {
  receitas: number;
  nomes: string[];
  /** Na mesma ordem de `nomes`. */
  slugs: string[];
  texto: string;
};

export type ListaDeReceitas = {
  aba: AbaDeReceitas;
  contagens: Record<AbaDeReceitas, number>;
  itens: ItemDaGrade[];
  descoberta: EstadoDaDescoberta;
  /** As perguntas das receitas de "Falta uma resposta sua", as que mexem em mais receitas primeiro. */
  perguntas_que_liberam: PerguntaQueLibera[];
  /** `null` quando nenhuma receita espera resposta (com os mesmos filtros). */
  esperando_resposta: EsperandoResposta | null;
  /** `null` quando nenhuma receita ficou de fora por falta de preço na internet. */
  sem_preco_na_internet: SemPrecoNaInternet | null;
};

export type FiltrosDeReceitas = {
  aba?: AbaDeReceitas;
  q?: string;
  usa?: string;
  tempo_max?: number;
  so_com_o_que_tenho?: boolean;
  nota_min?: number;
  ordem?: OrdemDeReceitas;
};

export type FonteDaReceita = { site: string | null; url: string | null; autor: string | null };

export type TemposDaReceita = {
  preparo_min: number | null;
  cozimento_min: number | null;
  total_min: number | null;
  /** O tempo de fogo e de trabalho por cozinhada, sem as esperas. */
  ativo_min: number | null;
};

export type CodigoDaCozinha = CodigoDoSelo | "nao_da";

/** Só a cozinha e a despensa, sem o gosto: é o que decide a aba da grade. */
export type VereditoDaCozinha = { codigo: CodigoDaCozinha; rotulo: string; motivo: string };

/** `confirmar`: a despensa tem um item parecido, e falta ela dizer se é o mesmo. */
export type SituacaoDoIngrediente = "tem" | "tem_parte" | "falta" | "a_gosto" | "opcional" | "nao_entendi" | "confirmar";

export type IngredienteDaReceita = {
  nome: string;
  item_id: string | null;
  precisa: { texto: string };
  tem: { texto: string } | null;
  sobra: { texto: string } | null;
  situacao: SituacaoDoIngrediente;
  /** `cabe` é `null` quando o preço ainda não é conhecido. */
  compra: { texto: string; cabe: boolean | null } | null;
  /** A medida caseira da tabela do IBGE, quando foi ela que fez a conta. */
  medida_de_referencia: MedidaDeReferencia | null;
};

export type LinhaNaoEntendida = { texto: string; pergunta: string };
export type Opcional = { nome: string; texto: string };
export type AvisoDaReceita = { tipo: string; texto: string };

/** O que ela disse sobre a receita e a página não dizia (rendimento, tempo no fogo, uma linha). */
export type RespostaSobreAReceita = {
  /** `rendimento_porcoes`, `tempo_cozimento_min`, `modo_preparo`, ou o texto da linha. */
  campo: string;
  texto: string;
  quando_texto: string;
};

/** Um item de `falta_comprar.itens` (a forma de `custo.json#ingrediente_que_falta_exemplo`). */
export type IngredienteQueFalta = {
  nome: string;
  quantidade_texto: string;
  preco_conhecido: boolean;
  custo_compra: Dinheiro | null;
  custo_no_prato: Dinheiro | null;
  derivacao: string;
  origem_preco?: string;
  cabe_no_orcamento?: boolean | null;
  /** O preço de referência que cotou a compra; `null` quando o preço é dela. */
  referencia?: PrecoDeReferencia | null;
};

export type Requisito = {
  tipo: "equipamento" | "tecnica" | (string & {});
  id: string;
  nome: string;
  estado: EstadoPosse;
  suposto: boolean;
  evidencia: string;
  /** As palavras do passo que denunciaram o requisito. */
  trecho: string;
  rotulo_estado: string;
  /** O que ela tem e resolve no lugar (a air fryer do forno). */
  substituto: { id: string; nome: string } | null;
  /** Se a conferência pergunta por ele (o que toda cozinha tem, não). */
  conferido: boolean;
};

/** Um requisito que nenhum passo menciona, com a origem: "nome", "ingredientes", "receita". */
export type RequisitoDaReceita = Requisito & { origem: string };

export type LimiteDoPasso = {
  tipo: string;
  minutos: number | null;
  graus: number | null;
  texto: string;
  trecho: string;
  equipamento: string | null;
};

export type Passo = {
  ordem: number;
  texto: string;
  /**
   * A parte da receita em que o passo está, com o nome que a página mostra
   * ("Massa", "Cobertura"); `null` quando a página não dá nome à parte.
   */
  secao?: string | null;
  requisitos: Requisito[];
  limites: LimiteDoPasso[];
};

/**
 * O estado de um item do checklist de produção, do que libera ao que segura:
 * `confirmado` (ela disse, a despensa mostra, ou a receita não precisa),
 * `pre_determinado` (a plataforma pôs o valor, com a fonte, e ela muda se
 * quiser), `suposto` (toda cozinha tem e ela ainda não confirmou), `falta_saber`
 * e `nao_da`.
 */
export type StatusDoChecklist = "confirmado" | "pre_determinado" | "suposto" | "falta_saber" | "nao_da";

/** De onde veio o que o item diz. O texto para ela vem pronto em `origem_texto`. */
export type OrigemDoChecklist = "a_senhora_disse" | "suposto" | "referencia" | "receita";

/** Uma linha do checklist de produção (`receita.json#checklist.grupos[].itens[]`). */
export type ItemDoChecklist = {
  id: string;
  /** `equipamento`, `tecnica`, `rotina`, `ingrediente`, `compra`, `orcamento`, `porcoes`, `peso`, `preco` ou `modo_preparo`. */
  tipo: string;
  nome: string;
  detalhe: string | null;
  status: StatusDoChecklist;
  /** O estado dito para ela ("confirmado pela senhora", "suposto: confirme", "não precisa"). */
  status_texto: string;
  origem: OrigemDoChecklist;
  /** "a senhora disse", "suposto", "referência de medidas do IBGE", "receita". */
  origem_texto: string;
  /** O que ela responde ali mesmo, na forma de `perguntas[]`; `null` quando não há o que responder. */
  pergunta: PerguntaDaReceita | null;
  /** No pré-determinado: como ela muda o valor, na mesma forma da pergunta. */
  editar: PerguntaDaReceita | null;
};

export type GrupoDoChecklist = {
  id: "equipamentos" | "tecnicas" | "rotina" | "ingredientes" | "pre_determinados" | (string & {});
  titulo: string;
  /** O estado do pior item do grupo. */
  status: StatusDoChecklist;
  itens: ItemDoChecklist[];
  /** O que dizer quando a receita não pede nada do grupo. */
  vazio_texto: string;
};

/** Um item que toda cozinha tem e ela ainda não confirmou. */
export type ItemAConfirmar = { tipo: "equipamento" | "tecnica"; id: string; nome: string };

/** A pergunta de confirmar a cozinha, uma só, e os itens que ela confirma de uma vez. */
export type ConfirmarACozinha = { pergunta: string; itens: ItemAConfirmar[] };

/**
 * O checklist de produção: tudo o que precisa estar certo antes do aceite,
 * grupo por grupo. `pode_aceitar` e `falta_para_aceitar` saem prontos da API.
 */
export type ChecklistDeProducao = {
  titulo: string;
  pode_aceitar: boolean;
  resumo: string;
  /** Cada coisa que segura o aceite, dita para ela; vazia quando ela pode aceitar. */
  falta_para_aceitar: string[];
  /** `null` quando a receita não se apoia em nada que ela ainda não confirmou. */
  confirmar_a_cozinha: ConfirmarACozinha | null;
  grupos: GrupoDoChecklist[];
};

export type CategoriaDeEstrela = "sabor" | "facilidade" | "tempo" | "entrega" | "apelo";

export type AvaliacaoDaReceita = {
  gosta: boolean | null;
  /** De 1 a 5; `null` onde ela não deu estrela. */
  estrelas: Record<CategoriaDeEstrela, number | null>;
  notas: string;
  pontuacao: PontuacaoComConta | null;
};

export type DetalheDaReceita = {
  slug: string;
  nome: string;
  imagem: Imagem;
  fonte: FonteDaReceita;
  origem: OrigemDaReceita;
  tempos: TemposDaReceita;
  tempo_texto: string | null;
  rendimento_texto: string | null;
  /** Quantas porções rende: o que a receita diz, ou a estimativa pelo peso, que ela muda. */
  rendimento: RendimentoDaReceita | null;
  /** Valor técnico, com o gosto dela. A tela mostra `veredito_rotulo`. */
  veredito: Veredito;
  veredito_rotulo: string;
  veredito_da_cozinha: VereditoDaCozinha;
  resumo: string;
  ingredientes: IngredienteDaReceita[];
  linhas_nao_entendidas: LinhaNaoEntendida[];
  opcionais: Opcional[];
  avisos: AvisoDaReceita[];
  falta_comprar: {
    itens: IngredienteQueFalta[];
    /** `null` quando falta o preço de algum item. */
    custo: Dinheiro | null;
    cabe_no_orcamento: boolean | null;
    texto: string;
  };
  custo_porcao: Dinheiro | null;
  pode_precificar: boolean;
  passos: Passo[];
  requisitos_da_receita: RequisitoDaReceita[];
  perguntas: PerguntaDaReceita[];
  avaliacao: AvaliacaoDaReceita;
  posicao_no_ranking: number | null;
  /** O que ela respondeu sobre a receita, anotado como dito por ela. */
  respostas: RespostaSobreAReceita[];
  rascunho_chat: string;
  /** O checklist de produção: o que precisa estar certo antes do aceite. */
  checklist: ChecklistDeProducao;
  rota: string;
};

/**
 * O corpo do POST da resposta a uma pergunta da própria receita (a da grade, ali
 * mesmo). No peso de uma linha, `por_unidade` diz se é o de uma unidade (`true`)
 * ou o da linha inteira (`false`).
 */
export type RespostaDaReceita = { campo: string; resposta: string; por_unidade?: boolean };

/** O corpo do PUT da avaliação: só o que mudou; `null` apaga. */
export type AvaliacaoEnviada = {
  gosta?: boolean | null;
  estrelas?: Partial<Record<CategoriaDeEstrela, number | null>>;
};

export type RespostaDaAvaliacao = {
  slug: string;
  nome: string;
  avaliacao: AvaliacaoDaReceita;
  posicao_no_ranking: number | null;
  atualizado_texto: string;
  texto: string;
};

export type RespostaDasNotas = { slug: string; notas: string; atualizado_texto: string; texto: string };

/** A receita trazida pelo endereço: `nova` quando o servidor leu agora (201), não quando já conhecia (200). */
export type ReceitaTrazida = { receita: DetalheDaReceita; nova: boolean };

/**
 * O custo de uma porção (`custo.json`): cada linha com a conta, o que vai a
 * gosto e a explicação. Receita que a conferência não libera é recusada (409).
 */
export type CustoDaPorcao = {
  prato: string;
  rendimento_original: number;
  /** A faixa entre `minimo` e `maximo` quando algum peso é estimado. */
  e_faixa: boolean;
  total: Dinheiro;
  minimo: Dinheiro;
  maximo: Dinheiro;
  linhas: LinhaCMV[];
  itens_a_gosto: string[];
  explicacao: string;
};

export type InicioDaDescoberta = {
  execucao_id: string;
  estado: EstadoDaDescoberta["estado"];
  texto: string;
  /** O fluxo desta rodada, na API (`/api/receitas/descoberta/eventos?execucao=`). */
  eventos: string;
};

export type EventoDaDescoberta =
  | { seq: number; tipo: "progresso"; etapa: string; texto: string; lidas: number; encontradas: number }
  | { seq: number; tipo: "receita.encontrada" | "receita.atualizada"; aba: AbaDeReceitas; receita: ItemDaGrade }
  | { seq: number; tipo: "fim"; estado: EstadoDaDescoberta["estado"]; lidas: number; encontradas: number; texto: string }
  | { seq: number; tipo: "erro"; texto: string; categoria?: string };

const daReceita = (slug: string) => `/receitas/${encodeURIComponent(slug)}`;

export const receitas = {
  listar: (filtros: FiltrosDeReceitas = {}, opcoes?: OpcoesDoPedido) =>
    pedir<ListaDeReceitas>(`/receitas${consulta(filtros)}`, opcoes),

  /** O detalhe, com a conferência dentro: pôr preço numa receita é pela conversa. */
  detalhe: (slug: string, opcoes?: OpcoesDoPedido) => pedir<DetalheDaReceita>(daReceita(slug), opcoes),

  /** Trazer uma receita pelo endereço. Buscar a página pode levar alguns segundos. */
  trazer: async (url: string): Promise<ReceitaTrazida> => {
    const { dados, status } = await pedirComStatus<DetalheDaReceita>("/receitas", {
      ...comCorpo("POST", { url }),
      tempoLimiteMs: 60_000,
    });
    return { receita: dados, nova: status === 201 };
  },

  avaliar: (slug: string, avaliacao: AvaliacaoEnviada) =>
    pedir<RespostaDaAvaliacao>(`${daReceita(slug)}/avaliacao`, comCorpo("PUT", avaliacao)),

  salvarNotas: (slug: string, texto: string) =>
    pedir<RespostaDasNotas>(`${daReceita(slug)}/notas`, comCorpo("PUT", { texto })),

  /** A resposta a uma pergunta da receita (rendimento, tempo no fogo, uma linha): volta o detalhe. */
  responder: (slug: string, resposta: RespostaDaReceita) =>
    pedir<DetalheDaReceita>(`${daReceita(slug)}/resposta`, comCorpo("POST", resposta)),

  /** O custo por porção. Passa pela conferência: receita que não dá, não tem custo. */
  custo: (slug: string, opcoes?: OpcoesDoPedido) => pedir<CustoDaPorcao>(`${daReceita(slug)}/custo`, opcoes),

  /** Pede uma rodada de descoberta ("Procurar mais receitas"). */
  descobrir: () => pedir<InicioDaDescoberta>("/receitas/descoberta", comCorpo("POST")),

  /** O fluxo de eventos da descoberta (SSE), com a retomada por `desde`. */
  urlDaDescoberta: (desde?: number) => urlDeEventos("/receitas/descoberta/eventos", desde),

  /**
   * O fluxo de uma rodada (`InicioDaDescoberta.eventos`, que a API escreve com
   * `/api/`), pelo proxy do navegador. Um endereço fora do fluxo da descoberta
   * vira o fluxo geral: a tela nunca abre um endereço que não conhece.
   */
  urlDaRodada: (eventos: string, desde?: number): string => {
    const [caminho = "", busca = ""] = eventos.split("?", 2);
    if (caminho !== "/api/receitas/descoberta/eventos") return urlDeEventos("/receitas/descoberta/eventos", desde);
    const parametros = new URLSearchParams(busca);
    if (desde !== undefined) parametros.set("desde", String(desde));
    const texto = parametros.toString();
    return `/motor/receitas/descoberta/eventos${texto ? `?${texto}` : ""}`;
  },
} as const;

/* -------------------------------------------------------------------------- */
/* Rotas de hoje                                                               */
/* -------------------------------------------------------------------------- */

export const receitasDeHoje = {
  /** Uma receita já avaliada, para a tela de preço abrir preenchida. */
  receita: (prato: string) => pedir<ReceitaGuardada>(`/receita?prato=${encodeURIComponent(prato)}`),

  /** Uma receita da internet, pelo endereço. Só endereço público. */
  receitaDaWeb: (url: string, fonte = "") =>
    pedir<ReceitaDaWeb>("/receita-da-web", {
      method: "POST",
      body: JSON.stringify({ url, fonte }),
      tempoLimiteMs: 60_000,
    }),
} as const;
