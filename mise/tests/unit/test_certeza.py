"""A certeza antes do aceite: o que toda cozinha tem, confirmado por ela, numa pergunta só.

O portão deixa passar o que toda cozinha tem como suposto; o aceite e a compra
pedem que ela confirme o que a receita usa disso. Só o que a receita usa, uma
vez só, e pelas duas portas: a conversa e a tela.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mise import perfil_historico as historico
from mise.certeza import (
    NOTA_DA_GRADE,
    Acao,
    ItemSuposto,
    apoio_suposto,
    confirmacao_json,
    exigir_cozinha_confirmada,
    nota_da_grade,
    pergunta_de_confirmacao,
    pressupostos_da_cozinha,
    pressupostos_da_receita,
    tecnica_falada,
    texto_da_confirmacao,
)
from mise.dossie import Canal, Dossie
from mise.erros import (
    CozinhaNaoConfirmada,
    ErroDeUso,
    ViabilidadeNaoConfirmada,
    VocabularioDesconhecido,
)
from mise.mcp_server import ReceitaEntrada, Sessao, abrir_sessao, construir_servidor
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.perfil_historico import TipoDeItem
from mise.receita import Receita, receita
from mise.receita import ingrediente as ing
from mise.serializacao import _erro_json
from mise.taxonomia import EQUIPAMENTOS, TECNICAS
from mise.viabilidade import avaliar

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

ARROZ: dict[str, Any] = {
    "nome": "Arroz com frango",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 40,
    "modo_preparo": ["Refogue a cebola.", "Junte o frango e o arroz e cozinhe na panela."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}

COM_MILHO: dict[str, Any] = {
    **ARROZ,
    "nome": "Frango com milho",
    "ingredientes": [
        *ARROZ["ingredientes"],
        {"texto": "1 lata de milho", "nome": "milho verde", "quantidade": 1, "medida": "lata"},
    ],
}

PERGUNTA_DO_ARROZ = "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?"


def _batata() -> Receita:
    return receita(
        "Batata frita",
        [ing("1 kg de batata", "batata", 1, "kg")],
        modo_preparo=(
            "Descasque e corte a batata em palitos com a faca.",
            "Frite em óleo quente na panela funda até dourar.",
        ),
    )


def _bolo_de_liquidificador() -> Receita:
    """Não usa nada do que toda cozinha tem: liquidificador e forno, que o portão pergunta."""
    return receita(
        "Bolo de liquidificador",
        [ing("3 ovos", "ovos", 3, "ovo")],
        modo_preparo=("Bata tudo no liquidificador.", "Leve ao forno por 40 minutos."),
    )


def _cozinha_sem_o_basico() -> PerfilCozinha:
    """Tudo o que não é de toda cozinha respondido; o que toda cozinha tem, suposto."""
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e.id, Posse.TEM) for e in EQUIPAMENTOS if not e.pressuposto)
    perfil = perfil.com_tecnicas((t.id, Posse.TEM) for t in TECNICAS if not t.pressuposta)
    return perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)


# --------------------------------------------------------------------------- #
# O que a receita usa do suposto
# --------------------------------------------------------------------------- #


def test_so_o_que_a_receita_usa_e_na_ordem_da_pergunta() -> None:
    itens = pressupostos_da_receita(_batata(), PerfilCozinha.inicial())
    assert [(i.tipo, i.id) for i in itens] == [
        (TipoDeItem.EQUIPAMENTO, "fogao"),
        (TipoDeItem.EQUIPAMENTO, "panela_funda"),
        (TipoDeItem.EQUIPAMENTO, "faca"),
        (TipoDeItem.TECNICA, "fritar"),
    ]
    assert pergunta_de_confirmacao(itens) == (
        "Antes de aceitar, a senhora confirma que tem fogão, panela funda e faca e que sabe fritar?"
    )


def test_receita_que_nao_usa_o_basico_nao_pede_confirmacao() -> None:
    perfil = _cozinha_sem_o_basico()
    assert perfil.suposto("fogao"), "o fogão continua suposto"
    assert pressupostos_da_receita(_bolo_de_liquidificador(), perfil) == ()
    exigir_cozinha_confirmada(_bolo_de_liquidificador(), perfil, Acao.ACEITAR)


def test_o_que_ela_confirmou_nao_e_perguntado_de_novo() -> None:
    perfil = PerfilCozinha.inicial().com_equipamento("fogao", Posse.TEM)
    itens = pressupostos_da_receita(_batata(), perfil)
    assert [i.id for i in itens] == ["panela_funda", "faca", "fritar"]


def test_nao_tem_e_nao_sei_ficam_com_o_portao() -> None:
    """O "não tenho" bloqueia e o "não sei" pergunta: nenhum dos dois é suposto."""
    perfil = PerfilCozinha.inicial().com_equipamento("fogao", Posse.NAO_TEM).sem_resposta("faca")
    assert [i.id for i in pressupostos_da_receita(_batata(), perfil)] == ["panela_funda", "fritar"]


def test_o_substituto_suposto_e_o_que_se_confirma() -> None:
    """Frigideira antiaderente que ninguém perguntou passa pela frigideira, que é suposta."""
    omelete = receita(
        "Omelete",
        [ing("3 ovos", "ovos", 3, "ovo")],
        modo_preparo=("Bata os ovos.",),
        equipamentos=("frigideira_antiaderente",),
    )
    perfil = PerfilCozinha.inicial()
    assert apoio_suposto("frigideira_antiaderente", perfil) == "frigideira"
    assert [i.id for i in pressupostos_da_receita(omelete, perfil)] == ["frigideira"]
    confirmada = perfil.com_equipamento("frigideira_antiaderente", Posse.TEM)
    assert pressupostos_da_receita(omelete, confirmada) == ()


def test_o_substituto_confirmado_dispensa_o_suposto() -> None:
    """Com a batedeira dita, o batedor de arame suposto não precisa de confirmação."""
    mousse = receita(
        "Mousse",
        [ing("3 ovos", "ovos", 3, "ovo")],
        modo_preparo=("Bata as claras.",),
        equipamentos=("fouet",),
    )
    perfil = PerfilCozinha.inicial().com_equipamento("batedeira", Posse.TEM)
    assert apoio_suposto("fouet", perfil) is None
    assert pressupostos_da_receita(mousse, perfil) == ()


def test_toda_a_cozinha_suposta() -> None:
    perfil = PerfilCozinha.inicial()
    todos = pressupostos_da_cozinha(perfil)
    assert len(todos) == sum(e.pressuposto for e in EQUIPAMENTOS) + sum(
        t.pressuposta for t in TECNICAS
    )
    assert todos[0] == ItemSuposto(TipoDeItem.EQUIPAMENTO, "fogao", "Fogão")
    assert len(pressupostos_da_cozinha(perfil.com_tecnica("refogar", Posse.TEM))) == len(todos) - 1


# --------------------------------------------------------------------------- #
# A pergunta e a frase
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nome", "falado"),
    [
        ("Refogar", "refogar"),
        ("Cozinhar feijão", "cozinhar feijão"),
        ("Bolo caseiro", "fazer bolo caseiro"),
        ("Brigadeiro / doce de panela", "fazer brigadeiro ou doce de panela"),
    ],
)
def test_a_tecnica_no_meio_da_frase(nome: str, falado: str) -> None:
    assert tecnica_falada(nome) == falado


def test_a_pergunta_so_de_equipamento_so_de_tecnica_e_da_compra() -> None:
    fogao = ItemSuposto(TipoDeItem.EQUIPAMENTO, "fogao", "Fogão")
    panela = ItemSuposto(TipoDeItem.EQUIPAMENTO, "panela_funda", "Panela funda")
    refogar = ItemSuposto(TipoDeItem.TECNICA, "refogar", "Refogar")
    assert pergunta_de_confirmacao([fogao, panela, refogar]) == (
        "Antes de aceitar, a senhora confirma que tem fogão e panela funda e que sabe refogar?"
    )
    assert pergunta_de_confirmacao([fogao]) == "Antes de aceitar, a senhora confirma que tem fogão?"
    assert pergunta_de_confirmacao([refogar], Acao.COMPRAR) == (
        "Antes de comprar, a senhora confirma que sabe refogar?"
    )
    assert texto_da_confirmacao([fogao, refogar]) == "Anotei: a senhora tem fogão e sabe refogar."
    assert texto_da_confirmacao([]).startswith("Não havia nada para confirmar")


def test_a_recusa_traz_a_pergunta_os_itens_e_como_gravar() -> None:
    arroz = ReceitaEntrada(**ARROZ).para_dominio()
    with pytest.raises(CozinhaNaoConfirmada) as recusa:
        exigir_cozinha_confirmada(arroz, PerfilCozinha.inicial(), Acao.ACEITAR, receita_id="x")
    assert recusa.value.pergunta == PERGUNTA_DO_ARROZ
    assert recusa.value.itens == ("fogao", "refogar")
    assert recusa.value.receita_id == "x"
    erro = _erro_json(recusa.value)
    assert (erro["categoria"], erro["tipo"], erro["pergunta"]) == (
        "regra",
        "CozinhaNaoConfirmada",
        PERGUNTA_DO_ARROZ,
    )
    assert "registrar_resposta(tipo='cozinha'" in erro["orientacao"]
    assert erro["contexto"]["confirmar"] == "fogao, refogar"
    assert confirmacao_json(arroz, PerfilCozinha.inicial()) == {
        "pergunta": PERGUNTA_DO_ARROZ,
        "itens": [
            {"tipo": "equipamento", "id": "fogao", "nome": "Fogão"},
            {"tipo": "tecnica", "id": "refogar", "nome": "Refogar"},
        ],
    }


def test_as_outras_recusas_continuam_pedindo_para_nao_contornar() -> None:
    erro = _erro_json(ViabilidadeNaoConfirmada("Arroz", "FALTA INFO"))
    assert "pergunta" not in erro
    assert erro["orientacao"].startswith("Não contorne")


def test_a_nota_da_grade(despensa: Any) -> None:
    arroz = ReceitaEntrada(**ARROZ).para_dominio()
    suposto = _cozinha_sem_o_basico()
    dito = suposto.com_equipamento("fogao", Posse.TEM).com_tecnica("refogar", Posse.TEM)
    sem_fogao = suposto.com_equipamento("fogao", Posse.NAO_TEM)
    assert nota_da_grade(arroz, suposto, avaliar(arroz, suposto, despensa)) == NOTA_DA_GRADE
    assert nota_da_grade(arroz, dito, avaliar(arroz, dito, despensa)) is None
    assert nota_da_grade(arroz, sem_fogao, avaliar(arroz, sem_fogao, despensa)) is None


# --------------------------------------------------------------------------- #
# A gravação: de uma vez, com o histórico
# --------------------------------------------------------------------------- #


def test_confirmar_de_uma_vez_grava_cada_item_com_o_canal(tmp_path: Path) -> None:
    with Dossie(tmp_path / "d.db") as dossie:
        itens = [(TipoDeItem.EQUIPAMENTO, "fogao"), (TipoDeItem.TECNICA, "refogar")]
        mudancas = historico.confirmar_itens(dossie, itens, Canal.TELA)
        assert [m.mudou for m in mudancas] == [True, True]
        perfil = dossie.carregar_perfil()
        assert not perfil.suposto("fogao") and not perfil.suposto("refogar")
        eventos = historico.eventos(dossie)
        assert [(e.campo, e.canal, e.texto) for e in eventos] == [
            ("refogar", Canal.TELA, "a senhora disse que tem prática com refogar"),
            ("fogao", Canal.TELA, "a senhora disse que tem fogão"),
        ]
        # Confirmar de novo não enche o histórico.
        de_novo = historico.confirmar_itens(dossie, itens, Canal.CONVERSA)
        assert [m.mudou for m in de_novo] == [False, False]
        assert len(historico.eventos(dossie)) == 2


def test_confirmar_recusa_o_que_nao_se_confirma(tmp_path: Path) -> None:
    with Dossie(tmp_path / "d.db") as dossie:
        with pytest.raises(ErroDeUso, match="só equipamento e técnica"):
            historico.confirmar_itens(dossie, [(TipoDeItem.OPERACIONAL, "bocas_fogao")], "tela")
        with pytest.raises(VocabularioDesconhecido):
            historico.confirmar_itens(dossie, [(TipoDeItem.TECNICA, "levitar")], "tela")
        with pytest.raises(VocabularioDesconhecido):
            historico.confirmar_itens(dossie, [(TipoDeItem.EQUIPAMENTO, "teletransporte")], "tela")
        assert historico.eventos(dossie) == ()


# --------------------------------------------------------------------------- #
# A sessão: o aceite, a compra e a confirmação pelas duas portas
# --------------------------------------------------------------------------- #


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    sessao = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    sessao.dossie.salvar_perfil(_cozinha_sem_o_basico())
    for prato in ("Arroz com frango", "Frango com milho", "Bolo de liquidificador"):
        sessao.dossie.registrar_gosto(prato, Gosto.GOSTA)
    return sessao


@pytest.fixture
def servidor(sessao: Sessao) -> Any:
    return construir_servidor(sessao)


async def chamar(servidor: Any, ferramenta: str, **argumentos: Any) -> dict[str, Any]:
    resultado = await servidor.call_tool(ferramenta, argumentos)
    return json.loads(resultado.content[0].text)


async def test_aceite_recusado_ate_ela_confirmar_e_liberado_depois(
    servidor: Any, sessao: Sessao
) -> None:
    avaliada = await chamar(servidor, "avaliar_receita", receita=ARROZ)
    assert avaliada["veredito"] == "APTO", "o portão continua dizendo que dá"
    assert avaliada["pode_aceitar"] is False
    assert avaliada["confirmar_a_cozinha"]["pergunta"] == PERGUNTA_DO_ARROZ
    assert avaliada["falta_para_aceitar"] == [
        "Confirmar que a senhora tem fogão e que sabe refogar."
    ]

    recusa = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    assert (recusa["categoria"], recusa["tipo"], recusa["pergunta"]) == (
        "regra",
        "CozinhaNaoConfirmada",
        PERGUNTA_DO_ARROZ,
    )
    assert recusa["contexto"]["receita_id"] == avaliada["receita_id"]
    assert sessao.dossie.cardapio == ()

    sim = await chamar(
        servidor,
        "registrar_resposta",
        tipo="cozinha",
        campo=avaliada["receita_id"],
        resposta="tenho sim",
    )
    assert sim["confirmados"] == ["Fogão", "Refogar"]
    assert sim["texto"] == "Anotei: a senhora tem fogão e sabe refogar."
    assert (await chamar(servidor, "avaliar_receita", receita_id=avaliada["receita_id"]))[
        "pode_aceitar"
    ]

    aceite = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    assert aceite["preco"] == "R$ 12,00"
    assert sessao.dossie.cardapio == ("Arroz com frango",)
    eventos = historico.eventos(sessao.dossie)
    assert {(e.campo, e.canal) for e in eventos} == {
        ("fogao", Canal.CONVERSA),
        ("refogar", Canal.CONVERSA),
    }


async def test_receita_que_nao_usa_o_basico_aceita_sem_perguntar(servidor: Any) -> None:
    bolo = {
        "nome": "Bolo de liquidificador",
        "rendimento_porcoes": 8,
        "tempo_cozimento_min": 40,
        "modo_preparo": ["Bata tudo no liquidificador.", "Leve ao forno por 40 minutos."],
        "ingredientes": [{"texto": "3 ovos", "nome": "ovos", "quantidade": 3, "medida": "ovo"}],
    }
    avaliada = await chamar(servidor, "avaliar_receita", receita=bolo)
    assert (avaliada["pode_aceitar"], avaliada["confirmar_a_cozinha"]) == (True, None)
    aceite = await chamar(
        servidor, "registrar_decisao", prato="Bolo de liquidificador", decisao="aceito", preco=20.0
    )
    assert "erro" not in aceite


async def test_o_portao_vem_antes_da_confirmacao(servidor: Any, sessao: Sessao) -> None:
    """Prato que ainda não dá recusa pelo motivo dele; a cozinha é a última pergunta."""
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.DESCONHECIDO)
    await chamar(servidor, "avaliar_receita", receita=ARROZ)
    recusa = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    assert recusa["tipo"] == "ViabilidadeNaoConfirmada"


async def test_compra_recusada_ate_ela_confirmar(servidor: Any, sessao: Sessao) -> None:
    await chamar(
        servidor,
        "registrar_preco_mercado",
        ingrediente="milho verde",
        valor=6.0,
        quantidade=1,
        unidade="lata",
    )
    avaliada = await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    comprar = {
        "prato": "Frango com milho",
        "ingrediente": "milho verde",
        "quantidade": 1,
        "unidade": "lata",
        "valor": 6.0,
    }
    recusa = await chamar(servidor, "registrar_compra", **comprar)
    assert recusa["tipo"] == "CozinhaNaoConfirmada"
    assert recusa["pergunta"].startswith("Antes de comprar, a senhora confirma que tem fogão")
    assert sessao.dossie.orcamento().gasto.valor == 0

    await chamar(
        servidor, "registrar_resposta", tipo="cozinha", campo="toda_cozinha", resposta="sim"
    )
    assert pressupostos_da_cozinha(sessao.perfil) == ()
    comprado = await chamar(servidor, "registrar_compra", **comprar)
    assert comprado["registrado"] is True
    assert avaliada["receita_id"]


async def test_so_o_sim_se_grava_de_uma_vez(servidor: Any, sessao: Sessao) -> None:
    await chamar(servidor, "avaliar_receita", receita=ARROZ)
    for resposta in ("nao_tem", "não sei"):
        d = await chamar(
            servidor,
            "registrar_resposta",
            tipo="cozinha",
            campo="Arroz com frango",
            resposta=resposta,
        )
        assert d["categoria"] == "uso", resposta
        assert "item por item" in d["erro"]
    # O nome do prato também serve, como no aceite.
    d = await chamar(
        servidor, "registrar_resposta", tipo="cozinha", campo="Arroz com frango", resposta="tem"
    )
    assert d["confirmados"] == ["Fogão", "Refogar"]
    ausente = await chamar(
        servidor, "registrar_resposta", tipo="cozinha", campo="lasanha", resposta="tem"
    )
    assert ausente["categoria"] == "uso"


def test_confirmar_pela_tela_item_por_item(sessao: Sessao) -> None:
    confirmados = sessao.confirmar_a_cozinha(
        itens=[("tecnica", "refogar"), ("equipamento", "faca")], canal=Canal.TELA
    )
    assert [i.nome for i in confirmados] == ["Refogar", "Faca"]
    perfil = sessao.perfil
    assert not perfil.suposto("refogar") and not perfil.suposto("faca")
    assert perfil.suposto("fogao")
    for tipo in ("operacional", "gosto"):
        with pytest.raises(ErroDeUso, match="só equipamento e técnica"):
            sessao.confirmar_a_cozinha(itens=[(tipo, "bocas_fogao")])
