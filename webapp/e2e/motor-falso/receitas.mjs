/* global structuredClone, URL */
/**
 * As receitas do motor falso: um catálogo em memória, que começa com as
 * receitas dos contratos (`receitas.json` e `receita.json`) e muda como a API
 * de verdade muda: trazer pelo endereço, avaliar, anotar, responder a pergunta
 * da receita, dizer o preço do que falta e procurar mais receitas. A grade de
 * cada aba sai das mesmas regras do `LEIA.md`: só o que ela consegue fazer, a
 * aba decidida pela cozinha sem o gosto, "não quer" à parte.
 *
 * **A receita trazida pelo endereço sai do próprio endereço**, para os testes
 * montarem o caso de que precisam sem rota de controle. O último pedaço do
 * caminho dá o nome, e uma marca no fim dá a situação:
 *
 *     .../pudim-de-leite-x1-com-o-que-tem   dá com o que ela tem
 *     ...-comprando         dá comprando milho verde (R$ 6,00, cabe)
 *     ...-falta-tempo       falta o tempo no fogo (resposta sobre a receita)
 *     ...-falta-rendimento  falta quantas porções rende
 *     ...-falta-linha       uma linha dos ingredientes que a leitura não entendeu
 *     ...-falta-medida      falta o peso de uma linha (as colheres de alcaparras)
 *     ...-falta-preco       falta o preço do creme de leite
 *     ...-falta-forno       falta saber se ela tem forno (a cozinha)
 *     ...-falta-bocas       falta saber quantas bocas tem o fogão
 *     ...-falta-preparo     falta o modo de preparo (só pela conversa)
 *     ...-nao-da            a cozinha dela não dá conta: não entra em aba nenhuma
 *     ...-supostos          dá com o que ela tem, apoiada no fogão e no refogar que ela não confirmou
 *     ...-sem-receita       a página não traz receita estruturada (recusa)
 *     ...-sem-foto          sem foto (o card mostra o gradiente)
 *
 * Os testes rodam em paralelo contra o mesmo motor: cada um põe um marcador
 * único no nome e filtra a grade por ele (`q`), e não enxerga as receitas dos
 * outros. A pergunta da cozinha (forno, bocas) se resolve pelo perfil do motor
 * falso, que é de todos: nenhum teste ponta a ponta responde a ela.
 *
 * O checklist de produção de cada receita sai do registro, na forma de
 * `receita.json#checklist`. O que toda cozinha tem e a receita usa sem ela ter
 * confirmado fica no próprio registro (`supostos`): o "Confirmar a cozinha" de
 * uma receita limpa só o dela, e não o perfil de todos, para um teste não
 * mexer no que o outro confere. O "Tenho tudo isso" da cozinha, que é de todos,
 * limpa o perfil e as receitas.
 *
 * O dinheiro é formatado aqui porque aqui é o lugar da API, e só nos testes.
 */

import { createHash } from "node:crypto";

import { confirmarNoPerfil, contagens, todaCozinha } from "./cozinha.mjs";

const copia = (valor) => structuredClone(valor);
const FUSO = "America/Sao_Paulo";
const agora = () =>
  `hoje, ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: FUSO })}`;
const reais = (valor) =>
  `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const numero = (valor, casas = 4) => valor.toLocaleString("pt-BR", { maximumFractionDigits: casas });
const maiuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);
const minuscula = (texto) => (/^\p{Lu}\p{Ll}/u.test(texto) ? texto.charAt(0).toLowerCase() + texto.slice(1) : texto);

function semAcento(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

const ABAS = ["pode_fazer", "falta_resposta", "ranking", "nao_quer"];
const ORDENS = ["aproveitamento", "pontuacao", "compra", "tempo", "recentes"];
const ORDEM_DA_ABA = { pode_fazer: "aproveitamento", falta_resposta: "aproveitamento", ranking: "pontuacao", nao_quer: "recentes" };
const DA_PARA_FAZER = ["com_o_que_tem", "comprando"];
const ORCAMENTO = 80;

const SELO = { com_o_que_tem: "Com o que a senhora tem", falta_resposta: "Falta uma resposta da senhora" };

/** O que as receitas dos contratos usam da despensa, para o filtro `usa`: o item da grade não traz os ingredientes. */
const USA_DA_DESPENSA = {
  "arroz-com-frango": ["peito-de-frango", "arroz-branco-tipo-1", "cebola", "sal"],
  "8747bf504b200286": ["peito-de-frango", "cebola", "oleo-de-soja", "sal"],
};

/** As estrelas das receitas dos contratos: dão as pontuações que as fixtures mostram (86,9 e 88,8). */
const ESTRELAS_DOS_CONTRATOS = {
  "arroz-com-frango": { gosta: true, estrelas: { sabor: 5, facilidade: 4, tempo: 4, entrega: 4, apelo: 4 }, notas: "" },
};

const SEM_ESTRELAS = { sabor: null, facilidade: null, tempo: null, entrega: null, apelo: null };

/* -------------------------------------------------------------------------- */
/* A pontuação, com a conta (a mesma do LEIA)                                   */
/* -------------------------------------------------------------------------- */

const PESOS = [
  ["sabor", 0.3, "sabor"],
  ["apelo", 0.25, "apelo de venda"],
  ["entrega", 0.2, "aguenta a entrega"],
  ["facilidade", 0.15, "facilidade"],
  ["tempo", 0.1, "tempo"],
];

function pontuar({ gosta, estrelas }) {
  const dadas = PESOS.filter(([categoria]) => estrelas[categoria] != null);
  if (dadas.length === 0) return null;
  const somaDosPesos = dadas.reduce((soma, [, peso]) => soma + peso, 0);
  const nota = dadas.reduce((soma, [categoria, peso]) => soma + (peso * (estrelas[categoria] - 1)) / 4, 0) / somaDosPesos;
  const g = gosta === true ? 1 : gosta === false ? 0 : 0.5;
  const valor = Math.round(1000 * (0.75 * nota + 0.25 * g)) / 10;
  const texto = valor.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pesoTexto = (peso) => peso.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
  const partes = dadas.map(([categoria, peso, nome], indice) =>
    indice === 0 ? `${nome} ${estrelas[categoria]} (peso ${pesoTexto(peso)})` : `${nome} ${estrelas[categoria]} (${pesoTexto(peso)})`,
  );
  const todas = dadas.length === PESOS.length ? "" : " (contam só as que a senhora deu)";
  const gosto =
    gosta === true
      ? "a senhora gosta de fazer, que vale 1"
      : gosta === false
        ? "a senhora não gosta de fazer, que vale 0"
        : "a senhora ainda não disse se gosta, que vale 0,5";
  const derivacao =
    `Estrelas: ${partes.join(", ")}, dão ${numero(nota)} de 1${todas}; ${gosto}; ` +
    `pontuação = 100 × (0,75 × ${numero(nota)} + 0,25 × ${numero(g, 1)}) = ${texto}`;
  return { valor, texto, derivacao };
}

/* -------------------------------------------------------------------------- */
/* As perguntas de cada situação                                               */
/* -------------------------------------------------------------------------- */

const NAO_SEI = { rotulo: "Não sei", resposta: "nao_sei" };

/** A pergunta de cada situação, com a forma inteira de `receita.json#perguntas[]`. */
function perguntaDa(marca, nome) {
  const pergunta = perguntaSemAssunto(marca, nome);
  if (!pergunta) return null;
  const compras = marca === "falta-preco" ? [{ ingrediente: "creme de leite", quantidade_texto: "1 caixa" }] : [];
  return { ...pergunta, assunto: assuntoDa(pergunta), compras };
}

