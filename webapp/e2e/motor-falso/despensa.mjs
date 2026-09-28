/* global structuredClone */
/**
 * A despensa do motor falso: a lista, o item, as mudanças dela e os R$ 80.
 *
 * O estado começa nos exemplos de `contratos/web/` (a lista, os dois detalhes e
 * as mudanças) e muda em memória como a API de verdade muda: acrescentar "já
 * tinha" não mexe no orçamento, "comprei com os R$ 80" debita, tirar devolve,
 * desfazer volta o item (e debita de novo), devolver uma compra tira o item que
 * ela acrescentou. As frases imitam as da API; o dinheiro é formatado aqui
 * porque aqui é o lugar da API, e só nos testes.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const INICIAL = 80;
const FUSO = "America/Sao_Paulo";

const reais = (valor) =>
  `${valor < 0 ? "-" : ""}R$ ${Math.abs(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dinheiro = (valor) => ({ valor: Math.round(valor * 100) / 100, texto: reais(valor) });
const numero = (valor, casas = 3) => valor.toLocaleString("pt-BR", { maximumFractionDigits: casas });
const copia = (valor) => structuredClone(valor);
const minusculo = (nome) => nome.charAt(0).toLowerCase() + nome.slice(1);

/** O que vai na resposta: sem os campos internos (`_linha`, `_antes`…). */
function semInternos(objeto) {
  return Object.fromEntries(Object.entries(objeto).filter(([chave]) => !chave.startsWith("_")).map(([k, v]) => [k, copia(v)]));
}
const agora = () =>
  `hoje, ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: FUSO })}`;

