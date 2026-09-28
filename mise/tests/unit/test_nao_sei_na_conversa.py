""" "Não sei" pela conversa: o portão volta a perguntar, e o agente sabe que ela respondeu."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mise import perfil_historico
from mise.dossie import Canal
from mise.mcp_server import Sessao, abrir_sessao, construir_servidor
from mise.perfil import Gosto, Posse
from mise.perfil_historico import TipoDeItem

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

FRANGO_ASSADO: dict[str, Any] = {
    "nome": "Frango assado",
    "rendimento_porcoes": 4,
    "modo_preparo": ["Tempere o frango.", "Leve ao forno a 200 °C por 40 minutos."],
    "ingredientes": [
        {
            "texto": "500 g de peito de frango",
            "nome": "peito de frango",
            "quantidade": 500,
            "medida": "g",
        },
    ],
}


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    return abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")


@pytest.fixture
def servidor(sessao: Sessao) -> Any:
    return construir_servidor(sessao)


async def chamar(servidor: Any, ferramenta: str, **argumentos: Any) -> dict[str, Any]:
    resultado = await servidor.call_tool(ferramenta, argumentos)
    return json.loads(resultado.content[0].text)


def _campos(avaliacao: dict[str, Any]) -> set[str]:
    return {p["campo"] for p in avaliacao["perguntas"]}


async def _com_uma_hora_por_cozinhada(servidor: Any) -> None:
    """Os 40 min de forno cabem na hora dela: o forno fica sendo a única pergunta."""
    await chamar(
        servidor,
        "registrar_resposta",
        tipo="operacional",
        campo="tempo_max_por_fornada_min",
        resposta="1 hora",
    )


async def test_nao_sei_faz_o_portao_perguntar_de_novo(servidor: Any, sessao: Sessao) -> None:
    await chamar(servidor, "registrar_gosto", prato="Frango assado", gosta=True)
    await _com_uma_hora_por_cozinhada(servidor)
    antes = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    assert "forno" in _campos(antes)

    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    com_forno = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    assert "forno" not in _campos(com_forno)
    assert com_forno["veredito"] == "APTO"

    d = await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="não sei"
    )
    assert (d["registrado"], d["nao_sei"]) == (True, True)
    assert d["impacto"]["pendentes"] == ["Frango assado"]
    assert sessao.perfil.tem_equipamento("forno") is Posse.DESCONHECIDO
    assert "forno" not in sessao.perfil.confirmados

    de_novo = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    assert de_novo["veredito"] == "FALTA INFO"
    assert "forno" in _campos(de_novo), "não sei não é não tem: o portão pergunta de novo"
    assert not de_novo["impedimentos"]


@pytest.mark.parametrize("resposta", ["não sei", "nao_sei", "Não sei.", "sei lá", "NÃO SEI NÃO"])
async def test_formas_de_dizer_nao_sei(servidor: Any, sessao: Sessao, resposta: str) -> None:
    await chamar(servidor, "registrar_resposta", tipo="tecnica", campo="bechamel", resposta="sim")
    d = await chamar(
        servidor, "registrar_resposta", tipo="tecnica", campo="bechamel", resposta=resposta
    )
    assert d["nao_sei"] is True
    assert sessao.perfil.domina_tecnica("bechamel") is Posse.DESCONHECIDO


async def test_nao_sei_de_restricao_volta_a_perguntar(servidor: Any, sessao: Sessao) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="operacional", campo="bocas_fogao", resposta="4"
    )
    await chamar(
        servidor, "registrar_resposta", tipo="operacional", campo="tem_gas_sobrando", resposta="sim"
    )
    for campo in ("bocas_fogao", "tem_gas_sobrando"):
        d = await chamar(
            servidor, "registrar_resposta", tipo="operacional", campo=campo, resposta="não sei"
        )
        assert d["nao_sei"] is True
        assert getattr(sessao.perfil.restricoes, campo) is None


async def test_nao_sei_do_gosto_volta_a_perguntar(servidor: Any, sessao: Sessao) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="gosto", campo="Frango assado", resposta="gosta"
    )
    d = await chamar(
        servidor, "registrar_resposta", tipo="gosto", campo="Frango assado", resposta="não sei"
    )
    assert "desconhecido" in d["registrado"]
    opiniao = sessao.dossie.gosto_por("Frango assado")
    assert opiniao is not None
    assert opiniao.gosto is Gosto.DESCONHECIDO
    avaliacao = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    assert "gosto" in _campos(avaliacao)


@pytest.mark.parametrize("resposta", ["nan", "inf", "-inf"])
async def test_numero_que_nao_e_numero_e_recusado(
    servidor: Any, sessao: Sessao, resposta: str
) -> None:
    d = await chamar(
        servidor, "registrar_resposta", tipo="operacional", campo="bocas_fogao", resposta=resposta
    )
    assert d["categoria"] == "uso"
    assert sessao.perfil.restricoes.bocas_fogao is None


async def test_resposta_da_conversa_fica_no_historico_com_o_canal(
    servidor: Any, sessao: Sessao
) -> None:
    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    (evento,) = perfil_historico.eventos(sessao.dossie)
    assert (evento.tipo, evento.campo, evento.canal) == (
        TipoDeItem.EQUIPAMENTO,
        "forno",
        Canal.CONVERSA,
    )


async def test_resposta_traz_o_impacto_nas_receitas(servidor: Any) -> None:
    await chamar(servidor, "registrar_gosto", prato="Frango assado", gosta=True)
    await _com_uma_hora_por_cozinhada(servidor)
    await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    d = await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="sim"
    )
    assert d["impacto"] == {
        "liberadas": ["Frango assado"],
        "bloqueadas": [],
        "pendentes": [],
        "texto": "Com forno, Frango assado passa a dar.",
    }
    repetida = await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="sim"
    )
    assert repetida["impacto"]["texto"] == "Isso já estava anotado assim; nada muda nas receitas."


async def test_consultar_perfil_mostra_o_que_ela_nao_sabe(servidor: Any) -> None:
    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="não sei"
    )
    d = await chamar(servidor, "consultar_perfil")
    assert d["ela_disse_que_nao_sabe"] == ["a senhora disse que não sabe se tem forno"]
    assert "Forno" not in d["ela_confirmou"]["tem"]


async def test_proxima_pergunta_avisa_que_ela_ja_disse_nao_sei(servidor: Any) -> None:
    await chamar(servidor, "registrar_gosto", prato="Frango assado", gosta=True)
    await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    d = await chamar(servidor, "proxima_pergunta")
    assert (d["campo"], d["ela_disse_que_nao_sabe"]) == ("forno", False)

    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="não sei"
    )
    d = await chamar(servidor, "proxima_pergunta")
    assert (d["campo"], d["ela_disse_que_nao_sabe"]) == ("forno", True)


async def test_proxima_pergunta_de_gosto_nao_tem_historico(servidor: Any) -> None:
    await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    d = await chamar(servidor, "proxima_pergunta")
    # O campo do gosto é o prato: é por ele que registrar_resposta grava o gosto.
    assert (d["tipo"], d["campo"], d["ela_disse_que_nao_sabe"]) == (
        "gosto",
        "Frango assado",
        False,
    )


# --------------------------------------------------------------------------- #
# avaliar_receita ganha o passo a passo
# --------------------------------------------------------------------------- #


async def test_avaliar_receita_traz_o_passo_a_passo(servidor: Any) -> None:
    d = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    assert d["exige"] == {"equipamentos": ["Forno"], "tecnicas": []}
    um, dois = d["por_passo"]["passos"]
    assert um["requisitos"] == []
    (forno,) = dois["requisitos"]
    assert (forno["id"], forno["estado"], forno["trecho"]) == ("forno", "desconhecido", "forno")
    assert [lim["texto"] for lim in dois["limites"]] == ["forno a 200 °C", "40 min no forno"]
    assert d["por_passo"]["requisitos_da_receita"] == []
    pergunta_do_forno = next(p for p in d["perguntas"] if p["campo"] == "forno")
    assert [o["rotulo"] for o in pergunta_do_forno["opcoes"]] == ["Tenho", "Não tenho", "Não sei"]
    assert pergunta_do_forno["passos"] == [2]
    assert "orientacao" in d, "sem viabilidade confirmada, a orientação continua"


async def test_o_passo_a_passo_nao_muda_o_veredito(servidor: Any, sessao: Sessao) -> None:
    """O parecer da ferramenta é o mesmo do portão: veredito, impedimentos e perguntas."""
    d = await chamar(servidor, "avaliar_receita", receita=FRANGO_ASSADO)
    receita = sessao.dossie.candidata("Frango assado")
    assert receita is not None
    avaliacao = sessao.avaliar(receita)
    assert d["veredito"] == avaliacao.veredito.rotulo
    assert [(p["campo"], p["texto"]) for p in d["perguntas"]] == [
        (p.campo, p.texto) for p in avaliacao.perguntas
    ]


@pytest.mark.parametrize(
    ("campo", "resposta"),
    [("bocas_fogao", "0"), ("bocas_fogao", "80"), ("tempo_max_por_fornada_min", "13 horas")],
)
async def test_numero_fora_da_faixa_volta_para_perguntar_de_novo(
    servidor: Any, sessao: Sessao, campo: str, resposta: str
) -> None:
    """A mesma faixa da tela: "0 bocas" bloquearia toda receita de duas panelas."""
    d = await chamar(
        servidor, "registrar_resposta", tipo="operacional", campo=campo, resposta=resposta
    )
    assert d["categoria"] == "uso"
    assert "entre" in d["erro"]
    assert getattr(sessao.perfil.restricoes, campo) is None
    assert perfil_historico.eventos(sessao.dossie) == ()
