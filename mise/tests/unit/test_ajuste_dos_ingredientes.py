"""Cada linha da receita diante da despensa: quanto pede, de onde sai e o que falta.

A conferência não deixa linha nenhuma sumir: a opcional que ela não tem fica
listada, a que não deu para ler vira pergunta, e a parte que ela tem sai do
estoque antes de a compra entrar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mise.compras import Comprado, Medida
from mise.despensa import Despensa, LinhaDaDespensa, montar_despensa
from mise.dinheiro import Dinheiro
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.unidades import Dimensao, Quantidade
from mise.viabilidade import (
    Avaliacao,
    Checagem,
    ChecagemDeIngredientes,
    Pergunta,
    SituacaoDoIngrediente,
    TipoRestricao,
    Veredito,
    checar_ingredientes,
)


def _despensa(*linhas: LinhaDaDespensa) -> Despensa:
    return montar_despensa(list(linhas))


def _linha(nome: str, estoque: str, unidade: str, preco: str | None = "10.00") -> LinhaDaDespensa:
    return LinhaDaDespensa(
        nome=nome,
        estoque=Decimal(estoque),
        unidade=unidade,
        quantidade_comprada=Decimal(1),
        preco_pago=Decimal(preco) if preco is not None else None,
    )


def _ajustes(checagem: Checagem) -> dict[str, object]:
    assert isinstance(checagem, ChecagemDeIngredientes)
    return {a.ingrediente.nome: a for a in checagem.ajustes}


def test_linha_vazia_nao_vira_ajuste_nem_pergunta(despensa: Despensa) -> None:
    r = receita("Arroz", [ing("1 kg de arroz", "arroz", 1, "kg"), ing("  ", "", entendida=False)])
    checagem, *_ = checar_ingredientes(r, despensa)
    assert isinstance(checagem, ChecagemDeIngredientes)
    assert [a.ingrediente.nome for a in checagem.ajustes] == ["arroz"]
    assert checagem.veredito is Veredito.APTO


def test_opcional_nao_entendido_nao_vira_pergunta(despensa: Despensa) -> None:
    r = receita("Arroz", [ing("salsinha picadinha", "salsinha", opcional=True, entendida=False)])
    checagem, _, _, a_gosto = checar_ingredientes(r, despensa)
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.OPCIONAL
    assert not checagem.perguntas and a_gosto == ()


def test_opcional_coberto_pelo_que_ela_comprou_entra_na_conta(despensa: Despensa) -> None:
    passas = ing("100 g de uva-passa", "uva-passa", 100, "g", opcional=True)
    comprado = Comprado(Medida(Quantidade(Decimal("0.2"), Dimensao.MASSA)), Dinheiro.de(8))
    checagem, usos, faltantes, _ = checar_ingredientes(
        receita("Farofa", [passas]), despensa, compras={"uva-passa": comprado}
    )
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.TEM
    assert ajuste.do_comprado == Quantidade(Decimal("0.1"), Dimensao.MASSA)
    assert not faltantes and usos[0].rotulo == "uva-passa (comprado)"


def test_comprado_cobre_parte_e_o_resto_e_compra(despensa: Despensa) -> None:
    passas = ing("300 g de uva-passa", "uva-passa", 300, "g")
    comprado = Comprado(Medida(Quantidade(Decimal("0.1"), Dimensao.MASSA)), Dinheiro.de(4))
    checagem, _, faltantes, _ = checar_ingredientes(
        receita("Farofa", [passas]), despensa, compras={"uva-passa": comprado}
    )
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.TEM_PARTE
    assert ajuste.falta == Medida(Quantidade(Decimal("0.2"), Dimensao.MASSA))
    assert faltantes[0].nome == "uva-passa"


def test_estoque_parcial_de_um_opcional_fica_de_fora_inteiro() -> None:
    despensa = _despensa(_linha("Queijo parmesão ralado", "0.05", "kg", "40.00"))
    queijo = ing("100 g de parmesão", "parmesão", 100, "g", opcional=True)
    checagem, usos, faltantes, _ = checar_ingredientes(receita("Massa", [queijo]), despensa)
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.OPCIONAL
    assert (usos, faltantes) == ((), ())


def test_o_que_acabou_e_compra_inteira() -> None:
    despensa = _despensa(_linha("Cebola", "0", "kg", "5.00"))
    checagem, usos, faltantes, _ = checar_ingredientes(
        receita("Sopa", [ing("1 kg de cebola", "cebola", 1, "kg")]), despensa
    )
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.FALTA
    assert ajuste.de_casa == Quantidade(Decimal(0), Dimensao.MASSA)
    assert usos == () and faltantes[0].origem_do_preco == "planilha"


def test_sem_o_preco_pago_o_estoque_entra_e_o_custo_nao_pergunta() -> None:
    despensa = _despensa(_linha("Coentro", "0.05", "kg", None))
    checagem, usos, faltantes, _ = checar_ingredientes(
        receita("Moqueca", [ing("100 g de coentro", "coentro", 100, "g")]), despensa
    )
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.TEM_PARTE
    # Sem o preço dela e sem referência, a receita fica de fora: ninguém pergunta.
    assert ajuste.pergunta is None
    assert not checagem.perguntas
    assert any(i.id == "sem_preco" for i in checagem.impedimentos)
    assert usos == ()
    assert faltantes[0].custo_estimado is None, "sem o preço pago não há como repor pela planilha"


@pytest.mark.parametrize(
    ("linha", "trecho"),
    [
        (ing("1 xícara de canela", "Canela em pó", 1, "ramo"), "não achei em fonte nenhuma"),
        (ing("1 punhado de arroz", "arroz", 1, "punhado"), "não achei em fonte nenhuma"),
    ],
)
def test_medida_que_nao_bate_com_o_item_nao_vira_pergunta(
    despensa: Despensa, linha: object, trecho: str
) -> None:
    checagem, *_ = checar_ingredientes(receita("Doce", [linha]), despensa)  # type: ignore[list-item]
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.TEM
    assert ajuste.pergunta is None
    assert trecho in ajuste.sem_dado
    assert checagem.veredito is Veredito.BLOQUEADO
    assert not checagem.perguntas


def test_medida_que_nao_bate_num_opcional_so_fica_listada(despensa: Despensa) -> None:
    opcional = ing("1 ramo de canela", "Canela em pó", 1, "ramo", opcional=True)
    checagem, *_ = checar_ingredientes(receita("Doce", [opcional]), despensa)
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.situacao is SituacaoDoIngrediente.OPCIONAL
    assert checagem.veredito is Veredito.APTO


def test_a_cozinha_sem_o_gosto_e_o_que_ficou_de_fora(despensa: Despensa) -> None:
    ingredientes = Checagem("ingredientes")
    gosto = Checagem("gosto")
    gosto.perguntar(Pergunta(TipoRestricao.GOSTO, "gosto", "Gosta?"))
    avaliacao = Avaliacao("Arroz", Veredito.FALTA_INFO, (ingredientes, gosto))
    assert avaliacao.veredito_da_cozinha is Veredito.APTO
    assert avaliacao.perguntas_da_cozinha == ()
    assert avaliacao.ajustes == () and avaliacao.opcionais_de_fora == ()
    assert Avaliacao("Nada", Veredito.APTO, ()).veredito_da_cozinha is Veredito.APTO
