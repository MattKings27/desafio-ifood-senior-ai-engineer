/* global process, console, setTimeout, clearTimeout, setInterval, clearInterval, URL, structuredClone */
/**
 * Motor falso para os testes ponta a ponta.
 *
 * Serve o envelope REST da API (`{ok, dados, erro, categoria, pergunta}`) com
 * os dados das fixtures de contrato (`contratos/web/*.json`), e os fluxos de
 * eventos (SSE) do turno de conversa e da descoberta com os `.jsonl` de lá,
 * evento a evento. O estado é em memória: adicionar e tirar da despensa,
 * avaliar e anotar valem até o processo acabar (ou até `POST /__reiniciar`).
 *
 * O cardápio (`cardapio.mjs`), o histórico (`historico.mjs`) e a tela de pôr
 * preço (`preco.mjs`) moram cada um no seu arquivo, como as receitas.
 *
 * Para simular falha: `POST /__falhar {"caminho": "/api/atividades", "status": 503, "vezes": 1}`.
 *
 *     PORTA=8790 node e2e/motor-falso/servidor.mjs
 */

import { cardapioInicial, rotasDoCardapio } from "./cardapio.mjs";
import { rotasDoHistorico } from "./historico.mjs";
import { custoDaPorcao, rotasDoPreco } from "./preco.mjs";
import { rotasDasReceitas } from "./receitas.mjs";

import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cozinhaInicial, rotasDaCozinha } from "./cozinha.mjs";
import { despensaInicial, rotasDaDespensa } from "./despensa.mjs";

const AQUI = dirname(fileURLToPath(import.meta.url));
const CONTRATOS = join(AQUI, "..", "..", "..", "contratos", "web");
const PORTA = Number(process.env.PORTA ?? 8790);
const ATRASO_DO_FLUXO_MS = Number(process.env.ATRASO_DO_FLUXO_MS ?? 150);

const json = (pasta, arquivo) => JSON.parse(readFileSync(join(pasta, arquivo), "utf-8"));
const jsonl = (arquivo) =>
  readFileSync(join(CONTRATOS, arquivo), "utf-8")
    .split("\n")
    .filter((linha) => linha.trim() !== "")
    .map((linha) => JSON.parse(linha));
const copia = (valor) => structuredClone(valor);

/* -------------------------------------------------------------------------- */
/* Estado                                                                      */
/* -------------------------------------------------------------------------- */

function estadoInicial() {
  return {
    visaoGeral: json(CONTRATOS, "visao-geral.json"),
    despensa: despensaInicial(CONTRATOS),
    planilha: readFileSync(join(CONTRATOS, "despensa-planilha.txt.exemplo"), "utf-8"),
    receitas: json(CONTRATOS, "receitas.json"),
    receita: json(CONTRATOS, "receita.json"),
    custo: json(CONTRATOS, "custo.json"),
    avaliacaoEscrita: json(CONTRATOS, "avaliacao-escrita.json"),
    notasEscrita: json(CONTRATOS, "notas-escrita.json"),
    descobertaInicio: json(CONTRATOS, "descoberta-inicio.json"),
    perfil: cozinhaInicial(CONTRATOS),
    estimativa: json(CONTRATOS, "estimativa.json"),
    parametroEscrita: json(CONTRATOS, "parametro-escrita.json"),
    exportacao: json(CONTRATOS, "exportacao.json"),
    restauracao: json(CONTRATOS, "restauracao.json"),
    cardapio: cardapioInicial(CONTRATOS, json),
    atividades: json(CONTRATOS, "atividades.json"),
    conversas: json(CONTRATOS, "conversas.json"),
    conversa: json(CONTRATOS, "conversa.json"),
    turno: json(CONTRATOS, "conversa-turno.json"),
    eventosDoTurno: jsonl("chat-eventos.jsonl"),
    eventosDaDescoberta: jsonl("receitas-descoberta.jsonl"),
    contadores: { itens: 0, turnos: 0, conversas: 0 },
    falhas: [],
    // As receitas de pôr preço (o `receita_id` da conferência) cuja cozinha ela já confirmou.
    confirmadasNoPreco: new Set(),
  };
}

let estado = estadoInicial();

/* -------------------------------------------------------------------------- */
/* Respostas                                                                   */
/* -------------------------------------------------------------------------- */

