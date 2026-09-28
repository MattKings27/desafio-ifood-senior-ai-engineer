"""As prateleiras da despensa: a da planilha é fixa, a de um item novo sai do nome."""

from __future__ import annotations

import pytest

from mise import categorias


def test_toda_categoria_da_planilha_existe() -> None:
    assert set(categorias.DA_PLANILHA.values()) <= set(categorias.POR_ID)
    assert len(categorias.DA_PLANILHA) == 37


def test_categorias_na_ordem_da_tela_e_com_outros_por_ultimo() -> None:
    ids = [c.id for c in categorias.CATEGORIAS]
    assert ids[:2] == ["proteinas", "graos"]
    assert ids[-1] == "outros"
    assert categorias.categoria("proteinas").rotulo == "Carnes e ovos"
    assert categorias.categoria("nao-existe") is categorias.OUTROS


@pytest.mark.parametrize(
    ("nome", "esperada"),
    [
        ("Creme de leite", "laticinios"),
        ("Leite condensado", "confeitaria"),
        ("Milho verde em lata", "conservas"),
        ("Farinha de rosca", "graos"),
        ("Linguiça calabresa", "proteinas"),
        ("Cebolinha", "hortifruti"),
        ("Pimenta-do-reino", "temperos"),
        ("Azeite", "oleos"),
        ("Sal grosso", "temperos"),
        ("Salsinha", "hortifruti"),
        ("Trufa branca", "outros"),
        ("", "outros"),
    ],
)
def test_categoria_de_item_novo_sai_da_palavra_mais_especifica(nome: str, esperada: str) -> None:
    assert categorias.pelo_nome(nome).id == esperada


def test_item_da_planilha_usa_a_categoria_escrita_e_o_novo_usa_o_nome() -> None:
    assert categorias.do_item("aceto-balsamico", "Aceto balsâmico").id == "temperos"
    assert categorias.do_item("item-12345678", "Queijo coalho").id == "laticinios"
    assert categorias.valida("oleos")
    assert not categorias.valida("oleo")
