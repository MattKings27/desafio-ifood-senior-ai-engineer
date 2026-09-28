/**
 * A busca na plataforma inteira, com fonte e rota: a forma de
 * `contratos/web/conhecimento.json`, que é a resposta da ferramenta
 * `consultar_conhecimento` do agente.
 *
 * A tela não chama esta busca: ela chega pelo card "De onde eu tirei isso"
 * (`fontes`), que o backend monta com os mesmos trechos. O tipo existe para o
 * contrato ficar conferido dos dois lados.
 */

/** As partes da plataforma de onde um trecho pode vir; é também o filtro `tipos`. */
export type TipoDoTrecho =
  | "despensa"
  | "cozinha"
  | "receita"
  | "avaliacao"
  | "cardapio"
  | "orcamento"
  | "conhecimento";

/** Um trecho com a fonte e a tela que o mostra (`null` na base de conhecimento de cozinha). */
export type TrechoDoConhecimento = {
  id: string;
  tipo: TipoDoTrecho;
  rota: string | null;
  fonte: string;
  texto: string;
  /** De 0 a 1: 1 é o primeiro colocado nos dois braços da busca. */
  pontuacao: number;
};

/** A resposta da busca; sem trecho, `nada_relevante` e o texto do "não sei". */
export type RespostaDoConhecimento = {
  trechos: TrechoDoConhecimento[];
  nada_relevante: boolean;
  texto: string;
};