function enviar(res, status, corpo, cabecalhos = {}) {
  const texto = typeof corpo === "string" ? corpo : JSON.stringify(corpo);
  res.writeHead(status, {
    "Content-Type": typeof corpo === "string" ? "text/plain; charset=utf-8" : "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...cabecalhos,
  });
  res.end(texto);
}

const ok = (res, dados, status = 200) =>
  enviar(res, status, { ok: true, dados, erro: null, categoria: null, pergunta: null });

const recusa = (res, status, categoria, erro, pergunta = null, dados = null) =>
  enviar(res, status, { ok: false, dados, erro, categoria, pergunta });

const ausente = (res, erro = "Não encontrei o que a senhora procurou.") => recusa(res, 404, "ausente", erro);

async function lerCorpo(req) {
  let texto = "";
  for await (const pedaco of req) texto += pedaco;
  if (!texto) return {};
  try {
    return JSON.parse(texto);
  } catch {
    return {};
  }
}

function semAcento(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Um fluxo de eventos (SSE) com `id:`, retomável por `?desde=` ou Last-Event-ID. */
function fluxo(req, res, url, eventos) {
  const desde = Number(url.searchParams.get("desde") ?? req.headers["last-event-id"] ?? 0) || 0;
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    Connection: "keep-alive",
  });
  res.write(": conectado\n\n");
  const fila = eventos.filter((evento) => evento.seq > desde);
  let indice = 0;
  let relogio = null;
  const manterVivo = setInterval(() => res.write(": keepalive\n\n"), 10_000);
  const encerrar = () => {
    clearTimeout(relogio);
    clearInterval(manterVivo);
  };
  const proximo = () => {
    if (indice >= fila.length) {
      encerrar();
      res.end();
      return;
    }
    const evento = fila[indice];
    indice += 1;
    res.write(`id: ${evento.seq}\ndata: ${JSON.stringify(evento)}\n\n`);
    relogio = setTimeout(proximo, ATRASO_DO_FLUXO_MS);
  };
  relogio = setTimeout(proximo, ATRASO_DO_FLUXO_MS);
  req.on("close", encerrar);
}

/** Uma foto que não é foto: um gradiente na cor da chave, para a grade ter corpo. */
function imagemDaChave(chave) {
  const tom = parseInt(chave.slice(0, 6), 16) % 360;
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">' +
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    `<stop offset="0" stop-color="hsl(${tom} 65% 62%)"/><stop offset="1" stop-color="hsl(${(tom + 35) % 360} 60% 38%)"/>` +
    "</linearGradient></defs>" +
    '<rect width="640" height="480" fill="url(#g)"/>' +
    `<circle cx="320" cy="250" r="130" fill="hsl(${tom} 55% 90%)" opacity=".5"/>` +
    "</svg>"
  );
}

/* -------------------------------------------------------------------------- */
/* Rotas                                                                       */
/* -------------------------------------------------------------------------- */

const ROTAS = [];
const rota = (metodo, padrao, tratar) => ROTAS.push({ metodo, padrao, tratar });

// Saúde e controle dos testes
rota("GET", /^\/saude\/(vivo|pronto)$/, (_req, res) => enviar(res, 200, { ok: true }));
rota("POST", /^\/__reiniciar$/, (_req, res) => {
  estado = estadoInicial();
  enviar(res, 200, { reiniciado: true });
});
rota("POST", /^\/__falhar$/, async (req, res) => {
  const { caminho, status = 503, vezes = 1 } = await lerCorpo(req);
  estado.falhas.push({ caminho, status, vezes });
  enviar(res, 200, { agendado: { caminho, status, vezes } });
});

// Visão geral
rota("GET", /^\/api\/visao-geral$/, (_req, res) => ok(res, estado.visaoGeral));

// Despensa (em `despensa.mjs`): a lista, o item, as mudanças, o orçamento e a devolução
rota("GET", /^\/api\/despensa\/planilha\.txt$/, (_req, res) => enviar(res, 200, estado.planilha));
rotasDaDespensa({ rota, ok, recusa, ausente, lerCorpo, despensa: () => estado.despensa });

// Receitas (em `receitas.mjs`): o catálogo, as abas, o detalhe, a avaliação, as
// notas, a resposta sobre a receita, a receita trazida pelo endereço, o preço
// do que falta e a descoberta.
rotasDasReceitas({ rota, ok, recusa, ausente, lerCorpo, fluxo, estado: () => estado });

