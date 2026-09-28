from __future__ import annotations

from decimal import Decimal

import pytest

from mise.dinheiro import Dinheiro
from mise.erros import QuantidadeInvalida
from mise.preco import (
    FOOD_COSTS_PADRAO,
    RETENCAO,
    TAXA_PLATAFORMA,
    Cenario,
    lucro_em,
    montar_cenarios,
    preco_minimo,
    preco_por_food_cost,
    preco_por_margem,
    preco_por_markup,
    sensibilidade,
)

CMV = Dinheiro.de("8.68")


def test_constantes_do_enunciado() -> None:
    assert TAXA_PLATAFORMA == Decimal("0.10")
    assert RETENCAO == Decimal("0.90")


def test_preco_minimo_do_enunciado() -> None:
    """`P >= CMV / 0,90`: 8,68 ÷ 0,90 = 9,6444..., e o mínimo sobe para 9,65.

    A R$ 9,64 ela receberia 0,90 × 9,64 = R$ 8,676, menos que os R$ 8,68 gastos.
    """
    assert montar_cenarios(CMV).preco_minimo == Dinheiro.de("9.65")
    assert lucro_em(Dinheiro.de("9.64"), CMV).valor < 0
    assert lucro_em(Dinheiro.de("9.65"), CMV).valor >= 0


def test_os_tres_cenarios_do_desafio() -> None:
    tabela = montar_cenarios(CMV)
    assert [c.nome for c in tabela] == ["Conservador", "Equilibrado", "Premium"]
    assert [str(c.preco) for c in tabela] == ["R$ 21,70", "R$ 24,80", "R$ 28,93"]


def test_tres_formulas_convergem_no_mesmo_ponto() -> None:
    """markup 1,0× == margem 45% == food cost 45%."""
    a = preco_por_markup(CMV, Decimal("1.0")).arredondado()
    b = preco_por_margem(CMV, Decimal("0.45")).arredondado()
    c = preco_por_food_cost(CMV, Decimal("0.45")).arredondado()
    assert a == b == c == Dinheiro.de("19.29")


def test_decomposicao_do_cenario() -> None:
    cenario = montar_cenarios(CMV).cenarios[1]
    assert cenario.preco == Dinheiro.de("24.80")
    assert cenario.valor_da_taxa.arredondado() == Dinheiro.de("2.48")
    assert cenario.recebe.arredondado() == Dinheiro.de("22.32")
    assert cenario.lucro.arredondado() == Dinheiro.de("13.64")
    assert round(cenario.food_cost, 2) == Decimal("0.35")
    assert round(cenario.multiplo_do_cmv, 1) == Decimal("2.9")
    assert not cenario.da_prejuizo


def test_explicacoes_sao_em_portugues_e_citam_os_numeros() -> None:
    tabela = montar_cenarios(CMV)
    texto_taxa = tabela.explicacao_da_taxa()
    assert "R$ 8,68" in texto_taxa
    assert "÷ 0,90" in texto_taxa, "a divisão tem que aparecer com vírgula decimal"
    assert "10%" in texto_taxa

    explicacao = tabela.cenarios[1].explicacao()
    for trecho in ("R$ 24,80", "R$ 2,48", "R$ 22,32", "R$ 13,64"):
        assert trecho in explicacao


def test_cenario_com_prejuizo_e_detectado() -> None:
    ruim = Cenario("Ruim", "abaixo do mínimo", Dinheiro.de("9.00"), CMV, TAXA_PLATAFORMA)
    assert ruim.da_prejuizo
    assert ruim.lucro.valor < 0


def test_propriedades_com_preco_zero_nao_explodem() -> None:
    vazio = Cenario("Zero", "", Dinheiro.zero(), CMV, TAXA_PLATAFORMA)
    assert vazio.food_cost == 0
    assert vazio.margem_sobre_preco == 0


