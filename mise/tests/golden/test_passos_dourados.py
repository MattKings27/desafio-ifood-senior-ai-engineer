"""Casos dourados do passo a passo: quatro receitas de verdade, contra a despensa dela.

Cada caso fixa o que a tela e a conversa mostram de cada passo: o requisito, o
trecho que o denunciou, o estado na cozinha dela (com o perfil de partida: nada
respondido) e os limites de tempo, frio, temperatura e panela a mais. E fixa que
as perguntas são as do portão, com as opções e os passos que as pedem.

O veredito vem junto de propósito: o passo a passo não pode mudá-lo.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from mise.despensa import Despensa
from mise.passos import detalhar
from mise.perfil import Gosto, PerfilCozinha
from mise.receita import Receita, ingrediente, receita
from mise.viabilidade import avaliar

SIM_NAO_NAO_SEI = ["sim", "nao", "nao_sei"]


def _arroz_com_frango() -> Receita:
    return receita(
        "Arroz com frango",
        [
            ingrediente("500 g de peito de frango", "peito de frango", 500, "g"),
            ingrediente("2 xícaras de arroz", "arroz", 2, "xicara"),
            ingrediente("1 cebola", "cebola", 1, "unidade"),
            ingrediente("2 dentes de alho", "alho", 2, "dente"),
            ingrediente("2 colheres de sopa de óleo", "óleo", 2, "colher de sopa"),
            ingrediente("sal a gosto", "sal"),
        ],
        rendimento_porcoes=4,
        modo_preparo=[
            "Refogue a cebola e o alho no óleo.",
            "Junte o frango e doure.",
            "Acrescente o arroz e a água e cozinhe por 20 minutos.",
        ],
    )


def _frango_assado() -> Receita:
    return receita(
        "Frango assado",
        [
            ingrediente("1 kg de coxa e sobrecoxa", "frango", 1, "kg"),
            ingrediente("2 dentes de alho", "alho", 2, "dente"),
            ingrediente("sal a gosto", "sal"),
        ],
        rendimento_porcoes=4,
        modo_preparo=[
            "Tempere o frango com alho, sal e limão e deixe marinar por 2 horas na geladeira.",
            "Pré-aqueça o forno a 200 °C.",
            "Asse por 1 hora e 30 minutos, regando com o próprio caldo.",
        ],
    )


def _mousse_de_maracuja() -> Receita:
    return receita(
        "Mousse de maracujá",
        [
            ingrediente("1 lata de leite condensado", "leite condensado", 1, "lata"),
            ingrediente("1 lata de creme de leite", "creme de leite", 1, "lata"),
            ingrediente("1 xícara de suco de maracujá", "suco de maracujá", 1, "xicara"),
        ],
        rendimento_porcoes=6,
        modo_preparo=[
            "Bata no liquidificador o leite condensado, o creme de leite e o suco de maracujá "
            "por 3 minutos.",
            "Despeje em taças e leve à geladeira por 4 horas.",
        ],
    )


def _macarrao_ao_sugo() -> Receita:
    return receita(
        "Macarrão ao sugo",
        [
            ingrediente("500 g de macarrão", "macarrão", 500, "g"),
            ingrediente("1 lata de molho de tomate", "molho de tomate", 1, "lata"),
            ingrediente("3 dentes de alho", "alho", 3, "dente"),
        ],
        rendimento_porcoes=4,
        modo_preparo=[
            "Cozinhe o macarrão em água fervente com sal por 10 a 12 minutos.",
            "Em outra panela, refogue o alho no azeite e junte o molho de tomate.",
            "Deixe apurar por 15 minutos em fogo baixo e misture ao macarrão.",
        ],
    )


def _detalhe(
    r: Receita, despensa: Despensa, perfil: PerfilCozinha | None = None
) -> tuple[str, dict[str, Any]]:
    perfil = perfil or PerfilCozinha.inicial()
    avaliacao = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    saida = detalhar(r, perfil, avaliacao)
    json.dumps(saida, ensure_ascii=False)
    return avaliacao.veredito.rotulo, saida


def _requisitos(passo: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (r["tipo"], r["id"], r["estado"], r["suposto"], r["trecho"], r["rotulo_estado"])
        for r in passo["requisitos"]
    ]


def _limites(passo: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (lim["tipo"], lim["minutos"], lim["graus"], lim["texto"], lim["trecho"], lim["equipamento"])
        for lim in passo["limites"]
    ]


def _perguntas(saida: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (p["tipo"], p["campo"], p["passos"], [o["resposta"] for o in p["opcoes"]], p["entrada"])
        for p in saida["perguntas"]
    ]


def test_arroz_com_frango(despensa: Despensa) -> None:
    """Tudo em casa: dá pra fazer, e o passo a passo mostra o refogado e os 20 min de fogo.

    Os 20 minutos cabem na hora que ela tem por cozinhada. O fogão aparece nos
    passos de refogar e de cozinhar, suposto: ninguém perguntou, e toda cozinha tem.
    """
    uma_hora = PerfilCozinha.inicial().com_restricao("tempo_max_por_fornada_min", 60)
    # Refogar e dourar não dizem o tempo: vale o cozimento que a receita declara.
    com_o_cozimento = replace(_arroz_com_frango(), tempo_cozimento_min=35)
    veredito, saida = _detalhe(com_o_cozimento, despensa, uma_hora)
    assert veredito == "APTO"
    um, dois, tres = saida["por_passo"]["passos"]
    assert _requisitos(um) == [
        ("equipamento", "fogao", "tem", True, "Refogue", "suposto"),
        ("tecnica", "refogar", "tem", True, "Refogue", "suposto"),
    ]
    assert _limites(um) == []
    # "doure" sozinho não está na taxonomia: sem requisito, e o portão também não pede.
    assert _requisitos(dois) == _limites(dois) == []
    assert _requisitos(tres) == [("equipamento", "fogao", "tem", True, "cozinhe", "suposto")]
    assert _limites(tres) == [("tempo", 20, None, "20 min no fogo", "20 minutos", "fogao")]
    assert saida["por_passo"]["requisitos_da_receita"] == []
    assert saida["perguntas"] == []
    assert saida["exige"] == {"equipamentos": ["Fogão"], "tecnicas": ["Refogar"]}


def test_arroz_com_frango_sem_o_tempo_dela_pergunta_so_isso(despensa: Despensa) -> None:
    """Sem saber quanto tempo ela tem por cozinhada, os 20 min de fogo viram a única pergunta."""
    veredito, saida = _detalhe(_arroz_com_frango(), despensa)
    assert veredito == "FALTA INFO"
    assert _perguntas(saida) == [
        (
            "operacional",
            "tempo_max_por_fornada_min",
            [],
            ["nao_sei"],
            # Em horas, como ela responde; o motor guarda em minutos.
            {"tipo": "horas", "unidade": "horas", "min": 0.5, "max": 12, "passo": 0.5, "casas": 2},
        ),
    ]


def test_frango_assado_com_forno(despensa: Despensa) -> None:
    """O forno aparece nos dois passos que o pedem, e a pergunta aponta os dois."""
    veredito, saida = _detalhe(_frango_assado(), despensa)
    assert veredito == "FALTA INFO"
    um, dois, tres = saida["por_passo"]["passos"]
    assert _requisitos(um) == [("equipamento", "geladeira", "tem", True, "geladeira", "suposto")]
    assert _limites(um) == [
        ("geladeira", 120, None, "2 h na geladeira", "2 horas", "geladeira"),
    ]
    assert _requisitos(dois) == [
        ("equipamento", "forno", "desconhecido", False, "forno", "ainda não perguntei"),
    ]
    assert _limites(dois) == [
        ("temperatura", None, 200, "forno a 200 °C", "200 °C", "forno"),
    ]
    assert _requisitos(tres) == [
        ("equipamento", "forno", "desconhecido", False, "Asse", "ainda não perguntei"),
        ("tecnica", "assar", "tem", True, "Asse", "suposto"),
    ]
    assert _limites(tres) == [
        ("tempo", 90, None, "1 h 30 min no forno", "1 hora e 30 minutos", "forno"),
    ]
    # O nome também pede forno, mas o preparo já diz: não entra no balde da receita.
    assert saida["por_passo"]["requisitos_da_receita"] == []
    assert _perguntas(saida) == [
        ("equipamento", "forno", [2, 3], SIM_NAO_NAO_SEI, None),
        (
            "operacional",
            "tempo_max_por_fornada_min",
            [],
            ["nao_sei"],
            # Em horas, como ela responde; o motor guarda em minutos.
            {"tipo": "horas", "unidade": "horas", "min": 0.5, "max": 12, "passo": 0.5, "casas": 2},
        ),
        (
            "operacional",
            "espaco_geladeira_litros",
            [],
            ["nao_sei"],
            {"tipo": "inteiro", "unidade": "litros", "min": 0, "max": 1000},
        ),
    ]


def test_frango_assado_sem_preparo_pede_forno_pelo_nome(despensa: Despensa) -> None:
    """ "Frango assado" pede forno mesmo sem passo nenhum dizer: fica no balde, com a origem."""
    r = receita("Frango assado", [ingrediente("1 kg de coxa e sobrecoxa", "frango", 1, "kg")])
    veredito, saida = _detalhe(r, despensa)
    assert veredito == "FALTA INFO"
    assert saida["por_passo"]["passos"] == []
    (do_nome,) = saida["por_passo"]["requisitos_da_receita"]
    assert (do_nome["id"], do_nome["origem"], do_nome["trecho"], do_nome["estado"]) == (
        "forno",
        "nome",
        "assado",
        "desconhecido",
    )
    assert ("equipamento", "forno", [], SIM_NAO_NAO_SEI, None) in _perguntas(saida)


def test_mousse_com_quatro_horas_de_geladeira(despensa: Despensa) -> None:
    """A geladeira é suposta, mas as 4 horas nela viram limite e o espaço vira pergunta.

    Sem preço de referência aqui, a compra do leite condensado não se confirma e
    a receita fica de fora (nunca pergunta de preço); os passos continuam lidos.
    """
    veredito, saida = _detalhe(_mousse_de_maracuja(), despensa)
    assert veredito == "BLOQUEADO"
    um, dois = saida["por_passo"]["passos"]
    assert _requisitos(um) == [
        (
            "equipamento",
            "liquidificador",
            "desconhecido",
            False,
            "liquidificador",
            "ainda não perguntei",
        ),
    ]
    assert _limites(um) == [
        ("tempo", 3, None, "3 min no liquidificador", "3 minutos", "liquidificador"),
    ]
    assert _requisitos(dois) == [("equipamento", "geladeira", "tem", True, "geladeira", "suposto")]
    assert _limites(dois) == [
        ("geladeira", 240, None, "4 h na geladeira", "4 horas", "geladeira"),
    ]
    campos = {p["campo"]: p for p in saida["perguntas"]}
    assert campos["liquidificador"]["passos"] == [1]
    assert campos["espaco_geladeira_litros"]["entrada"]["unidade"] == "litros"


def test_macarrao_com_outra_panela(despensa: Despensa) -> None:
    """ "Em outra panela" é uma boca a mais ao mesmo tempo: o passo mostra, e o portão pergunta.

    O portão lê a mesma marca do passo: duas panelas no fogo juntas pedem duas
    bocas. Sem saber quantas o fogão tem, a pergunta das bocas entra; com uma
    boca só, vira aviso (`test_restricoes_operacionais`).
    """
    veredito, saida = _detalhe(_macarrao_ao_sugo(), despensa)
    # Sem preço de referência aqui, o molho não se confirma: fica de fora, sem pergunta.
    assert veredito == "BLOQUEADO"
    um, dois, tres = saida["por_passo"]["passos"]
    assert _requisitos(um) == [("equipamento", "fogao", "tem", True, "fervente", "suposto")]
    assert _limites(um) == [
        ("tempo", 12, None, "10 a 12 min no fogo", "10 a 12 minutos", "fogao"),
    ]
    assert _requisitos(dois) == [
        ("equipamento", "fogao", "tem", True, "panela", "suposto"),
        ("tecnica", "refogar", "tem", True, "refogue", "suposto"),
        ("tecnica", "molho_tomate", "tem", True, "molho de tomate", "suposto"),
    ]
    assert _limites(dois) == [
        (
            "outra_panela",
            None,
            None,
            "mais uma boca do fogão ao mesmo tempo",
            "Em outra panela",
            "fogao",
        ),
    ]
    assert _requisitos(tres) == [("equipamento", "fogao", "tem", True, "fogo baixo", "suposto")]
    assert _limites(tres) == [("tempo", 15, None, "15 min no fogo", "15 minutos", "fogao")]
    bocas = next(p for p in saida["perguntas"] if p["campo"] == "bocas_fogao")
    assert "ao mesmo tempo (passo 2)" in bocas["motivo"]


@pytest.mark.parametrize(
    "montar", [_arroz_com_frango, _frango_assado, _mousse_de_maracuja, _macarrao_ao_sugo]
)
def test_evidencia_de_cada_requisito_contem_o_trecho(montar: Any, despensa: Despensa) -> None:
    """A evidência da taxonomia e o trecho original apontam para as mesmas palavras."""
    from mise.taxonomia import _normalizar

    _, saida = _detalhe(montar(), despensa)
    for passo in saida["por_passo"]["passos"]:
        for requisito in passo["requisitos"]:
            assert _normalizar(requisito["trecho"]) in requisito["evidencia"]
            assert requisito["trecho"] in passo["texto"]