// Cozinha (em `cozinha.mjs`): o perfil, cada item e os limites da rotina
rotasDaCozinha({ rota, ok, recusa, ausente, lerCorpo, cozinha: () => estado.perfil });

// Preço preliminar e as premissas dele

/** O valor escrito na unidade da premissa: dinheiro com "R$", o resto com a unidade dele. */
function textoDaPremissa(anterior, valor) {
  const numero = (casas) => valor.toFixed(casas).replace(".", ",");
  const achado = /^(R\$ )?[\d.,]+\s*(.*)$/.exec(anterior ?? "");
  if (!achado) return `R$ ${numero(2)}`;
  const [, cifrao, unidade] = achado;
  const sufixo = unidade ? ` ${unidade}` : "";
  return cifrao ? `R$ ${numero(2)}${sufixo}` : `${Number.isInteger(valor) ? valor : numero(2)}${sufixo}`;
}
rota("GET", /^\/api\/parametros\/([^/]+)$/, (_req, res, { partes }) => {
  const premissa = estado.estimativa.premissas.find((p) => p.nome === decodeURIComponent(partes[1]));
  return premissa ? ok(res, premissa) : ausente(res, "Não encontrei esse parâmetro.");
});
rota("PUT", /^\/api\/parametros\/([^/]+)$/, async (req, res, { partes }) => {
  const premissa = estado.estimativa.premissas.find((p) => p.nome === decodeURIComponent(partes[1]));
  if (!premissa) return ausente(res, "Não encontrei esse parâmetro.");
  const { valor = null } = await lerCorpo(req);
  if (valor !== null && (typeof valor !== "number" || !(valor >= 0))) return recusa(res, 422, "uso", "Esse valor não serve.");
  const gravada = copia(estado.parametroEscrita.resposta);
  // O motor falso só ecoa o número; o texto segue a unidade da premissa, como a
  // API de verdade escreve ("R$ 1,20 por porção", "67 horas de fogo").
  const texto = valor === null ? null : textoDaPremissa(premissa.valor?.texto, valor);
  // Sem o valor dela, a premissa volta ao padrão com fonte; sem padrão, falta.
  const padrao = premissa.origem === "padrao" ? copia(premissa) : null;
  Object.assign(premissa, {
    ...gravada,
    nome: premissa.nome,
    rotulo: premissa.rotulo,
    valor: valor === null ? padrao?.valor ?? null : { valor, texto },
    origem: valor === null ? (padrao ? "padrao" : "falta") : "dela",
    fonte: valor === null ? padrao?.fonte ?? null : gravada.fonte,
  });
  ok(res, premissa);
});

// Cardápio (em `cardapio.mjs`): os pratos, a decisão, o desfazer e as notas
rotasDoCardapio({
  rota,
  ok,
  recusa,
  ausente,
  lerCorpo,
  cardapio: () => estado.cardapio,
  custoDaPorcao: () => custoDaPorcao((arquivo) => json(CONTRATOS, arquivo)),
});

// Histórico (em `historico.mjs`): a busca, os filtros, os dias e o cursor
rotasDoHistorico({ rota, ok, recusa, atividades: () => estado.atividades });

// Pôr preço (em `preco.mjs`): a conferência, o custo, os caminhos e o controle
rotasDoPreco({
  rota,
  ok,
  ausente,
  lerCorpo,
  contrato: (arquivo) => json(CONTRATOS, arquivo),
  confirmadas: () => estado.confirmadasNoPreco,
});

// Os dados dela, para baixar
/*
 * "Restaurar os dados da planilha": responde como a API, com a confirmação.
 * O estado do motor falso é de todos os testes, que rodam juntos: aqui ele não
 * volta ao começo (o recomeço de verdade é conferido nos testes da API), só
 * conta o pedido, para o teste ver que a tela pediu uma vez só.
 */
rota("POST", /^\/api\/dados\/restaurar$/, async (req, res) => {
  const { confirmar } = await lerCorpo(req);
  if (confirmar !== true) {
    return recusa(res, 200, "uso", "Para restaurar, é preciso confirmar: tudo o que a senhora mudou volta a ser como na planilha.");
  }
  estado.restauracoes = (estado.restauracoes ?? 0) + 1;
  ok(res, copia(estado.restauracao));
});
rota("GET", /^\/__restauracoes$/, (_req, res) => ok(res, { vezes: estado.restauracoes ?? 0 }));

