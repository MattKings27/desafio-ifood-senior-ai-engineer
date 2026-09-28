from __future__ import annotations

from decimal import Decimal

import pytest

from mise.erros import (
    DensidadeDesconhecida,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
    UnidadesIncompativeis,
)
from mise.unidades import (
    DENSIDADES,
    Dimensao,
    Quantidade,
    converter_medida,
    converter_medida_para_volume,
    interpretar_unidade_compra,
)

# --------------------------------------------------------------------------- #
# Quantidade
# --------------------------------------------------------------------------- #


def test_quantidade_e_imutavel() -> None:
    q = Quantidade(Decimal("1"), Dimensao.MASSA)
    with pytest.raises(AttributeError):
        q.valor = Decimal("2")  # type: ignore[misc]


def test_quantidade_coage_nao_decimal() -> None:
    assert Quantidade(Decimal("1.5"), Dimensao.MASSA).valor == Decimal("1.5")


@pytest.mark.parametrize("ruim", [Decimal("NaN"), Decimal("Infinity")])
def test_quantidade_rejeita_nao_finito(ruim: Decimal) -> None:
    with pytest.raises(QuantidadeInvalida):
        Quantidade(ruim, Dimensao.MASSA)


def test_quantidade_rejeita_negativo() -> None:
    with pytest.raises(QuantidadeInvalida):
        Quantidade(Decimal("-1"), Dimensao.MASSA)


def test_aritmetica_na_mesma_dimensao() -> None:
    a = Quantidade(Decimal("2"), Dimensao.MASSA)
    b = Quantidade(Decimal("0.5"), Dimensao.MASSA)
    assert (a + b).valor == Decimal("2.5")
    assert (a - b).valor == Decimal("1.5")
    assert (a * 3).valor == Decimal("6")
    assert (a / 2).valor == Decimal("1")


@pytest.mark.parametrize("op", ["add", "sub", "lt", "le"])
def test_dimensoes_diferentes_sao_barradas(op: str) -> None:
    massa = Quantidade(Decimal("1"), Dimensao.MASSA)
    volume = Quantidade(Decimal("1"), Dimensao.VOLUME)
    with pytest.raises(UnidadesIncompativeis):
        getattr(massa, f"__{op}__")(volume)


def test_comparacao_na_mesma_dimensao() -> None:
    a = Quantidade(Decimal("1"), Dimensao.MASSA)
    b = Quantidade(Decimal("2"), Dimensao.MASSA)
    assert a < b
    assert a <= b
    assert not b < a


def test_divisao_por_zero() -> None:
    with pytest.raises(QuantidadeInvalida):
        Quantidade(Decimal("1"), Dimensao.MASSA) / 0


def test_str_da_quantidade() -> None:
    assert str(Quantidade(Decimal("2.000"), Dimensao.MASSA)) == "2 kg"
    # Como se escreve no Brasil: é o texto que ela lê na conta.
    assert str(Quantidade(Decimal("0.5"), Dimensao.VOLUME)) == "0,5 L"


# --------------------------------------------------------------------------- #
# Unidades de compra
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("rotulo", "dimensao", "conteudo"),
    [
        ("kg", Dimensao.MASSA, "1"),
        ("KG", Dimensao.MASSA, "1"),
        ("L", Dimensao.VOLUME, "1"),
        ("l", Dimensao.VOLUME, "1"),
        ("g", Dimensao.MASSA, "0.001"),
        ("ml", Dimensao.VOLUME, "0.001"),
        ("balde 2kg", Dimensao.MASSA, "2"),
        ("un 500g", Dimensao.MASSA, "0.5"),
        ("un 400g", Dimensao.MASSA, "0.4"),
        ("un 500ml", Dimensao.VOLUME, "0.5"),
        ("un 100ml", Dimensao.VOLUME, "0.1"),
        ("pacote 1,5kg", Dimensao.MASSA, "1.5"),
        ("caixa 12 ml", Dimensao.VOLUME, "0.012"),
    ],
)
def test_interpreta_unidades(rotulo: str, dimensao: Dimensao, conteudo: str) -> None:
    u = interpretar_unidade_compra(rotulo)
    assert u.dimensao is dimensao
    assert u.conteudo_por_embalagem is not None
    assert u.conteudo_por_embalagem.valor == Decimal(conteudo)
    assert not u.opaca
    assert u.derivacao