function perguntaSemAssunto(marca, nome) {
  const prato = minuscula(nome);
  switch (marca) {
    case "falta-tempo":
      return {
        tipo: "operacional",
        campo: "tempo_cozimento_min",
        texto: `Pelos passos não dá para saber quanto tempo a receita de ${prato} fica no fogo, no forno ou com algum aparelho ligado. Mais ou menos quantos minutos?`,
        motivo: "a senhora tem 60 minutos por cozinhada, e sem o tempo da receita não dá para saber se cabe",
        opcoes: [],
        entrada: { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 },
        passos: [],
      };
    case "falta-rendimento":
      return {
        tipo: "operacional",
        campo: "rendimento_porcoes",
        texto: `Essa receita de ${prato} rende quantas porções do tamanho que a senhora vai vender?`,
        motivo: "o custo de cada porção é o custo da receita dividido pelas porções",
        opcoes: [],
        entrada: { tipo: "inteiro", unidade: "porções", min: 1, max: 500 },
        passos: [],
      };
    case "falta-preco":
      return {
        tipo: "ingrediente",
        campo: "creme de leite",
        texto: "Falta comprar: creme de leite. Quanto custa aí na sua região, e por qual quantidade (o quilo, a lata, o pacote)?",
        motivo: "sem o preço não dá para saber se cabe no orçamento",
        opcoes: [],
        entrada: { tipo: "texto" },
        passos: [],
      };
    case "falta-forno":
      return {
        tipo: "equipamento",
        campo: "forno",
        texto: "A senhora tem forno? Pode ser o do fogão mesmo, ou elétrico.",
        motivo: `${nome} precisa de forno`,
        opcoes: [{ rotulo: "Tenho", resposta: "sim" }, { rotulo: "Não tenho", resposta: "nao" }, NAO_SEI],
        entrada: null,
        passos: [3],
      };
    case "falta-bocas":
      return {
        tipo: "operacional",
        campo: "bocas_fogao",
        texto: "Seu fogão tem quantas bocas? Isso limita quantas panelas andam juntas.",
        motivo: `${nome} usa duas panelas no fogo ao mesmo tempo (passo 4)`,
        opcoes: [NAO_SEI],
        entrada: { tipo: "inteiro", unidade: "bocas", min: 1, max: 8 },
        passos: [],
      };
    case "falta-medida":
      return {
        tipo: "ingrediente",
        assunto: "medida",
        campo: LINHA_DA_MEDIDA,
        texto: "Não sei quanto pesa uma colher de sopa de alcaparras. Se a senhora souber, em gramas, eu calculo.",
        motivo: "sem o peso, não dá para saber quanto sai da despensa nem quanto custa o prato",
        opcoes: [],
        entrada: { tipo: "peso", unidade: "g", peso_de: { cada: "1 colher de sopa", tudo: "2 colheres de sopa" } },
        passos: [],
      };
    case "falta-preparo":
      return {
        tipo: "equipamento",
        campo: "modo_preparo",
        texto: `Como a senhora faz ${prato}? Vai ao forno, é de panela, de fritar? Me conta o passo a passo que eu confiro se a cozinha dá conta.`,
        motivo: "sem o modo de preparo não dá para saber que equipamento o prato pede",
        opcoes: [],
        entrada: { tipo: "texto" },
        passos: [],
      };
    default:
      return null;
  }
}

/** A linha da pergunta de medida: a receita pede duas colheres, e a pergunta, o peso de uma. */
const LINHA_DA_MEDIDA = "2 colheres de sopa de alcaparras";

/** "300", "20 g", "0,3 kg": em gramas, ou `null`. */
function gramasDaResposta(texto) {
  const achado = /(\d+(?:[.,]\d+)?)\s*(kg|g)?\b/i.exec(texto);
  if (!achado) return null;
  const numero = Number(achado[1].replace(",", "."));
  const gramas = achado[2]?.toLowerCase() === "kg" ? numero * 1000 : numero;
  return gramas > 0 ? gramas : null;
}

/** "40", "40 minutos", "1 hora e 10 minutos", "1h10": em minutos, ou `null`. */
function minutosDaResposta(texto) {
  const limpo = semAcento(texto).trim();
  if (/^\d+$/.test(limpo)) return Number(limpo);
  const horas = /(\d+)\s*(?:h\b|hora)/.exec(limpo);
  const minutos = /(\d+)\s*(?:min|m\b)/.exec(limpo) ?? (horas ? /h\s*(\d+)\s*$/.exec(limpo) : null);
  const total = (horas ? Number(horas[1]) * 60 : 0) + (minutos ? Number(minutos[1]) : 0);
  return total > 0 ? total : null;
}

function tempoTexto(minutos) {
  if (!minutos) return null;
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  if (!horas) return `${minutos} min`;
  return resto ? `${horas} h ${resto} min` : `${horas} h`;
}

function minutosDe(texto) {
  if (!texto) return null;
  const horas = /(\d+)\s*h/.exec(texto);
  const minutos = /(\d+)\s*min/.exec(texto);
  return (horas ? Number(horas[1]) * 60 : 0) + (minutos ? Number(minutos[1]) : 0) || null;
}

/* -------------------------------------------------------------------------- */
/* O catálogo                                                                   */
/* -------------------------------------------------------------------------- */

const MARCAS = [
  "com-o-que-tem",
  "comprando",
  "falta-tempo",
  "falta-rendimento",
  "falta-linha",
  "falta-medida",
  "falta-preco",
  "falta-forno",
  "falta-bocas",
  "falta-preparo",
  "nao-da",
  "supostos",
];

/** O que toda cozinha tem e a receita marcada com `-supostos` usa sem ela ter confirmado. */
const SUPOSTOS_DA_RECEITA = [
  { tipo: "equipamento", id: "fogao", nome: "Fogão" },
  { tipo: "tecnica", id: "refogar", nome: "Refogar" },
];

const SITES = { tudogostoso: "TudoGostoso", panelinha: "Panelinha", receitasnestle: "Receitas Nestlé", cybercook: "CyberCook" };

function avaliacaoVazia() {
  return { gosta: null, estrelas: { ...SEM_ESTRELAS }, notas: "" };
}

function criarCatalogo(estado) {
  const catalogo = { registros: new Map(), proxima: 0, porUrl: new Map(), descoberta: copia(estado.receitas.descoberta) };
  const pôr = (registro) => {
    catalogo.proxima += 1;
    catalogo.registros.set(registro.slug, { criada: catalogo.proxima, respostas: [], linha: false, ...registro });
  };
  for (const item of estado.receitas.itens) {
    const doContrato = item.slug === estado.avaliacaoEscrita.resposta.slug ? estado.avaliacaoEscrita.resposta.avaliacao : null;
    pôr({
      slug: item.slug,
      nome: item.nome,
      imagem: item.imagem,
      site: item.site,
      url: null,
      autor: null,
      origem: item.site ? "descoberta" : "dita",
      tempo_texto: item.tempo_texto,
      codigo: item.selo.codigo,
      pergunta: null,
      depois: item.selo.codigo,
      usa: USA_DA_DESPENSA[item.slug] ?? [],
      usa_texto: item.usa_texto,
      falta: item.falta_texto === "nada a comprar" ? [] : [{ nome: "milho verde", quantidade: "1 lata", preco: 6 }],
      avaliacao: doContrato
        ? { gosta: doContrato.gosta, estrelas: copia(doContrato.estrelas), notas: doContrato.notas }
        : copia(ESTRELAS_DOS_CONTRATOS[item.slug] ?? avaliacaoVazia()),
    });
  }
  const modelo = estado.receita;
  pôr({
    slug: modelo.slug,
    nome: modelo.nome,
    imagem: modelo.imagem,
    site: modelo.fonte.site,
    url: modelo.fonte.url,
    autor: modelo.fonte.autor,
    origem: modelo.origem,
    tempo_texto: modelo.tempo_texto,
    codigo: modelo.veredito_da_cozinha.codigo,
    pergunta: copia(modelo.perguntas[0] ?? null),
    depois: "comprando",
    linha: true,
    usa: modelo.ingredientes.map((i) => i.item_id).filter(Boolean),
    usa_texto: "usa 6 de 7 ingredientes que a senhora tem",
    falta: [{ nome: "milho verde", quantidade: "1 lata", preco: 6 }],
    avaliacao: { gosta: modelo.avaliacao.gosta, estrelas: copia(modelo.avaliacao.estrelas), notas: modelo.avaliacao.notas },
    respostas: copia(modelo.respostas),
    supostos: copia(modelo.checklist.confirmar_a_cozinha?.itens ?? []),
  });
  return catalogo;
}

