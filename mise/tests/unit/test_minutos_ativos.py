"""O tempo ativo: o que a receita deixa o fogo, o forno ou um aparelho ligado."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mise.passos import (
    EQUIPAMENTOS_SEM_FOGO,
    TECNICAS_SEM_FOGO,
    minutos_ativos,
    minutos_no_fogo,
    onde_corre,
)
from mise.receita import Receita, receita
from mise.receita import ingrediente as ing
from mise.taxonomia import EQUIPAMENTOS_POR_ID, TECNICAS_POR_ID
from mise.tempo import MinutosAtivos, OrigemDoTempo


def _prato(*passos: str, **extras: int) -> Receita:
    return receita("Prato", [ing("1 kg de arroz", "arroz", 1, "kg")], modo_preparo=passos, **extras)


# --------------------------------------------------------------------------- #
# minutos_ativos
# --------------------------------------------------------------------------- #


def test_soma_os_passos_com_fogo_e_aparelho_ligados() -> None:
    ativos = minutos_ativos(
        _prato(
            "Cozinhe o feijão na panela de pressão por 40 minutos.",
            "Junte as carnes e cozinhe em fogo baixo por 50 minutos.",
        )
    )
    assert ativos == MinutosAtivos(
        90, 0, OrigemDoTempo.PASSOS, "pelos passos, 40 + 50 = 90 minutos no fogo"
    )
    assert ativos.conhecido


def test_um_passo_so_diz_qual_passo() -> None:
    ativos = minutos_ativos(_prato("Tempere.", "Asse no forno por 90 minutos."))
    assert ativos.derivacao == "pelo passo 2, são 90 minutos no forno"


def test_dois_tempos_no_mesmo_passo_somam_no_passo() -> None:
    ativos = minutos_ativos(
        _prato(
            "Cozinhe por 10 minutos, junte o molho e cozinhe por mais 5 minutos.",
            "Sirva quente.",
        )
    )
    assert (ativos.ativos, ativos.derivacao) == (15, "pelo passo 1, são 15 minutos no fogo")


def test_as_esperas_nao_contam_e_ficam_a_parte() -> None:
    """Marinar, descansar e gelar não são fogo: vão para `passivos`, fora da conta."""
    ativos = minutos_ativos(
        _prato(
            "Tempere o frango e deixe marinar por 12 horas na geladeira.",
            "Deixe a massa descansar por 30 minutos.",
            "Leve à geladeira de um dia para o outro.",
            "Asse no forno por 40 minutos.",
        )
    )
    assert ativos == MinutosAtivos(
        40, 12 * 60 + 30, OrigemDoTempo.PASSOS, "pelo passo 4, são 40 minutos no forno"
    )


def test_faixa_conta_pelo_maior() -> None:
    assert minutos_ativos(_prato("Asse por 30 a 40 minutos.")).ativos == 40


def test_sem_tempo_nos_passos_vale_o_cozimento_declarado() -> None:
    ativos = minutos_ativos(
        _prato("Cozinhe em fogo baixo até desmanchar.", tempo_cozimento_min=180)
    )
    assert ativos == MinutosAtivos.pelo_tempo_declarado(180)
    assert (ativos.ativos, ativos.origem) == (180, OrigemDoTempo.TEMPO_DECLARADO)


def test_os_passos_valem_mais_que_o_cozimento_declarado() -> None:
    ativos = minutos_ativos(_prato("Asse por 40 minutos.", tempo_cozimento_min=60))
    assert (ativos.ativos, ativos.origem) == (40, OrigemDoTempo.PASSOS)


def test_preparo_e_total_declarados_nao_sao_tempo_de_fogo() -> None:
    ativos = minutos_ativos(_prato("Cozinhe o arroz.", tempo_preparo_min=20, tempo_total_min=60))
    assert ativos == MinutosAtivos.desconhecido()
    assert not ativos.conhecido


def test_cozimento_zero_nao_e_tempo() -> None:
    """Zero declarado é campo vazio, não receita instantânea (`pelo_tempo_declarado`)."""
    assert minutos_ativos(_prato("Cozinhe o arroz.", tempo_cozimento_min=0)) == (
        MinutosAtivos.desconhecido()
    )


def test_sem_passos_e_sem_cozimento_o_tempo_e_desconhecido() -> None:
    assert minutos_ativos(_prato()).origem is OrigemDoTempo.DESCONHECIDO


def test_receita_que_nao_acende_fogo_tem_tempo_ativo_zero() -> None:
    """Misturar e gelar não liga nada: zero, e isso também é tempo dos passos."""
    ativos = minutos_ativos(
        _prato("Misture o creme com o leite condensado.", "Leve à geladeira por 4 horas.")
    )
    assert ativos == MinutosAtivos(
        0, 240, OrigemDoTempo.PASSOS, "pelos passos, nada vai ao fogo nem liga aparelho"
    )


@pytest.mark.parametrize(
    "passos",
    [
        # o verbo de fogo, sem tempo
        ("Refogue a cebola.",),
        # o aparelho que não esquenta, sem tempo
        ("Bata no liquidificador.",),
        # o verbo de calor que serve a vários aparelhos
        ("Derreta o chocolate.",),
    ],
)
def test_passo_que_liga_algo_sem_tempo_fica_desconhecido(passos: tuple[str, ...]) -> None:
    assert minutos_ativos(_prato(*passos)).origem is OrigemDoTempo.DESCONHECIDO


def test_equipamento_ou_tecnica_de_fogo_sem_passo_que_diga_fica_desconhecido() -> None:
    """O nome pede forno ("assado") mesmo sem passo nenhum acender nada."""
    assado = receita(
        "Frango assado", [ing("1 kg de frango", "frango", 1, "kg")], modo_preparo=["Tempere."]
    )
    assert "forno" in assado.equipamentos
    assert minutos_ativos(assado).origem is OrigemDoTempo.DESCONHECIDO

    com_tecnica = replace(_prato("Tempere."), tecnicas=frozenset({"ponto_carne"}))
    assert minutos_ativos(com_tecnica).origem is OrigemDoTempo.DESCONHECIDO


def test_o_que_nao_acende_fogo_existe_na_taxonomia() -> None:
    assert set(EQUIPAMENTOS_SEM_FOGO) <= set(EQUIPAMENTOS_POR_ID)
    assert set(TECNICAS_SEM_FOGO) <= set(TECNICAS_POR_ID)


# --------------------------------------------------------------------------- #
# minutos_no_fogo
# --------------------------------------------------------------------------- #


def test_no_fogo_conta_so_o_fogao() -> None:
    receita_mista = _prato(
        "Refogue a cebola na panela por 10 minutos.",
        "Asse no forno por 40 minutos.",
        "Bata no liquidificador por 3 minutos.",
    )
    assert minutos_no_fogo(receita_mista) == 10


def test_no_forno_so_nao_gasta_o_botijao_do_fogao() -> None:
    assert minutos_no_fogo(_prato("Asse no forno por 90 minutos.")) == 0


def test_cozimento_declarado_conta_como_fogo_quando_vai_ao_fogao() -> None:
    assert minutos_no_fogo(_prato("Cozinhe em fogo baixo.", tempo_cozimento_min=120)) == 120


def test_cozimento_declarado_sem_fogao_nao_e_tempo_de_fogo() -> None:
    assert minutos_no_fogo(_prato("Leve ao forno.", tempo_cozimento_min=120)) is None


def test_sem_tempo_nenhum_nao_da_para_saber_o_fogo() -> None:
    assert minutos_no_fogo(_prato("Cozinhe em fogo baixo.")) is None


# --------------------------------------------------------------------------- #
# onde_corre
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("passos", "onde"),
    [
        (("Cozinhe em fogo baixo por 20 minutos.",), "no fogo"),
        (("Asse no forno por 40 minutos.",), "no forno"),
        (("Leve ao forno elétrico por 30 minutos.",), "no forno"),
        (("Frite na air fryer por 15 minutos.",), "na air fryer"),
        (
            ("Cozinhe em fogo baixo por 20 minutos.", "Asse no forno por 40 minutos."),
            "no fogo e no forno",
        ),
        (
            ("Cozinhe em fogo baixo por 20 minutos.", "Bata no liquidificador por 3 minutos."),
            "com o fogo ou o aparelho ligado",
        ),
        (("Bata no liquidificador por 3 minutos.",), "com o fogo ou o aparelho ligado"),
        (("Reserve por 10 minutos.",), "com o fogo ou o aparelho ligado"),
        (("Cozinhe em fogo baixo.",), "no fogo ou no forno"),
    ],
)
def test_onde_o_tempo_corre(passos: tuple[str, ...], onde: str) -> None:
    assert onde_corre(_prato(*passos)) == onde


# --------------------------------------------------------------------------- #
# Passo que liga algo e não diz o tempo
# --------------------------------------------------------------------------- #


def test_passo_sem_tempo_faz_da_soma_so_um_minimo() -> None:
    ativos = minutos_ativos(
        _prato("Cozinhe o feijão até ficar macio.", "Refogue o alho por 3 minutos.")
    )
    assert ativos == MinutosAtivos(
        None,
        0,
        OrigemDoTempo.DESCONHECIDO,
        "pelos passos, pelo menos 3 minutos no fogo, e o passo 1 não diz o tempo",
    )


def test_passo_sem_tempo_com_cozimento_declarado_vale_o_declarado() -> None:
    ativos = minutos_ativos(
        _prato(
            "Cozinhe o feijão até ficar macio.",
            "Refogue o alho por 3 minutos.",
            tempo_cozimento_min=180,
        )
    )
    assert ativos == MinutosAtivos(
        180,
        0,
        OrigemDoTempo.TEMPO_DECLARADO,
        "os passos dizem 3 minutos, e o passo 1 não diz o tempo; a receita declara 180 "
        "minutos de cozimento, e a conta usa esse número",
    )


def test_cozimento_declarado_menor_que_os_passos_nao_vale() -> None:
    """Se só o que os passos dizem já passa do declarado, o declarado está errado."""
    ativos = minutos_ativos(
        _prato(
            "Cozinhe o feijão até ficar macio.",
            "Asse no forno por 90 minutos.",
            "Doure a cebola.",
            tempo_cozimento_min=30,
        )
    )
    assert ativos.origem is OrigemDoTempo.DESCONHECIDO
    assert ativos.derivacao.endswith("e os passos 1 e 3 não dizem o tempo")


def test_referencia_ao_passo_seguinte_nao_liga_nada() -> None:
    """ "30 minutos antes de assar" espera; quem liga o forno é o passo de assar."""
    ativos = minutos_ativos(
        _prato(
            "Retire a carne da geladeira 30 minutos antes de assar.",
            "Asse no forno por 40 minutos.",
        )
    )
    assert ativos == MinutosAtivos(
        40, 30, OrigemDoTempo.PASSOS, "pelo passo 2, são 40 minutos no forno"
    )


def test_minimo_sem_passo_com_tempo_e_zero() -> None:
    from mise.passos import minimo_pelos_passos

    assert minimo_pelos_passos(_prato("Cozinhe o arroz."), panelas_juntas=True) == (0, "")


def test_panelas_juntas_so_com_todo_tempo_dito() -> None:
    from mise.passos import minutos_com_panelas_juntas

    juntas = _prato(
        "Cozinhe o arroz por 35 minutos.", "Em outra panela, cozinhe o feijão por 30 minutos."
    )
    assert minutos_com_panelas_juntas(juntas) == 35
    faltando = _prato("Cozinhe o arroz.", "Em outra panela, cozinhe o feijão por 30 minutos.")
    assert minutos_com_panelas_juntas(faltando) is None
    assert minutos_com_panelas_juntas(_prato("Cozinhe o arroz por 20 minutos.")) is None


def test_no_fogo_com_passo_sem_tempo_e_o_minimo_dito() -> None:
    """Sem o tempo inteiro, o fogão que os passos dizem já é um mínimo de gás."""
    assert (
        minutos_no_fogo(_prato("Cozinhe o feijão por 70 minutos.", "Asse o pão até dourar.")) == 70
    )
