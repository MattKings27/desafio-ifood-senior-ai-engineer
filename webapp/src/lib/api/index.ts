/**
 * A API por domínio: `api.despensa.listar()`, `api.receitas.detalhe(slug)`…
 *
 * Server components aguardam estas funções direto; o `ErroDoMotor` que elas
 * lançam vira `<Problema>` (ou `notFound()` quando a categoria é `ausente`).
 * Escritas passam por Server Actions em `src/lib/acoes/`, que usam as mesmas
 * funções e devolvem `Resultado` em vez de lançar.
 */

import { atividades } from "./atividades";
import { cardapio } from "./cardapio";
import { conversa } from "./conversa";
import { dados } from "./dados";
import { despensa } from "./despensa";
import { perfil } from "./perfil";
import { preco } from "./preco";
import { receitas } from "./receitas";
import { visaoGeral } from "./visao-geral";

export const api = {
  atividades,
  cardapio,
  conversa,
  dados,
  despensa,
  perfil,
  preco,
  receitas,
  visaoGeral,
} as const;

export type { CategoriaDeErro, Dinheiro, Envelope, Imagem, OpcoesDoPedido } from "./base";
export { ErroDoMotor, MENSAGENS, TEMPO_LIMITE_PADRAO_MS } from "./base";