/** A URL canônica (host sem `www.`, caminho sem barra final, sem consulta) e o slug dela. */
function canonica(url) {
  const endereco = new URL(url);
  const caminho = endereco.pathname.replace(/\/+$/, "");
  return `${endereco.hostname.toLowerCase().replace(/^www\./, "")}${caminho}`;
}
const sha = (texto) => createHash("sha256").update(texto).digest("hex");

/** A receita que a página do endereço "traz", montada pelo próprio endereço. */
function registroDoEndereco(url) {
  const endereco = new URL(url);
  const pedaco = decodeURIComponent(endereco.pathname.split("/").filter(Boolean).at(-1) ?? "receita").replace(/\.html?$/, "");
  const marca = MARCAS.find((m) => pedaco.endsWith(`-${m}`)) ?? "comprando";
  const semFoto = pedaco.includes("sem-foto");
  const palavras = pedaco
    .replace(new RegExp(`-${marca}$`), "")
    .replace(/-?sem-foto/, "")
    .replace(/^\d+-/, "")
    .split("-")
    .filter(Boolean);
  const nome = maiuscula(palavras.join(" ") || "Receita");
  const host = endereco.hostname.toLowerCase().replace(/^www\./, "");
  const primeiro = host.split(".")[0] ?? host;
  const site = SITES[primeiro] ?? maiuscula(primeiro);
  const slug = sha(canonica(url)).slice(0, 16);
  const codigo =
    marca === "com-o-que-tem" || marca === "supostos"
      ? "com_o_que_tem"
      : marca === "nao-da"
        ? "nao_da"
        : marca === "comprando"
          ? "comprando"
          : "falta_resposta";
  const pergunta = perguntaDa(marca, nome);
  const precoFalta = marca === "falta-preco";
  return {
    slug,
    nome,
    imagem: semFoto ? null : { url: `/motor/imagens/${sha(url).slice(0, 32)}`, credito: `Foto: ${site}` },
    site,
    url,
    autor: "Cozinha de teste",
    origem: "url_dela",
    tempo_texto: marca === "falta-tempo" ? null : "35 min",
    codigo,
    pergunta,
    linha: marca === "falta-linha",
    depois: precoFalta ? "comprando" : "com_o_que_tem",
    usa: ["cebola", "alho", "oleo-de-soja", "arroz-branco-tipo-1"],
    usa_texto: codigo === "com_o_que_tem" ? "usa 6 de 6 ingredientes que a senhora tem" : "usa 5 de 6 ingredientes que a senhora tem",
    falta:
      codigo === "com_o_que_tem"
        ? []
        : precoFalta
          ? [{ nome: "creme de leite", quantidade: "1 caixa", preco: null }]
          : [{ nome: "milho verde", quantidade: "1 lata", preco: 6 }],
    supostos: marca === "supostos" ? copia(SUPOSTOS_DA_RECEITA) : [],
    avaliacao: avaliacaoVazia(),
  };
}

/* -------------------------------------------------------------------------- */
/* As perguntas que liberam receitas                                            */
/* -------------------------------------------------------------------------- */

/** Do que a pergunta trata, como a API diz em `assunto`. */
function assuntoDa(pergunta) {
  if (pergunta.assunto) return pergunta.assunto;
  if (pergunta.tipo === "equipamento") return pergunta.campo === "modo_preparo" ? "modo_preparo" : "equipamento";
  if (pergunta.tipo === "tecnica") return "tecnica";
  if (pergunta.campo === "rendimento_porcoes") return "rendimento";
  if (pergunta.campo === "tempo_cozimento_min") return "tempo_cozimento";
  if (pergunta.tipo === "operacional") return "rotina";
  return "preco_de_compra";
}

const DA_COZINHA = new Set(["equipamento", "tecnica", "rotina"]);
const RESPONDE_ALI = new Set([
  ...DA_COZINHA,
  "rendimento",
  "tempo_cozimento",
  "linha_nao_lida",
  "mesmo_ingrediente",
  "medida",
  "preco_de_compra",
]);
const contagemDe = (n) => `${n} ${n === 1 ? "receita" : "receitas"}`;

/** `receitas.json#perguntas_que_liberam`: aqui cada receita espera uma pergunta só, e ela libera. */
function perguntasQueLiberam(pendentes) {
  const grupos = new Map();
  for (const le of pendentes) {
    const { registro } = le;
    if (!registro.pergunta) continue;
    const assunto = assuntoDa(registro.pergunta);
    if (!RESPONDE_ALI.has(assunto)) continue;
    const chave = DA_COZINHA.has(assunto) ? `${assunto}|${registro.pergunta.campo}` : `${assunto}|${registro.slug}`;
    const grupo = grupos.get(chave) ?? { pergunta: { compras: [], ...copia(registro.pergunta), assunto }, registros: [] };
    grupo.registros.push(registro);
    grupos.set(chave, grupo);
  }
  return [...grupos.values()]
    .sort((a, b) => b.registros.length - a.registros.length)
    .slice(0, 5)
    .map(({ pergunta, registros }) => ({
      pergunta: registros.length > 1 ? { ...pergunta, motivo: "" } : pergunta,
      receitas: registros.length,
      liberadas: registros.length,
      ...semCompra(registros),
      nomes: registros.map((r) => r.nome),
      slugs: registros.map((r) => r.slug),
      rota: registros.length === 1 ? `/receitas/${registros[0].slug}` : "/receitas?aba=falta_resposta",
      texto: `libera ${contagemDe(registros.length)}`,
    }));
}

/**
 * A receita que espera resposta e não pede compra: a que vai para "com o que
 * tem" quando ela responde (`depois`), como a API separa pela despensa.
 */
const semNadaAComprar = (registro) => registro.depois === "com_o_que_tem";

/** `sem_compra` e `sem_compra_texto` de uma pergunta: das receitas dela, as sem nada a comprar. */
function semCompra(registros) {
  const sem = registros.filter(semNadaAComprar).length;
  let texto = null;
  if (sem > 0 && registros.length === 1) texto = "usa só o que a senhora tem";
  else if (sem > 0 && sem === registros.length) texto = "todas usam só o que a senhora tem";
  else if (sem > 0) texto = `${sem} delas ${sem === 1 ? "usa" : "usam"} só o que a senhora tem`;
  return { sem_compra: sem, sem_compra_texto: texto };
}

/** A pergunta da cozinha no meio da frase, como o motor diz ("se tem forno"). */
const NA_FRASE = {
  tempo_max_por_fornada_min: "quanto tempo consegue ficar cozinhando de uma vez",
  bocas_fogao: "quantas bocas tem o seu fogão",
};
function naFrase(pergunta) {
  const assunto = assuntoDa(pergunta);
  if (assunto === "equipamento") return `se tem ${pergunta.campo.replaceAll("_", " ")}`;
  if (assunto === "tecnica") return `se tem prática com ${pergunta.campo.replaceAll("_", " ")}`;
  if (assunto === "rotina") return NA_FRASE[pergunta.campo] ?? null;
  return null;
}
const listaFalada = (partes) => (partes.length <= 1 ? partes.join("") : `${partes.slice(0, -1).join(", ")} e ${partes.at(-1)}`);

/** `receitas.json#esperando_resposta`: quantas usam só o que ela tem, e o que falta ela dizer. */
function esperandoResposta(pendentes) {
  if (pendentes.length === 0) return null;
  const so = pendentes.filter((le) => semNadaAComprar(le.registro)).map((le) => le.registro);
  const comprando = pendentes.length - so.length;
  const frases = [...new Set(so.map((r) => (r.pergunta ? naFrase(r.pergunta) : null)).filter(Boolean))];
  const outras = so.filter((r) => r.pergunta && !naFrase(r.pergunta)).length;
  const resto = comprando ? [`${contagemDe(comprando)} ${comprando === 1 ? "pede" : "pedem"} alguma compra`] : [];
  let texto;
  if (so.length > 0) {
    const elas = so.length === 1 ? "ela" : "elas";
    const falta = frases.length
      ? `falta só a senhora me dizer ${listaFalada(outras ? [...frases, `mais ${outras} ${outras === 1 ? "coisa" : "coisas"} sobre ${elas}`] : frases)}`
      : `falta só a senhora responder ${outras} ${outras === 1 ? "pergunta" : "perguntas"} sobre ${elas}`;
    const usam = `${contagemDe(so.length)} ${so.length === 1 ? "usa" : "usam"}`;
    texto = `${usam} só o que a senhora tem; ${falta}.${resto.length ? ` ${resto[0].charAt(0).toUpperCase()}${resto[0].slice(1)}.` : ""}`;
  } else if (comprando === 1) {
    texto = "A receita que espera resposta pede alguma compra.";
  } else {
    texto = `Nenhuma das ${comprando} receitas que esperam resposta usa só o que a senhora tem: todas pedem alguma compra.`;
  }
  return {
    receitas: pendentes.length,
    so_com_o_que_tem: so.length,
    precisa_comprar: comprando,
    linha_sem_leitura: 0,
    nomes: so.map((r) => r.nome),
    slugs: so.map((r) => r.slug),
    falta_dizer: frases,
    texto,
  };
}

