"""A avaliação dela: a conta da pontuação e as estrelas e notas gravadas por receita."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mise.avaliacoes import (
    CATEGORIAS,
    NA_TELA,
    PESOS,
    TAMANHO_DAS_NOTAS,
    Avaliacoes,
    conferir_estrelas,
    pontuar,
    sem_estrelas,
)
from mise.dossie import Dossie
from mise.erros import ErroDeUso

TODAS = {"sabor": 4, "facilidade": 5, "tempo": 4, "entrega": 5, "apelo": 4}


def test_os_pesos_somam_um_e_cada_categoria_tem_nome_na_tela() -> None:
    assert sum(PESOS.values()) == Decimal(1)
    assert set(PESOS) == set(CATEGORIAS) == set(NA_TELA)


def test_a_conta_do_contrato() -> None:
    """Sabor 4, facilidade 5, tempo 4, entrega 5, apelo 4 e ela gosta: 87,8."""
    pontuacao = pontuar(TODAS, gosta=True)
    assert pontuacao is not None
    assert (pontuacao.valor, pontuacao.texto) == (Decimal("87.8"), "87,8")
    assert pontuacao.derivacao == (
        "Estrelas: sabor 4 (peso 0,30), apelo de venda 4 (0,25), aguenta a entrega 5 (0,20), "
        "facilidade 5 (0,15), tempo 4 (0,10), dão 0,8375 de 1; a senhora gosta de fazer, que "
        "vale 1; pontuação = 100 × (0,75 × 0,8375 + 0,25 × 1) = 87,8"
    )


@pytest.mark.parametrize(
    ("gosta", "valor", "frase"),
    [
        (True, Decimal("100.0"), "gosta de fazer, que vale 1"),
        (None, Decimal("87.5"), "ainda não disse se gosta de fazer, que vale 0,5"),
        (False, Decimal("75.0"), "não gosta de fazer, que vale 0"),
    ],
)
def test_o_gosto_entra_a_parte(gosta: bool | None, valor: Decimal, frase: str) -> None:
    pontuacao = pontuar({"sabor": 5}, gosta)
    assert pontuacao is not None
    assert pontuacao.valor == valor
    assert frase in pontuacao.derivacao
    assert "(contam só as que a senhora deu)" in pontuacao.derivacao


def test_so_as_estrelas_dadas_contam_e_a_nota_inexata_diz_cerca_de() -> None:
    pontuacao = pontuar({"sabor": 2, "facilidade": 1, "apelo": None}, None)
    assert pontuacao is not None
    assert pontuacao.valor == Decimal("25.0")
    assert "dão cerca de 0,1667 de 1" in pontuacao.derivacao
    assert pontuacao.texto == "25,0"


def test_sem_estrela_nao_ha_pontuacao() -> None:
    assert pontuar({}, True) is None
    assert pontuar(dict.fromkeys(CATEGORIAS), True) is None


@pytest.mark.parametrize(
    ("estrelas", "mensagem"),
    [
        ({"cheiro": 4}, "categoria"),
        ({"sabor": 6}, "vai de 1 a 5"),
        ({"sabor": 0}, "vai de 1 a 5"),
        ({"sabor": True}, "inteiro"),
        ({"sabor": 4.5}, "inteiro"),
    ],
)
def test_estrela_fora_da_regra_e_recusada(estrelas: dict[str, object], mensagem: str) -> None:
    with pytest.raises(ErroDeUso, match=mensagem):
        conferir_estrelas(estrelas)


def test_grava_so_o_que_mudou_e_null_apaga(tmp_path: Path) -> None:
    with Dossie(tmp_path / "dossie.db") as dossie:
        avaliacoes = Avaliacoes(dossie)
        assert avaliacoes.obter("arroz") == sem_estrelas("arroz")
        assert not avaliacoes.obter("arroz").avaliada
        primeira = avaliacoes.gravar("arroz", estrelas={"sabor": 4, "apelo": 3}, notas=" oi ")
        assert primeira.estrelas["sabor"] == 4 and primeira.notas == "oi"
        assert primeira.avaliada and primeira.atualizada_em is not None
        depois = avaliacoes.gravar("arroz", estrelas={"apelo": None})
        assert (depois.estrelas["sabor"], depois.estrelas["apelo"], depois.notas) == (4, None, "oi")
        apagou = avaliacoes.gravar("arroz", notas="")
        assert apagou.notas == "" and apagou.estrelas["sabor"] == 4
        assert set(avaliacoes.todas()) == {"arroz"}
        with pytest.raises(ErroDeUso, match="até"):
            avaliacoes.gravar("arroz", notas="x" * (TAMANHO_DAS_NOTAS + 1))