@pytest.mark.parametrize("rotulo", ["un", "und", "unid", "unidade", "peça", "peca", "dúzia", "pc"])
def test_contagem_pura_e_opaca(rotulo: str) -> None:
    u = interpretar_unidade_compra(rotulo)
    assert u.opaca
    assert u.dimensao is Dimensao.CONTAGEM
    assert u.conteudo_por_embalagem is None


@pytest.mark.parametrize("rotulo", ["", "   ", "caixa", "saco", "xyz"])
def test_rotulo_desconhecido_e_barrado(rotulo: str) -> None:
    with pytest.raises(UnidadeNaoNormalizavel):
        interpretar_unidade_compra(rotulo)


def test_embalagem_com_zero_e_barrada() -> None:
    with pytest.raises(QuantidadeInvalida):
        interpretar_unidade_compra("balde 0kg")


def test_preserva_o_rotulo_original() -> None:
    assert interpretar_unidade_compra("  Balde 2KG  ").rotulo_original == "Balde 2KG"


# --------------------------------------------------------------------------- #
# Medidas culinárias
# --------------------------------------------------------------------------- #


def test_xicara_de_farinha_usa_densidade_e_nao_volume() -> None:
    """O erro de +89%: 1 xícara de farinha é 127 g, não 240 g."""
    c = converter_medida(1, "xicara", "farinha de trigo")
    assert c.quantidade.valor == Decimal("0.1272")
    assert c.quantidade.dimensao is Dimensao.MASSA
    assert "0,53 g/ml" in c.derivacao


@pytest.mark.parametrize(
    ("quantidade", "medida", "escrita"),
    [
        (1, "xicara", "1 xícara = 240 ml"),
        (2, "xicara", "2 xícaras = 480 ml"),
        ("1.5", "colher de sopa", "1,5 colher de sopa = 22,5 ml"),
        (2, "colher de cha", "2 colheres de chá = 10 ml"),
        (3, "colher", "3 colheres = 45 ml"),
    ],
)
def test_a_conta_escreve_a_medida_como_ela_escreve(quantidade, medida, escrita) -> None:
    """Com acento e no plural a partir de dois: "2 xicara" na tela parecia defeito."""
    assert converter_medida_para_volume(Decimal(str(quantidade)), medida).derivacao == escrita


def test_acentuacao_e_ignorada() -> None:
    a = converter_medida(1, "xícara", "açúcar")
    b = converter_medida(1, "xicara", "acucar")
    assert a.quantidade.valor == b.quantidade.valor


@pytest.mark.parametrize(
    ("medida", "gramas"),
    [("g", "1"), ("grama", "1"), ("gramas", "1"), ("kg", "1000"), ("quilo", "1000")],
)
def test_massa_direta_nao_tem_incerteza(medida: str, gramas: str) -> None:
    c = converter_medida(1, medida, "qualquer coisa")
    assert c.quantidade.valor == Decimal(gramas) / 1000
    assert c.incerteza_relativa == 0
    assert c.confiavel


@pytest.mark.parametrize(
    ("valor", "medida", "ingrediente", "gramas"),
    [
        (2, "ovo", "ovos", "90"),
        (3, "dente de alho", "alho", "13.2"),
        (1, "cebola", "cebola", "70"),
        (2, "tomate medio", "tomate", "200"),
        (1, "", "peito de frango", "180"),
        (1, "", "pimentão verde", "55"),
    ],
)
def test_itens_contados_usam_o_peso_da_tabela_do_ibge(
    valor: int, medida: str, ingrediente: str, gramas: str
) -> None:
    c = converter_medida(valor, medida, ingrediente)
    assert c.quantidade.valor == Decimal(gramas) / 1000
    assert not c.confiavel, "medida caseira é estimativa e precisa carregar incerteza"
    assert c.referencia is not None
    assert c.referencia.trecho.split(" | ")[8] == str(c.referencia.gramas)
    assert "pela referência de medidas do IBGE" in c.derivacao