/* -------------------------------------------------------------------------- */
/* A leitura: aba, grade e detalhe                                              */
/* -------------------------------------------------------------------------- */

/** A situação na cozinha agora: a pergunta da cozinha se resolve pelo perfil. */
function codigoDe(registro, perfil) {
  if (registro.codigo !== "falta_resposta" || !registro.pergunta) return registro.codigo;
  const { tipo, campo } = registro.pergunta;
  if (tipo === "equipamento" || tipo === "tecnica") {
    const lista = (tipo === "equipamento" ? perfil?.equipamentos : perfil?.tecnicas) ?? [];
    return lista.find((item) => item.id === campo)?.estado === "tem" ? registro.depois : "falta_resposta";
  }
  if (tipo === "operacional" && perfil?.restricoes?.[campo]) {
    return perfil.restricoes[campo].valor != null ? registro.depois : "falta_resposta";
  }
  return "falta_resposta";
}

function faltaTexto(registro, codigo) {
  if (codigo === "com_o_que_tem" || registro.falta.length === 0) return "nada a comprar";
  return `falta comprar ${registro.falta.map((f) => f.nome).join(" e ")}`;
}

function compraDe(registro) {
  if (registro.falta.some((f) => f.preco == null)) return null;
  return registro.falta.reduce((soma, f) => soma + f.preco, 0);
}

function seloDe(registro, codigo) {
  if (codigo !== "comprando") return { codigo: codigo === "nao_da" ? "falta_resposta" : codigo, texto: SELO[codigo] ?? SELO.falta_resposta };
  const compra = compraDe(registro);
  return { codigo, texto: compra == null ? "Comprando o que falta" : `Comprando ${reais(compra)}, cabe nos ${reais(ORCAMENTO)}` };
}

function leitura(registro, perfil) {
  const codigo = codigoDe(registro, perfil);
  const pontuacao = pontuar(registro.avaliacao);
  return { registro, codigo, pontuacao, gosta: registro.avaliacao.gosta, minutos: minutosDe(registro.tempo_texto) };
}

function naAba(le, aba) {
  if (le.codigo === "nao_da") return false;
  if (aba === "ranking") return Boolean(le.pontuacao) && DA_PARA_FAZER.includes(le.codigo);
  if (aba === "nao_quer") return le.gosta === false;
  if (le.gosta === false) return false;
  return aba === "falta_resposta" ? le.codigo === "falta_resposta" : DA_PARA_FAZER.includes(le.codigo);
}

function passaNosFiltros(le, url) {
  const q = url.searchParams.get("q");
  const usa = url.searchParams.get("usa");
  const tempoMax = url.searchParams.get("tempo_max");
  const notaMin = url.searchParams.get("nota_min");
  const { registro } = le;
  const ondeProcurar = `${registro.nome} ${registro.site ?? ""} ${registro.falta.map((f) => f.nome).join(" ")}`;
  if (q && !semAcento(ondeProcurar).includes(semAcento(q))) return false;
  if (usa && !registro.usa.includes(usa)) return false;
  if (tempoMax && (le.minutos === null || le.minutos > Number(tempoMax))) return false;
  if (url.searchParams.get("so_com_o_que_tenho") === "true" && faltaTexto(registro, le.codigo) !== "nada a comprar") return false;
  if (notaMin && (!le.pontuacao || le.pontuacao.valor < Number(notaMin))) return false;
  return true;
}

function ordenar(leituras, ordem) {
  const lista = [...leituras];
  const porPontuacao = (a, b) => (b.pontuacao?.valor ?? -1) - (a.pontuacao?.valor ?? -1);
  if (ordem === "pontuacao") return lista.sort((a, b) => (a.gosta === false) - (b.gosta === false) || porPontuacao(a, b));
  if (ordem === "compra") return lista.sort((a, b) => (compraDe(a.registro) ?? Infinity) - (compraDe(b.registro) ?? Infinity));
  if (ordem === "tempo") return lista.sort((a, b) => (a.minutos ?? Infinity) - (b.minutos ?? Infinity));
  if (ordem === "recentes") return lista.sort((a, b) => b.registro.criada - a.registro.criada);
  return lista.sort((a, b) => a.registro.falta.length - b.registro.falta.length || a.registro.criada - b.registro.criada);
}

function itemDaGrade(le, aba) {
  const { registro, codigo, pontuacao } = le;
  return {
    slug: registro.slug,
    nome: registro.nome,
    imagem: copia(registro.imagem),
    site: registro.site,
    tempo_texto: registro.tempo_texto,
    selo: seloDe(registro, codigo),
    usa_texto: registro.usa_texto,
    falta_texto: faltaTexto(registro, codigo),
    pontuacao: pontuacao ? { valor: pontuacao.valor, texto: pontuacao.texto } : null,
    // O que ela disse de fazer o prato (`receitas.json#itens[].gosta`): `null` enquanto não disse.
    gosta: registro.avaliacao.gosta,
    pergunta: aba === "falta_resposta" && codigo === "falta_resposta" ? copia(registro.pergunta) : null,
    // O que falta comprar com preço de referência (não dito por ela), com a fonte.
    referencias: codigo === "com_o_que_tem" ? [] : registro.falta.filter((f) => f.referencia).map((f) => copia(f.referencia)),
    nota_da_cozinha: DA_PARA_FAZER.includes(codigo) && (registro.supostos?.length ?? 0) > 0 ? "Confirme a cozinha" : null,
    rota: `/receitas/${registro.slug}`,
  };
}

function ranking(leituras) {
  return ordenar(
    leituras.filter((le) => naAba(le, "ranking")),
    "pontuacao",
  );
}

const POSICOES = ["primeiro", "segundo", "terceiro", "quarto", "quinto", "sexto", "sétimo", "oitavo", "nono", "décimo"];

function vereditoCompleto(codigo, gosta) {
  if (codigo === "nao_da" || gosta === false) return ["BLOQUEADO", "Não dá"];
  if (codigo === "falta_resposta" || gosta === null) return ["FALTA INFO", "Falta saber"];
  return codigo === "comprando" ? ["APTO COM COMPRA", "Dá, comprando"] : ["APTO", "Dá pra fazer"];
}

function faltaComprar(registro, codigo) {
  if (codigo === "com_o_que_tem" || registro.falta.length === 0) {
    return { itens: [], custo: { valor: 0, texto: "R$ 0,00" }, cabe_no_orcamento: true, texto: "nada a comprar" };
  }
  const itens = registro.falta.map((f) => {
    if (f.preco == null) {
      return {
        nome: f.nome,
        quantidade_texto: f.quantidade,
        preco_conhecido: false,
        custo_compra: null,
        custo_no_prato: null,
        derivacao: `ainda não sei quanto custa ${f.nome}`,
        cabe_no_orcamento: null,
        referencia: null,
      };
    }
    return {
      nome: f.nome,
      quantidade_texto: f.quantidade,
      preco_conhecido: true,
      custo_compra: { valor: f.preco, texto: reais(f.preco) },
      custo_no_prato: { valor: f.preco, texto: reais(f.preco) },
      derivacao: `${f.quantidade} × ${reais(f.preco)} por ${f.por ?? f.quantidade} = ${reais(f.preco)}; na compra, 1 × ${reais(f.preco)} = ${reais(f.preco)}`,
      origem_preco: f.referencia ? "preço de referência" : "informado pela senhora",
      cabe_no_orcamento: f.preco <= ORCAMENTO,
      referencia: f.referencia ? copia(f.referencia) : null,
    };
  });
  const compra = compraDe(registro);
  const nomes = registro.falta.map((f) => f.nome).join(" e ");
  return {
    itens,
    custo: compra == null ? null : { valor: compra, texto: reais(compra) },
    cabe_no_orcamento: compra == null ? null : compra <= ORCAMENTO,
    texto:
      compra == null
        ? `falta comprar ${nomes}; ainda não sei o preço`
        : `falta comprar ${nomes}, ${reais(compra)}; cabe nos ${reais(ORCAMENTO)} que restam`,
  };
}

