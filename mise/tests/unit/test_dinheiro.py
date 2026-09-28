from __future__ import annotations

from decimal import Decimal

import pytest

from mise.dinheiro import CENTAVO, Dinheiro, soma
from mise.erros import QuantidadeInvalida


def test_construcao_a_partir_de_float_nao_herda_ruido_binario() -> None:
    assert Dinheiro.de(0.1).valor == Decimal("0.1")
    assert Dinheiro.de(0.1) + Dinheiro.de(0.2) == Dinheiro.de("0.3")


def test_construcao_de_varios_tipos() -> None:
    assert Dinheiro.de(10) == Dinheiro.de("10") == Dinheiro.de(Decimal("10"))
    assert Dinheiro.zero() == Dinheiro.de(0)


def test_coercao_de_nao_decimal_no_construtor() -> None:
    assert Dinheiro(Decimal("5")).valor == Decimal("5")


@pytest.mark.parametrize("ruim", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_rejeita_valores_nao_finitos(ruim: Decimal) -> None:
    with pytest.raises(QuantidadeInvalida):
        Dinheiro(ruim)


def test_aritmetica() -> None:
    a, b = Dinheiro.de("10.50"), Dinheiro.de("4.25")
    assert a + b == Dinheiro.de("14.75")
    assert a - b == Dinheiro.de("6.25")
    assert a * 2 == Dinheiro.de("21.00")
    assert 2 * a == Dinheiro.de("21.00")
    assert a / 2 == Dinheiro.de("5.25")
    assert -a == Dinheiro.de("-10.50")


def test_divisao_por_zero_e_barrada() -> None:
    with pytest.raises(QuantidadeInvalida):
        Dinheiro.de("10") / 0


def test_valor_negativo_e_permitido() -> None:
    """Prejuízo é um resultado legítimo: precisa ser representável."""
    assert (Dinheiro.de("5") - Dinheiro.de("8")).valor < 0


def test_booleano_segue_o_valor() -> None:
    assert not Dinheiro.zero()
    assert Dinheiro.de("0.01")


def test_ordenacao() -> None:
    assert Dinheiro.de("1") < Dinheiro.de("2")
    assert sorted([Dinheiro.de("3"), Dinheiro.de("1")]) == [Dinheiro.de("1"), Dinheiro.de("3")]


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("0", "R$ 0,00"),
        ("1", "R$ 1,00"),
        ("10.5", "R$ 10,50"),
        ("1234.56", "R$ 1.234,56"),
        ("1234567.89", "R$ 1.234.567,89"),
        ("-42.10", "-R$ 42,10"),
        ("0.005", "R$ 0,01"),
    ],
)
def test_formatacao_pt_br(valor: str, esperado: str) -> None:
    assert str(Dinheiro.de(valor)) == esperado


def test_repr_mostra_o_decimal_cru() -> None:
    assert repr(Dinheiro.de("1.5")) == "Dinheiro(1.5)"


def test_arredondamento_meio_para_cima() -> None:
    assert Dinheiro.de("1.005").arredondado() == Dinheiro.de("1.01")
    assert Dinheiro.de("1.004").arredondado() == Dinheiro.de("1.00")


def test_centavos_inteiros() -> None:
    assert Dinheiro.de("12.34").centavos == 1234
    assert Dinheiro.de("0.1").centavos == 10


def test_soma_de_iteravel() -> None:
    assert soma([Dinheiro.de("1"), Dinheiro.de("2"), Dinheiro.de("3")]) == Dinheiro.de("6")
    assert soma([]) == Dinheiro.zero()


def test_centavo_e_a_menor_unidade() -> None:
    assert CENTAVO == Decimal("0.01")
