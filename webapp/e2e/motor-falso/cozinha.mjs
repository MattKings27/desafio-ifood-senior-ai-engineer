/* global structuredClone */
/**
 * A cozinha do motor falso: o perfil de `contratos/web/perfil.json`, mudado em
 * memória como a API muda. Cada item vem com a `imagem` do contrato (a
 * miniatura pelo proxy, que o motor falso serve para qualquer chave), ou `null`.
 *
 * "Não sei" volta o item para o desconhecido com `nao_sei`; as contagens, o
 * resumo e o progresso saem com as mesmas frases da API. O impacto nas receitas
 * é um roteiro curto: item que alguma receita em avaliação pede libera,
 * segura ou deixa pendente uma receita de exemplo, com o texto que a API
 * escreveria. "O que toda cozinha tem" (`toda_cozinha`) sai do perfil de agora;
 * a confirmação (`POST /api/perfil/supostos/confirmar`) mora em `receitas.mjs`,
 * que conhece as receitas.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const FUSO = "America/Sao_Paulo";
const copia = (valor) => structuredClone(valor);
const agora = () =>
  `hoje, ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: FUSO })}`;
const contagem = (n, singular, plural) => `${n} ${n === 1 ? singular : plural}`;

/**
 * O tempo por cozinhada dito para ela, como a API escreve: "meia hora", "1,5 hora",
 * "2 horas", "1 hora e 40 minutos". A tela manda horas; aqui é o lugar da API.
 */
export function horasTexto(horas) {
  const minutos = Math.round(horas * 60);
  const hora = (n) => (n < 2 ? "hora" : "horas");
  if (minutos === 30) return "meia hora";
  const [inteiras, resto] = [Math.floor(minutos / 60), minutos % 60];
  if (resto === 0) return `${inteiras} ${hora(inteiras)}`;
  if (minutos % 3 === 0) return `${String(minutos / 60).replace(".", ",")} ${hora(minutos / 60)}`;
  const emMinutos = `${resto} ${resto === 1 ? "minuto" : "minutos"}`;
  return inteiras ? `${inteiras} ${hora(inteiras)} e ${emMinutos}` : emMinutos;
}

/**
 * As receitas de exemplo que cada item pede, para o impacto de uma mudança. Os
 * três primeiros são os do exemplo do contrato; o liquidificador e a panela de
 * pressão entram aqui para cada teste ponta a ponta mexer num item só dele
 * (os testes rodam juntos, e o estado do motor falso é um só).
 */
const RECEITAS_DO_ITEM = {
  forno: ["Frango assado"],
  fogao: ["Arroz com frango", "Arroz refogado"],
  refogar: ["Arroz com frango", "Arroz refogado"],
  liquidificador: ["Bolo de fubá"],
  panela_pressao: ["Feijão tropeiro"],
};

export function cozinhaInicial(contratos) {
  const perfil = JSON.parse(readFileSync(join(contratos, "perfil.json"), "utf-8"));
  for (const item of [...perfil.equipamentos, ...perfil.tecnicas]) {
    item.imagem ??= null;
    const receitas = RECEITAS_DO_ITEM[item.id];
    if (!receitas) continue;
    item.receitas_afetadas = receitas.length;
    item.receitas_afetadas_texto = contagem(receitas.length, "receita", "receitas");
  }
  return perfil;
}

/** Um item de "O que toda cozinha tem", com o estado dito para ela, como a API diz. */
function itemDeTodaCozinha(item, tipo) {
  const deTer = tipo === "equipamento";
  let status = "falta_saber";
  let texto = item.nao_sei ? "a senhora não sabe" : "falta saber";
  if (item.suposto && item.estado === "tem") [status, texto] = ["suposto", "suposto: confirme"];
  else if (item.estado === "tem") [status, texto] = ["confirmado", deTer ? "a senhora tem" : "a senhora faz"];
  else if (item.estado === "nao_tem") [status, texto] = ["nao_da", deTer ? "a senhora não tem" : "a senhora não faz"];
  return { tipo, id: item.id, nome: item.nome, imagem: item.imagem ?? null, estado: item.estado, status, status_texto: texto };
}