rota("GET", /^\/api\/exportacao$/, (_req, res) =>
  enviar(res, 200, JSON.stringify(estado.exportacao, null, 2), {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Disposition": 'attachment; filename="sabor-da-maria-dados.json"',
  }),
);

// Imagens (só chave hexadecimal, nunca endereço)
rota("GET", /^\/api\/imagens\/([0-9a-f]{8,64})$/, (_req, res, { partes }) =>
  enviar(res, 200, imagemDaChave(partes[1]), {
    "Content-Type": "image/svg+xml",
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
  }),
);
rota("GET", /^\/api\/imagens\/([0-9a-f]{8,64})\/credito$/, (_req, res) =>
  ok(res, { credito: "Foto: Wikimedia Commons (CC BY-SA 4.0)", licenca: "CC BY-SA 4.0", fonte_url: null }),
);

// Conversa
//
// Cada teste da conversa trabalha na sua própria "sessão" (o cookie
// `e2e-sessao`), com conversas e turnos só dela: os testes rodam em paralelo,
// e um turno de um teste não pode aparecer como "respondendo" na tela de
// outro. Sem o cookie, vale a sessão padrão, com as conversas do contrato.
//
// O turno segue um roteiro com tempos (ms desde o POST), escolhido pelo que
// ela escreveu: o do contrato; "porção de arroz" (valores escondidos até a
// conta fechar); "devagar" (turno longo, para parar e recarregar no meio);
// "cozinha" (um card de pergunta com botões); e um pedido com `acao` (o
// backend executa antes e diz o que anotou). O fluxo manda o que já passou do
// tempo e o resto na hora certa; parar corta o roteiro e encerra o turno.

const SENTINELA = "";

function chatInicial() {
  const lista = copia(estado.conversas);
  const aberta = copia(estado.conversa);
  const conversas = new Map(
    lista.conversas.map((resumo) => [
      resumo.id,
      resumo.id === aberta.id
        ? { ...aberta, previa: resumo.previa, atualizado_texto: resumo.atualizado_texto }
        : { id: resumo.id, titulo: resumo.titulo, mensagens: [], previa: resumo.previa, atualizado_texto: resumo.atualizado_texto },
    ]),
  );
  return { atual: lista.atual, ordem: lista.conversas.map((c) => c.id), conversas, turnos: new Map(), ultimoPedido: null, disponivel: true };
}

function chatDe(req) {
  const sessao = /(?:^|;\s*)e2e-sessao=([^;]+)/.exec(req.headers.cookie ?? "")?.[1] ?? "padrao";
  estado.chats ??= new Map();
  if (!estado.chats.has(sessao)) estado.chats.set(sessao, chatInicial());
  return estado.chats.get(sessao);
}

const OPCOES_DO_FORNO = [
  {
    rotulo: "Tenho",
    texto: "Tenho forno.",
    acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "sim" },
  },
  {
    rotulo: "Não tenho",
    texto: "Não tenho forno.",
    acao: { tipo: "responder", tipo_pergunta: "equipamento", campo: "forno", resposta: "nao" },
  },
  { rotulo: "Não sei", texto: "Não sei se tenho forno." },
];

/** Os 15 cards do contrato, um exemplo de cada (`contratos/web/cartoes/`). */
const TIPOS_DE_CARTAO = [
  "despensa_resumo",
  "ingrediente",
  "receita",
  "viabilidade",
  "comparacao",
  "pergunta",
  "cozinha_atualizada",
  "orcamento",
  "custo_porcao",
  "cenarios",
  "ponto_de_preco",
  "preco_preliminar",
  "decisao",
  "avaliacao_da_receita",
  "fontes",
];