function semAcento(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

/* -------------------------------------------------------------------------- */
/* O artigo do nome, como o léxico da API faz com os nomes mais comuns          */
/* -------------------------------------------------------------------------- */

const FEMININOS = new Set(
  "farinha cobertura carne cebola couve batata manteiga polenta canela castanha salsinha abobrinha cenoura calabresa linguica massa mandioca pimenta goiabada gelatina ervilha lentilha".split(" "),
);
const MASCULINOS = new Set(
  "creme milho leite arroz feijao queijo oleo azeite acucar sal alho tomate ovo peito miolo macarrao bacon fuba caldo chocolate doce frango presunto".split(" "),
);

/** "do creme de leite", "da farinha", ou "de tahine" quando o gênero não é conhecido. */
function doNome(nome) {
  const com = comArtigo(nome);
  return com ? `d${com}` : `de ${minusculo(nome)}`;
}

function comArtigo(nome) {
  const nucleo = semAcento(nome).split(/\s+(?:de|com|em)\s+/)[0].split(/\s+/)[0] ?? "";
  const plural = nucleo.endsWith("s") && !nucleo.endsWith("ss");
  const singular = plural ? nucleo.replace(/(oe|ae)s$/, "ao").replace(/s$/, "") : nucleo;
  if (FEMININOS.has(singular)) return `${plural ? "as" : "a"} ${minusculo(nome)}`;
  if (MASCULINOS.has(singular)) return `${plural ? "os" : "o"} ${minusculo(nome)}`;
  return null;
}

/* -------------------------------------------------------------------------- */
/* Unidades: as que a conta da API lê                                          */
/* -------------------------------------------------------------------------- */

const BASE = { kg: ["kg", 1], g: ["kg", 0.001], mg: ["kg", 0.000001], l: ["L", 1], ml: ["L", 0.001] };
const CONTAGEM = new Set(["un", "und", "unid", "unidade", "unidades", "pc", "pct", "peca", "peça", "duzia", "dúzia"]);

/** `{base, fator, conteudo}`: `conteudo` é o que vem em cada embalagem, `null` se não diz. */
function lerUnidade(rotulo) {
  const limpo = semAcento(rotulo ?? "");
  if (BASE[limpo]) return { base: BASE[limpo][0], fator: BASE[limpo][1], embalagem: null };
  const achado = /(\d+(?:[.,]\d+)?)\s*(kg|mg|g|ml|l)\b/i.exec(limpo);
  if (achado) {
    const quanto = Number(achado[1].replace(",", "."));
    if (!(quanto > 0)) return null;
    const [base, fator] = BASE[achado[2].toLowerCase()];
    return { base, fator: quanto * fator, embalagem: `${numero(quanto)} ${achado[2].toLowerCase() === "l" ? "L" : achado[2].toLowerCase()}` };
  }
  if (CONTAGEM.has(limpo)) return { base: "un", fator: null, embalagem: null };
  return null;
}

function quantidadeTexto(valorBase, base) {
  if (base === "kg") return valorBase < 1 ? `${numero(valorBase * 1000)} g` : `${numero(valorBase)} kg`;
  if (base === "L") return valorBase < 1 ? `${numero(valorBase * 1000)} ml` : `${numero(valorBase)} L`;
  return `${numero(valorBase)} ${valorBase === 1 ? "unidade" : "unidades"}`;
}

const embalagens = (n) => `${numero(n)} ${n === 1 ? "embalagem" : "embalagens"}`;

/** O item com a conta refeita a partir do que ela disse (`_linha`). */
function montar(item) {
  item._pendencia = null;
  const { estoque, unidade, quantidade, preco } = item._linha;
  const lida = lerUnidade(unidade);
  const opaca = lida.base === "un" && lida.fator === null && CONTAGEM.has(semAcento(unidade)) && item._embalagemOpaca;
  const fator = lida.fator ?? 1;
  const estoqueBase = estoque * fator;
  const compradoBase = quantidade * fator;
  item.estoque = Math.round(estoqueBase * 10000) / 10000;
  item.unidade = lida.base;
  if (estoque === 0) item.estoque_texto = "acabou";
  else if (opaca) item.estoque_texto = `${embalagens(estoque)} (peso não informado)`;
  else if (lida.embalagem) item.estoque_texto = `${quantidadeTexto(estoqueBase, lida.base)} (${embalagens(estoque)} de ${lida.embalagem})`;
  else item.estoque_texto = quantidadeTexto(estoqueBase, lida.base);
  item.pago = preco === null ? null : dinheiro(preco);
  const conhecido = preco !== null && !opaca && compradoBase > 0;
  item.custo_unitario = conhecido ? { ...dinheiro(preco / compradoBase), texto: `${reais(preco / compradoBase)}/${lida.base}` } : null;
  const conta = lida.embalagem
    ? `${numero(quantidade)} × ${numero(fator)} ${lida.base} = ${numero(compradoBase)} ${lida.base}; `
    : "";
  if (preco === null) item.derivacao = "a senhora não disse quanto pagou; sem o preço, não dá para saber o custo";
  else if (opaca) item.derivacao = `${reais(preco)} ÷ ${embalagens(quantidade)}; sem o peso da embalagem, não dá para saber o custo por quilo`;
  else item.derivacao = `${conta}${reais(preco)} ÷ ${numero(compradoBase)} ${lida.base} = ${item.custo_unitario.texto}`;
  item.confianca = conhecido ? (lida.embalagem ? "media" : "alta") : "desconhecida";
  item.confianca_rotulo = !conhecido
    ? preco === null
      ? "falta o preço que a senhora pagou"
      : "falta o peso da embalagem"
    : lida.embalagem
      ? "conta com conversão de embalagem"
      : item.origem === "planilha"
        ? "conta direta da planilha"
        : "conta direta";
  item.pendente = preco === null || opaca;
  item._comprado = `${lida.embalagem ? `${embalagens(quantidade)} de ${lida.embalagem}` : opaca ? embalagens(quantidade) : quantidadeTexto(compradoBase, lida.base)} por ${preco === null ? "preço não informado" : reais(preco)}`;
  return item;
}

/* -------------------------------------------------------------------------- */
/* Estado                                                                      */
/* -------------------------------------------------------------------------- */

const lerJson = (pasta, arquivo) => JSON.parse(readFileSync(join(pasta, arquivo), "utf-8"));

/** O que a lista de exemplo diz de cada item, lido de volta para `_linha`. */
function linhaDoExemplo(item, detalhes) {
  const detalhe = detalhes.get(item.id);
  const rotulo = detalhe?.unidade_compra_rotulo;
  if (rotulo && lerUnidade(rotulo)?.embalagem) {
    const fator = lerUnidade(rotulo).fator;
    const quantidade = Math.round((item.estoque / fator) * 1000) / 1000;
    return { estoque: quantidade, unidade: rotulo, quantidade, preco: item.pago?.valor ?? null };
  }
  const opaca = item.confianca === "desconhecida" && item.pago !== null;
  return {
    estoque: opaca ? 1 : item.estoque,
    unidade: opaca ? "un" : item.unidade,
    quantidade: opaca ? 1 : item.estoque || 1,
    preco: item.pago?.valor ?? null,
  };
}

export function despensaInicial(contratos) {
  const lista = lerJson(contratos, "despensa.json");
  const detalhes = new Map(
    ["despensa-item.json", "despensa-item-comprado.json"].map((arquivo) => {
      const detalhe = lerJson(contratos, arquivo);
      return [detalhe.id, detalhe];
    }),
  );
  const pendencias = new Map(lista.pendencias.map((p) => [p.id, p]));
  const itens = lista.itens.map((item) => {
    const detalhe = detalhes.get(item.id);
    return {
      ...copia(item),
      _linha: linhaDoExemplo(item, detalhes),
      _embalagemOpaca: pendencias.get(item.id)?.tipo === "conteudo_embalagem",
      _pendencia: copia(pendencias.get(item.id) ?? null),
      _comprado:
        detalhe?.comprado_texto ?? (item.pago ? `${item.estoque_texto} por ${item.pago.texto}` : `${item.estoque_texto}, sem o preço`),
      _usos: item.receitas_que_usam,
      _receitas: copia(detalhe?.receitas ?? []),
      _planilha:
        item.origem === "planilha"
          ? copia(
              detalhe?.historico?.[0] ?? {
                id: "planilha",
                tipo: "planilha",
                acao: "planilha",
                texto: `Veio da planilha: ${item.pago ? `${item.estoque_texto} por ${item.pago.texto}` : item.estoque_texto}.`,
                quando_texto: "na planilha que a senhora entregou",
                canal: "planilha",
                pode_desfazer: false,
                desfaz: null,
                item_id: item.id,
                item_nome: item.nome,
                motivo: null,
                rota: item.rota,
              },
            )
          : null,
      _prato: null,
    };
  });
  const eventos = [];
  for (const detalhe of detalhes.values()) {
    for (const evento of detalhe.historico) if (evento.id !== "planilha") eventos.push(copia(evento));
  }
  const compras = copia(lista.orcamento.compras);
  return {
    itens,
    eventos,
    compras,
    categorias: copia(lista.categorias_para_escolher),
    rotulos: new Map(lista.categorias_para_escolher.map((c) => [c.id, c.rotulo])),
    chaves: new Map(),
    contadores: {
      itens: 0,
      eventos: Math.max(0, ...eventos.map((e) => Number(e.id.replace("ev-", "")))),
      compras: Math.max(0, ...compras.map((c) => c.id)),
    },
  };
}

/* -------------------------------------------------------------------------- */
/* As formas de resposta                                                        */
/* -------------------------------------------------------------------------- */

function totalInvestido(d) {
  return d.itens.reduce((soma, item) => soma + (item.pago?.valor ?? 0), 0);
}

function publico(item, d) {
  const total = totalInvestido(d);
  const fracao = total > 0 && item.pago ? item.pago.valor / total : 0;
  const usos = item._usos;
  const saida = semInternos(item);
  saida.fracao_do_total = Math.round(fracao * 10000) / 10000;
  saida.fracao_texto = item.pago ? `${Math.round(fracao * 100)}% do que a senhora pagou` : "sem o preço, fica fora do total";
  saida.receitas_que_usam = usos;
  saida.receitas_que_usam_texto = usos === 0 ? "ainda sem receita" : `entra em ${usos} ${usos === 1 ? "receita" : "receitas"}`;
  return saida;
}

function pendenciaDe(item) {
  if (!item.pendente) return null;
  if (item._pendencia) return copia(item._pendencia);
  const nome = minusculo(item.nome);
  if (item.pago === null) {
    return {
      id: item.id,
      ingrediente: item.nome,
      tipo: "preco_pago",
      pergunta: `Dona Maria, sobre ${comArtigo(item.nome) ?? nome}: quanto a senhora pagou, e por qual quantidade? Se não lembrar, o preço de hoje no mercado serve.`,
      impacto: dinheiro(0),
      impacto_texto: `sem o preço, as receitas com ${nome} ficam sem custo`,
      resposta_inline: { tipo: "preco_pago", rotulo: "Quanto a senhora pagou?", unidades: [], campos: ["preco_pago", "quantidade_comprada"] },
      rascunho_chat: `Paguei por ${nome} `,
      rota: `/despensa/${item.id}`,
    };
  }
  return {
    id: item.id,
    ingrediente: item.nome,
    tipo: "conteudo_embalagem",
    pergunta: `Dona Maria, quanto vem na embalagem ${doNome(item.nome)} que a senhora comprou por ${item.pago.texto}? Se estiver escrito no rótulo (em gramas ou ml), me diz que eu calculo certinho.`,
    impacto: copia(item.pago),
    impacto_texto: `${item.pago.texto} parados até isso ser respondido`,
    resposta_inline: { tipo: "conteudo_embalagem", rotulo: "Quanto vem na embalagem?", unidades: ["g", "kg", "ml", "L"] },
    rascunho_chat: `A embalagem ${doNome(item.nome)} tem `,
    rota: `/despensa/${item.id}`,
  };
}

const ativas = (d) => d.compras.filter((c) => !c.estornada && !c.estorno);

function orcamento(d) {
  const gasto = ativas(d).reduce((soma, c) => soma + c.valor.valor, 0);
  const restante = INICIAL - gasto;
  return {
    inicial: dinheiro(INICIAL),
    restante: dinheiro(restante),
    gasto: dinheiro(gasto),
    fracao_gasta: Math.round((gasto / INICIAL) * 10000) / 10000,
    texto:
      gasto === 0
        ? `Nada gasto ainda: restam ${reais(restante)} para complementos.`
        : `Saíram ${reais(gasto)} dos complementos; restam ${reais(restante)}.`,
    compras: copia(ativas(d)),
  };
}

const NENHUMA = { liberadas: [], bloqueadas: [], mudaram: [], texto: "Nenhuma receita em avaliação mudou." };

function ordenar(itens, ordem, d) {
  const nome = (a, b) => semAcento(a.nome).localeCompare(semAcento(b.nome), "pt-BR");
  if (ordem === "nome") return itens.sort(nome);
  if (ordem === "custo") {
    return itens.sort((a, b) => {
      if (!a.custo_unitario || !b.custo_unitario) return (a.custo_unitario ? 0 : 1) - (b.custo_unitario ? 0 : 1);
      return b.custo_unitario.valor - a.custo_unitario.valor;
    });
  }
  if (ordem === "categoria") {
    const posicao = new Map(d.categorias.map((c, n) => [c.id, n]));
    return itens.sort((a, b) => (posicao.get(a.categoria) ?? 99) - (posicao.get(b.categoria) ?? 99) || nome(a, b));
  }
  return itens.sort((a, b) => (b.pago?.valor ?? 0) - (a.pago?.valor ?? 0));
}

function lista(d, url) {
  const q = url.searchParams.get("q");
  const categoria = url.searchParams.get("categoria");
  const ordem = url.searchParams.get("ordem") ?? "valor";
  let itens = [...d.itens];
  if (q) itens = itens.filter((item) => semAcento(item.nome).includes(semAcento(q)));
  if (categoria) itens = itens.filter((item) => item.categoria === categoria);
  const contagem = new Map();
  for (const item of d.itens) contagem.set(item.categoria, (contagem.get(item.categoria) ?? 0) + 1);
  return {
    itens: ordenar(itens, ordem, d).map((item) => publico(item, d)),
    total_investido: dinheiro(totalInvestido(d)),
    total_itens: d.itens.length,
    encontrados: itens.length,
    categorias: d.categorias
      .filter((c) => contagem.get(c.id))
      .map((c) => ({ id: c.id, rotulo: c.rotulo, quantidade: contagem.get(c.id) })),
    categorias_para_escolher: copia(d.categorias),
    pendencias: d.itens.map(pendenciaDe).filter(Boolean),
    orcamento: orcamento(d),
  };
}

function historicoDe(d, item) {
  const doItem = d.eventos.filter((e) => e.item_id === item.id).sort((a, b) => a.id.localeCompare(b.id));
  return [...(item._planilha ? [copia(item._planilha)] : []), ...doItem.map(semInternos)];
}

function detalhe(d, item) {
  return {
    ...publico(item, d),
    comprado_texto: item._comprado,
    unidade_compra_rotulo: item._linha.unidade,
    pendencia: pendenciaDe(item),
    receitas: copia(item._receitas),
    historico: historicoDe(d, item),
    compras: copia(d.compras.filter((c) => c.item_id === item.id && !c.estorno)),
    rascunho_chat: `O que eu posso fazer com ${minusculo(item.nome)}?`,
  };
}

/* -------------------------------------------------------------------------- */
/* Mudanças                                                                     */
/* -------------------------------------------------------------------------- */

function novoEvento(d, item, tipo, acao, texto, extra = {}) {
  d.contadores.eventos += 1;
  for (const e of d.eventos) if (e.item_id === item.id) e.pode_desfazer = false;
  const evento = {
    id: `ev-${String(d.contadores.eventos).padStart(4, "0")}`,
    tipo,
    acao,
    texto,
    quando_texto: agora(),
    canal: "tela",
    pode_desfazer: true,
    desfaz: null,
    item_id: item.id,
    item_nome: item.nome,
    motivo: null,
    rota: `/despensa/${item.id}`,
    ...extra,
  };
  d.eventos.push(evento);
  return evento;
}

function resposta(d, item, evento, texto, extra = {}) {
  return {
    item: item && d.itens.includes(item) ? publico(item, d) : null,
    id: item.id,
    ingrediente: item.nome,
    repetida: false,
    evento: evento?.id ?? null,
    removido: null,
    estorno: null,
    compra: null,
    pendencias_resolvidas: [],
    pendencia: d.itens.includes(item) ? pendenciaDe(item) : null,
    receitas_afetadas: copia(NENHUMA),
    orcamento: orcamento(d),
    texto,
    ...extra,
  };
}

function debitar(d, item, valor, prato) {
  d.contadores.compras += 1;
  const compra = {
    id: d.contadores.compras,
    descricao: `${item.nome} (despensa${prato ? `, para ${prato}` : ""})`,
    ingrediente: null,
    item_id: item.id,
    valor: dinheiro(valor),
    quando_texto: agora(),
    canal: "tela",
    estornada: false,
    estorno: false,
    pode_estornar: true,
    rota_estorno: `/api/compras/${d.contadores.compras}/estorno`,
  };
  d.compras.push(compra);
  return compra;
}

/** Devolve as compras ativas do item; o total devolvido. */
function devolver(d, item) {
  let total = 0;
  for (const compra of ativas(d).filter((c) => c.item_id === item.id)) {
    compra.estornada = true;
    compra.pode_estornar = false;
    total += compra.valor.valor;
  }
  return total;
}

const restante = (d) => INICIAL - ativas(d).reduce((soma, c) => soma + c.valor.valor, 0);

/** A chave de idempotência: o mesmo clique responde o mesmo, com `repetida`. */
function repetida(d, chave) {
  if (!chave || !d.chaves.has(chave)) return null;
  return { ...copia(d.chaves.get(chave)), repetida: true, texto: "Isso já estava anotado.", orcamento: orcamento(d) };
}

function lembrar(d, chave, corpo) {
  if (chave) d.chaves.set(chave, copia(corpo));
  return corpo;
}

const numeroOuNulo = (valor) => (valor === undefined || valor === null || valor === "" ? null : Number(valor));

export function rotasDaDespensa({ rota, ok, recusa, ausente, lerCorpo, despensa }) {
  const naoAchei = (res) => ausente(res, "não encontrei esse ingrediente na despensa");
  const achar = (id) => despensa().itens.find((item) => item.id === id);

  rota("GET", /^\/api\/despensa$/, (_req, res, { url }) => {
    const ordem = url.searchParams.get("ordem");
    if (ordem && !["valor", "nome", "custo", "categoria"].includes(ordem)) return recusa(res, 422, "uso", "ordem desconhecida");
    ok(res, lista(despensa(), url));
  });

  rota("GET", /^\/api\/despensa\/eventos$/, (_req, res, { url }) => {
    const d = despensa();
    const limite = Number(url.searchParams.get("limite") ?? 50) || 50;
    const cursor = url.searchParams.get("cursor");
    const todos = [...d.eventos].sort((a, b) => b.id.localeCompare(a.id));
    const inicio = cursor ? todos.findIndex((e) => e.id === cursor) + 1 : 0;
    const pagina = todos.slice(inicio, inicio + limite);
    const mais = inicio + limite < todos.length;
    ok(res, { eventos: pagina.map(semInternos), proximo_cursor: mais ? pagina.at(-1).id : null, total: todos.length, versao: d.contadores.eventos });
  });

  rota("GET", /^\/api\/despensa\/itens\/([^/]+)$/, (_req, res, { partes }) => {
    const item = achar(decodeURIComponent(partes[1]));
    return item ? ok(res, detalhe(despensa(), item)) : naoAchei(res);
  });

  rota("POST", /^\/api\/despensa\/itens$/, async (req, res) => {
    const d = despensa();
    const pedido = await lerCorpo(req);
    const chave = req.headers["idempotency-key"] ?? pedido.id_cliente ?? null;
    const de_novo = repetida(d, chave);
    if (de_novo) return ok(res, de_novo);
    const nome = String(pedido.nome ?? "").trim().replace(/\s+/g, " ");
    if (!nome) return recusa(res, 200, "uso", "diga o nome do ingrediente");
    if (d.itens.some((item) => semAcento(item.nome) === semAcento(nome))) {
      const existente = d.itens.find((item) => semAcento(item.nome) === semAcento(nome));
      return recusa(res, 200, "uso", `${existente.nome} já está na despensa; corrija o item em vez de acrescentar outro`);
    }
    const unidade = String(pedido.unidade ?? "").trim();
    if (!lerUnidade(unidade)) {
      return recusa(res, 200, "uso", `não entendi a unidade '${unidade}': use kg, g, L, ml, un, ou a embalagem com o peso, como 'pacote 500 g'`);
    }
    const estoque = Number(pedido.estoque);
    if (!(estoque >= 0)) return recusa(res, 422, "uso", "O estoque precisa ser um número.");
    const preco = numeroOuNulo(pedido.preco_pago);
    const origem = pedido.origem === "orcamento" ? "orcamento" : "ja_tinha";
    if (origem === "orcamento" && !(preco > 0)) return recusa(res, 200, "uso", "para comprar com os complementos, diga quanto a senhora pagou");
    if (origem === "orcamento" && preco > restante(d) + 1e-9) {
      return recusa(res, 200, "regra", `a compra exige ${reais(preco)} e restam ${reais(restante(d))} do orçamento`);
    }
    const categoria = pedido.categoria && d.rotulos.has(pedido.categoria) ? pedido.categoria : "outros";
    d.contadores.itens += 1;
    const id = `item-${(0x5a000000 + d.contadores.itens).toString(16)}`;
    const quantidade = numeroOuNulo(pedido.quantidade_comprada) ?? (estoque > 0 ? estoque : 1);
    const item = montar({
      id,
      nome,
      categoria,
      categoria_rotulo: d.rotulos.get(categoria),
      origem,
      origem_rotulo: origem === "orcamento" ? "comprado com os complementos" : "a senhora já tinha",
      imagem: null,
      rota: `/despensa/${id}`,
      _linha: { estoque, unidade, quantidade, preco },
      _embalagemOpaca: CONTAGEM.has(semAcento(unidade)),
      _usos: 0,
      _receitas: [],
      _planilha: null,
      _prato: pedido.receita ?? pedido.prato ?? null,
    });
    d.itens.push(item);
    let compra = null;
    if (origem === "orcamento") compra = debitar(d, item, preco, item._prato);
    const anotei = comArtigo(nome) ? `Anotei ${comArtigo(nome)}.` : `Anotei na despensa: ${minusculo(nome)}.`;
    const texto = compra
      ? `${anotei} Saíram ${reais(preco)} dos complementos; restam ${reais(restante(d))}.`
      : `${anotei} Como a senhora já tinha, não mexi nos complementos.`;
    const historico = compra
      ? `A senhora comprou com os complementos: ${item._comprado}.`
      : `A senhora acrescentou o que já tinha: ${item.estoque_texto}${preco === null ? ", sem o preço" : ""}.`;
    const evento = novoEvento(d, item, "adicionar", "adicionar", historico, { _antes: null, _compra: compra?.id ?? null });
    ok(res, lembrar(d, chave, resposta(d, item, evento, texto, { compra: compra ? dinheiro(preco) : null })));
  });

  rota("PATCH", /^\/api\/despensa\/itens\/([^/]+)$/, async (req, res, { partes }) => {
    const d = despensa();
    const item = achar(decodeURIComponent(partes[1]));
    if (!item) return naoAchei(res);
    const pedido = await lerCorpo(req);
    const chave = req.headers["idempotency-key"] ?? pedido.id_cliente ?? null;
    const de_novo = repetida(d, chave);
    if (de_novo) return ok(res, de_novo);
    if (pedido.nome !== undefined && semAcento(pedido.nome) !== semAcento(item.nome)) {
      return recusa(
        res,
        200,
        "uso",
        "o nome de um item não muda: cotações e compras usam o nome como chave; tire o item e acrescente com o nome novo",
      );
    }
    const campos = ["estoque", "unidade", "quantidade_comprada", "preco_pago", "categoria", "conteudo_da_embalagem"].filter(
      (campo) => pedido[campo] !== undefined && pedido[campo] !== null,
    );
    if (campos.length === 0) return recusa(res, 200, "uso", "diga o que mudou no item");
    if (pedido.categoria && !d.rotulos.has(pedido.categoria)) return recusa(res, 200, "uso", "categoria desconhecida");
    if (pedido.unidade && !lerUnidade(pedido.unidade)) {
      return recusa(res, 200, "uso", `não entendi a unidade '${pedido.unidade}': use kg, g, L, ml, un, ou a embalagem com o peso, como 'pacote 500 g'`);
    }
    const antes = copia(item);
    const pendenteAntes = item.pendente;
    const linha = item._linha;
    let acao = "corrigir";
    if (pedido.conteudo_da_embalagem) {
      const conteudo = String(pedido.conteudo_da_embalagem).replace(/\s+/g, "");
      if (!lerUnidade(`un ${conteudo}`)?.embalagem) {
        return recusa(res, 200, "uso", `não entendi ${pedido.conteudo_da_embalagem}: diga o peso ou o volume, como 400 g ou 1 L`);
      }
      linha.unidade = `un ${conteudo}`;
      item._embalagemOpaca = false;
      if (campos.length === 1) acao = "informar_embalagem";
    }
    if (pedido.unidade) {
      linha.unidade = pedido.unidade;
      item._embalagemOpaca = CONTAGEM.has(semAcento(pedido.unidade));
    }
    if (pedido.estoque !== undefined && pedido.estoque !== null) linha.estoque = Number(pedido.estoque);
    if (pedido.quantidade_comprada) linha.quantidade = Number(pedido.quantidade_comprada);
    if (pedido.preco_pago !== undefined && pedido.preco_pago !== null) linha.preco = Number(pedido.preco_pago);
    if (pedido.categoria) {
      item.categoria = pedido.categoria;
      item.categoria_rotulo = d.rotulos.get(pedido.categoria);
    }
    if (Number(pedido.estoque) === 0 && campos.length === 1) acao = "acabou";
    montar(item);
    const nome = comArtigo(item.nome) ?? minusculo(item.nome);
    const custo = item.custo_unitario ? ` Agora sai a ${item.custo_unitario.texto}.` : "";
    const textos = {
      acabou: `Anotei que ${nome} acabou.`,
      informar_embalagem: item.custo_unitario
        ? `Com ${lerUnidade(linha.unidade).embalagem} na embalagem, ${nome} sai a ${item.custo_unitario.texto}.`
        : `Anotei ${lerUnidade(linha.unidade).embalagem} na embalagem ${doNome(item.nome)}. Falta o preço que a senhora pagou para saber o custo.`,
      corrigir: `Corrigi ${nome}.${custo}`,
    };
    const historico = {
      acabou: "A senhora avisou que acabou.",
      informar_embalagem: `Embalagem de ${lerUnidade(linha.unidade).embalagem} informada.`,
      corrigir: "Corrigido pela senhora.",
    };
    const evento = novoEvento(d, item, "corrigir", acao, historico[acao], { _antes: antes });
    const resolvidas = pendenteAntes && !item.pendente ? [item.nome] : [];
    ok(res, lembrar(d, chave, resposta(d, item, evento, textos[acao], { pendencias_resolvidas: resolvidas })));
  });

  rota("DELETE", /^\/api\/despensa\/itens\/([^/]+)$/, (req, res, { partes, url }) => {
    const d = despensa();
    const chave = req.headers["idempotency-key"] ?? url.searchParams.get("id_cliente");
    const de_novo = repetida(d, chave);
    if (de_novo) return ok(res, de_novo);
    const item = achar(decodeURIComponent(partes[1]));
    if (!item) return naoAchei(res);
    const devolvido = devolver(d, item);
    d.itens = d.itens.filter((atual) => atual !== item);
    const nome = comArtigo(item.nome) ?? minusculo(item.nome);
    const texto = devolvido
      ? `Tirei ${nome} e devolvi ${reais(devolvido)} aos complementos; restam ${reais(restante(d))}.`
      : `Tirei ${nome} da despensa. Não mexi nos complementos.`;
    const historico = devolvido ? `Tirado da despensa. ${reais(devolvido)} voltaram para os complementos.` : "Tirado da despensa.";
    const evento = novoEvento(d, item, "remover", "remover", historico, { _item: copia(item), _devolvido: devolvido });
    ok(
      res,
      lembrar(d, chave, resposta(d, item, evento, texto, { removido: item.id, estorno: devolvido ? dinheiro(devolvido) : null })),
    );
  });

  rota("POST", /^\/api\/despensa\/eventos\/([^/]+)\/desfazer$/, async (req, res, { partes }) => {
    const d = despensa();
    const pedido = await lerCorpo(req);
    const chave = req.headers["idempotency-key"] ?? pedido.id_cliente ?? null;
    const de_novo = repetida(d, chave);
    if (de_novo) return ok(res, de_novo);
    const evento = d.eventos.find((e) => e.id === decodeURIComponent(partes[1]));
    if (!evento) return ausente(res, "não encontrei essa mudança");
    if (!evento.pode_desfazer) return recusa(res, 200, "uso", "só a última mudança de um item dá para desfazer");
    let item = achar(evento.item_id);
    let texto;
    let compra = null;
    let removido = null;
    let estorno = null;
    let tipo = "corrigir";
    let historico = "Desfeita a correção.";
    if (evento.tipo === "remover") {
      item = copia(evento._item);
      d.itens.push(item);
      if (evento._devolvido) {
        debitar(d, item, evento._devolvido, item._prato);
        compra = dinheiro(evento._devolvido);
      }
      const nome = comArtigo(item.nome) ?? minusculo(item.nome);
      texto = compra
        ? `Voltei ${nome} para a despensa. Saíram de novo ${compra.texto} dos complementos; restam ${reais(restante(d))}.`
        : `Voltei ${nome} para a despensa.`;
      tipo = "restaurar";
      historico = compra ? `Voltou para a despensa. ${compra.texto} saíram de novo dos complementos.` : "Voltou para a despensa.";
    } else if (evento.tipo === "adicionar") {
      const devolvido = devolver(d, item);
      d.itens = d.itens.filter((atual) => atual !== item);
      removido = item.id;
      estorno = devolvido ? dinheiro(devolvido) : null;
      texto = `Desfiz: ${minusculo(item.nome)} saiu da despensa.`;
      tipo = "remover";
      historico = "Desfeito: saiu da despensa.";
    } else {
      const antes = copia(evento._antes);
      Object.assign(item, antes);
      texto = `Desfiz a última correção de ${minusculo(item.nome)}.`;
    }
    const novo = novoEvento(d, item, tipo, "desfazer", historico, {
      desfaz: evento.id,
      _item: removido ? copia(item) : undefined,
      _devolvido: estorno?.valor ?? 0,
      _antes: null,
    });
    ok(res, lembrar(d, chave, resposta(d, item, novo, texto, { compra, removido, estorno })));
  });

  rota("POST", /^\/api\/compras\/([^/]+)\/estorno$/, (_req, res, { partes }) => {
    const d = despensa();
    const compra = d.compras.find((c) => String(c.id) === decodeURIComponent(partes[1]));
    if (!compra) return ausente(res, "não encontrei essa compra");
    if (compra.estorno) return recusa(res, 200, "uso", "essa linha já é uma devolução");
    if (compra.estornada) {
      return ok(res, {
        compra_id: compra.id,
        estorno_id: compra._estorno_id,
        estorno: copia(compra.valor),
        removido: null,
        receitas_afetadas: copia(NENHUMA),
        orcamento: orcamento(d),
        texto: `Essa compra já tinha voltado para os complementos; restam ${reais(restante(d))}.`,
      });
    }
    compra.estornada = true;
    compra.pode_estornar = false;
    d.contadores.compras += 1;
    compra._estorno_id = d.contadores.compras;
    const item = achar(compra.item_id);
    let removido = null;
    if (item) {
      d.itens = d.itens.filter((atual) => atual !== item);
      removido = item.id;
      novoEvento(d, item, "remover", "estorno", `A compra voltou para os complementos (${compra.valor.texto}) e o item saiu da despensa.`, {
        _item: copia(item),
        _devolvido: compra.valor.valor,
      });
    }
    const saiu = item ? ` ${item.nome} saiu da despensa.` : "";
    ok(res, {
      compra_id: compra.id,
      estorno_id: compra._estorno_id,
      estorno: copia(compra.valor),
      removido,
      receitas_afetadas: copia(NENHUMA),
      orcamento: orcamento(d),
      texto: `Devolvi ${compra.valor.texto} aos complementos; restam ${reais(restante(d))}.${saiu}`,
    });
  });
}

