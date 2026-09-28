"""Invariantes de precificação, verificadas por property-based testing.

Um golden test prova que *um* caso está certo. Estas provas dizem que a
identidade vale para qualquer CMV e qualquer taxa, inclusive nos valores que
eu não pensei em testar. Como estas fórmulas decidem quanto a Dona Maria cobra,
a diferença importa.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mise.dinheiro import Dinheiro
from mise.preco import (
    RETENCAO,
    TAXA_PLATAFORMA,
    lucro_em,
    montar_cenarios,
    preco_minimo,
    preco_por_food_cost,
    preco_por_margem,
    preco_por_markup,
)

TOLERANCIA = Decimal("0.0000000001")

cmvs = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("5000"), places=2, allow_nan=False
).map(Dinheiro)

taxas = st.decimals(min_value=Decimal("0"), max_value=Decimal("0.85"), places=4)

food_costs = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1"), places=4)


@given(cmv=cmvs, taxa=taxas)
def test_preco_minimo_tem_lucro_exatamente_zero(cmv: Dinheiro, taxa: Decimal) -> None:
    """A definição de ponto de equilíbrio: nem ganha, nem perde."""
    assert abs(lucro_em(preco_minimo(cmv, taxa), cmv, taxa).valor) < TOLERANCIA


@given(cmv=cmvs, food_cost=food_costs, taxa=taxas)
def test_identidade_do_lucro(cmv: Dinheiro, food_cost: Decimal, taxa: Decimal) -> None:
    """`L = CMV · (1 − taxa − f) / f` para qualquer combinação."""
    preco = preco_por_food_cost(cmv, food_cost, taxa)
    esperado = cmv.valor * (Decimal("1") - taxa - food_cost) / food_cost
    assert abs(lucro_em(preco, cmv, taxa).valor - esperado) < TOLERANCIA


@given(cmv=cmvs, food_cost=food_costs, taxa=taxas)
def test_prejuizo_exatamente_quando_food_cost_passa_da_retencao(
    cmv: Dinheiro, food_cost: Decimal, taxa: Decimal
) -> None:
    """O limiar de prejuízo é `f > 1 − taxa`, e não `f > 1`.

    É o erro mental mais caro do delivery: achar que vender acima do custo basta.
    """
    retencao = Decimal("1") - taxa
    lucro = lucro_em(preco_por_food_cost(cmv, food_cost, taxa), cmv, taxa)
    if food_cost > retencao:
        assert lucro.valor < 0
    elif food_cost < retencao:
        assert lucro.valor > 0


@given(
    cmv=cmvs,
    f1=food_costs,
    f2=food_costs,
    taxa=taxas,
)
def test_preco_cai_quando_food_cost_sobe(
    cmv: Dinheiro, f1: Decimal, f2: Decimal, taxa: Decimal
) -> None:
    """Monotonicidade: aceitar food cost maior só pode baratear o prato."""
    assume(f1 < f2)
    assert preco_por_food_cost(cmv, f1, taxa).valor > preco_por_food_cost(cmv, f2, taxa).valor


@given(cmv=cmvs, markup=st.decimals(min_value=Decimal("0"), max_value=Decimal("20"), places=3))
def test_markup_entrega_o_lucro_pedido(cmv: Dinheiro, markup: Decimal) -> None:
    """Pedir markup de `k` produz lucro de exatamente `k × CMV`."""
    lucro = lucro_em(preco_por_markup(cmv, markup), cmv)
    assert abs(lucro.valor - markup * cmv.valor) < TOLERANCIA


@given(
    cmv=cmvs,
    margem=st.decimals(min_value=Decimal("0"), max_value=Decimal("0.89"), places=4),
)
def test_margem_entrega_a_fracao_pedida(cmv: Dinheiro, margem: Decimal) -> None:
    """Pedir margem de `m` produz lucro de exatamente `m × preço`."""
    preco = preco_por_margem(cmv, margem)
    assert abs(lucro_em(preco, cmv).valor - margem * preco.valor) < TOLERANCIA


@given(cmv=cmvs, food_cost=food_costs, taxa=taxas)
def test_ida_e_volta_do_food_cost(cmv: Dinheiro, food_cost: Decimal, taxa: Decimal) -> None:
    """Calcular o preço a partir de `f` e reextrair `f` devolve o mesmo `f`."""
    preco = preco_por_food_cost(cmv, food_cost, taxa)
    assert abs(cmv.valor / preco.valor - food_cost) < TOLERANCIA


@given(
    cmv=cmvs,
    p1=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), places=2),
    delta=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000"), places=2),
    taxa=taxas,
)
def test_lucro_cresce_com_o_preco(
    cmv: Dinheiro, p1: Decimal, delta: Decimal, taxa: Decimal
) -> None:
    """Preço maior, mantendo custo e taxa, nunca reduz o lucro."""
    assume(taxa < 1)
    menor = lucro_em(Dinheiro(p1), cmv, taxa)
    maior = lucro_em(Dinheiro(p1 + delta), cmv, taxa)
    assert maior.valor > menor.valor


@given(cmv=cmvs)
@settings(max_examples=60)
def test_cenarios_sao_ordenados_e_lucrativos(cmv: Dinheiro) -> None:
    """Os três cenários oferecidos crescem em preço e nenhum dá prejuízo."""
    tabela = montar_cenarios(cmv)
    precos = [c.preco.valor for c in tabela]

    assert len(tabela) == 3
    assert precos == sorted(precos), "cenários fora de ordem confundem a decisão"
    for cenario in tabela:
        assert not cenario.da_prejuizo
        assert cenario.preco.valor >= tabela.preco_minimo.valor
        assert cenario.recebe.valor > cenario.cmv.valor


@given(cmv=cmvs)
def test_a_taxa_sai_do_preco_e_nao_do_lucro(cmv: Dinheiro) -> None:
    """Decomposição contábil: preço = taxa + CMV + lucro, sem sobra nem falta."""
    for cenario in montar_cenarios(cmv):
        recomposto = cenario.valor_da_taxa + cenario.cmv + cenario.lucro
        assert abs(recomposto.valor - cenario.preco.valor) < TOLERANCIA


@given(cmv=cmvs)
def test_retencao_e_o_complemento_da_taxa(cmv: Dinheiro) -> None:
    """Sanidade do enunciado: com taxa de 10%, ela recebe 0,90·P."""
    assert RETENCAO == Decimal("1") - TAXA_PLATAFORMA
    tabela = montar_cenarios(cmv)
    for cenario in tabela:
        assert abs(cenario.recebe.valor - cenario.preco.valor * RETENCAO) < TOLERANCIA


#: Custo antes do arredondamento: soma de linhas com frações de centavo.
cmvs_brutos = st.decimals(
    min_value=Decimal("0.0001"), max_value=Decimal("5000"), places=4, allow_nan=False
).map(Dinheiro)


@given(cmv=cmvs_brutos, taxa=taxas)
def test_o_minimo_exibido_nunca_da_prejuizo(cmv: Dinheiro, taxa: Decimal) -> None:
    """O número que a tela chama de "mínimo sem prejuízo" cumpre o que diz.

    E é o menor que cumpre: um centavo abaixo já perde dinheiro. Com o
    arredondamento meio-para-cima, a primeira metade falhava em 45% dos custos.
    """
    tabela = montar_cenarios(cmv, taxa)
    assert lucro_em(tabela.preco_minimo, cmv, taxa).valor >= 0
    um_centavo_abaixo = tabela.preco_minimo - Dinheiro.de("0.01")
    assert lucro_em(um_centavo_abaixo, cmv, taxa).valor < 0


@given(
    custos=st.lists(
        st.decimals(min_value=Decimal("0"), max_value=Decimal("300"), places=6), min_size=1
    ),
    porcoes=st.integers(min_value=1, max_value=40),
)
def test_as_linhas_exibidas_somam_o_total_exibido(custos: list[Decimal], porcoes: int) -> None:
    """Quem soma as linhas na tela chega ao total da tela, ao centavo."""
    from mise.cmv import CMV, LinhaCMV

    linhas = tuple(
        LinhaCMV(f"i{n}", "1 un", Dinheiro(c / porcoes), "d", Decimal(0))
        for n, c in enumerate(custos)
    )
    total = sum((linha.custo for linha in linhas), Dinheiro.zero())
    cmv = CMV("x", linhas, total, Decimal(0), (), porcoes)
    exibidos = cmv.custos_exibidos()

    assert sum((e for e in exibidos), Dinheiro.zero()) == cmv.para_precificar
    for linha, exibido in zip(linhas, exibidos, strict=True):
        assert abs(exibido.valor - linha.custo.valor) < Decimal("0.01")
