/**
 * Os dados dela para baixar: tudo o que a plataforma guarda, num arquivo só.
 * E o recomeço pela planilha ("Restaurar os dados da planilha").
 *
 * `GET /api/exportacao` devolve o arquivo (`contratos/web/exportacao.json`),
 * fora do envelope e com o nome já no cabeçalho: a tela só aponta um link para
 * ele, com `download`, e o navegador salva.
 */

import type { Dinheiro } from "./base";
import { comCorpo, pedir } from "./base";
import type { OrcamentoDaDespensa, ListaDaDespensa } from "./despensa";
import type { PerfilDaCozinha } from "./perfil";
import type { ReceitaGuardada } from "./receitas";

export type ExportacaoDosDados = {
  arquivo: "sabor-da-maria-dados";
  versao: number;
  gerado_em: string;
  despensa: ListaDaDespensa;
  despensa_eventos: Record<string, unknown>[];
  cozinha: PerfilDaCozinha;
  cozinha_eventos: Record<string, unknown>[];
  orcamento: OrcamentoDaDespensa;
  compras: OrcamentoDaDespensa["compras"];
  decisoes: Record<string, unknown>[];
  cardapio: string[];
  gostos: Record<string, unknown>[];
  precos_de_mercado: Record<string, unknown>[];
  receitas_em_avaliacao: (ReceitaGuardada & { receita_id: string })[];
};

/** Uma conta da restauração: número e texto já em pt-BR. */
type DinheiroDaRestauracao = Dinheiro;

/**
 * "Restaurar os dados da planilha" (`POST /api/dados/restaurar`,
 * `contratos/web/restauracao.json`): a frase para ela, a conciliação com a
 * planilha (37 ingredientes, R$ 663,39, os R$ 80,00), o que saiu, o que ficou
 * e os recursos que mudaram (todas as telas).
 */
export type RestauracaoDosDados = {
  texto: string;
  mudou: boolean;
  conciliacao: {
    ingredientes: number;
    total_pago: DinheiroDaRestauracao;
    orcamento_inicial: DinheiroDaRestauracao;
    orcamento_restante: DinheiroDaRestauracao;
    cozinha_texto: string;
    texto: string;
  };
  /** Quantas linhas saíram de cada coisa, dito para ela ("decisões do cardápio": 2). */
  apagado: Record<string, number>;
  mantido: { receitas: number; texto: string };
  /** O nome da pasta da cópia guardada antes (não vai para a tela). */
  copia: string;
  recursos: string[];
  /** A mesma chave de clique já restaurou: nada foi feito de novo. */
  repetida: boolean;
};

export const dados = {
  /** O endereço do arquivo, pelo proxy. */
  urlDaExportacao: "/motor/exportacao",
  /** O nome com que o navegador salva (o mesmo do cabeçalho da API). */
  nomeDoArquivo: "sabor-da-maria-dados.json",

  /** Volta tudo à planilha, depois de guardar uma cópia. Só com a confirmação dela. */
  restaurar: (idCliente: string) =>
    pedir<RestauracaoDosDados>("/dados/restaurar", {
      ...comCorpo("POST", { confirmar: true, id_cliente: idCliente }),
      headers: { "Idempotency-Key": idCliente },
      tempoLimiteMs: 60_000,
    }),
} as const;