def test_peso_unitario_encontrado_pelo_ingrediente() -> None:
    """Quando a medida é genérica, o nome do ingrediente resolve."""
    assert converter_medida(2, "unidade", "ovo").quantidade.valor == Decimal("0.09")


@pytest.mark.parametrize(
    ("valor", "medida", "ingrediente", "gramas"),
    [
        (2, "colher de sopa", "margarina", "64"),
        (2, "colheres de sopa", "extrato de tomate", "40"),
        (1, "colher de sobremesa", "alcaparras", "13"),
        (3, "colher de sopa", "leite condensado", "45"),
        (1, "colher de chá", "pimenta-do-reino", "1.5"),
    ],
)
def test_medida_caseira_da_tabela_do_ibge(
    valor: int, medida: str, ingrediente: str, gramas: str
) -> None:
    c = converter_medida(valor, medida.replace("colheres", "colher"), ingrediente)
    assert c.quantidade.valor == Decimal(gramas) / 1000
    assert c.referencia is not None


@pytest.mark.parametrize(
    ("medida", "ingrediente"),
    [
        ("", "tomate cereja"),
        ("colher de sopa", "trufa branca"),
    ],
)
def test_sem_linha_na_tabela_nao_ha_peso(medida: str, ingrediente: str) -> None:
    """Sem fonte nem classe, o peso não se inventa: a conversão falha, e ninguém pergunta."""
    with pytest.raises((DensidadeDesconhecida, UnidadeNaoNormalizavel)):
        converter_medida(1, medida, ingrediente)


def test_volume_sem_densidade_conhecida_e_barrado() -> None:
    with pytest.raises(DensidadeDesconhecida):
        converter_medida(1, "xicara", "bacalhau desfiado")


def test_densidade_escolhe_o_nome_mais_especifico() -> None:
    """'queijo parmesao ralado' (0,40) deve vencer um casamento parcial."""
    c = converter_medida(1, "xicara", "queijo parmesao ralado")
    assert c.quantidade.valor == Decimal("240") * Decimal("0.40") / 1000


def test_medida_desconhecida_e_barrada() -> None:
    with pytest.raises(UnidadeNaoNormalizavel):
        converter_medida(1, "punhado", "arroz")


def test_valor_negativo_e_barrado() -> None:
    with pytest.raises(QuantidadeInvalida):
        converter_medida(-1, "g", "sal")


def test_conversao_escala_linearmente() -> None:
    um = converter_medida(1, "xicara", "acucar").quantidade.valor
    tres = converter_medida(3, "xicara", "acucar").quantidade.valor
    assert tres == um * 3


def test_pitada_e_minuscula_mas_existe() -> None:
    """'sal a gosto' vira pitada: custo desprezível, mas declarado."""
    c = converter_medida(1, "pitada", "sal")
    assert c.quantidade.valor > 0
    assert c.quantidade.valor < Decimal("0.001")


# --------------------------------------------------------------------------- #
# Volume mantido como volume
# --------------------------------------------------------------------------- #


def test_volume_puro_nao_precisa_de_densidade() -> None:
    """Óleo é custado por litro: converter para massa seria imprecisão gratuita."""
    c = converter_medida_para_volume(2, "colher de sopa")
    assert c.quantidade.dimensao is Dimensao.VOLUME
    assert c.quantidade.valor == Decimal("0.03")


def test_volume_puro_rejeita_medida_desconhecida() -> None:
    with pytest.raises(UnidadeNaoNormalizavel):
        converter_medida_para_volume(1, "punhado")


def test_tabela_de_densidades_e_plausivel() -> None:
    """Nenhuma densidade alimentar fora de uma faixa fisicamente razoável."""
    for nome, (densidade, incerteza) in DENSIDADES.items():
        assert Decimal("0.3") <= densidade <= Decimal("1.3"), nome
        assert Decimal("0") < incerteza <= Decimal("0.2"), nome
