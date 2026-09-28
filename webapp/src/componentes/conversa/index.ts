/**
 * A API pública da conversa com o agente, para o resto da interface:
 *
 *     const { abrir } = useConversa();
 *     abrir({ rascunho: "Dá pra eu fazer Bolo de cenoura?", contexto: { tela: "receitas", tipo: "receita", id: slug, rotulo: nome } });
 *
 *     <BotaoPerguntar rascunho={detalhe.rascunho_chat} contexto={...} />
 *
 * `abrir` abre o painel (computador) ou a folha (celular) com o rascunho na
 * caixa e o contexto no chip "Vendo: …". Nunca envia sozinho: quem manda é ela.
 */

export { BotaoConversa } from "./BotaoConversa";
export { BotaoPerguntar } from "./BotaoPerguntar";
export { PainelDaConversa } from "./PainelDaConversa";
export { ProvedorDaConversa, enderecoDaConversa, useConversa } from "./ProvedorDaConversa";
export type { PedidoDeAbertura, ValorDaConversa } from "./ProvedorDaConversa";
export type { ContextoDaConversa } from "@/lib/api/conversa";