function ingredientesDe(modelo, registro, codigo, pendente) {
  const resposta = registro.respostas.find((r) => r.linha);
  const lidos = modelo.ingredientes
    .filter((i) => i.situacao !== "falta")
    .flatMap((i) => {
      if (i.situacao !== "nao_entendi") return [i];
      if (registro.linha && pendente) return [i];
      if (registro.linha && resposta) return [{ ...i, precisa: { texto: resposta.valor }, situacao: "a_gosto" }];
      return [];
    });
  const faltam = registro.falta.map((f) =>
    codigo === "com_o_que_tem"
      ? {
          nome: f.nome,
          item_id: null,
          precisa: { texto: f.quantidade },
          tem: { texto: `2 ${f.quantidade.split(" ").at(-1)}s` },
          sobra: { texto: f.quantidade },
          situacao: "tem",
          compra: null,
          medida_de_referencia: null,
        }
      : {
          nome: f.nome,
          item_id: null,
          precisa: { texto: f.quantidade },
          tem: null,
          sobra: null,
          situacao: "falta",
          compra: { texto: f.preco == null ? f.quantidade : `${f.quantidade}, ${reais(f.preco)}`, cabe: f.preco == null ? null : f.preco <= ORCAMENTO },
          medida_de_referencia: null,
        },
  );
  const posicao = lidos.findIndex((i) => i.situacao === "a_gosto");
  return posicao < 0 ? [...lidos, ...faltam] : [...lidos.slice(0, posicao), ...faltam, ...lidos.slice(posicao)];
}

/* -------------------------------------------------------------------------- */
/* O checklist de produção                                                     */
/* -------------------------------------------------------------------------- */

const TEXTO_DO_STATUS = {
  confirmado: "confirmado pela senhora",
  pre_determinado: "pré-determinado",
  suposto: "suposto: confirme",
  falta_saber: "falta saber",
  nao_da: "não dá",
};
const TEXTO_DA_ORIGEM = { a_senhora_disse: "a senhora disse", suposto: "suposto", receita: "receita" };
const GRAVIDADE = ["confirmado", "pre_determinado", "suposto", "falta_saber", "nao_da"];

function itemDaLista(id, tipo, nome, status, origem, extras = {}) {
  return {
    id,
    tipo,
    nome,
    detalhe: extras.detalhe ?? null,
    status,
    status_texto: extras.status_texto ?? TEXTO_DO_STATUS[status],
    origem,
    origem_texto: extras.origem_texto ?? TEXTO_DA_ORIGEM[origem],
    pergunta: extras.pergunta ?? null,
    editar: extras.editar ?? null,
  };
}

function grupoDaLista(id, titulo, itens, vazio = "") {
  const status = itens.reduce((pior, item) => (GRAVIDADE.indexOf(item.status) > GRAVIDADE.indexOf(pior) ? item.status : pior), "confirmado");
  return { id, titulo, status, itens, vazio_texto: vazio };
}

/** A pergunta de um item que toda cozinha tem, para ela responder só ele. */
function perguntaDoSuposto(item, nome) {
  const tecnica = item.tipo === "tecnica";
  return {
    tipo: item.tipo,
    assunto: item.tipo,
    campo: item.id,
    texto: tecnica ? `A senhora tem prática com ${item.nome.toLowerCase()}?` : `A senhora tem ${item.nome.toLowerCase()} aí na cozinha?`,
    motivo: `${nome} ${tecnica ? "pede" : "usa"} ${item.nome.toLowerCase()}`,
    compras: [],
    opcoes: [{ rotulo: tecnica ? "Faço" : "Tenho", resposta: "sim" }, { rotulo: tecnica ? "Não faço" : "Não tenho", resposta: "nao" }, NAO_SEI],
    entrada: null,
    passos: [1],
  };
}

/** "tem fogão e que sabe refogar": o miolo da pergunta de confirmar a cozinha. */
export function oQueElaConfirma(itens) {
  const tem = itens.filter((i) => i.tipo === "equipamento").map((i) => i.nome.toLowerCase());
  const sabe = itens.filter((i) => i.tipo === "tecnica").map((i) => i.nome.toLowerCase());
  return [tem.length ? `tem ${listaFalada(tem)}` : null, sabe.length ? `sabe ${listaFalada(sabe)}` : null].filter(Boolean).join(" e que ");
}

function doKitDaCozinha(item, registro) {
  const suposto = (registro.supostos ?? []).find((s) => s.id === item.id);
  if (!suposto) return itemDaLista(item.id, item.tipo, item.nome, "confirmado", "a_senhora_disse");
  return itemDaLista(item.id, item.tipo, item.nome, "suposto", "suposto", {
    detalhe: item.tipo === "tecnica" ? "Toda cozinheira faz, e a senhora ainda não confirmou." : "Toda cozinha tem, e a senhora ainda não confirmou.",
    pergunta: perguntaDoSuposto(item, registro.nome),
  });
}

function perguntaDasPorcoes(nome) {
  return {
    tipo: "operacional",
    assunto: "rendimento",
    campo: "rendimento_porcoes",
    texto: `Quantas porções a receita de ${minuscula(nome)} rende na sua cozinha?`,
    motivo: "o custo de cada porção é o custo da receita dividido por elas",
    compras: [],
    opcoes: [],
    entrada: { tipo: "inteiro", unidade: "porções", min: 1, max: 500 },
    passos: [],
  };
}