function roteiro(pedido, conversaId) {
  const texto = semAcento(pedido.texto ?? "");
  const atividade = (id, ferramenta, rotulo, rotuloFeito) => ({
    tipo: "atividade.iniciada",
    atividade_id: id,
    ferramenta,
    rotulo,
    rotulo_feito: rotuloFeito,
  });
  if (pedido.acao) {
    return [
      [0, { tipo: "turno.iniciado", conversa_id: conversaId }],
      [150, { tipo: "acao.resultado", ok: true, texto: "Anotei: a senhora tem forno." }],
      [300, { tipo: "estado.alterado", recursos: ["perfil", "receitas"] }],
      [450, { tipo: "texto.final", texto: "Anotado. Com o forno, o arroz com frango continua de pé.", retirados: 0 }],
      [600, { tipo: "turno.concluido" }],
    ];
  }
  if (texto.includes("todos os cartoes")) {
    const cartoes = TIPOS_DE_CARTAO.map((tipo, indice) => {
      const exemplo = json(CONTRATOS, `cartoes/${tipo}.json`);
      return [100 + indice * 40, { tipo: "cartao", ...exemplo, cartao_id: `k-todos-${indice}` }];
    });
    return [
      [0, { tipo: "turno.iniciado", conversa_id: conversaId }],
      ...cartoes,
      [900, { tipo: "texto.final", texto: "Aqui está um card de cada tipo que eu mostro na conversa.", retirados: 0 }],
      [1000, { tipo: "turno.concluido" }],
    ];
  }
  if (texto.includes("porcao de arroz")) {
    return [
      [0, { tipo: "turno.iniciado", conversa_id: conversaId }],
      [300, atividade("at-1", "calcular_cmv", "calculando o custo por porção", "calculei o custo por porção")],
      [900, { tipo: "atividade.concluida", atividade_id: "at-1", ok: true }],
      [1100, { tipo: "texto.parcial", delta: `A porção de arroz com frango sai ${SENTINELA} de ingrediente` }],
      [1300, { tipo: "texto.parcial", delta: `, e o preço mínimo fica em ${SENTINELA} por porção.` }],
      [
        4500,
        {
          tipo: "texto.final",
          texto: "A porção de arroz com frango sai **R$ 2,47** de ingrediente, e o preço mínimo fica em R$ 2,75 por porção.",
          retirados: 0,
        },
      ],
      [4600, { tipo: "sugestoes", opcoes: [{ rotulo: "Quanto cobrar?", texto: "Quanto eu cobro por porção?" }] }],
      [4700, { tipo: "turno.concluido" }],
    ];
  }
  if (texto.includes("devagar")) {
    const passos = [
      ["diagnostico_despensa", "olhando sua despensa", "olhei sua despensa"],
      ["consultar_planilha", "lendo a sua planilha", "li a sua planilha"],
      ["comparar_candidatas", "comparando as receitas", "comparei as receitas"],
      ["consultar_orcamento", "vendo o orçamento", "vi o orçamento"],
    ];
    return [
      [0, { tipo: "turno.iniciado", conversa_id: conversaId }],
      ...passos.flatMap(([ferramenta, rotulo, feito], i) => [
        [300 + i * 2500, atividade(`at-${i + 1}`, ferramenta, rotulo, feito)],
        [2300 + i * 2500, { tipo: "atividade.concluida", atividade_id: `at-${i + 1}`, ok: true }],
      ]),
      [10_500, { tipo: "texto.parcial", delta: "Olhei tudo com calma. " }],
      [11_500, { tipo: "texto.final", texto: "Olhei tudo com calma: a despensa, a planilha, as receitas e o orçamento.", retirados: 0 }],
      [11_700, { tipo: "turno.concluido" }],
    ];
  }
  if (texto.includes("cozinha")) {
    return [
      [0, { tipo: "turno.iniciado", conversa_id: conversaId }],
      [150, atividade("at-1", "proxima_pergunta", "separando a próxima pergunta", "separei a próxima pergunta")],
      [300, { tipo: "atividade.concluida", atividade_id: "at-1", ok: true }],
      [
        450,
        {
          tipo: "cartao",
          cartao_id: "k-pergunta",
          tipo_cartao: "pergunta",
          ref: { rota: null },
          gerado_texto: "agora",
          dados: {
            ha_pergunta: true,
            pergunta: "A senhora tem forno em casa?",
            tipo: "equipamento",
            campo: "forno",
            por_que_esta: "O arroz com frango termina no forno.",
            pratos_afetados: ["Arroz com frango"],
            opcoes: OPCOES_DO_FORNO,
          },
        },
      ],
      [600, { tipo: "texto.final", texto: "Antes de seguir, preciso saber uma coisa da sua cozinha.", retirados: 0 }],
      [750, { tipo: "turno.concluido" }],
    ];
  }
  return estado.eventosDoTurno.map((evento, indice) => {
    const resto = Object.fromEntries(Object.entries(evento).filter(([campo]) => campo !== "seq" && campo !== "turno_id"));
    return [indice * ATRASO_DO_FLUXO_MS, resto.tipo === "turno.iniciado" ? { ...resto, conversa_id: conversaId } : resto];
  });
}

