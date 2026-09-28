"""Os três tempos que a receita declara ficam separados: preparo, cozimento e total."""

from __future__ import annotations

import pytest

from mise.erros import QuantidadeInvalida
from mise.passos import ENTRADAS_DA_RECEITA, como_responder, quais_passos
from mise.receita import Receita, receita
from mise.receita import ingrediente as ing
from mise.viabilidade import Pergunta, TipoRestricao


def _com(**tempos: int | None) -> Receita:
    return receita("Bolo", [ing("3 ovos", "ovos", 3, "ovo")], **tempos)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("tempos", "declarado"),
    [
        ({"tempo_total_min": 60, "tempo_preparo_min": 20, "tempo_cozimento_min": 30}, 60),
        ({"tempo_preparo_min": 20, "tempo_cozimento_min": 40}, 60),
        ({"tempo_cozimento_min": 40}, 40),
        ({"tempo_preparo_min": 20}, 20),
        ({}, None),
    ],
)
def test_tempo_para_mostrar(tempos: dict[str, int], declarado: int | None) -> None:
    """O cartão mostra o total; sem ele, preparo mais cozimento, senão o que vier."""
    assert _com(**tempos).tempo_declarado_min == declarado


@pytest.mark.parametrize(
    ("campo", "rotulo"),
    [
        ("tempo_preparo_min", "tempo de preparo"),
        ("tempo_cozimento_min", "tempo de cozimento"),
        ("tempo_total_min", "tempo total"),
    ],
)
def test_tempo_negativo_e_recusado(campo: str, rotulo: str) -> None:
    with pytest.raises(QuantidadeInvalida, match=rotulo):
        _com(**{campo: -5})


def test_os_tempos_vao_e_voltam_do_dossie() -> None:
    r = _com(tempo_preparo_min=20, tempo_cozimento_min=40, tempo_total_min=70)
    dados = r.para_dict()
    assert (dados["tempo_cozimento_min"], dados["tempo_total_min"]) == (40, 70)
    assert Receita.de_dict(dados) == r


def test_receita_guardada_antes_dos_tempos_separados_ainda_abre() -> None:
    dados = _com(tempo_preparo_min=20).para_dict()
    del dados["tempo_cozimento_min"], dados["tempo_total_min"]
    volta = Receita.de_dict(dados)
    assert (volta.tempo_preparo_min, volta.tempo_cozimento_min, volta.tempo_total_min) == (
        20,
        None,
        None,
    )


def test_por_porcao_guarda_os_tempos() -> None:
    r = receita(
        "Bolo",
        [ing("3 ovos", "ovos", 3, "ovo")],
        rendimento_porcoes=6,
        tempo_preparo_min=20,
        tempo_cozimento_min=40,
        tempo_total_min=60,
    )
    uma = r.por_porcao()
    assert (uma.tempo_preparo_min, uma.tempo_cozimento_min, uma.tempo_total_min) == (20, 40, 60)


# --------------------------------------------------------------------------- #
# A pergunta do tempo da receita e as citações de passo
# --------------------------------------------------------------------------- #


def test_pergunta_do_tempo_da_receita_vem_com_a_faixa_em_minutos() -> None:
    pergunta = Pergunta(TipoRestricao.OPERACIONAL, "tempo_cozimento_min", "Quanto tempo?")
    opcoes, entrada = como_responder(pergunta)
    assert opcoes == []
    assert entrada == {"tipo": "inteiro", "unidade": "minutos", "min": 1, "max": 1440}
    assert entrada is not ENTRADAS_DA_RECEITA["tempo_cozimento_min"], "cópia, não o original"


@pytest.mark.parametrize(
    ("ordens", "com_artigo", "sem_artigo"),
    [
        ((2,), "o passo 2", "passo 2"),
        ((2, 4), "os passos 2 e 4", "passos 2 e 4"),
        ((1, 3, 5), "os passos 1, 3 e 5", "passos 1, 3 e 5"),
    ],
)
def test_quais_passos(ordens: tuple[int, ...], com_artigo: str, sem_artigo: str) -> None:
    assert quais_passos(ordens) == com_artigo
    assert quais_passos(ordens, artigo=False) == sem_artigo