function checklistDe(registro, modelo, { codigo, pendente, podePrecificar }) {
  const nome = registro.nome;
  const supostos = registro.supostos ?? [];
  const gosta = registro.avaliacao.gosta;
  const doModelo = (grupo) => copia(modelo.checklist.grupos.find((g) => g.id === grupo)?.itens ?? []);

  const equipamentos = [doKitDaCozinha({ tipo: "equipamento", id: "fogao", nome: "Fogão" }, registro)];
  if (codigo === "nao_da") {
    equipamentos.push(
      itemDaLista("forno", "equipamento", "Forno", "nao_da", "a_senhora_disse", { detalhe: "A receita vai ao forno, e a senhora disse que não tem forno." }),
    );
  }
  if (pendente?.tipo === "equipamento") {
    const doPreparo = pendente.campo === "modo_preparo";
    equipamentos.push(
      itemDaLista(pendente.campo, doPreparo ? "modo_preparo" : "equipamento", doPreparo ? "Modo de preparo" : maiuscula(pendente.campo), "falta_saber", "receita", {
        detalhe: pendente.texto,
        pergunta: copia(pendente),
      }),
    );
  }
  const tecnicas = [doKitDaCozinha({ tipo: "tecnica", id: "refogar", nome: "Refogar" }, registro)];

  const rotina = doModelo("rotina").map((item) => {
    const doTempo = item.id === "tempo_max_por_fornada_min" && pendente?.campo === "tempo_cozimento_min";
    if (pendente?.tipo !== "operacional" || (pendente.campo !== item.id && !doTempo)) return item;
    return itemDaLista(item.id, "rotina", item.nome, "falta_saber", "receita", { detalhe: `${maiuscula(pendente.motivo)}.`, pergunta: copia(pendente) });
  });

  const ingredientes = doModelo("ingredientes").filter((item) => item.id === "na_despensa");
  const faltam = codigo === "com_o_que_tem" ? [] : registro.falta;
  for (const f of faltam) {
    const precoPendente = pendente?.assunto === "preco_de_compra" ? copia(pendente) : null;
    ingredientes.push(
      f.preco == null
        ? itemDaLista(`compra:${f.nome}`, "compra", maiuscula(f.nome), "falta_saber", "receita", {
            detalhe: `Comprar ${f.quantidade}; falta saber o preço.`,
            pergunta: precoPendente,
          })
        : itemDaLista(`compra:${f.nome}`, "compra", maiuscula(f.nome), "confirmado", "a_senhora_disse", {
            detalhe: `Comprar ${f.quantidade}, ${reais(f.preco)}.`,
            status_texto: "vai comprar",
          }),
    );
  }
  const compra = faltam.length === 0 ? 0 : compraDe(registro);
  ingredientes.push(
    faltam.length === 0
      ? itemDaLista("orcamento", "orcamento", `Cabe nos ${reais(ORCAMENTO)}`, "confirmado", "receita", {
          detalhe: `Nada a comprar; restam ${reais(ORCAMENTO)}.`,
          status_texto: "não precisa",
        })
      : compra == null
        ? itemDaLista("orcamento", "orcamento", `Cabe nos ${reais(ORCAMENTO)}`, "falta_saber", "receita", {
            detalhe: "Falta saber o preço do que falta comprar.",
          })
        : itemDaLista("orcamento", "orcamento", `Cabe nos ${reais(ORCAMENTO)}`, "confirmado", "a_senhora_disse", {
            detalhe: `A compra dá ${reais(compra)}; restam ${reais(ORCAMENTO)}.`,
            status_texto: "cabe",
          }),
  );
  if (pendente?.tipo === "ingrediente" && pendente.assunto !== "preco_de_compra") {
    ingredientes.push(
      itemDaLista(`pergunta:${pendente.campo}`, "ingrediente", maiuscula(pendente.campo), "falta_saber", "receita", {
        detalhe: pendente.texto,
        pergunta: copia(pendente),
      }),
    );
  }

  const dita = registro.respostas.find((r) => r.campo === "rendimento_porcoes");
  const porcoes =
    pendente?.campo === "rendimento_porcoes"
      ? itemDaLista("porcoes", "porcoes", "Porções", "falta_saber", "receita", { detalhe: pendente.texto, pergunta: copia(pendente) })
      : dita
        ? itemDaLista("porcoes", "porcoes", "Porções", "confirmado", "a_senhora_disse", {
            detalhe: `Rende ${registro.porcoes ?? 4} porções.`,
            editar: perguntaDasPorcoes(nome),
          })
        : itemDaLista("porcoes", "porcoes", "Porções", "pre_determinado", "receita", {
            detalhe: "Rende 4 porções, como a receita diz.",
            editar: perguntaDasPorcoes(nome),
          });
  const preDeterminados = [porcoes, ...(registro.slug === modelo.slug ? doModelo("pre_determinados").filter((item) => item.tipo === "peso") : [])];

  const podeAceitar = podePrecificar && supostos.length === 0;
  const bloqueada = codigo === "nao_da" || gosta === false;
  const falta = podeAceitar
    ? []
    : bloqueada
      ? [codigo === "nao_da" ? "A receita vai ao forno, e a senhora disse que não tem forno." : `A senhora disse que não gosta de fazer ${minuscula(nome)}.`]
      : [
          ...(pendente ? [`Responder: ${pendente.texto}`] : []),
          ...(gosta === null ? [`Dizer se a senhora gosta de fazer ${minuscula(nome)}.`] : []),
          ...(supostos.length > 0 ? [`Confirmar que a senhora ${oQueElaConfirma(supostos)}.`] : []),
        ];
  return {
    titulo: "Checklist de produção",
    pode_aceitar: podeAceitar,
    resumo: podeAceitar
      ? "Está tudo certo para a senhora aceitar este prato."
      : bloqueada
        ? "Pelo que a senhora me disse, esta receita não dá."
        : `Antes de aceitar, ${falta.length === 1 ? "falta 1 coisa" : `faltam ${falta.length} coisas`}.`,
    falta_para_aceitar: falta,
    confirmar_a_cozinha:
      supostos.length > 0
        ? { pergunta: `Antes de aceitar, a senhora confirma que ${oQueElaConfirma(supostos)}?`, itens: copia(supostos) }
        : null,
    grupos: [
      grupoDaLista("equipamentos", "Equipamentos", equipamentos, "Esta receita não pede equipamento."),
      grupoDaLista("tecnicas", "Técnicas", tecnicas, "Esta receita não pede técnica especial."),
      grupoDaLista("rotina", "Rotina", rotina),
      grupoDaLista("ingredientes", "Ingredientes", ingredientes),
      grupoDaLista("pre_determinados", "Pré-determinados", preDeterminados),
    ],
  };
}

function detalheDe(registro, estado, leituras) {
  const modelo = estado.receita;
  const le = leitura(registro, estado.perfil);
  const { codigo, pontuacao } = le;
  const pendente = codigo === "falta_resposta" ? registro.pergunta : null;
  const [veredito, vereditoRotulo] = vereditoCompleto(codigo, registro.avaliacao.gosta);
  const podePrecificar = veredito === "APTO" || veredito === "APTO COM COMPRA";
  const falta = faltaComprar(registro, codigo);
  const prato = minuscula(registro.nome);
  const cozinha = {
    com_o_que_tem: { rotulo: "Com o que a senhora tem", motivo: "A senhora tem o que a receita pede, e a cozinha dá conta." },
    comprando: { rotulo: "Dá, comprando o que falta", motivo: `${maiuscula(falta.texto)}.` },
    falta_resposta: {
      rotulo: "Falta uma resposta da senhora",
      motivo:
        pendente && registro.linha
          ? modelo.veredito_da_cozinha.motivo
          : pendente
            ? `${maiuscula(pendente.motivo)}.`
            : "Falta uma resposta da senhora.",
    },
    nao_da: { rotulo: "Não dá", motivo: "A receita vai ao forno, e a senhora disse que não tem forno." },
  }[codigo];
  const posicao = ranking(leituras).findIndex((l) => l.registro.slug === registro.slug);
  const minutos = minutosDe(registro.tempo_texto);
  return {
    ...copia(modelo),
    slug: registro.slug,
    nome: registro.nome,
    imagem: copia(registro.imagem),
    fonte: { site: registro.site, url: registro.url, autor: registro.autor },
    origem: registro.origem,
    tempos:
      registro.slug === modelo.slug
        ? copia(modelo.tempos)
        : minutos
          ? { preparo_min: 10, cozimento_min: Math.max(minutos - 10, 1), total_min: minutos, ativo_min: Math.max(minutos - 5, 1) }
          : { preparo_min: 10, cozimento_min: null, total_min: null, ativo_min: null },
    tempo_texto: registro.tempo_texto,
    veredito,
    veredito_rotulo: vereditoRotulo,
    veredito_da_cozinha: { codigo, ...cozinha },
    resumo: pendente
      ? `${registro.nome}: antes de decidir, preciso saber 1 coisa`
      : `${registro.nome}: ${vereditoRotulo.toLowerCase()}`,
    ingredientes: ingredientesDe(modelo, registro, codigo, pendente),
    linhas_nao_entendidas: registro.linha && pendente ? copia(modelo.linhas_nao_entendidas) : [],
    falta_comprar: falta,
    custo_porcao: podePrecificar ? copia(estado.custo.total) : null,
    pode_precificar: podePrecificar,
    perguntas: pendente ? [copia(pendente)] : [],
    avaliacao: { ...copia(registro.avaliacao), pontuacao },
    posicao_no_ranking: posicao < 0 ? null : posicao + 1,
    respostas: registro.respostas.map(({ campo, texto, quando_texto }) => ({ campo, texto, quando_texto })),
    rascunho_chat: podePrecificar
      ? `Quanto eu cobro por uma porção de ${prato}?`
      : codigo === "falta_resposta"
        ? `O que falta para eu poder fazer ${prato}?`
        : codigo === "nao_da"
          ? `Por que eu não consigo fazer ${prato}?`
          : `Vale a pena eu fazer ${prato} para vender?`,
    checklist: checklistDe(registro, modelo, { codigo, pendente, podePrecificar }),
    rota: `/receitas/${registro.slug}`,
  };
}