def test_multiplo_com_cmv_zero_nao_explode() -> None:
    gratis = Cenario("Grátis", "", Dinheiro.de("10"), Dinheiro.zero(), TAXA_PLATAFORMA)
    assert gratis.multiplo_do_cmv == 0


def test_tabela_e_iteravel_e_tem_tamanho() -> None:
    tabela = montar_cenarios(CMV)
    assert len(tabela) == 3
    assert len(list(tabela)) == 3


def test_food_costs_padrao_cobrem_a_faixa_de_mercado() -> None:
    valores = [f for _, _, f in FOOD_COSTS_PADRAO]
    assert valores == sorted(valores, reverse=True), "do mais barato ao mais caro"
    assert all(Decimal("0.25") <= f <= Decimal("0.45") for f in valores)


# --------------------------------------------------------------------------- #
# Validações
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("taxa", [Decimal("-0.1"), Decimal("1"), Decimal("1.5")])
def test_taxa_fora_da_faixa(taxa: Decimal) -> None:
    with pytest.raises(QuantidadeInvalida, match="taxa"):
        preco_minimo(CMV, taxa)


@pytest.mark.parametrize("f", [Decimal("0"), Decimal("-0.1"), Decimal("1.5")])
def test_food_cost_fora_da_faixa(f: Decimal) -> None:
    with pytest.raises(QuantidadeInvalida, match="food cost"):
        preco_por_food_cost(CMV, f)


def test_markup_negativo() -> None:
    with pytest.raises(QuantidadeInvalida, match="markup"):
        preco_por_markup(CMV, Decimal("-0.5"))


@pytest.mark.parametrize("m", [Decimal("-0.1"), Decimal("0.90"), Decimal("0.95")])
def test_margem_fora_da_faixa(m: Decimal) -> None:
    """Margem de 90% é inalcançável com taxa de 10%: o teto é a retenção."""
    with pytest.raises(QuantidadeInvalida, match="margem"):
        preco_por_margem(CMV, m)


@pytest.mark.parametrize("cmv", [Dinheiro.zero(), Dinheiro.de("-1")])
def test_cenarios_exigem_cmv_positivo(cmv: Dinheiro) -> None:
    with pytest.raises(QuantidadeInvalida, match="CMV"):
        montar_cenarios(cmv)


def test_lucro_em_valida_taxa() -> None:
    with pytest.raises(QuantidadeInvalida):
        lucro_em(Dinheiro.de("10"), CMV, Decimal("2"))


# --------------------------------------------------------------------------- #
# Sensibilidade
# --------------------------------------------------------------------------- #


def test_sensibilidade_a_alta_de_insumo() -> None:
    s = sensibilidade(CMV, Dinheiro.de("24.80"))
    assert s["cmv_com_alta"] == Dinheiro.de("10.42")
    assert s["lucro_original"] == Dinheiro.de("13.64")
    assert s["lucro_com_alta"] == Dinheiro.de("11.90")
    assert s["ainda_lucrativo"] is True


def test_sensibilidade_detecta_margem_que_nao_aguenta() -> None:
    """Preço colado no mínimo não sobrevive a nenhuma alta."""
    s = sensibilidade(CMV, Dinheiro.de("9.70"), variacao=Decimal("0.20"))
    assert s["ainda_lucrativo"] is False


def test_folga_ate_zerar_o_lucro() -> None:
    s = sensibilidade(CMV, Dinheiro.de("24.80"))
    folga = s["folga_ate_zerar"]
    assert isinstance(folga, Decimal)
    assert Decimal("1.5") < folga < Decimal("1.6"), "≈ +157% de alta antes de zerar"


def test_sensibilidade_com_cmv_zero_nao_divide_por_zero() -> None:
    s = sensibilidade(Dinheiro.zero(), Dinheiro.de("10"))
    assert s["folga_ate_zerar"] == Decimal("0")


def test_sensibilidade_valida_taxa() -> None:
    with pytest.raises(QuantidadeInvalida):
        sensibilidade(CMV, Dinheiro.de("20"), taxa=Decimal("1.2"))
