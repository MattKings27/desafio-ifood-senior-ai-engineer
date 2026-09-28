"""As peças da busca: normalização, BM25, n-gramas com hash e a fusão por posição.

A medição de que cada braço sozinho erra onde o outro acerta mora agora nos
testes do corpus (`test_corpus_busca.py`) e na ablação do conjunto dourado
(`evals/casos/recuperacao.yaml`).
"""

from __future__ import annotations

import pytest

from retrieval.indice import (
    BM25,
    NGramasHasheados,
    cosseno,
    fundir_por_rrf,
    normalizar,
    tokenizar,
)

# --------------------------------------------------------------------------- #
# Tokenização                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("Açafrão", "acafrao"), ("BÉCHAMEL", "bechamel"), ("cúrcuma", "curcuma")],
)
def test_normalizar_tira_acento_e_caixa(bruto: str, esperado: str) -> None:
    assert normalizar(bruto) == esperado


def test_tokenizar_remove_palavras_vazias() -> None:
    """ "de", "para", "com" não discriminam nada e só somam ruído ao BM25."""
    assert tokenizar("o rendimento de um quilo de feijão") == ["rendimento", "quilo", "feijao"]


def test_tokenizar_ignora_letra_solta() -> None:
    assert "a" not in tokenizar("a b farinha")


# --------------------------------------------------------------------------- #
# BM25                                                                         #
# --------------------------------------------------------------------------- #


def test_bm25_prefere_documento_com_o_termo() -> None:
    bm = BM25([tokenizar("manteiga e oleo"), tokenizar("feijao e arroz")])
    notas = bm.pontuar(tokenizar("manteiga"))
    assert notas[0] > notas[1]


def test_bm25_satura_frequencia() -> None:
    """Dez ocorrências não valem dez vezes uma: é o que `k1` controla."""
    bm = BM25([tokenizar("manteiga " * 10), tokenizar("manteiga")])
    notas = bm.pontuar(tokenizar("manteiga"))
    assert notas[0] < notas[1] * 10


def test_bm25_com_corpus_vazio_nao_quebra() -> None:
    assert BM25([]).pontuar(["qualquer"]) == []


def test_termo_ausente_nao_pontua() -> None:
    bm = BM25([tokenizar("feijao")])
    assert bm.pontuar(tokenizar("trufa"))[0] == 0.0


# --------------------------------------------------------------------------- #
# Vetorização                                                                  #
# --------------------------------------------------------------------------- #


def test_vetor_e_deterministico_entre_execucoes() -> None:
    """Usa SHA-1 e não `hash()`, que é aleatorizado por processo.

    Com `hash()`, o mesmo texto daria vetores diferentes a cada execução e a
    busca seria impossível de testar.
    """
    v = NGramasHasheados()
    assert v.vetorizar("manteiga") == v.vetorizar("manteiga")


def test_vetor_e_normalizado() -> None:
    v = NGramasHasheados().vetorizar("farinha de trigo")
    assert sum(x * x for x in v) == pytest.approx(1.0)


def test_vetor_de_texto_vazio_nao_quebra() -> None:
    assert all(x == 0.0 for x in NGramasHasheados().vetorizar(""))


def test_palavras_parecidas_ficam_proximas() -> None:
    """É o que n-grama de caractere compra: morfologia e erro de digitação."""
    v = NGramasHasheados()
    proximo = cosseno(v.vetorizar("empanar"), v.vetorizar("empanado"))
    distante = cosseno(v.vetorizar("empanar"), v.vetorizar("geladeira"))
    assert proximo > distante


# --------------------------------------------------------------------------- #
# Fusão                                                                        #
# --------------------------------------------------------------------------- #


def test_rrf_funde_por_posicao_e_nao_por_nota() -> None:
    """A nota do BM25 é ilimitada; a do cosseno vive entre -1 e 1.

    Somar as duas daria peso arbitrário a quem tem escala maior. Posição não tem
    esse problema, e é por isso que a fusão é por posição.
    """
    lexical = [(0, 999.0), (1, 998.0)]  # notas enormes
    vetorial = [(1, 0.9), (0, 0.1)]  # notas pequenas
    fundido = fundir_por_rrf(lexical, vetorial)

    # O documento 1 é 2º no lexical e 1º no vetorial; o 0 é 1º e 2º. Empatam.
    assert fundido[0][0] == pytest.approx(fundido[1][0])


def test_rrf_premia_quem_aparece_nos_dois() -> None:
    fundido = fundir_por_rrf([(0, 1.0), (1, 0.5)], [(0, 1.0)])
    assert fundido[0][0] > fundido[1][0]


def test_rrf_registra_a_posicao_de_cada_braco() -> None:
    fundido = fundir_por_rrf([(7, 1.0)], [(9, 1.0)])
    assert fundido[7] == (pytest.approx(1 / 61), 1, None)
    assert fundido[9] == (pytest.approx(1 / 61), None, 1)
