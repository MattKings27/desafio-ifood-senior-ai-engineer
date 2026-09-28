"""O tempo ativo de uma receita: a forma do resultado e os casos que não dependem dos passos."""

from __future__ import annotations

import pytest

from mise.tempo import MinutosAtivos, OrigemDoTempo


def test_pelos_passos_a_conta_vem_junto() -> None:
    tempo = MinutosAtivos(
        90, 240, OrigemDoTempo.PASSOS, "pelos passos, 40 + 50 = 90 minutos no fogo"
    )
    assert tempo.conhecido
    assert tempo.para_json() == {
        "ativos": 90,
        "passivos": 240,
        "origem": "passos",
        "derivacao": "pelos passos, 40 + 50 = 90 minutos no fogo",
    }


def test_sem_tempo_nos_passos_vale_o_da_receita_como_premissa() -> None:
    tempo = MinutosAtivos.pelo_tempo_declarado(45)
    assert (tempo.ativos, tempo.passivos, tempo.origem) == (45, 0, OrigemDoTempo.TEMPO_DECLARADO)
    assert "a receita declara 45 min" in tempo.derivacao


@pytest.mark.parametrize("minutos", [None, 0, -5])
def test_sem_tempo_nenhum_e_desconhecido(minutos: int | None) -> None:
    tempo = MinutosAtivos.pelo_tempo_declarado(minutos)
    assert tempo == MinutosAtivos.desconhecido()
    assert not tempo.conhecido
    assert tempo.para_json()["origem"] == "desconhecido"
    assert tempo.derivacao == "a receita não diz quanto tempo leva"


@pytest.mark.parametrize(
    ("ativos", "passivos", "origem"),
    [
        (-1, 0, OrigemDoTempo.PASSOS),
        (10, -1, OrigemDoTempo.PASSOS),
        (None, 0, OrigemDoTempo.PASSOS),
        (30, 0, OrigemDoTempo.DESCONHECIDO),
    ],
)
def test_tempo_sem_sentido_e_recusado(
    ativos: int | None, passivos: int, origem: OrigemDoTempo
) -> None:
    with pytest.raises(ValueError, match="tempo"):
        MinutosAtivos(ativos, passivos, origem)
