"""O que ela responde sobre uma receita guardada entra; o resto da receita não muda."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mise.complemento import (
    A_GOSTO_DITO_POR_ELA,
    DITO_POR_ELA,
    completar,
    diferencas,
)
from mise.erros import ErroDeUso
from mise.receita import Receita, receita
from mise.receita import ingrediente as ing

ARROZ = ing("2 xícaras de arroz", "arroz", 2, "xicara")
TEMPEROS = ing("temperos de sua preferência", "temperos de sua preferência", entendida=False)
SAL = ing("sal a gosto", "sal")


def _da_pagina(**campos: object) -> Receita:
    base = receita("Arroz da página", [ARROZ, TEMPEROS, SAL], modo_preparo=["Cozinhe na panela."])
    return Receita(**{**{f: getattr(base, f) for f in base.__slots__}, **campos})  # type: ignore[arg-type]


def test_linha_nao_entendida_ganha_a_quantidade_que_ela_disse() -> None:
    guardada = _da_pagina()
    nova = receita(
        "qualquer nome",
        [ing("temperos de sua preferência", "temperos", 1, "colher de cha")],
    )
    feito = completar(guardada, nova)
    assert feito.mudou
    linha = feito.receita.ingredientes[1]
    assert (linha.quantidade, linha.medida, linha.observacao) == (
        Decimal(1),
        "colher de cha",
        DITO_POR_ELA,
    )
    assert linha.texto_original == "temperos de sua preferência"
    assert not linha.nao_entendida
    assert feito.respostas == (("temperos de sua preferência", "1 colher de chá"),)
    assert feito.receita.nome == "Arroz da página"


def test_linha_nao_entendida_pode_virar_a_gosto() -> None:
    nova = receita("x", [ing("temperos de sua preferência a gosto", "temperos de sua preferência")])
    feito = completar(_da_pagina(), nova)
    linha = feito.receita.ingredientes[1]
    assert linha.a_gosto and linha.observacao == A_GOSTO_DITO_POR_ELA
    assert feito.respostas == (("temperos de sua preferência", "a gosto"),)


def test_linha_a_gosto_ganha_a_medida_dela_e_a_repetida_nao_muda_nada() -> None:
    nova = receita("x", [ing("sal a gosto", "sal", 1, "pitada"), ARROZ, SAL])
    feito = completar(_da_pagina(), nova)
    assert feito.receita.ingredientes[2].quantidade == Decimal(1)
    assert feito.respostas == (("sal a gosto", "1 pitada"),)
    assert not completar(_da_pagina(), receita("x", [ARROZ, SAL, TEMPEROS])).mudou


def test_quantidade_que_a_pagina_ja_diz_nao_muda() -> None:
    nova = receita("x", [ing("2 xícaras de arroz", "arroz", 3, "xicara")])
    with pytest.raises(ErroDeUso, match="já diz quanto vai de arroz"):
        completar(_da_pagina(), nova)


def test_linha_que_a_pagina_nao_tem_e_recusada() -> None:
    nova = receita("x", [ing("200 g de bacon", "bacon", 200, "g")])
    with pytest.raises(ErroDeUso, match="não está na receita guardada") as erro:
        completar(_da_pagina(), nova)
    assert "receita_id" in erro.value.mensagem


def test_rendimento_que_faltava_entra_e_o_informado_nao_muda() -> None:
    sem = _da_pagina(rendimento_informado=False)
    feito = completar(sem, receita("x", [ARROZ], rendimento_porcoes=6))
    assert (feito.receita.rendimento_porcoes, feito.receita.rendimento_informado) == (6, True)
    assert feito.respostas == (("rendimento_porcoes", "6 porções"),)
    uma = completar(sem, receita("x", [ARROZ], rendimento_porcoes=1))
    assert uma.respostas == (("rendimento_porcoes", "1 porção"),)
    nao_disse = Receita(nome="x", ingredientes=(ARROZ,), rendimento_informado=False)
    assert not completar(sem, nao_disse).mudou
    com = _da_pagina(rendimento_porcoes=4)
    with pytest.raises(ErroDeUso, match="rende 4 porções"):
        completar(com, receita("x", [ARROZ], rendimento_porcoes=8))
    assert not completar(com, receita("x", [ARROZ], rendimento_porcoes=4)).mudou


def test_preparo_que_faltava_entra_com_o_que_ele_pede() -> None:
    sem = _da_pagina(modo_preparo=(), equipamentos=frozenset(), tecnicas=frozenset())
    nova = receita("x", [ARROZ], modo_preparo=["Leve ao forno por 30 minutos."])
    feito = completar(sem, nova)
    assert feito.receita.modo_preparo == ("Leve ao forno por 30 minutos.",)
    assert "forno" in feito.receita.equipamentos
    assert feito.respostas == (("modo_preparo", "Leve ao forno por 30 minutos."),)
    with pytest.raises(ErroDeUso, match="já traz o modo de preparo"):
        completar(_da_pagina(), nova)
    igual = receita("x", [ARROZ], modo_preparo=["cozinhe  na PANELA."])
    assert not completar(_da_pagina(), igual).mudou


def test_diferencas_diz_o_que_mudou() -> None:
    base = _da_pagina()
    assert diferencas(base, base) == ()
    assert diferencas(base, _da_pagina(nome="ARROZ DA PÁGINA")) == ()
    assert diferencas(base, _da_pagina(nome="Outro")) == (
        "o nome ('Outro' no lugar de 'Arroz da página')",
    )
    menos = _da_pagina(ingredientes=(ARROZ, SAL, ing("1 ovo", "ovo", 1, "ovo")))
    (so_ingredientes,) = diferencas(base, menos)
    assert "sem 'temperos de sua preferencia'" in so_ingredientes
    assert "com '1 ovo'" in so_ingredientes
    mais = _da_pagina(ingredientes=(ing("2 xícaras de arroz", "arroz", 3, "xicara"), TEMPEROS, SAL))
    assert diferencas(base, mais) == ("os ingredientes (as quantidades)",)
    assert diferencas(base, _da_pagina(rendimento_porcoes=3)) == ("o rendimento",)
    assert diferencas(base, _da_pagina(modo_preparo=("Asse.",))) == ("o modo de preparo",)