function novoTurno(chat, conversa, pedido) {
  estado.contadores.turnos += 1;
  const id = `t-falso-${estado.contadores.turnos}`;
  const inicio = Date.now();
  const eventos = roteiro(pedido, conversa.id).map(([t, evento], indice) => ({
    t: inicio + t,
    evento: { seq: indice + 1, turno_id: id, ...evento },
  }));
  const turno = { id, conversaId: conversa.id, inicio, eventos, estado: "em_andamento", pedido, guardado: false };
  chat.turnos.set(id, turno);
  return turno;
}

const jaPassaram = (turno, agora = Date.now()) => turno.eventos.filter((item) => item.t <= agora);
const fimDoTurno = (tipo) => tipo === "turno.concluido" || tipo === "turno.cancelado" || tipo === "turno.falhou";

/** O turno que terminou vira a resposta guardada na conversa (uma vez só). */
function guardarSeTerminou(chat, turno) {
  const ultimo = jaPassaram(turno).at(-1)?.evento;
  if (turno.guardado || !ultimo || !fimDoTurno(ultimo.tipo)) return;
  turno.guardado = true;
  turno.estado = ultimo.tipo === "turno.concluido" ? "concluido" : ultimo.tipo === "turno.cancelado" ? "cancelado" : "falhou";
  const conversa = chat.conversas.get(turno.conversaId);
  if (!conversa) return;
  const eventos = turno.eventos.map((item) => item.evento);
  const final = eventos.find((evento) => evento.tipo === "texto.final");
  const rascunho = eventos.filter((evento) => evento.tipo === "texto.parcial").map((evento) => evento.delta).join("");
  const texto = final ? final.texto : rascunho;
  const resultado = eventos.find((evento) => evento.tipo === "acao.resultado");
  estado.contadores.mensagens = (estado.contadores.mensagens ?? 0) + 1;
  conversa.mensagens.push({
    id: `m-falsa-${estado.contadores.mensagens}`,
    papel: "consultora",
    turno_id: turno.id,
    partes: [
      ...(texto ? [{ tipo: "texto", texto, ...(final ? {} : { rascunho: true }) }] : []),
      ...eventos
        .filter((evento) => evento.tipo === "cartao")
        .map(({ cartao_id, tipo_cartao, ref, gerado_texto, dados }) => ({
          tipo: "cartao",
          cartao: { cartao_id, tipo_cartao, ref, gerado_texto, dados },
        })),
    ],
    quando_texto: "agora",
    estado: turno.estado,
    retirados: final?.retirados ?? 0,
    atividades: eventos
      .filter((evento) => evento.tipo === "atividade.iniciada")
      .map((evento) => ({ rotulo_feito: evento.rotulo_feito, ok: true })),
    acao_resultado: resultado ? { ok: resultado.ok, texto: resultado.texto } : null,
    sugestoes: eventos.find((evento) => evento.tipo === "sugestoes")?.opcoes ?? [],
  });
  if (texto) conversa.previa = texto.replace(/\*\*/g, "").slice(0, 80);
}

function emAndamento(chat, conversaId) {
  for (const turno of chat.turnos.values()) {
    guardarSeTerminou(chat, turno);
    if (turno.conversaId === conversaId && !turno.guardado) return turno;
  }
  return null;
}

function estadoDoTurno(turno) {
  return {
    turno_id: turno.id,
    estado: turno.guardado ? turno.estado : "em_andamento",
    ultimo_seq: jaPassaram(turno).length,
    iniciado_texto: "agora",
  };
}

function resumoDe(chat, conversa) {
  return {
    id: conversa.id,
    titulo: conversa.titulo,
    previa: conversa.previa ?? "",
    atualizado_texto: conversa.atualizado_texto ?? "agora",
    respondendo: emAndamento(chat, conversa.id) !== null,
  };
}

function conversaParaTela(chat, conversa) {
  const turno = emAndamento(chat, conversa.id);
  return {
    id: conversa.id,
    titulo: conversa.titulo,
    mensagens: conversa.mensagens,
    atual: chat.atual === conversa.id,
    turno_em_andamento: turno ? estadoDoTurno(turno) : null,
  };
}

