/**
 * Acessibilidade das primitivas, verificada pelo axe.
 *
 * Vale como portão porque tudo que a interface mostra é composto destas peças:
 * um papel errado ou um controle sem nome aqui se multiplica por todas as
 * telas. O contraste não entra (o jsdom não pinta): esse é conferido nos
 * tokens (`contraste.test.ts`) e na tela de verdade, pelo axe do Playwright.
 */

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import type { Dinheiro } from "@/lib/api/base";

import {
  Abas,
  AbasDeNavegacao,
  AcimaDoLink,
  AreaDeTexto,
  Barra,
  Botao,
  BotaoFiltros,
  BotaoIcone,
  BotaoLink,
  Busca,
  CabecalhoDaPagina,
  Campo,
  Card,
  CardLink,
  Chip,
  ChipsAtivos,
  Derivacao,
  Dialogo,
  DialogoDeConfirmacao,
  Entrada,
  EntradaNumero,
  EsqueletoDaPagina,
  EstadoVazio,
  Estrelas,
  FiltroChips,
  Folha,
  ImagemComFallback,
  IndicadorDeSalvamento,
  ListaDoTempo,
  ListaExpansivel,
  Ordenacao,
  Problema,
  ProvedorDeToasts,
  Segmentado,
  Selecao,
  SeloVeredito,
  TituloSecao,
  Valor,
  Vazio,
} from "./Primitivas";

const reais: Dinheiro = { valor: 1234.56, texto: "R$ 1.234,56" };
const nada = () => {};

