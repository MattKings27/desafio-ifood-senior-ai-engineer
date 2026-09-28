/**
 * Camada **Shared** do design system: as primitivas que todo o resto compõe.
 *
 * Este arquivo é só o barril: cada primitiva mora no seu arquivo, com o seu
 * teste. Os nomes de antes (`Vazio`, `Problema` com `mensagem`/`categoria`)
 * continuam valendo, para as telas antigas não quebrarem enquanto mudam.
 *
 * A hierarquia Shared → Global → Product é a que o time do iFood descreve no
 * blog de engenharia deles. Toda cor e todo radius vêm de `globals.css`, que
 * vem do `DESIGN.md` medido. Nenhum valor hexadecimal literal nos componentes.
 */

export { Abas, AbasDeNavegacao } from "./Abas";
export type { Aba, AbaDeNavegacao } from "./Abas";
export { Barra } from "./Barra";
export type { TomDaBarra } from "./Barra";
export { Botao, BotaoIcone } from "./Botao";
export type { PropsDoBotao, PropsDoBotaoIcone } from "./Botao";
export { BotaoLink } from "./BotaoLink";
export type { PropsDoBotaoLink } from "./BotaoLink";
export { classesDoBotao } from "./estilosDoBotao";
export type { TamanhoBotao, VarianteBotao } from "./estilosDoBotao";
export { AreaDeTexto, Busca, Campo, Entrada, EntradaNumero, Selecao } from "./Campos";
export { AcimaDoLink, Card, CardLink, LinkEsticado } from "./Card";
export type { DensidadeDoCard, ElementoDoCard, TomDoCard } from "./Card";
export { Chip, SeloVeredito } from "./Chip";
export type { TomDoChip } from "./Chip";
export { Dialogo, DialogoDeConfirmacao, useDialogoNativo } from "./Dialogo";
export { Esqueleto, EsqueletoCartao, EsqueletoDaPagina, EsqueletoGrade, EsqueletoLista, EsqueletoTexto } from "./Esqueleto";
export type { VarianteDoEsqueleto } from "./Esqueleto";
export { EstadoVazio, Vazio } from "./EstadoVazio";
export { Estrelas } from "./Estrelas";
export { BotaoFiltros, ChipsAtivos, FiltroChips, Ordenacao } from "./Filtros";
export type { FiltroAtivo, OpcaoDeFiltro } from "./Filtros";
export { Folha } from "./Folha";
export type { LadoDaFolha } from "./Folha";
export { ImagemComFallback } from "./ImagemComFallback";
export type { ProporcaoDaImagem, TipoDeImagem } from "./ImagemComFallback";
export { IndicadorDeSalvamento } from "./IndicadorDeSalvamento";
export type { EstadoDoSalvamento } from "./IndicadorDeSalvamento";
export { ListaDoTempo } from "./ListaDoTempo";
export type { GrupoDoTempo, ItemDoTempo } from "./ListaDoTempo";
export { ListaExpansivel } from "./ListaExpansivel";
export { AnimatePresence, ComMovimento, DURACAO, EASE_PADRAO, ProvedorDeMovimento, Revelar, Surgir, m } from "./Movimento";
export { Problema } from "./Problema";
export { DESCRICAO_DO_PROBLEMA, TITULO_DO_PROBLEMA, textoDoProblema } from "./textosDoProblema";
export { Segmentado } from "./Segmentado";
export type { OpcaoDoSegmentado } from "./Segmentado";
export { CabecalhoDaPagina, TituloSecao } from "./Titulos";
export { ProvedorDeToasts, useToast } from "./Toast";
export type { PedidoDeAviso, TomDoAviso } from "./Toast";
export { Derivacao, Valor } from "./Valor";
export type { TamanhoDoValor, TomDoValor } from "./Valor";