/** O fluxo de um turno: o que já passou do tempo, de uma vez, e o resto na hora certa. */
function fluxoDoTurno(req, res, url, chat, turno) {
  let enviados = Number(url.searchParams.get("desde") ?? req.headers["last-event-id"] ?? 0) || 0;
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    Connection: "keep-alive",
  });
  res.write(": conectado\n\n");
  const manterVivo = setInterval(() => res.write(": keepalive\n\n"), 10_000);
  const relogio = setInterval(() => {
    for (const { evento } of jaPassaram(turno).filter((item) => item.evento.seq > enviados)) {
      res.write(`id: ${evento.seq}\ndata: ${JSON.stringify(evento)}\n\n`);
      enviados = evento.seq;
      if (fimDoTurno(evento.tipo)) {
        guardarSeTerminou(chat, turno);
        encerrar();
        res.end();
        return;
      }
    }
  }, 50);
  function encerrar() {
    clearInterval(relogio);
    clearInterval(manterVivo);
  }
  req.on("close", encerrar);
}

rota("GET", /^\/api\/conversas$/, (req, res) => {
  const chat = chatDe(req);
  ok(res, {
    atual: chat.atual,
    conversas: chat.ordem.map((id) => chat.conversas.get(id)).filter(Boolean).map((conversa) => resumoDe(chat, conversa)),
  });
});
rota("POST", /^\/api\/conversas$/, async (req, res) => {
  const chat = chatDe(req);
  const { titulo = "Conversa nova" } = await lerCorpo(req);
  estado.contadores.conversas += 1;
  const conversa = { id: `cv-nova-${estado.contadores.conversas}`, titulo, mensagens: [], previa: "", atualizado_texto: "agora" };
  chat.conversas.set(conversa.id, conversa);
  chat.ordem.unshift(conversa.id);
  chat.atual = conversa.id;
  ok(res, conversaParaTela(chat, conversa), 201);
});
rota("GET", /^\/api\/conversas\/([^/]+)$/, (req, res, { partes }) => {
  const chat = chatDe(req);
  const conversa = chat.conversas.get(decodeURIComponent(partes[1]));
  if (!conversa) return ausente(res, "Não encontrei essa conversa.");
  ok(res, conversaParaTela(chat, conversa));
});
rota("PATCH", /^\/api\/conversas\/([^/]+)$/, async (req, res, { partes }) => {
  const chat = chatDe(req);
  const conversa = chat.conversas.get(decodeURIComponent(partes[1]));
  if (!conversa) return ausente(res, "Não encontrei essa conversa.");
  const { titulo, atual } = await lerCorpo(req);
  if (typeof titulo === "string" && titulo.trim()) conversa.titulo = titulo.trim().slice(0, 200);
  if (atual === true) chat.atual = conversa.id;
  ok(res, { id: conversa.id, titulo: conversa.titulo, atual: chat.atual === conversa.id });
});
rota("DELETE", /^\/api\/conversas\/([^/]+)$/, (req, res, { partes }) => {
  const chat = chatDe(req);
  const id = decodeURIComponent(partes[1]);
  if (!chat.conversas.delete(id)) return ausente(res, "Não encontrei essa conversa.");
  chat.ordem = chat.ordem.filter((outra) => outra !== id);
  for (const [turnoId, turno] of chat.turnos) if (turno.conversaId === id) chat.turnos.delete(turnoId);
  if (chat.atual === id) chat.atual = chat.ordem[0] ?? null;
  ok(res, { apagada: id, atual: chat.atual });
});
rota("POST", /^\/api\/conversas\/([^/]+)\/turnos$/, async (req, res, { partes }) => {
  const chat = chatDe(req);
  const conversa = chat.conversas.get(decodeURIComponent(partes[1]));
  if (!conversa) return ausente(res, "Não encontrei essa conversa.");
  const pedido = await lerCorpo(req);
  if (!pedido.id_cliente) return recusa(res, 422, "uso", "Faltou o id_cliente do turno.");
  if (!chat.disponivel) return recusa(res, 503, "rede", "O agente está fora do ar agora.");
  const rodando = emAndamento(chat, conversa.id);
  if (rodando) {
    return recusa(res, 409, "ocupado", "Ainda estou respondendo a mensagem anterior.", null, { turno_id: rodando.id });
  }
  chat.ultimoPedido = pedido;
  const turno = novoTurno(chat, conversa, pedido);
  estado.contadores.mensagens = (estado.contadores.mensagens ?? 0) + 1;
  conversa.mensagens.push({
    id: `m-falsa-${estado.contadores.mensagens}`,
    papel: "senhora",
    turno_id: turno.id,
    partes: [{ tipo: "texto", texto: pedido.texto }],
    quando_texto: "agora",
    contexto: pedido.contexto ?? null,
  });
  if (conversa.titulo === "Conversa nova" && pedido.texto) conversa.titulo = pedido.texto.slice(0, 40);
  conversa.previa = pedido.texto;
  ok(res, { turno_id: turno.id }, 202);
});
rota("GET", /^\/api\/conversas\/([^/]+)\/turnos\/([^/]+)$/, (req, res, { partes }) => {
  const chat = chatDe(req);
  const turno = chat.turnos.get(decodeURIComponent(partes[2]));
  if (!turno) return ausente(res, "Não encontrei esse turno.");
  guardarSeTerminou(chat, turno);
  ok(res, estadoDoTurno(turno));
});
rota("POST", /^\/api\/conversas\/([^/]+)\/turnos\/([^/]+)\/parar$/, (req, res, { partes }) => {
  const chat = chatDe(req);
  const turno = chat.turnos.get(decodeURIComponent(partes[2]));
  if (!turno) return ausente(res, "Não encontrei esse turno.");
  const agora = Date.now();
  const passados = jaPassaram(turno, agora);
  // Ainda rodando: o resto do roteiro sai, e o turno termina cancelado agora.
  if (!turno.guardado && !fimDoTurno(passados.at(-1)?.evento.tipo ?? "")) {
    turno.eventos = [
      ...passados,
      { t: agora, evento: { seq: passados.length + 1, turno_id: turno.id, tipo: "turno.cancelado" } },
    ];
  }
  ok(res, { ...estadoDoTurno(turno), estado: "cancelado" });
});
rota("GET", /^\/api\/conversas\/([^/]+)\/turnos\/([^/]+)\/eventos$/, (req, res, { partes, url }) => {
  const chat = chatDe(req);
  const turno = chat.turnos.get(decodeURIComponent(partes[2]));
  if (turno) return fluxoDoTurno(req, res, url, chat, turno);
  // O turno do contrato (a conversa de exemplo), para quem chega por ele.
  const turnoId = decodeURIComponent(partes[2]);
  fluxo(req, res, url, estado.eventosDoTurno.map((evento) => ({ ...evento, turno_id: turnoId })));
});
rota("GET", /^\/api\/chat\/estado$/, (req, res) => {
  const chat = chatDe(req);
  ok(res, {
    disponivel: chat.disponivel,
    perfil: "sabor-da-maria",
    modelo: "claude-fable-5-1",
    ...(chat.disponivel ? {} : { motivo: "O agente está fora do ar agora. As outras telas continuam funcionando normalmente." }),
  });
});
// Controle dos testes da conversa: o último pedido que chegou, e ligar ou
// desligar o agente (a faixa de fora do ar).
rota("GET", /^\/__conversa\/ultimo-pedido$/, (req, res) => enviar(res, 200, { pedido: chatDe(req).ultimoPedido }));
rota("POST", /^\/__conversa\/disponivel$/, async (req, res) => {
  const chat = chatDe(req);
  const { disponivel = true } = await lerCorpo(req);
  chat.disponivel = Boolean(disponivel);
  enviar(res, 200, { disponivel: chat.disponivel });
});

