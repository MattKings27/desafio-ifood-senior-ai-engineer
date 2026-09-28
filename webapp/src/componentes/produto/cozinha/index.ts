/**
 * As peças da cozinha que outras telas usam: o seletor Tenho / Não tenho /
 * Não sei (Faço / Não faço / Não sei para técnica), que a tela de receitas põe
 * nos passos e nas perguntas, a gravação 300 ms depois da última escolha, e a
 * leitura da resposta de um item.
 *
 *     <SeletorDePosse tipo="equipamento" legenda="Forno" valor={respostaDoItem(item)} aoMudar={gravar} />
 */

export { OPCOES_DE_POSSE, SeletorDePosse, respostaDoItem } from "./SeletorDePosse";
export type { TipoDePosse } from "./SeletorDePosse";
export { ItemDaCozinha, NotaDoImpacto } from "./ItemDaCozinha";
export { TodaCozinha } from "./TodaCozinha";
export { useGravacaoAdiada } from "./useGravacaoAdiada";