/** "O que toda cozinha tem" (`perfil.json#toda_cozinha`), refeito do perfil de agora. */
export function todaCozinha(perfil) {
  const itens = [
    ...perfil.equipamentos.filter((item) => item.pressuposto).map((item) => itemDeTodaCozinha(item, "equipamento")),
    ...perfil.tecnicas.filter((item) => item.pressuposta).map((item) => itemDeTodaCozinha(item, "tecnica")),
  ];
  const aConfirmar = itens.filter((item) => item.status === "suposto").length;
  return {
    titulo: "O que toda cozinha tem",
    texto: aConfirmar
      ? "Eu supus que a senhora tem estas coisas e faz estes pratos do dia a dia. Confirme para eu ter certeza antes de qualquer compra."
      : "A senhora já me disse de tudo isso.",
    a_confirmar: aConfirmar,
    a_confirmar_texto: `${aConfirmar} para confirmar`,
    tudo_confirmado: aConfirmar === 0,
    itens,
  };
}

/**
 * Ela confirma que tem (ou faz) os itens do perfil que `alvo` escolhe: cada um
 * vira "tem", dito pela tela. Devolve os confirmados, na forma de
 * `perfil-supostos.json#resposta.confirmados`.
 */
export function confirmarNoPerfil(perfil, alvo) {
  const confirmados = [];
  for (const [lista, tipo] of [
    ["equipamentos", "equipamento"],
    ["tecnicas", "tecnica"],
  ]) {
    for (const item of perfil[lista]) {
      if (!alvo(item, tipo)) continue;
      item.estado = "tem";
      item.suposto = false;
      item.nao_sei = false;
      item.atualizado_por = "tela";
      item.atualizado_texto = agora();
      confirmados.push({ tipo, id: item.id, nome: item.nome });
    }
  }
  return confirmados;
}

export function contagens(perfil) {
  const itens = [...perfil.equipamentos, ...perfil.tecnicas];
  const respondidos = itens.filter((i) => !i.suposto && i.estado !== "desconhecido").length;
  const supostos = itens.filter((i) => i.suposto && i.estado === "tem").length;
  const emAberto = itens.filter((i) => i.estado === "desconhecido").length;
  const naoSabe = itens.filter((i) => i.estado === "desconhecido" && i.nao_sei).length;
  const partes = [`${contagem(respondidos, "respondido", "respondidos")} pela senhora`, contagem(supostos, "suposto", "supostos")];
  if (naoSabe) partes.push(`${naoSabe} que a senhora não sabe`);
  partes.push(`${emAberto - naoSabe} ainda não perguntei`);
  return {
    respondidos,
    supostos,
    em_aberto: emAberto,
    fracao_respondida: Math.round((respondidos / itens.length) * 10000) / 10000,
    resumo: partes.join(" · "),
    progresso_texto: `${respondidos} de ${itens.length} respondidos pela senhora`,
  };
}

function lista(nomes) {
  return nomes.length === 1 ? nomes[0] : `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}`;
}

function impacto(item, antes, tipo) {
  const vazio = { liberadas: [], bloqueadas: [], pendentes: [] };
  if (antes.estado === item.estado && antes.nao_sei === item.nao_sei) {
    return { ...vazio, texto: "Isso já estava anotado assim; nada muda nas receitas." };
  }
  const receitas = RECEITAS_DO_ITEM[item.id] ?? [];
  if (receitas.length === 0) return { ...vazio, texto: "Anotado. Nenhuma receita em avaliação muda com isso." };
  const plural = receitas.length > 1;
  const nome = item.nome.toLowerCase();
  const causa = tipo === "equipamentos" && !item.nao_sei ? `${item.estado === "nao_tem" ? "Sem" : "Com"} ${nome}, ` : "";
  const frase = (texto) => {
    const inteira = `${causa}${texto}.`;
    return inteira.charAt(0).toUpperCase() + inteira.slice(1);
  };
  if (item.estado === "tem") {
    return { ...vazio, liberadas: receitas, texto: frase(`${lista(receitas)} ${plural ? "passam" : "passa"} a dar`) };
  }
  if (item.estado === "nao_tem") {
    return { ...vazio, bloqueadas: receitas, texto: frase(`${lista(receitas)} ${plural ? "deixam" : "deixa"} de dar`) };
  }
  return {
    ...vazio,
    pendentes: receitas,
    texto: frase(`${lista(receitas)} ${plural ? "ficam" : "fica"} dependendo de uma resposta da senhora`),
  };
}

