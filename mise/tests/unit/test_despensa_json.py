"""A despensa em palavras: o que a tela e o agente dizem de cada item, sem conta feita por eles."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from mise import despensa_json as dj
from mise.despensa import (
    Despensa,
    LinhaDaDespensa,
    OrigemDoItem,
    Pendencia,
    TipoDePendencia,
    carregar_despensa,
)
from mise.despensa import montar_ingrediente as montar
from mise.despensa_editavel import Acao, Evento, Mudanca, TipoDeEvento
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Dossie, EstadoOrcamento, LinhaDoExtrato
from mise.mcp_server import Sessao
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente, receita
from mise.unidades import Dimensao, Quantidade
from mise.viabilidade import Veredito

if TYPE_CHECKING:
    from collections.abc import Iterator

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"
AGORA = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)


@pytest.fixture
def sessao(tmp_path: Path) -> Iterator[Sessao]:
    s = Sessao(
        planilha=carregar_despensa(PLANILHA),
        dossie=Dossie(tmp_path / "dossie.db", relogio=lambda: AGORA),
        arquivo_txt=None,
    )
    yield s
    s.dossie.fechar()


def _item(**campos: Any) -> Any:
    base: dict[str, Any] = {
        "nome": "Creme de leite",
        "estoque": Decimal(2),
        "unidade": "un 200g",
        "quantidade_comprada": Decimal(2),
        "preco_pago": Decimal("9.00"),
    }
    item, _ = montar(LinhaDaDespensa(**{**base, **campos}))
    return item


# --------------------------------------------------------------------------- #
# Números, quantidades e datas
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("valor", "texto"),
    [("0.5", "0,5"), ("2", "2"), ("1234", "1.234"), ("1.50", "1,5"), ("0.0010", "0,001")],
)
def test_numero_em_pt_br(valor: str, texto: str) -> None:
    assert dj.numero_texto(Decimal(valor)) == texto


@pytest.mark.parametrize(
    ("valor", "dimensao", "texto"),
    [
        ("0.8", Dimensao.MASSA, "800 g"),
        ("1.5", Dimensao.MASSA, "1,5 kg"),
        ("0", Dimensao.MASSA, "0 kg"),
        ("0.3", Dimensao.VOLUME, "300 ml"),
        ("2", Dimensao.VOLUME, "2 L"),
        ("1", Dimensao.CONTAGEM, "1 unidade"),
        ("30", Dimensao.CONTAGEM, "30 unidades"),
    ],
)
def test_quantidade_escrita(valor: str, dimensao: Dimensao, texto: str) -> None:
    assert dj.quantidade_texto(Quantidade(Decimal(valor), dimensao)) == texto


@pytest.mark.parametrize(
    ("momento", "texto"),
    [
        (datetime(2026, 9, 25, 12, 32, tzinfo=UTC), "hoje, 09:32"),
        (datetime(2026, 9, 24, 23, 0, tzinfo=UTC), "ontem, 20:00"),
        (datetime(2026, 9, 25, 2, 0, tzinfo=UTC), "ontem, 23:00"),
        (datetime(2026, 9, 20, 15, 0, tzinfo=UTC), "20 de setembro"),
        (datetime(2025, 3, 2, 15, 0, tzinfo=UTC), "2 de março de 2025"),
    ],
)
def test_quando_no_horario_dela(momento: datetime, texto: str) -> None:
    assert dj.quando_texto(momento, AGORA) == texto


def test_data_e_hora_da_planilha_em_texto() -> None:
    assert dj.data_hora_texto(AGORA) == "2026-09-25 10:00"


@pytest.mark.parametrize(
    ("nome", "com_artigo"),
    [
        ("Cobertura de chocolate", "a cobertura de chocolate"),
        ("Ovos", "os ovos"),
        ("Alcaparras", "as alcaparras"),
        ("Feijão preto", "o feijão preto"),
        ("Creme de leite", "o creme de leite"),
        ("Sal", "o sal"),
        ("UHT integral", "UHT integral"),
    ],
)
def test_o_item_com_o_artigo_que_a_terminacao_diz(nome: str, com_artigo: str) -> None:
    assert dj.o_item(nome) == com_artigo


# --------------------------------------------------------------------------- #
# Um item
# --------------------------------------------------------------------------- #

TEXTOS_DA_PLANILHA: dict[str, tuple[str, str, str, str]] = {
    "peito-de-frango": (
        "2 kg",
        "2 kg por R$ 28,00",
        "conta direta da planilha",
        "4% do que a senhora pagou",
    ),
    "miolo-de-alcatra": (
        "800 g",
        "800 g por R$ 34,00",
        "conta direta da planilha",
        "5% do que a senhora pagou",
    ),
    "ovos": (
        "30 unidades",
        "30 unidades por R$ 24,00",
        "conta direta da planilha",
        "4% do que a senhora pagou",
    ),
    "sal": (
        "1 kg",
        "1 kg por R$ 1,85",
        "conta direta da planilha",
        "menos de 1% do que a senhora pagou",
    ),
    "alcaparras": (
        "2 kg (1 balde de 2 kg)",
        "1 balde de 2 kg por R$ 82,00",
        "conta com conversão de embalagem",
        "12% do que a senhora pagou",
    ),
    "azeite-de-oliva-extra-virgem": (
        "500 ml (1 embalagem de 500 ml)",
        "1 embalagem de 500 ml por R$ 30,99",
        "conta com conversão de embalagem",
        "5% do que a senhora pagou",
    ),
    "cobertura-de-chocolate": (
        "1 kg (1 embalagem de 1 kg)",
        "1 embalagem de 1 kg por R$ 79,90",
        "conta com conversão de embalagem",
        "12% do que a senhora pagou",
    ),
}


@pytest.mark.parametrize("item_id", list(TEXTOS_DA_PLANILHA))
def test_textos_dos_itens_da_planilha(despensa: Despensa, item_id: str) -> None:
    item = despensa.por_id(item_id)
    assert item is not None
    estoque, comprado, confianca, fracao = TEXTOS_DA_PLANILHA[item_id]
    assert dj.estoque_texto(item) == estoque
    assert dj.comprado_texto(item) == comprado
    assert dj.confianca_rotulo(item) == confianca
    assert dj.fracao_texto(despensa.fracao_de(item), item) == fracao


def test_item_da_lista_tem_a_forma_do_contrato(despensa: Despensa) -> None:
    alcaparras = dj.item_json(despensa["Alcaparras"], despensa, 1)
    assert alcaparras["custo_unitario"] == {"valor": 41.0, "texto": "R$ 41,00/kg"}
    assert alcaparras["derivacao"] == "1 × 2 kg = 2 kg; R$ 82,00 ÷ 2 kg = R$ 41,00/kg"
    assert alcaparras["categoria_rotulo"] == "Conservas e molhos"
    assert alcaparras["receitas_que_usam_texto"] == "entra em 1 receita"
    assert alcaparras["rota"] == "/despensa/alcaparras"
    # A foto do Commons, pelo proxy da API, com o crédito que a licença pede.
    assert alcaparras["imagem"]["url"].startswith("/motor/imagens/")
    assert alcaparras["imagem"]["credito"].endswith(", Wikimedia Commons")
    assert alcaparras["fracao_do_total"] == 0.1236

    cobertura = dj.item_json(despensa["Cobertura de chocolate"], despensa)
    # O peso que a planilha não diz vem estimado, com a fonte: nada pendente para ela.
    assert cobertura["custo_unitario"] == {"valor": 79.9, "texto": "R$ 79,90/kg"}
    assert cobertura["pendente"] is False
    assert cobertura["derivacao"].startswith("R$ 79,90 ÷ 1 kg = R$ 79,90/kg; o peso é cerca de")
    assert "estimativa" in cobertura["derivacao"]
    assert cobertura["receitas_que_usam_texto"] == "ainda sem receita"


def test_item_sem_preco_nao_tem_pago_nem_custo() -> None:
    item = _item(nome="Farinha de rosca", unidade="kg", estoque=Decimal("0.5"), preco_pago=None)
    despensa = Despensa(itens={item.nome: item})
    corpo = dj.item_json(item, despensa)
    assert corpo["pago"] is None
    assert corpo["custo_unitario"] is None
    assert corpo["confianca_rotulo"] == "falta o preço que a senhora pagou"
    assert corpo["fracao_texto"] == "sem o preço, fica fora do total"
    assert dj.comprado_texto(item) == "a senhora não disse quanto pagou"
    assert dj.custo_texto(item) == "sem o preço, não dá para saber"


@pytest.mark.parametrize(
    ("campos", "estoque", "comprado"),
    [
        ({}, "400 g (2 embalagens de 200 g)", "2 embalagens de 200 g por R$ 9,00"),
        (
            {"unidade": "lata 395g", "estoque": Decimal(1), "quantidade_comprada": Decimal(1)},
            "395 g (1 lata de 395 g)",
            "1 lata de 395 g por R$ 9,00",
        ),
        (
            {"unidade": "pct", "estoque": Decimal(3), "quantidade_comprada": Decimal(3)},
            "3 pacotes",
            "3 pacotes por R$ 9,00",
        ),
        (
            {"unidade": "un", "estoque": Decimal(2), "quantidade_comprada": Decimal(1)},
            "2 embalagens (peso não informado)",
            "1 embalagem por R$ 9,00",
        ),
        (
            {"unidade": "un", "estoque": Decimal(12), "quantidade_comprada": Decimal(12)},
            "12 unidades",
            "12 unidades por R$ 9,00",
        ),
        (
            {"unidade": "g", "estoque": Decimal(500), "quantidade_comprada": Decimal(500)},
            "500 g",
            "500 g por R$ 9,00",
        ),
        ({"estoque": Decimal(0)}, "acabou", "2 embalagens de 200 g por R$ 9,00"),
        (
            {"unidade": "garrafa 1L", "estoque": Decimal(2), "quantidade_comprada": Decimal(2)},
            "2 L (2 garrafas de 1 L)",
            "2 garrafas de 1 L por R$ 9,00",
        ),
    ],
)
def test_estoque_e_compra_de_itens_novos(
    campos: dict[str, Any], estoque: str, comprado: str
) -> None:
    item = _item(**campos)
    assert dj.estoque_texto(item) == estoque
    assert dj.comprado_texto(item) == comprado


def test_confianca_de_itens_novos() -> None:
    ja_tinha = _item(unidade="kg", estoque=Decimal(1), origem=OrigemDoItem.JA_TINHA)
    assert dj.confianca_rotulo(ja_tinha) == "conta direta"
    informada = _item(
        unidade="un 1kg",
        estoque=Decimal(1),
        quantidade_comprada=Decimal(1),
        conteudo_informado=True,
    )
    assert dj.confianca_rotulo(informada) == "conta com o peso que a senhora informou"


def test_receitas_texto() -> None:
    assert dj.receitas_texto(0) == "ainda sem receita"
    assert dj.receitas_texto(1) == "entra em 1 receita"
    assert dj.receitas_texto(3) == "entra em 3 receitas"


def test_pendencias_na_forma_da_tela(despensa: Despensa) -> None:

    # A planilha não gera pendência nenhuma; a forma continua a do contrato.
    assert despensa.pendencias == []
    cobertura = Pendencia("Cobertura de chocolate", "sem peso", "", Dinheiro.de("79.90"))
    corpo = dj.pendencia_json(cobertura, despensa)
    assert corpo["id"] == "cobertura-de-chocolate"
    assert corpo["impacto"] == {"valor": 79.9, "texto": "R$ 79,90"}
    assert corpo["impacto_texto"] == "R$ 79,90 parados até isso ser respondido"
    assert corpo["resposta_inline"] == {
        "tipo": "conteudo_embalagem",
        "rotulo": "Quanto vem na embalagem?",
        "unidades": ["g", "kg", "ml", "L"],
    }
    assert corpo["rascunho_chat"] == "A embalagem da cobertura de chocolate tem "
    assert corpo["rota"] == "/despensa/cobertura-de-chocolate"

    item, sem_pendencia = montar(
        LinhaDaDespensa("Farinha de rosca", Decimal(1), "kg", Decimal(1), None)
    )
    assert sem_pendencia is None
    pendencia = Pendencia(
        "Farinha de rosca", "sem preço", "", Dinheiro.zero(), TipoDePendencia.PRECO
    )
    so_ela = Despensa(itens={item.nome: item}, pendencias=[pendencia])
    preco = dj.pendencia_json(pendencia, so_ela)
    assert preco["resposta_inline"]["tipo"] == "preco_pago"
    assert "sem o preço" in preco["impacto_texto"]
    assert preco["rascunho_chat"] == "Paguei por farinha de rosca "


# --------------------------------------------------------------------------- #
# Os R$ 80,00
# --------------------------------------------------------------------------- #


def test_resumo_do_orcamento() -> None:
    inicial = Dinheiro.de("80.00")
    assert (
        dj.resumo_do_orcamento(EstadoOrcamento(inicial, Dinheiro.zero()))
        == "Nada gasto ainda: restam R$ 80,00 para complementos."
    )
    assert (
        dj.resumo_do_orcamento(EstadoOrcamento(inicial, Dinheiro.de("9.00")))
        == "Saíram R$ 9,00 dos complementos; restam R$ 71,00."
    )


def test_orcamento_so_lista_as_compras_que_contam() -> None:
    compra = LinhaDoExtrato(1, "Creme (despensa)", Dinheiro.de("9.00"), AGORA, "tela", item_id="i")
    devolvida = LinhaDoExtrato(2, "Milho", Dinheiro.de("6.00"), AGORA, "conversa", estornada=True)
    devolucao = LinhaDoExtrato(
        3, "Devolução: Milho", Dinheiro.de("-6.00"), AGORA, "tela", estorna=2
    )
    corpo = dj.orcamento_json(
        EstadoOrcamento(Dinheiro.de("80.00"), Dinheiro.de("9.00")),
        (compra, devolvida, devolucao),
        AGORA,
    )
    assert [c["id"] for c in corpo["compras"]] == [1]
    assert corpo["compras"][0]["pode_estornar"] is True
    assert corpo["compras"][0]["quando_texto"] == "hoje, 10:00"
    assert corpo["compras"][0]["rota_estorno"] == "/api/compras/1/estorno"
    assert corpo["fracao_gasta"] == 0.1125
    zerado = dj.orcamento_json(EstadoOrcamento(Dinheiro.zero(), Dinheiro.zero()), (), AGORA)
    assert zerado["fracao_gasta"] == 0.0


# --------------------------------------------------------------------------- #
# Receitas e a sessão
# --------------------------------------------------------------------------- #


def _cozinha_pronta(sessao: Sessao) -> None:
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    sessao.dossie.salvar_perfil(
        perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
    )


def _arroz_com_frango(url: str | None = None) -> Any:
    return receita(
        "Arroz com frango",
        [
            ingrediente("500 g de frango", "frango", 500, "g"),
            ingrediente("2 xícaras de arroz", "arroz", 2, "xicara"),
            ingrediente("sal a gosto", "sal"),
        ],
        rendimento_porcoes=4,
        modo_preparo=["Refogue o frango na panela e junte o arroz."],
        url=url,
    )


def test_receitas_por_item_e_detalhe_com_o_que_a_receita_usa(sessao: Sessao) -> None:
    _cozinha_pronta(sessao)
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    sessao.guardar(_arroz_com_frango())
    usos = dj.receitas_por_item(sessao.despensa, sessao.candidatas)
    assert {nome for nome, rs in usos.items() if rs} == {
        "Peito de frango",
        "Arroz branco tipo 1",
        "Sal",
    }
    corpo = dj.detalhe(sessao, "peito-de-frango")
    (arroz,) = corpo["receitas"]
    assert arroz["slug"] == "arroz-com-frango"
    assert arroz["usa_texto"] == "usa 500 g"
    assert arroz["veredito_rotulo"] in {"Dá pra fazer", "Dá, comprando", "Falta saber", "Não dá"}
    assert corpo["receitas_que_usam"] == 1
    assert corpo["historico"][0]["texto"] == "Veio da planilha: 2 kg por R$ 28,00."
    assert corpo["rascunho_chat"] == "O que eu posso fazer com peito de frango?"
    sal = dj.detalhe(sessao, "sal")
    assert sal["receitas"][0]["usa_texto"] == "usa a gosto"


def test_slug_da_receita_pelo_endereco_ou_pelo_nome() -> None:
    pelo_nome = dj.slug_da_receita(_arroz_com_frango())
    assert pelo_nome == "arroz-com-frango"
    a = dj.slug_da_receita(_arroz_com_frango("https://www.Site.com/receita/1/?utm=x#passo"))
    b = dj.slug_da_receita(_arroz_com_frango("https://site.com/receita/1"))
    assert a == b
    assert len(a) == 16


def test_receitas_afetadas_sem_receita_e_com_receita_que_nao_mudou() -> None:
    assert dj.receitas_afetadas({}, {})["texto"] == "Ainda não há receita em avaliação."
    igual = dj.receitas_afetadas({"A": Veredito.APTO}, {"A": Veredito.APTO})
    assert igual["texto"] == "Nenhuma receita em avaliação mudou."
    varias = dj.receitas_afetadas(
        {"A": Veredito.FALTA_INFO, "B": Veredito.FALTA_INFO, "C": Veredito.APTO},
        {"A": Veredito.APTO, "B": Veredito.APTO_COM_COMPRA, "C": Veredito.BLOQUEADO},
    )
    assert varias["liberadas"] == ["A", "B"]
    assert varias["bloqueadas"] == ["C"]
    assert varias["texto"] == "Isso libera 2 receitas. Isso segura 1 receita."


def test_receita_que_mudou_sem_liberar_nem_segurar_tambem_e_dita() -> None:
    mudou = dj.receitas_afetadas(
        {"Arroz refogado": Veredito.APTO, "Bolo": Veredito.APTO},
        {"Arroz refogado": Veredito.APTO_COM_COMPRA, "Bolo": Veredito.APTO},
    )
    assert mudou["mudaram"] == [
        {"receita": "Arroz refogado", "antes": "Dá pra fazer", "depois": "Dá, comprando"}
    ]
    assert mudou["texto"] == "Arroz refogado passou para “Dá, comprando”."
    junto = dj.receitas_afetadas(
        {"A": Veredito.FALTA_INFO, "B": Veredito.APTO},
        {"A": Veredito.APTO, "B": Veredito.APTO_COM_COMPRA},
    )
    assert junto["texto"] == "Isso libera 1 receita. B passou para “Dá, comprando”."


def test_listar_com_busca_categoria_e_ordem(sessao: Sessao) -> None:
    tudo = dj.listar(sessao)
    assert tudo["total_itens"] == tudo["encontrados"] == 37
    assert tudo["itens"][0]["nome"] == "Alcaparras"
    assert tudo["total_investido"]["texto"] == "R$ 663,39"
    assert sum(c["quantidade"] for c in tudo["categorias"]) == 37
    assert [c["id"] for c in tudo["categorias_para_escolher"]][-1] == "outros"
    assert len(tudo["categorias_para_escolher"]) == 9
    assert tudo["pendencias"] == []
    assert tudo["orcamento"]["texto"] == "Nada gasto ainda: restam R$ 80,00 para complementos."

    busca = dj.listar(sessao, q="feijao")
    assert [i["nome"] for i in busca["itens"]] == ["Feijão carioquinha", "Feijão preto"]
    assert busca["total_itens"] == 37
    assert busca["encontrados"] == 2

    laticinios = dj.listar(sessao, categoria="laticinios", ordem="nome")
    assert [i["nome"] for i in laticinios["itens"]] == [
        "Leite integral",
        "Leite ninho em pó",
        "Manteiga",
        "Queijo mussarela",
        "Queijo parmesão ralado",
    ]
    por_custo = dj.listar(sessao, ordem="custo")["itens"]
    assert por_custo[0]["nome"] == "Cobertura de chocolate" or por_custo[0]["custo_unitario"]
    # Sem pendência na planilha, todo item tem custo; o mais barato por unidade vem por último.
    assert por_custo[-1]["custo_unitario"] is not None
    por_categoria = dj.listar(sessao, ordem="categoria")["itens"]
    assert por_categoria[0]["categoria"] == "proteinas"
    assert por_categoria[-1]["categoria"] == "confeitaria"


def test_listar_recusa_ordem_e_categoria_desconhecidas(sessao: Sessao) -> None:
    from mise.erros import ErroDeUso

    with pytest.raises(ErroDeUso, match="ordem"):
        dj.listar(sessao, ordem="preco")
    with pytest.raises(ErroDeUso, match="categoria"):
        dj.listar(sessao, categoria="joias")


def test_historico_e_eventos_contam_cada_mudanca(sessao: Sessao) -> None:
    sessao.editavel.informar_embalagem("cobertura-de-chocolate", "1 kg", canal=Canal.TELA)
    compra = sessao.editavel.adicionar(
        nome="Creme de leite",
        estoque=Decimal(2),
        unidade="un 200g",
        quantidade_comprada=Decimal(2),
        preco_pago=Decimal("9.00"),
        origem=OrigemDoItem.ORCAMENTO,
    )
    sessao.editavel.adicionar(nome="Nata", estoque=Decimal("0.2"), unidade="kg")
    sessao.editavel.adicionar(
        nome="Farinha de rosca", estoque=Decimal(1), unidade="kg", preco_pago=Decimal("8.00")
    )
    sessao.editavel.corrigir("peito-de-frango", estoque=Decimal("1.5"), preco_pago=Decimal("30"))
    sessao.editavel.corrigir(compra.item_id, preco_pago=Decimal("10.00"))
    sessao.editavel.acabou("bacon")
    remocao = sessao.editavel.remover(compra.item_id)
    sessao.editavel.desfazer(remocao.evento.id)
    sessao.editavel.remover("alcaparras")
    correcao = sessao.editavel.corrigir("canela-em-po", categoria="confeitaria")
    sessao.editavel.desfazer(correcao.evento.id)

    corpo = dj.eventos_json(sessao)
    textos = [e["texto"] for e in reversed(corpo["eventos"])]
    assert textos == [
        "Embalagem de 1 kg informada.",
        "A senhora comprou com os complementos: 2 embalagens de 200 g por R$ 9,00.",
        "A senhora acrescentou o que já tinha: 200 g, sem o preço.",
        "A senhora acrescentou o que já tinha: 1 kg, pagou R$ 8,00.",
        "Corrigido: estoque de 2 kg para 1,5 kg; preço de R$ 28,00 para R$ 30,00.",
        "Corrigido: preço de R$ 9,00 para R$ 10,00. Voltaram R$ 9,00 e saíram R$ 10,00 dos"
        " complementos.",
        "A senhora avisou que acabou.",
        "Tirado da despensa. R$ 10,00 voltaram para os complementos.",
        "Voltou para a despensa. R$ 10,00 saíram de novo dos complementos.",
        "Tirado da despensa.",
        "Corrigido: categoria de Temperos e condimentos para Confeitaria.",
        "Desfeita a correção: categoria de Confeitaria para Temperos e condimentos.",
    ]
    assert corpo["total"] == 12
    assert corpo["versao"] == 12
    assert corpo["eventos"][0]["pode_desfazer"] is True
    assert corpo["eventos"][0]["desfaz"] == corpo["eventos"][1]["id"]
    assert corpo["eventos"][-1]["quando_texto"] == "hoje, 10:00"
    assert len(dj.eventos_json(sessao, limite=2)["eventos"]) == 2

    detalhe = dj.detalhe(sessao, compra.item_id)
    assert detalhe["historico"][0]["tipo"] == "adicionar"
    assert [c["valor"]["texto"] for c in detalhe["compras"]] == [
        "R$ 9,00",
        "-R$ 9,00",
        "R$ 10,00",
        "-R$ 10,00",
        "R$ 10,00",
    ]
    assert detalhe["origem_rotulo"] == "comprado com os complementos"


def _mudanca(tipo: TipoDeEvento, acao: Acao, **campos: Any) -> Mudanca:
    evento = Evento(1, "k", "bacon", tipo, {"acao": acao.value}, "", "tela", None, AGORA)
    return Mudanca(evento=evento, antes=None, depois=None, nome="Bacon", **campos)


def test_textos_das_mudancas(despensa: Despensa) -> None:
    estado = EstadoOrcamento(Dinheiro.de("80.00"), Dinheiro.de("9.00"))
    assert dj.texto_da_mudanca(_mudanca(TipoDeEvento.CORRIGIR, Acao.ACABOU), estado) == (
        "Anotei que o bacon acabou."
    )
    restaurado = _mudanca(TipoDeEvento.RESTAURAR, Acao.DESFAZER)
    assert dj.texto_da_mudanca(restaurado, estado) == "Voltei o bacon para a despensa."
    bacon = despensa["Bacon"]
    corrigido = Mudanca(
        evento=Evento(1, "k", "bacon", TipoDeEvento.CORRIGIR, {}, "", "tela", None, AGORA),
        antes=bacon,
        depois=bacon,
        nome="Bacon",
    )
    assert dj.texto_da_mudanca(corrigido, estado) == "Corrigi o bacon. Agora sai a R$ 23,90/kg."
    repetida = Mudanca(evento=None, antes=None, depois=None, nome="Bacon", repetida=True)
    assert dj.texto_da_mudanca(repetida, estado) == "Isso já estava anotado."
    nada = Mudanca(evento=None, antes=bacon, depois=bacon, nome="Bacon")
    assert dj.texto_da_mudanca(nada, estado) == "Nada mudou no bacon: já estava assim."


def test_acabou_leva_o_artigo_do_nome(sessao: Sessao) -> None:
    acabou, afetadas = sessao.mudar_despensa(lambda e: e.acabou("alcaparras"))
    assert dj.mudanca_json(sessao, acabou, afetadas)["texto"] == (
        "Anotei que as alcaparras acabaram."
    )


def test_embalagem_sem_o_preco_nao_deixa_a_frase_sem_valor(sessao: Sessao) -> None:
    novo, _ = sessao.mudar_despensa(
        lambda e: e.adicionar(nome="Leite condensado", estoque=Decimal(2), unidade="un")
    )
    embalagem, afetadas = sessao.mudar_despensa(
        lambda e: e.informar_embalagem(novo.item_id, "395 g")
    )
    corpo = dj.mudanca_json(sessao, embalagem, afetadas)
    assert corpo["texto"] == (
        "Anotei 395 g na embalagem do leite condensado. Falta o preço que a senhora pagou "
        "para saber o custo."
    )
    assert corpo["item"]["estoque_texto"] == "790 g (2 embalagens de 395 g)"


def test_texto_de_evento_com_dados_estranhos_nao_quebra() -> None:
    estranho = Evento(
        1,
        "k",
        "item-x",
        TipoDeEvento.ADICIONAR,
        {"linha": {"nome": "Coisa"}},
        "",
        "tela",
        None,
        AGORA,
    )
    assert (
        dj.texto_do_evento(estranho, "Coisa", {}) == "A senhora acrescentou o que já tinha: Coisa."
    )
    unidade_ruim = Evento(
        2,
        "k2",
        "bacon",
        TipoDeEvento.CORRIGIR,
        {"acao": "informar_embalagem", "campos": {"unidade": "punhado"}},
        "",
        "tela",
        None,
        AGORA,
    )
    assert dj.texto_do_evento(unidade_ruim, "Bacon", {}) == "Embalagem de punhado informada."
    sem_campos = Evento(3, "k3", "bacon", TipoDeEvento.CORRIGIR, {}, "", "tela", None, AGORA)
    assert dj.texto_do_evento(sem_campos, "Bacon", {}) == "Corrigido: dados corrigidos."
    esquisito = Evento(
        4,
        "k4",
        "bacon",
        TipoDeEvento.CORRIGIR,
        {
            "campos": {"estoque": "x", "preco_pago": None},
            "antes": {"estoque": None, "preco_pago": "y"},
        },
        "",
        "tela",
        None,
        AGORA,
    )
    assert dj.texto_do_evento(esquisito, "Bacon", {}) == (
        "Corrigido: estoque de nada para x; preço de y para não informado."
    )


def test_respostas_das_mudancas_com_dinheiro(sessao: Sessao) -> None:
    compra, afetadas = sessao.mudar_despensa(
        lambda e: e.adicionar(
            nome="Creme de leite",
            estoque=Decimal(2),
            unidade="un 200g",
            quantidade_comprada=Decimal(2),
            preco_pago=Decimal("9.00"),
            origem=OrigemDoItem.ORCAMENTO,
        )
    )
    corpo = dj.mudanca_json(sessao, compra, afetadas)
    assert corpo["texto"] == (
        "Anotei o creme de leite. Saíram R$ 9,00 dos complementos; restam R$ 71,00."
    )
    assert corpo["compra"] == {"valor": 9.0, "texto": "R$ 9,00"}
    assert corpo["orcamento_mudou"] is True

    novo_preco, afetadas = sessao.mudar_despensa(
        lambda e: e.corrigir(
            compra.item_id, preco_pago=Decimal("10.00"), quantidade_comprada=Decimal(4)
        )
    )
    assert dj.mudanca_json(sessao, novo_preco, afetadas)["texto"] == (
        "Corrigi o creme de leite. Agora sai a R$ 12,50/kg. Os complementos acompanharam o valor"
        " novo; restam R$ 70,00."
    )
    (evento, *_) = reversed(sessao.editavel.eventos())
    assert dj.texto_do_evento(evento, "Creme de leite", {}, "un 200g") == (
        "Corrigido: quantidade comprada de 2 embalagens para 4 embalagens; preço de R$ 9,00"
        " para R$ 10,00."
    )

    tirado, afetadas = sessao.mudar_despensa(lambda e: e.remover(compra.item_id))
    assert dj.mudanca_json(sessao, tirado, afetadas)["texto"] == (
        "Tirei o creme de leite e devolvi R$ 10,00 aos complementos; restam R$ 80,00."
    )
    volta, afetadas = sessao.mudar_despensa(lambda e: e.desfazer(tirado.evento.id))
    assert dj.mudanca_json(sessao, volta, afetadas)["texto"] == (
        "Voltei o creme de leite para a despensa. Saíram de novo R$ 10,00 dos complementos;"
        " restam R$ 70,00."
    )

    (ativa,) = sessao.dossie.compras_do_item(compra.item_id)
    (estorno, mudanca), afetadas = sessao.mudar_despensa(lambda e: e.estornar_compra(ativa.id))
    resposta = dj.estorno_json(sessao, estorno, mudanca, afetadas)
    assert resposta["texto"] == (
        "Devolvi R$ 10,00 aos complementos; restam R$ 80,00. O creme de leite saiu da despensa."
    )
    assert resposta["removido"] == compra.item_id
    estorno_do_evento = next(e for e in sessao.editavel.eventos() if e.acao is Acao.ESTORNO)
    extrato = {linha.id: linha for linha in sessao.dossie.extrato()}
    assert dj.texto_do_evento(estorno_do_evento, "Creme de leite", extrato) == (
        "A compra voltou para os complementos (R$ 10,00) e o item saiu da despensa."
    )


def test_receita_que_pede_o_mesmo_item_duas_vezes_soma_o_que_usa(sessao: Sessao) -> None:
    sessao.guardar(
        receita(
            "Frango em dois tempos",
            [
                ingrediente("300 g de frango", "frango", 300, "g"),
                ingrediente("200 g de peito de frango", "peito de frango", 200, "g"),
            ],
            rendimento_porcoes=2,
        )
    )
    (usada,) = dj.detalhe(sessao, "peito-de-frango")["receitas"]
    assert usada["usa_texto"] == "usa 500 g"


def test_campo_desconhecido_na_correcao_nao_vira_texto() -> None:
    assert dj._campo_texto("conteudo_informado", False, True, "") == ""
    assert dj._na_unidade("30", "un") == "30 unidades"
    assert dj._na_unidade("1", "un") == "1 unidade"
    assert dj._na_unidade("x", "balde 2kg") == "x"
    assert dj._na_unidade(None, "kg") == "nada"


def test_eventos_por_cursor(sessao: Sessao) -> None:
    from mise.erros import ErroDeUso

    for item_id in ("bacon", "sal", "alho"):
        sessao.editavel.acabou(item_id)
    pagina = dj.eventos_json(sessao, limite=2)
    assert [e["item_id"] for e in pagina["eventos"]] == ["alho", "sal"]
    assert pagina["proximo_cursor"] == "ev-0002"
    resto = dj.eventos_json(sessao, limite=2, cursor=pagina["proximo_cursor"])
    assert [e["item_id"] for e in resto["eventos"]] == ["bacon"]
    assert resto["proximo_cursor"] is None
    assert dj.eventos_json(sessao, cursor="2")["eventos"][0]["id"] == "ev-0001"
    with pytest.raises(ErroDeUso, match="cursor"):
        dj.eventos_json(sessao, cursor="depois")
