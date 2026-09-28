/* global structuredClone */
/**
 * O cardápio do motor falso: começa com `cardapio.json` e muda como a API de
 * verdade muda. Tirar do cardápio (`POST /api/decisao` com "recusado") grava
 * a decisão no histórico e guarda o prato para o desfazer; desfazer
 * (`POST /api/cardapio/{prato}/desfazer`) volta o prato e grava que ela voltou
 * atrás. Nada some do histórico.
 *
 * Os testes rodam em paralelo contra o mesmo motor: cada um acrescenta o seu
 * prato (`POST /__cardapio/prato {prato}`) e mexe só nele.
 *
 * Aceitar um prato novo (o "Vou cobrar" do pôr preço) grava o prato com a
 * conta do preço dela: o que chega, o custo, o lucro e a frase saem da mesma
 * conta do `/api/preco-em` (`contaDoPreco`), como a API de verdade faz.
 *
 * O dinheiro é formatado aqui porque aqui é o lugar da API, e só nos testes.
 */

import { contaDoPreco } from "./preco.mjs";

const copia = (valor) => structuredClone(valor);
const FUSO = "America/Sao_Paulo";
const agora = () =>
  `hoje, ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: FUSO })}`;
const reais = (valor) =>
  `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function semAcento(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

const slug = (nome) => semAcento(nome).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** "o arroz com frango": no motor falso, todo prato é masculino. */
const oPrato = (prato) => `o ${prato.charAt(0).toLowerCase()}${prato.slice(1)}`;

export function cardapioInicial(contratos, json) {
  return { ...json(contratos, "cardapio.json"), retirados: {}, proximo: 100 };
}

function resumoDe(cardapio) {
  const n = cardapio.pratos.length;
  return {
    ...cardapio.resumo,
    pratos: n,
    texto: n === 0 ? "nenhum prato no cardápio ainda" : `${n} ${n === 1 ? "prato" : "pratos"} no cardápio`,
  };
}

/** O cardápio como a API devolve: sem o que o motor falso guarda para desfazer. */
function publico(cardapio) {
  const resto = copia(cardapio);
  delete resto.retirados;
  delete resto.proximo;
  return { ...resto, resumo: resumoDe(cardapio) };
}

function anotar(cardapio, prato, tipo, tipoRotulo, texto, rota) {
  for (const decisao of cardapio.historico) {
    if (semAcento(decisao.prato) === semAcento(prato)) decisao.pode_desfazer = false;
  }
  cardapio.proximo += 1;
  cardapio.historico.unshift({
    id: cardapio.proximo,
    prato,
    tipo,
    tipo_rotulo: tipoRotulo,
    texto_humano: texto,
    quando_texto: agora(),
    canal: "tela",
    pode_desfazer: tipo !== "desfeito",
    rota,
  });
}

function acharPrato(cardapio, pedido) {
  const alvo = semAcento(decodeURIComponent(pedido));
  const nomes = [
    ...cardapio.pratos.map((p) => p.prato),
    ...Object.keys(cardapio.retirados),
    ...cardapio.historico.map((h) => h.prato),
  ];
  return nomes.find((nome) => semAcento(nome) === alvo || slug(nome) === alvo) ?? null;
}

/** O prato aceito agora, com os números da conta do preço dela. */
function pratoAceito(prato, preco, custo) {
  const conta = contaDoPreco(preco, custo.valor);
  return {
    slug: slug(prato),
    prato,
    imagem: null,
    preco: conta.preco,
    recebe: conta.recebe,
    custo_porcao: custo,
    lucro_porcao: conta.lucro,
    derivacao: conta.explicacao,
    da_prejuizo: conta.da_prejuizo,
    aviso: null,
    nota: null,
    decidido_texto: agora(),
    notas: null,
    rota: `/receitas/${slug(prato)}`,
  };
}

export function rotasDoCardapio({ rota, ok, recusa, ausente, lerCorpo, cardapio, custoDaPorcao }) {
  rota("GET", /^\/api\/cardapio$/, (_req, res) => ok(res, publico(cardapio())));

  rota("POST", /^\/__cardapio\/prato$/, async (req, res) => {
    const { prato } = await lerCorpo(req);
    const atual = cardapio();
    const modelo = copia(atual.pratos[0]);
    atual.pratos.push({ ...modelo, prato, slug: slug(prato), rota: `/receitas/${slug(prato)}`, notas: null, aviso: null });
    ok(res, { prato });
  });

  rota("POST", /^\/api\/decisao$/, async (req, res) => {
    const { prato, decisao, preco } = await lerCorpo(req);
    if (!prato) return recusa(res, 422, "uso", "Diga qual prato.");
    const atual = cardapio();
    const indice = atual.pratos.findIndex((p) => semAcento(p.prato) === semAcento(prato));
    let texto;
    if (decisao === "aceito") {
      const valor = { valor: Number(preco), texto: reais(Number(preco)) };
      if (indice >= 0) {
        const antes = atual.pratos[indice].preco.texto;
        atual.pratos[indice].preco = valor;
        texto = `A senhora mudou o preço do ${prato.toLowerCase()} de ${antes} para ${valor.texto}.`;
        anotar(atual, prato, "preco", "Mudou o preço", texto, atual.pratos[indice].rota);
      } else {
        atual.pratos.push(pratoAceito(prato, Number(preco), custoDaPorcao()));
        texto = `A senhora aceitou ${oPrato(prato)} a ${valor.texto}.`;
        anotar(atual, prato, "aceito", "Aceitou", texto, `/receitas/${slug(prato)}`);
      }
    } else if (indice >= 0) {
      const [tirado] = atual.pratos.splice(indice, 1);
      atual.retirados[tirado.prato] = tirado;
      texto = `A senhora tirou ${oPrato(tirado.prato)} do cardápio.`;
      anotar(atual, tirado.prato, "retirado", "Tirou do cardápio", texto, tirado.rota);
    } else {
      texto =
        decisao === "adiado"
          ? `A senhora deixou ${oPrato(prato)} para decidir depois.`
          : `A senhora disse que não quer ${oPrato(prato)} no cardápio.`;
      anotar(atual, prato, decisao === "adiado" ? "adiado" : "recusado", decisao === "adiado" ? "Deixou para depois" : "Recusou", texto, "/cardapio");
    }
    ok(res, { prato, decisao, texto, cardapio: atual.pratos.map((p) => p.prato) });
  });

  rota("POST", /^\/api\/cardapio\/([^/]+)\/desfazer$/, (_req, res, { partes }) => {
    const atual = cardapio();
    const prato = acharPrato(atual, partes[1]);
    if (!prato) return ausente(res, "Não encontrei esse prato entre as decisões da senhora.");
    const ultima = atual.historico.find((h) => semAcento(h.prato) === semAcento(prato));
    if (!ultima?.pode_desfazer) return recusa(res, 200, "uso", `Não há o que desfazer: ${oPrato(prato)} já está como estava.`);
    let texto;
    if (ultima.tipo === "retirado" && atual.retirados[prato]) {
      const volta = atual.retirados[prato];
      delete atual.retirados[prato];
      atual.pratos.push(volta);
      texto = `A senhora voltou atrás: ${oPrato(prato)} está de novo no cardápio, a ${volta.preco.texto}.`;
    } else {
      atual.pratos = atual.pratos.filter((p) => semAcento(p.prato) !== semAcento(prato));
      texto = `A senhora voltou atrás: ${oPrato(prato)} fica para decidir depois.`;
    }
    anotar(atual, prato, "desfeito", "Voltou atrás", texto, ultima.rota);
    ok(res, { ...publico(atual), texto });
  });

  rota("PUT", /^\/api\/cardapio\/([^/]+)\/notas$/, async (req, res, { partes }) => {
    const atual = cardapio();
    const prato = atual.pratos.find((p) => semAcento(p.prato) === semAcento(decodeURIComponent(partes[1])));
    if (!prato) return ausente(res, "Esse prato não tem receita guardada para anotar.");
    const { texto = "" } = await lerCorpo(req);
    prato.notas = texto.trim() || null;
    ok(res, { ...publico(atual), texto: texto.trim() ? "Anotei." : "Apaguei as notas." });
  });
}
