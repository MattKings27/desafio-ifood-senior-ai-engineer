"""O tempo por cozinhada: ela responde em horas, o portão conta em minutos.

A pergunta é "Quanto tempo a senhora consegue ficar cozinhando de uma vez, sem
se estressar ou cansar?", e a resposta natural é "duas horas" ou "uma hora e
meia". O dossiê continua guardando minutos (a conta do portão e os casos
dourados não mudam); o que muda é o que chega nela e o que ela escreve.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mise.erros import ErroDeUso
from mise.perfil import (
    FORMATOS_OPERACIONAIS,
    PERGUNTAS_OPERACIONAIS,
    TipoDeCampo,
    em_horas,
    horas_texto,
    minutos_das_horas,
    minutos_ditos,
)

TEMPO = "tempo_max_por_fornada_min"


def test_a_pergunta_fala_de_estresse_e_de_cansaco() -> None:
    assert PERGUNTAS_OPERACIONAIS[TEMPO] == (
        "Quanto tempo a senhora consegue ficar cozinhando de uma vez, sem se estressar ou cansar?"
    )


def test_o_formato_do_tempo_e_em_horas_e_guarda_minutos() -> None:
    formato = FORMATOS_OPERACIONAIS[TEMPO]
    assert formato.tipo is TipoDeCampo.HORAS
    assert formato.unidade == "horas"
    assert (formato.minimo, formato.maximo) == (30, 720)
    assert formato.faixa_em_horas() == (Decimal("0.50"), Decimal("12.00"))


@pytest.mark.parametrize(
    ("minutos", "texto"),
    [
        (30, "meia hora"),
        (45, "0,75 hora"),
        (60, "1 hora"),
        (61, "1 hora e 1 minuto"),
        (75, "1,25 hora"),
        (90, "1,5 hora"),
        (100, "1 hora e 40 minutos"),
        (120, "2 horas"),
        (150, "2,5 horas"),
        (40, "40 minutos"),
        (1, "1 minuto"),
        (720, "12 horas"),
    ],
)
def test_horas_texto_diz_como_ela_fala(minutos: int, texto: str) -> None:
    assert horas_texto(minutos) == texto


@pytest.mark.parametrize(
    ("minutos", "horas"),
    [(90, Decimal("1.50")), (100, Decimal("1.67")), (120, Decimal("2.00")), (5, Decimal("0.08"))],
)
def test_em_horas_com_duas_casas(minutos: int, horas: Decimal) -> None:
    assert em_horas(minutos) == horas


@pytest.mark.parametrize(
    ("horas", "minutos"),
    [(2, 120), (1.5, 90), (0.75, 45), (1.25, 75), (Decimal("1.33"), 80), (12, 720)],
)
def test_minutos_das_horas_arredonda_para_o_minuto(horas: object, minutos: int) -> None:
    assert minutos_das_horas(horas) == minutos


@pytest.mark.parametrize(
    ("dito", "minutos"),
    [
        ("2", 120),
        ("2 horas", 120),
        ("1,5 hora", 90),
        ("1.5h", 90),
        ("1h30", 90),
        ("1 h 30 min", 90),
        ("1 hora e meia", 90),
        ("1 hora e 20 minutos", 80),
        ("uma hora e 20 minutos", 80),
        ("meia hora", 30),
        ("duas horas", 120),
        ("Três horas", 180),
        ("3 hrs", 180),
        ("90 minutos", 90),
        ("40 min", 40),
    ],
)
def test_minutos_ditos_entende_o_jeito_dela(dito: str, minutos: int) -> None:
    assert minutos_ditos(dito) == minutos


@pytest.mark.parametrize("dito", ["talvez", "umas horas", "", "2 dias"])
def test_minutos_ditos_recusa_o_que_nao_entende(dito: str) -> None:
    with pytest.raises(ErroDeUso, match="diga em horas"):
        minutos_ditos(dito)


def test_fora_da_faixa_a_recusa_fala_em_horas() -> None:
    formato = FORMATOS_OPERACIONAIS[TEMPO]
    with pytest.raises(ErroDeUso, match="entre meia hora e 12 horas"):
        formato.no_limite(minutos_ditos("15 minutos"))
    with pytest.raises(ErroDeUso, match="entre meia hora e 12 horas"):
        formato.conferir(12.5)