/* -------------------------------------------------------------------------- */
/* Servidor                                                                    */
/* -------------------------------------------------------------------------- */

function falhaAgendada(caminho) {
  const falha = estado.falhas.find((f) => caminho.startsWith(f.caminho) && f.vezes > 0);
  if (!falha) return null;
  falha.vezes -= 1;
  return falha.status;
}

const servidor = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORTA}`);
  const caminho = url.pathname;
  try {
    const status = caminho.startsWith("/__") ? null : falhaAgendada(caminho);
    if (status) return enviar(res, status, { detail: "falha simulada pelo motor falso" });

    for (const { metodo, padrao, tratar } of ROTAS) {
      if (metodo !== req.method) continue;
      const partes = caminho.match(padrao);
      if (partes) return await tratar(req, res, { partes, url });
    }
    return ausente(res, "Não encontrei esse endereço.");
  } catch (erro) {
    console.error("motor falso:", erro);
    return enviar(res, 500, { detail: "erro no motor falso" });
  }
});

servidor.listen(PORTA, "127.0.0.1", () => {
  console.log(`motor falso em http://127.0.0.1:${PORTA}`);
});

for (const sinal of ["SIGINT", "SIGTERM"]) {
  process.on(sinal, () => servidor.close(() => process.exit(0)));
}