function situacaoNoRanking(registro, posicao) {
  if (posicao !== null) {
    const onde = posicao <= POSICOES.length ? `em ${POSICOES[posicao - 1]} lugar` : `na posição ${posicao}`;
    return `${registro.nome} está ${onde} no ranking da senhora.`;
  }
  if (!pontuar(registro.avaliacao)) return `Quando a senhora der as estrelas, ${minuscula(registro.nome)} entra no ranking.`;
  return `${registro.nome} entra no ranking quando der para fazer com o que a senhora tem ou pode comprar.`;
}

/* -------------------------------------------------------------------------- */
/* As rotas                                                                     */
/* -------------------------------------------------------------------------- */

export function rotasDasReceitas({ rota, ok, recusa, ausente, lerCorpo, fluxo, estado }) {
  const catalogo = () => {
    const atual = estado();
    atual.catalogoDeReceitas ??= criarCatalogo(atual);
    return atual.catalogoDeReceitas;
  };
  const leituras = () => [...catalogo().registros.values()].map((registro) => leitura(registro, estado().perfil));
  const achar = (partes) => catalogo().registros.get(decodeURIComponent(partes[1]));
  const detalhe = (registro) => detalheDe(registro, estado(), leituras());
  const naoAchei = (res) => ausente(res, "Não encontrei essa receita.");

  rota("GET", /^\/api\/receitas$/, (_req, res, { url }) => {
    const aba = url.searchParams.get("aba") ?? "pode_fazer";
    const ordem = url.searchParams.get("ordem") ?? ORDEM_DA_ABA[aba];
    if (!ABAS.includes(aba)) return recusa(res, 422, "uso", "Essa aba não existe.");
    if (!ORDENS.includes(ordem)) return recusa(res, 422, "uso", "Essa ordem não existe.");
    const filtradas = leituras().filter((le) => passaNosFiltros(le, url));
    const contagens = Object.fromEntries(ABAS.map((a) => [a, filtradas.filter((le) => naAba(le, a)).length]));
    const itens = ordenar(
      filtradas.filter((le) => naAba(le, aba)),
      ordem,
    ).map((le) => itemDaGrade(le, aba));
    const pendentes = filtradas.filter((le) => naAba(le, "falta_resposta"));
    ok(res, {
      aba,
      contagens,
      itens,
      descoberta: copia(catalogo().descoberta),
      perguntas_que_liberam: perguntasQueLiberam(pendentes),
      esperando_resposta: esperandoResposta(pendentes),
      // O motor falso não tem receita sem preço na internet.
      sem_preco_na_internet: null,
    });
  });

  rota("POST", /^\/api\/receitas$/, async (req, res) => {
    const { url } = await lerCorpo(req);
    if (typeof url !== "string" || url.length < 8) return recusa(res, 422, "uso", "O pedido saiu incompleto.");
    let chave;
    try {
      chave = canonica(url);
    } catch {
      return recusa(res, 200, "uso", "não busco esse endereço: ele não é de uma página da internet");
    }
    if (!/^https?:\/\//i.test(url)) return recusa(res, 200, "uso", "não busco esse endereço: ele não é de uma página da internet");
    const conhecida = catalogo().porUrl.get(chave);
    if (conhecida) return ok(res, detalhe(catalogo().registros.get(conhecida)));
    if (/sem-receita/.test(url)) {
      return recusa(
        res,
        200,
        "dado",
        "a página abriu, mas não traz a receita em formato estruturado",
        "Esse site não publica a receita de um jeito que eu leia. Tenta outro?",
      );
    }
    const novo = registroDoEndereco(url);
    catalogo().proxima += 1;
    catalogo().registros.set(novo.slug, { criada: catalogo().proxima, respostas: [], ...novo });
    catalogo().porUrl.set(chave, novo.slug);
    ok(res, detalhe(catalogo().registros.get(novo.slug)), 201);
  });

  rota("POST", /^\/api\/receitas\/descoberta$/, (_req, res) => {
    // O que a rodada encontra entra no catálogo, como a API faria; com o nome de
    // outra, ganha o site entre parênteses (o nome é único no dossiê).
    for (const evento of estado().eventosDaDescoberta) {
      if (!evento.receita || catalogo().registros.has(evento.receita.slug)) continue;
      const item = evento.receita;
      const repetido = [...catalogo().registros.values()].some((r) => semAcento(r.nome) === semAcento(item.nome));
      catalogo().proxima += 1;
      catalogo().registros.set(item.slug, {
        criada: catalogo().proxima,
        slug: item.slug,
        nome: repetido && item.site ? `${item.nome} (${item.site})` : item.nome,
        imagem: copia(item.imagem),
        site: item.site,
        url: null,
        autor: null,
        origem: "descoberta",
        tempo_texto: item.tempo_texto,
        codigo: item.selo.codigo,
        pergunta: null,
        depois: item.selo.codigo,
        linha: false,
        usa: [],
        usa_texto: item.usa_texto,
        falta: item.falta_texto === "nada a comprar" ? [] : [{ nome: "milho verde", quantidade: "1 lata", preco: 6 }],
        avaliacao: avaliacaoVazia(),
        respostas: [],
      });
    }
    // A lista passa a contar a rodada, como a API contaria depois do fim dela.
    const fim = estado().eventosDaDescoberta.findLast((evento) => evento.tipo === "fim");
    if (fim) catalogo().descoberta = { estado: fim.estado, lidas: fim.lidas, encontradas: fim.encontradas, texto: fim.texto };
    ok(res, estado().descobertaInicio, 202);
  });
  rota("GET", /^\/api\/receitas\/descoberta\/eventos$/, (req, res, { url }) => fluxo(req, res, url, estado().eventosDaDescoberta));

  rota("GET", /^\/api\/receitas\/([^/]+)$/, (_req, res, { partes }) => {
    const registro = achar(partes);
    return registro ? ok(res, detalhe(registro)) : naoAchei(res);
  });

  rota("GET", /^\/api\/receitas\/([^/]+)\/custo$/, (_req, res, { partes }) => {
    const registro = achar(partes);
    if (!registro) return naoAchei(res);
    const receita = detalhe(registro);
    if (!receita.pode_precificar) {
      const prato = minuscula(receita.nome);
      const motivo =
        receita.veredito === "BLOQUEADO"
          ? `Não calculo o custo de ${prato}, porque esse prato não dá: ${
              registro.avaliacao.gosta === false ? "a senhora disse que não gosta de fazer" : minuscula(receita.veredito_da_cozinha.motivo)
            }`
          : `Ainda não calculo o custo de ${prato}: antes preciso saber uma coisa. ${
              receita.perguntas[0]?.texto ?? `A senhora gosta de fazer ${prato}?`
            }`;
      return recusa(res, 409, "regra", motivo);
    }
    const custo = copia(estado().custo);
    delete custo.ingrediente_que_falta_exemplo;
    delete custo.ingrediente_com_preco_de_referencia_exemplo;
    ok(res, { ...custo, prato: receita.nome });
  });

  rota("GET", /^\/api\/receitas\/([^/]+)\/estimativa$/, (_req, res, { partes }) => {
    const registro = achar(partes);
    if (!registro) return naoAchei(res);
    const receita = detalhe(registro);
    if (!DA_PARA_FAZER.includes(receita.veredito_da_cozinha.codigo)) {
      return recusa(res, 409, "regra", `Ainda não estimo o preço de ${minuscula(receita.nome)}: antes a receita tem que dar para fazer.`);
    }
    ok(res, { ...copia(estado().estimativa), slug: receita.slug, prato: receita.nome });
  });

  const respostaDaAvaliacao = (registro, anotou) => {
    const receita = detalhe(registro);
    const situacao = situacaoNoRanking(registro, receita.posicao_no_ranking);
    return {
      slug: registro.slug,
      nome: registro.nome,
      avaliacao: receita.avaliacao,
      posicao_no_ranking: receita.posicao_no_ranking,
      atualizado_texto: registro.avaliadaEm ?? "a senhora ainda não avaliou",
      texto: anotou ? `Anotei. ${situacao}` : situacao,
    };
  };

  rota("GET", /^\/api\/receitas\/([^/]+)\/avaliacao$/, (_req, res, { partes }) => {
    const registro = achar(partes);
    return registro ? ok(res, respostaDaAvaliacao(registro, false)) : naoAchei(res);
  });

  rota("PUT", /^\/api\/receitas\/([^/]+)\/avaliacao$/, async (req, res, { partes }) => {
    const registro = achar(partes);
    if (!registro) return naoAchei(res);
    const pedido = await lerCorpo(req);
    if ("gosta" in pedido) {
      if (pedido.gosta !== null && typeof pedido.gosta !== "boolean") return recusa(res, 422, "uso", "O pedido saiu incompleto.");
      registro.avaliacao.gosta = pedido.gosta;
    }
    for (const [categoria, nota] of Object.entries(pedido.estrelas ?? {})) {
      if (!(categoria in SEM_ESTRELAS)) return recusa(res, 422, "uso", "Essa categoria de estrela não existe.");
      if (nota !== null && !(Number.isInteger(nota) && nota >= 1 && nota <= 5)) {
        return recusa(res, 200, "uso", "A estrela vai de 1 a 5.");
      }
      registro.avaliacao.estrelas[categoria] = nota;
    }
    registro.avaliadaEm = agora();
    ok(res, respostaDaAvaliacao(registro, true));
  });

  rota("PUT", /^\/api\/receitas\/([^/]+)\/notas$/, async (req, res, { partes }) => {
    const registro = achar(partes);
    if (!registro) return naoAchei(res);
    const { texto = "" } = await lerCorpo(req);
    registro.avaliacao.notas = String(texto);
    ok(res, {
      slug: registro.slug,
      notas: registro.avaliacao.notas,
      atualizado_texto: agora(),
      texto: registro.avaliacao.notas ? "Guardei a anotação." : "Apaguei a anotação.",
    });
  });

  rota("POST", /^\/api\/receitas\/([^/]+)\/resposta$/, async (req, res, { partes }) => {
    const registro = achar(partes);
    if (!registro) return naoAchei(res);
    const { campo, resposta, por_unidade: porUnidade = null } = await lerCorpo(req);
    if (!campo || !resposta) return recusa(res, 422, "uso", "O pedido saiu incompleto.");
    const pergunta = registro.pergunta;
    // As porções ela muda quando quiser (o "Mudar" do checklist); o resto só responde o que falta.
    if (campo !== "rendimento_porcoes" && (!pergunta || pergunta.campo !== campo)) {
      return recusa(res, 200, "uso", "Isso a receita já diz; eu só anoto o que a página não dizia.");
    }
    const texto = String(resposta).trim();
    if (campo === "tempo_cozimento_min") {
      const minutos = minutosDaResposta(texto);
      if (!minutos || minutos > 1440) return recusa(res, 200, "uso", "Não entendi quanto tempo. A senhora pode escrever assim: 40 minutos.");
      registro.tempo_texto = tempoTexto(minutos);
      registro.respostas.push({ campo, texto: `A senhora disse que fica ${minutos} minutos no fogo.`, quando_texto: agora() });
    } else if (campo === "rendimento_porcoes") {
      const porcoes = Number(texto);
      if (!Number.isInteger(porcoes) || porcoes < 1 || porcoes > 500) return recusa(res, 200, "uso", "Não entendi quantas porções. Escreva só o número.");
      registro.porcoes = porcoes;
      registro.respostas.push({ campo, texto: `A senhora disse que rende ${porcoes} porções.`, quando_texto: agora() });
    } else if (registro.linha) {
      registro.respostas.push({ campo, linha: true, valor: texto, texto: `A senhora disse que vai ${texto} de ${campo}.`, quando_texto: agora() });
    } else if (pergunta.assunto === "medida" && pergunta.entrada?.tipo === "peso") {
      const gramas = gramasDaResposta(texto);
      if (!gramas || gramas > 50000) return recusa(res, 200, "uso", "Para o peso, preciso de um número em gramas ou quilos: por exemplo, 300 g.");
      const peso = gramas >= 1000 ? `${numero(gramas / 1000, 3)} kg` : `${numero(gramas, 3)} g`;
      const dito = porUnidade === false ? `“${campo}” pesam ${peso}` : `uma colher de sopa de alcaparras pesa ${peso}`;
      registro.respostas.push({ campo, texto: `A senhora disse que ${dito}.`, quando_texto: agora() });
    } else {
      return recusa(res, 200, "uso", "Essa pergunta a senhora responde pela conversa.");
    }
    if (pergunta?.campo === campo) {
      registro.pergunta = null;
      registro.codigo = registro.depois;
    }
    ok(res, detalhe(registro));
  });

  /*
   * A confirmação do que toda cozinha tem: `{}` confirma tudo o que ainda é
   * suposto no perfil (e o que as receitas usam), `{itens}` só eles, e
   * `{receita}` o que aquela receita usa. A receita do catálogo guarda o dela; a
   * de pôr preço (o `receita_id` da conferência) entra na lista das confirmadas.
   */
  rota("POST", /^\/api\/perfil\/supostos\/confirmar$/, async (req, res) => {
    const pedido = await lerCorpo(req);
    const perfil = estado().perfil;
    if (pedido.receita !== undefined && pedido.itens !== undefined) return recusa(res, 200, "uso", "mande os itens ou a receita, não os dois");
    let confirmados;
    if (typeof pedido.receita === "string") {
      const registro = catalogo().registros.get(pedido.receita);
      if (registro) {
        confirmados = copia(registro.supostos ?? []);
        registro.supostos = [];
      } else {
        // O prato de pôr preço com "supostos" no nome usa o fogão e o refogar.
        confirmados = /supostos/.test(pedido.receita) ? copia(SUPOSTOS_DA_RECEITA) : [];
        estado().confirmadasNoPreco.add(pedido.receita);
      }
    } else if (Array.isArray(pedido.itens)) {
      const ids = new Set(pedido.itens.map((item) => `${item.tipo}:${item.id}`));
      confirmados = confirmarNoPerfil(perfil, (item, tipo) => ids.has(`${tipo}:${item.id}`));
    } else {
      confirmados = confirmarNoPerfil(perfil, (item, tipo) => (tipo === "equipamento" ? item.pressuposto : item.pressuposta) && item.suposto && item.estado === "tem");
      for (const registro of catalogo().registros.values()) registro.supostos = [];
    }
    ok(res, {
      confirmados,
      texto: confirmados.length ? `Anotei: a senhora ${oQueElaConfirma(confirmados).replace(" e que ", " e ")}.` : "Não havia nada para confirmar: a senhora já tinha dito tudo isso.",
      perfil: contagens(perfil),
      toda_cozinha: todaCozinha(perfil),
    });
  });

  // O preço do que falta comprar: a pergunta de preço das receitas que esperam por ele se resolve.
  rota("POST", /^\/api\/preco-mercado$/, async (req, res) => {
    const { ingrediente, valor, quantidade = null, unidade = "", origem = "informado_por_ela" } = await lerCorpo(req);
    if (!ingrediente || typeof valor !== "number" || valor < 0) return recusa(res, 422, "uso", "O pedido saiu incompleto.");
    if (quantidade !== null && (!(quantidade > 0) || !String(unidade).trim())) {
      return recusa(res, 200, "uso", `não consegui entender a quantidade ${quantidade} ${unidade}`.trim());
    }
    const nome = semAcento(ingrediente).trim();
    for (const registro of catalogo().registros.values()) {
      const item = registro.falta.find((f) => semAcento(f.nome) === nome);
      if (!item) continue;
      item.preco = valor;
      item.por = quantidade ? `${numero(quantidade, 2)} ${unidade}`.trim() : item.quantidade;
      const pergunta = registro.pergunta;
      if (pergunta?.tipo === "ingrediente" && pergunta.campo.split(",").some((c) => semAcento(c).trim() === nome)) {
        registro.pergunta = null;
        registro.codigo = registro.depois;
      }
    }
    const texto = `Anotei: ${ingrediente} custa ${reais(valor)}${quantidade ? ` por ${numero(quantidade, 2)} ${unidade}`.trimEnd() : ""}.`;
    ok(res, {
      ingrediente,
      valor: { valor, texto: reais(valor) },
      por: quantidade ? `${numero(quantidade, 2)} ${unidade}`.trim() : null,
      origem,
      casou_com_o_que_falta: true,
      orcamento_restante: { valor: ORCAMENTO, texto: reais(ORCAMENTO) },
      texto,
    });
  });
}