const CASOS: [string, ReactElement][] = [
  ["botão primário", <Botao key="b">Calcular</Botao>],
  ["botão desabilitado", <Botao key="bd" disabled>Calcular</Botao>],
  ["botão carregando", <Botao key="bc" carregando rotuloCarregando="Salvando…">Salvar</Botao>],
  ["botão só de ícone", <BotaoIcone key="bi" rotulo="Fechar">x</BotaoIcone>],
  ["link com cara de botão", <BotaoLink key="bl" href="/receitas">Ver receitas</BotaoLink>],
  ["link externo", <BotaoLink key="be" href="https://exemplo.com.br" externo>Ver a receita no site</BotaoLink>],
  ["valor monetário", <Valor key="v" dinheiro={reais} />],
  ["valor ainda desconhecido", <Valor key="vd" dinheiro={null} />],
  ["derivação", <Derivacao key="d">R$ 28,00 ÷ 2 kg = R$ 14,00/kg</Derivacao>],
  ["selo de viabilidade", <SeloVeredito key="s" veredito="BLOQUEADO" />],
  ["barra com rótulo", <Barra key="ba" fracao={0.4} rotulo="orçamento usado" valorTexto="40% usado" />],
  ["chip", <Chip key="c" tom="atencao">Falta saber</Chip>],
  ["vazio (nome antigo)", <Vazio key="z" titulo="Nada ainda" />],
  [
    "estado vazio com ação",
    <EstadoVazio key="ev" titulo="Nenhuma receita" descricao="Traga uma receita." acao={<Botao>Trazer</Botao>} />,
  ],
  ["pergunta", <Problema key="p" mensagem="m" categoria="dado" pergunta="Quanto pesa?" />],
  ["problema com tentar de novo", <Problema key="pt" categoria="rede" aoTentarDeNovo={nada} nivelTitulo={2} />],
  ["título de seção com ver tudo", <TituloSecao key="t" titulo="Receitas" verMais={{ href: "/receitas" }} />],
  [
    "cabeçalho da página",
    <CabecalhoDaPagina key="cp" titulo="Despensa" descricao="37 ingredientes" voltar={{ href: "/", rotulo: "Início" }} acoes={<Botao>Adicionar</Botao>} />,
  ],
  [
    "cartão clicável com botão por cima",
    <CardLink key="cl" href="/despensa/alcaparras" titulo="Alcaparras">
      <AcimaDoLink>
        <Botao variante="texto">Perguntar</Botao>
      </AcimaDoLink>
    </CardLink>,
  ],
  [
    "campo com dica e erro",
    <Campo key="ca" rotulo="Quanto pagou" dica="o total da nota" erro="Escreva só o número.">
      <Entrada />
    </Campo>,
  ],
  [
    "número com botões",
    <Campo key="cn" rotulo="Bocas do fogão">
      <EntradaNumero valor={4} aoMudar={nada} casas={0} comBotoes min={1} max={8} unidade="bocas" />
    </Campo>,
  ],
  [
    "área de texto",
    <Campo key="at" rotulo="Notas">
      <AreaDeTexto value="" onChange={nada} />
    </Campo>,
  ],
  [
    "seleção",
    <Campo key="se" rotulo="Unidade">
      <Selecao opcoes={[{ valor: "kg", rotulo: "kg" }]} />
    </Campo>,
  ],
  ["busca sem campo em volta", <Busca key="bu" valor="alho" aoMudar={nada} rotulo="Buscar ingrediente" />],
  [
    "segmentado",
    <Segmentado
      key="sg"
      legenda="Forno"
      valor="tem"
      aoMudar={nada}
      opcoes={[
        { valor: "tem", rotulo: "Tenho" },
        { valor: "nao_tem", rotulo: "Não tenho" },
        { valor: "nao_sei", rotulo: "Não sei" },
      ]}
    />,
  ],
  [
    "abas",
    <Abas
      key="ab"
      rotulo="Receitas"
      abas={[
        { id: "todas", rotulo: "Todas", contagem: 12, conteudo: <p>grade</p> },
        { id: "ranking", rotulo: "Ranking", conteudo: <p>ranking</p> },
      ]}
    />,
  ],
  [
    "abas de navegação",
    <AbasDeNavegacao
      key="an"
      rotulo="Receitas"
      abas={[
        { href: "/receitas?aba=todas", rotulo: "Todas", ativa: true },
        { href: "/receitas?aba=ranking", rotulo: "Ranking", ativa: false },
      ]}
    />,
  ],
  ["estrelas para dar nota", <Estrelas key="es" legenda="Sabor" valor={3} aoMudar={nada} />],
  ["estrelas só para ver", <Estrelas key="el" legenda="Sabor" valor={4} somenteLeitura />],
  [
    "chips de filtro",
    <FiltroChips
      key="fc"
      legenda="Categoria"
      selecionados={["graos"]}
      aoMudar={nada}
      opcoes={[
        { valor: "graos", rotulo: "Grãos", contagem: 7 },
        { valor: "laticinios", rotulo: "Laticínios", contagem: 5 },
      ]}
    />,
  ],
  [
    "filtros ativos",
    <ChipsAtivos
      key="ca2"
      resumo="3 de 37 ingredientes"
      aoLimparTudo={nada}
      filtros={[
        { id: "a", rotulo: "Grãos", aoRemover: nada },
        { id: "b", rotulo: "Até R$ 20,00", aoRemover: nada },
      ]}
    />,
  ],
  ["botão de filtros", <BotaoFiltros key="bf" quantidade={2} aoAbrir={nada} />],
  [
    "ordenação",
    <Ordenacao
      key="or"
      valor="nota"
      aoMudar={nada}
      opcoes={[
        { valor: "nota", rotulo: "Nota" },
        { valor: "custo", rotulo: "Custo" },
      ]}
    />,
  ],
  [
    "lista expansível",
    <ListaExpansivel
      key="le"
      itens={["a", "b", "c", "d"]}
      visiveis={2}
      chave={(i) => i}
      renderizar={(i) => <span>{i}</span>}
    />,
  ],
  [
    "linha do tempo",
    <ListaDoTempo
      key="lt"
      grupos={[
        {
          id: "hoje",
          titulo: "Hoje",
          itens: [{ id: "1", texto: "Veio da planilha.", quandoTexto: "hoje, 10:02", link: { href: "/despensa", rotulo: "Ver" } }],
        },
      ]}
    />,
  ],
  ["indicador de salvamento", <IndicadorDeSalvamento key="is" estado="erro" aoTentarDeNovo={nada} />],
  ["foto que não existe", <ImagemComFallback key="im" src={null} alt="Peito de frango" tipo="ingrediente" />],
  ["foto decorativa", <ImagemComFallback key="id" src="/motor/imagens/9b1e22c4a0f35d7e" alt="" />],
  ["esqueleto da página", <EsqueletoDaPagina key="ep" variante="grade" />],
];

describe("axe nas primitivas", () => {
  it.each(CASOS)("%s não tem violação", async (_nome, elemento) => {
    const { container } = render(<ProvedorDeToasts>{elemento}</ProvedorDeToasts>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("um cartão com título e conteúdo não tem violação", async () => {
    const { container } = render(
      <Card>
        <TituloSecao titulo="Despensa" apoio="37 itens" />
        <Valor dinheiro={reais} />
      </Card>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("diálogo aberto, de confirmação e folha não têm violação", async () => {
    const { baseElement } = render(
      <>
        <Dialogo aberto aoFechar={nada} titulo="Editar ingrediente" descricao="Mude o que precisar.">
          <Campo rotulo="Nome">
            <Entrada />
          </Campo>
        </Dialogo>
        <DialogoDeConfirmacao
          aberto
          titulo="Tirar da despensa?"
          descricao="O creme de leite sai da lista."
          rotuloConfirmar="Tirar"
          perigoso
          aoConfirmar={nada}
          aoCancelar={nada}
        />
        <Folha aberto aoFechar={nada} titulo="Filtros" rodape={<Botao>Ver 12 receitas</Botao>}>
          <p>filtros</p>
        </Folha>
      </>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
