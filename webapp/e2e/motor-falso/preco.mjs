/* global structuredClone */
/**
 * A tela de pôr preço no motor falso: a conferência (`/api/avaliar`), o custo
 * de uma porção (`/api/cmv`), os três caminhos com os limites do controle
 * (`/api/precos`, o card `cenarios` do contrato) e o ponto de preço
 * (`/api/preco-em`), mais a receita guardada (`/api/receita`), a trazida da
 * internet (`/api/receita-da-web`) e o gosto (`/api/gosto`).
 *
 * A conferência pergunta o tempo no fogo quando a receita não traz: é assim
 * que o teste confere que a resposta volta dentro da receita, e não pela
 * rota das respostas da cozinha. O ponto de preço é a conta do desafio, feita
 * aqui porque aqui é a API; o custo de uma porção é um só em toda a tela (o do
 * `cartoes/cenarios.json`), e é o mesmo que o cardápio mostra depois do "Vou
 * cobrar" (`contaDoPreco`, que o `cardapio.mjs` também usa). O prato com
 * "supostos" no nome se apoia no fogão e no refogar que ela não confirmou: o
 * "Vou cobrar" espera até ela confirmar a cozinha pelo `receita_id`.
 */

const copia = (valor) => structuredClone(valor);
const reais = (valor) =>
  `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dinheiro = (valor) => ({ valor: Math.round(valor * 100) / 100, texto: reais(Math.round(valor * 100) / 100) });

const PERGUNTA_DO_TEMPO = {
  tipo: "operacional",
  campo: "tempo_cozimento_min",
  texto: "Pelos passos não dá para saber quanto tempo a receita fica no fogo. Mais ou menos quantos minutos?",
  motivo: "a senhora tem 60 minutos por cozinhada, e sem o tempo da receita não dá para saber se cabe",
  opcoes: [],
  entrada: { tipo: "inteiro", unidade: "minutos", min: 1, max: 1440 },
  passos: [],
};

const RECEITA_GUARDADA = {
  nome: "Arroz com frango",
  rendimento_porcoes: 4,
  rendimento_informado: true,
  modo_preparo: ["Refogue a cebola.", "Junte o frango e o arroz e cozinhe na panela."],
  tempo_cozimento_min: 40,
  url: null,
  fonte: null,
  ingredientes: [
    { texto: "500 g de frango", nome: "peito de frango", quantidade: 500, medida: "g" },
    { texto: "1 kg de arroz", nome: "arroz", quantidade: 1, medida: "kg" },
  ],
};

/** A conta de um preço, como a API escreve: taxa de 10%, o que chega, o lucro e a frase. */
export function contaDoPreco(preco, custo) {
  const taxa = preco * 0.1;
  const recebe = preco - taxa;
  const lucro = recebe - custo;
  return {
    preco: dinheiro(preco),
    taxa: dinheiro(taxa),
    recebe: dinheiro(recebe),
    lucro: dinheiro(lucro),
    food_cost: custo / preco,
    margem: lucro / preco,
    da_prejuizo: lucro < 0,
    explicacao: `Vendendo a ${reais(preco)}: o iFood fica com ${reais(taxa)} (10%), então chegam ${reais(recebe)} pra senhora. Tirando ${reais(custo)} de ingrediente, sobram ${reais(lucro)} limpos por porção.`,
  };
}

/** O custo de uma porção que toda a tela de preço usa. */
export const custoDaPorcao = (contrato) => contrato("cartoes/cenarios.json").dados.cmv;

/** O que toda cozinha tem e o prato com "supostos" no nome usa, sem ela ter confirmado. */
const SUPOSTOS_DO_PRATO = [
  { tipo: "equipamento", id: "fogao", nome: "Fogão" },
  { tipo: "tecnica", id: "refogar", nome: "Refogar" },
];

function avaliacao(receita, confirmadas) {
  const semTempo = !receita.tempo_cozimento_min;
  const receitaId = receita.nome.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  // O prato de teste com "supostos" no nome espera a cozinha confirmada antes do "Vou cobrar".
  const supostos = /supostos/i.test(receita.nome) && !confirmadas.has(receitaId) ? SUPOSTOS_DO_PRATO : [];
  const podeAceitar = !semTempo && supostos.length === 0;
  const falta = [
    ...(semTempo ? [`Responder: ${PERGUNTA_DO_TEMPO.texto}`] : []),
    ...(supostos.length ? ["Confirmar que a senhora tem fogão e que sabe refogar."] : []),
  ];
  return {
    pode_aceitar: podeAceitar,
    falta_para_aceitar: podeAceitar ? [] : falta,
    confirmar_a_cozinha: supostos.length
      ? { pergunta: "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?", itens: copia(supostos) }
      : null,
    prato: receita.nome,
    receita_id: receitaId,
    veredito: semTempo ? "FALTA INFO" : "APTO",
    pode_precificar: !semTempo,
    resumo: semTempo
      ? `Falta saber uma coisa para conferir ${receita.nome.toLowerCase()}.`
      : `Dá pra fazer ${receita.nome.toLowerCase()} com o que a senhora tem.`,
    impedimentos: [],
    perguntas: semTempo ? [copia(PERGUNTA_DO_TEMPO)] : [],
    ingredientes_na_despensa: receita.ingredientes.map((ingrediente) => ({
      ingrediente: ingrediente.nome,
      quantidade: ingrediente.texto,
      custo: dinheiro(1.5),
      derivacao: `${ingrediente.texto} a R$ 3,00 o quilo`,
    })),
    falta_comprar: [],
    a_gosto: [],
  };
}

export function rotasDoPreco({ rota, ok, ausente, lerCorpo, contrato, confirmadas }) {
  rota("POST", /^\/api\/avaliar$/, async (req, res) => ok(res, avaliacao(await lerCorpo(req), confirmadas())));

  rota("POST", /^\/api\/cmv$/, async (req, res) => {
    const receita = await lerCorpo(req);
    const custo = copia(contrato("custo.json"));
    delete custo.ingrediente_que_falta_exemplo;
    delete custo.ingrediente_com_preco_de_referencia_exemplo;
    // O mesmo custo dos três caminhos e do controle: a tela não mostra dois custos.
    const porcao = custoDaPorcao(contrato);
    ok(res, { ...custo, prato: receita.nome, total: porcao, minimo: porcao, maximo: porcao, e_faixa: false, incerteza: 0 });
  });

  rota("GET", /^\/api\/precos$/, (_req, res, { url }) => {
    const { dados } = copia(contrato("cartoes/cenarios.json"));
    ok(res, { ...dados, prato: url.searchParams.get("prato") ?? dados.prato });
  });

  rota("GET", /^\/api\/preco-em$/, (_req, res, { url }) => {
    const preco = Number(url.searchParams.get("preco"));
    ok(res, contaDoPreco(preco, custoDaPorcao(contrato).valor));
  });

  rota("GET", /^\/api\/receita$/, (_req, res, { url }) =>
    url.searchParams.get("prato") === RECEITA_GUARDADA.nome ? ok(res, copia(RECEITA_GUARDADA)) : ausente(res, "Não encontrei essa receita."),
  );

  rota("POST", /^\/api\/receita-da-web$/, async (req, res) => {
    const { url } = await lerCorpo(req);
    ok(res, {
      receita: { ...copia(RECEITA_GUARDADA), nome: "Frango da internet", tempo_cozimento_min: null, url, fonte: "TudoGostoso" },
      procedencia: { url, fonte: "TudoGostoso", citacao: "" },
    });
  });

  rota("POST", /^\/api\/gosto$/, async (req, res) => {
    const { prato, gosta, impedimento = "" } = await lerCorpo(req);
    ok(res, { prato, gosto: gosta ? "gosta" : "nao_gosta", impedimento, texto: "Anotei.", bloqueia: !gosta });
  });
}
