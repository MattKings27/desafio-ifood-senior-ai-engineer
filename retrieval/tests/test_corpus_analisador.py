"""O analisador de português: acento, palavras vazias, radical leve, unidades e sinônimos."""

from __future__ import annotations

import pytest

from retrieval.corpus.analisador import (
    SINONIMOS_DA_COZINHA,
    Analisador,
    palavras,
    radical,
    sem_acento,
    sinonimos_do_casamento,
)


def test_sem_acento_e_sem_caixa() -> None:
    assert sem_acento("AÇAFRÃO Béchamel") == "acafrao bechamel"


@pytest.mark.parametrize(
    ("palavra", "esperado"),
    [
        ("feijoes", "feijao"),
        ("paes", "pao"),
        ("sais", "sal"),
        ("pasteis", "pastel"),
        ("bens", "bem"),
        ("colheres", "colh"),
        ("ovos", "ovo"),
        ("graus", "grau"),
        ("refogado", "refog"),
        ("refogar", "refog"),
        ("congelamento", "congel"),
        ("salada", "salada"),
        ("farinha", "farinha"),
        ("gas", "gas"),
        ("2002", "2002"),
        ("paguei", "pag"),
        ("custou", "cust"),
        ("massa", "massa"),
        ("rapidamente", "rapida"),
    ],
)
def test_radical_leve(palavra: str, esperado: str) -> None:
    assert radical(palavra) == esperado


def test_unidades_e_graus_viram_palavra() -> None:
    assert palavras("R$ 41,00/kg; 2 L; 500 ml; 200 g; forno a 180 °C; 5ºC") == [
        "r", "41", "00", "quilo", "2", "litro", "500", "mililitro", "200", "grama",
        "forno", "a", "180", "graus", "5", "graus",
    ]  # fmt: skip


def test_termos_tiram_vazias_letra_solta_e_centavo_zerado() -> None:
    assert Analisador().termos("Quanto eu paguei no óleo? R$ 9,00 a L") == [
        "pag",
        "oleo",
        "litro",
    ]


def test_sinonimo_de_uma_palavra_so_na_pergunta() -> None:
    analisador = Analisador()
    grupos = analisador.grupos("A geladeira tem espaço?")
    assert grupos[0].original == "geladeira"
    assert {"refrigerador", "geladeira"} <= grupos[0].radicais
    assert analisador.termos("A geladeira tem espaço?") == ["geladeira", "espaco"]


def test_sinonimo_de_duas_palavras_entra_pela_primeira() -> None:
    grupos = Analisador().grupos("como faz molho branco?")
    assert grupos[0].original == "molho"
    assert "bechamel" in grupos[0].radicais
    assert grupos[1].radicais == frozenset({"branco"})


def test_palavra_repetida_conta_uma_vez() -> None:
    grupos = Analisador().grupos("frango frango e mais frango")
    assert [g.original for g in grupos] == ["frango"]


def test_consulta_junta_os_radicais_sem_repetir() -> None:
    termos = Analisador([("marmita", "embalagem")]).consulta("marmita e embalagem")
    assert sorted(termos) == ["embal", "marmita"]


def test_pergunta_so_de_palavras_vazias() -> None:
    assert Analisador().grupos("o que é isso?") == []


def test_grupo_de_sinonimo_vazio_nao_quebra() -> None:
    analisador = Analisador([("de", "a"), ("bolo", "torta")])
    assert "torta" in analisador.grupos("bolo")[0].radicais


def test_sinonimos_do_casamento_so_o_que_nao_casa_sozinho() -> None:
    pares = sinonimos_do_casamento(
        {
            "file de frango": "Peito de frango",
            "farinha": "Farinha de trigo",
            "muçarela": "Queijo mussarela",
            "frango": "Peito de frango",
        }
    )
    assert pares == [("file", "peito"), ("mucarela", "queijo mussarela")]


def test_os_sinonimos_da_cozinha_sao_grupos() -> None:
    assert all(len(grupo) >= 2 for grupo in SINONIMOS_DA_COZINHA)