export function rotasDaCozinha({ rota, ok, recusa, ausente, lerCorpo, cozinha }) {
  rota("GET", /^\/api\/perfil$/, (_req, res) =>
    ok(res, { ...copia(cozinha()), ...contagens(cozinha()), toda_cozinha: todaCozinha(cozinha()) }),
  );

  rota("PUT", /^\/api\/perfil\/(equipamentos|tecnicas)\/([^/]+)$/, async (req, res, { partes }) => {
    const perfil = cozinha();
    const [, tipo, id] = partes;
    const item = perfil[tipo].find((atual) => atual.id === decodeURIComponent(id));
    if (!item) {
      return ausente(res, tipo === "equipamentos" ? "esse equipamento não está na lista da cozinha" : "essa técnica não está na lista da cozinha");
    }
    const { estado } = await lerCorpo(req);
    if (!["tem", "nao_tem", "nao_sei"].includes(estado)) return recusa(res, 422, "uso", "O pedido saiu incompleto.");
    const antes = copia(item);
    item.estado = estado === "nao_sei" ? "desconhecido" : estado;
    item.nao_sei = estado === "nao_sei";
    item.suposto = false;
    item.atualizado_por = "tela";
    item.atualizado_texto = agora();
    ok(res, { item: copia(item), impacto: impacto(item, antes, tipo), perfil: contagens(perfil) });
  });

  rota("PUT", /^\/api\/perfil\/restricoes\/([^/]+)$/, async (req, res, { partes }) => {
    const perfil = cozinha();
    const campo = decodeURIComponent(partes[1]);
    const restricao = perfil.restricoes[campo];
    if (!restricao) return ausente(res, "essa restrição não está na lista da cozinha");
    const { valor = null } = await lerCorpo(req);
    if (valor !== null) {
      if (restricao.tipo === "sim_nao" && typeof valor !== "boolean") return recusa(res, 200, "uso", "a resposta aqui é sim ou não");
      if (restricao.tipo === "inteiro") {
        if (typeof valor !== "number" || !Number.isInteger(valor)) return recusa(res, 200, "uso", "a resposta aqui é um número inteiro");
        if (valor < restricao.min || valor > restricao.max) {
          return recusa(res, 200, "uso", `esse número precisa ficar entre ${restricao.min} e ${restricao.max} ${restricao.unidade}`);
        }
      }
      if (restricao.tipo === "horas") {
        if (typeof valor !== "number" || !Number.isFinite(valor)) return recusa(res, 200, "uso", "a resposta aqui é quantas horas, como 2 ou 1,5");
        if (valor < restricao.min || valor > restricao.max) {
          return recusa(res, 200, "uso", `esse tempo precisa ficar entre ${horasTexto(restricao.min)} e ${horasTexto(restricao.max)}`);
        }
      }
    }
    const mudou = restricao.valor !== valor || restricao.nao_sei !== (valor === null);
    restricao.valor = valor;
    if (restricao.tipo === "horas") restricao.valor_texto = valor === null ? null : horasTexto(valor);
    restricao.nao_sei = valor === null;
    restricao.atualizado_por = "tela";
    restricao.atualizado_texto = agora();
    ok(res, {
      item: { id: campo, ...copia(restricao) },
      impacto: {
        liberadas: [],
        bloqueadas: [],
        pendentes: [],
        texto: mudou ? "Anotado. Nenhuma receita em avaliação muda com isso." : "Isso já estava anotado assim; nada muda nas receitas.",
      },
      perfil: contagens(perfil),
    });
  });
}
