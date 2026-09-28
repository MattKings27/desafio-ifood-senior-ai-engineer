"""Devolver aos R$ 80,00: uma linha nova, que anula a compra sem apagar nada."""

from __future__ import annotations

from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Dossie
from mise.erros import Ausente, ErroDeUso, OrcamentoExcedido

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def dossie(tmp_path: Path) -> Iterator[Dossie]:
    with Dossie(tmp_path / "dossie.db") as d:
        yield d


def test_estorno_anula_a_compra_no_saldo_e_no_que_virou_estoque(dossie: Dossie) -> None:
    dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6.00"), chave="a")
    (compra,) = dossie.extrato()
    assert dossie.orcamento().restante == Dinheiro.de("74.00")

    estorno = dossie.estornar(compra.id, canal=Canal.TELA)
    assert estorno.valor == Dinheiro.de("-6.00")
    assert estorno.estorna == compra.id
    assert estorno.e_estorno
    assert not estorno.ativa
    assert estorno.descricao.startswith("Devolução: ")
    assert dossie.orcamento().restante == Dinheiro.de("80.00")
    assert dossie.compras() == {}
    original = dossie.compra(compra.id)
    assert original is not None
    assert original.estornada
    assert not original.ativa


def test_devolver_de_novo_nao_devolve_duas_vezes(dossie: Dossie) -> None:
    dossie.registrar_gasto("feira", Dinheiro.de("10.00"))
    (gasto,) = dossie.extrato()
    primeira = dossie.estornar(gasto.id)
    segunda = dossie.estornar(gasto.id)
    assert primeira == segunda
    assert len(dossie.extrato()) == 2
    assert dossie.orcamento().restante == Dinheiro.de("80.00")


def test_devolucao_nao_se_devolve_e_compra_que_nao_existe_e_ausente(dossie: Dossie) -> None:
    dossie.registrar_gasto("feira", Dinheiro.de("10.00"))
    (gasto,) = dossie.extrato()
    estorno = dossie.estornar(gasto.id)
    with pytest.raises(ErroDeUso, match="já é uma devolução"):
        dossie.estornar(estorno.id)
    with pytest.raises(Ausente):
        dossie.estornar(12345)
    assert dossie.compra(12345) is None


def test_linha_sem_valor_nao_se_devolve(dossie: Dossie) -> None:
    dossie.registrar_gasto("amostra grátis", Dinheiro.zero())
    (gasto,) = dossie.extrato()
    with pytest.raises(ErroDeUso, match="não tirou dinheiro"):
        dossie.estornar(gasto.id)


def test_compra_de_item_da_despensa_leva_o_item_e_confere_o_saldo(dossie: Dossie) -> None:
    compra = dossie.debitar_item("item-1", "Nata (despensa)", Dinheiro.de("7.50"), chave="x")
    assert compra.item_id == "item-1"
    assert compra.ingrediente is None
    assert dossie.compras_do_item("item-1") == (compra,)
    assert dossie.compras() == {}
    # A mesma chave não debita de novo.
    assert dossie.debitar_item("item-1", "Nata", Dinheiro.de("7.50"), chave="x") == compra
    assert dossie.orcamento().restante == Dinheiro.de("72.50")
    with pytest.raises(OrcamentoExcedido):
        dossie.debitar_item("item-2", "Caviar", Dinheiro.de("100.00"), chave="y")
    with pytest.raises(ErroDeUso, match="maior que zero"):
        dossie.debitar_item("item-3", "Nada", Dinheiro.zero(), chave="z")
    dossie.estornar(compra.id)
    assert dossie.compras_do_item("item-1") == ()


def test_banco_antigo_ganha_as_colunas_do_estorno(tmp_path: Path) -> None:
    import sqlite3

    banco = tmp_path / "antigo.db"
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute(
            "CREATE TABLE gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT NOT NULL "
            "UNIQUE, descricao TEXT NOT NULL, centavos INTEGER NOT NULL, registrado TEXT NOT NULL)"
        )
        conexao.execute(
            "INSERT INTO gastos (chave, descricao, centavos, registrado) "
            "VALUES ('g', 'feira', 500, '2026-09-24T10:00:00+00:00')"
        )
        conexao.commit()
    with Dossie(banco) as dossie:
        (linha,) = dossie.extrato()
        assert (linha.estorna, linha.item_id, linha.estornada) == (None, None, False)
        dossie.estornar(linha.id)
        assert dossie.orcamento().restante == Dinheiro.de("80.00")
