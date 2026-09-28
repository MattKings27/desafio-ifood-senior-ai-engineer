"""O tempero escrito só pelo nome vai a gosto, também na receita que já estava guardada."""

from __future__ import annotations

from typing import Any

import pytest

from mise.receita import IngredienteReceita, Origem, Receita
from mise.temperos import so_tempero


def _guardada(*linhas: IngredienteReceita) -> dict[str, Any]:
    receita = Receita(
        nome="Feijão temperado",
        ingredientes=linhas,
        modo_preparo=("Cozinhe o feijão.",),
        url="https://www.tudogostoso.com.br/receita/9-feijao.html",
        fonte="tudogostoso.com.br",
        origem=Origem.WEB,
    )
    return receita.para_dict()


def test_a_linha_guardada_antes_da_regra_passa_a_valer_a_gosto() -> None:
    """ "Sal" guardado como não lido segurava a receita; lido de novo, vale a gosto."""
    dados = _guardada(
        IngredienteReceita("500 g de feijão", "feijão", quantidade=None, entendida=True),
        IngredienteReceita("Sal e pimenta-do-reino", "Sal e pimenta-do-reino", entendida=False),
        IngredienteReceita("Milho", "Milho", entendida=False),
    )
    feijao, sal, milho = Receita.de_dict(dados).ingredientes
    assert feijao.a_gosto
    assert sal.a_gosto
    assert not sal.nao_entendida
    assert milho.nao_entendida, "o que muda a compra continua pergunta"


@pytest.mark.parametrize(
    ("linha", "tempero"),
    [("Azeite", True), ("Orégano seco", True), ("Sal e milho", False), ("2 g de sal", False)],
)
def test_so_tempero(linha: str, tempero: bool) -> None:
    assert so_tempero(linha) is tempero
