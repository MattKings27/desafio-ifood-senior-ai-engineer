"""A busca híbrida no corpus: os dois braços, a fusão, o portão do "não sei", a diversidade e a expansão."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from retrieval.corpus import Analisador, IndiceDoCorpus, Limiares, NGramas, Trecho
from retrieval.corpus.busca import (
    _margem,
    escolher_com_diversidade,
    fundir_por_posicao,
)


def _trecho(id_: str, tipo: str, cabecalho: str, corpo: str, **extra: object) -> Trecho:
    rota = None if tipo == "conhecimento" else f"/{tipo}"
    return Trecho(id_, tipo, rota, "fonte de teste", cabecalho, corpo, **extra)  # type: ignore[arg-type]


CORPUS = [
    _trecho(
        "despensa:alcaparras",
        "despensa",
        "Alcaparras, na despensa da senhora:",
        "Tem 2 kg. Comprou 1 balde de 2 kg por R$ 82,00. Custo de R$ 41,00/kg.",
        rotulo="Alcaparras, na sua despensa",
    ),
    _trecho(
        "despensa:azeite",
        "despensa",
        "Azeite de oliva, na despensa da senhora:",
        "Tem 500 ml. Comprou 1 garrafa por R$ 30,99.",
    ),
    _trecho(
        "cozinha:forno",
        "cozinha",
        "Forno, equipamento na cozinha da senhora:",
        "A senhora disse que tem forno. O que faz o mesmo papel: air fryer.",
        palavras=("assar", "gratinar"),
    ),
    _trecho(
        "receita:bolo",
        "receita",
        "Receita Bolo de fubá, TudoGostoso:",
        "Rende 8 porções. Situação para a senhora: dá pra fazer.",
    ),
    _trecho(
        "receita:bolo:passo-1",
        "receita",
        "Receita Bolo de fubá, TudoGostoso, passo 1 de 2:",
        "Bata tudo no liquidificador por 3 minutos.",
        pai="receita:bolo",
        ordem=1,
    ),
    _trecho(
        "receita:bolo:passo-2",
        "receita",
        "Receita Bolo de fubá, TudoGostoso, passo 2 de 2:",
        "Leve ao forno por 40 minutos.",
        pai="receita:bolo",
        ordem=2,
    ),
    _trecho(
        "conhecimento:geladeira",
        "conhecimento",
        "Conhecimento de cozinha, conservação:",
        "Comida pronta fica na geladeira abaixo de 5 °C.",
    ),
    _trecho(
        "conhecimento:empanar",
        "conhecimento",
        "Conhecimento de cozinha, técnica:",
        "Empanar é passar na farinha, no ovo e na farinha de rosca antes de fritar.",
    ),
]


@pytest.fixture
def indice() -> IndiceDoCorpus:
    return IndiceDoCorpus(CORPUS, Analisador(), NGramas(), versao="v1")


def ids(resultado: object) -> list[str]:
    return [a.trecho.id for a in resultado.achados]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# O trecho
# --------------------------------------------------------------------------- #


def test_trecho_com_nome_texto_e_indexavel() -> None:
    trecho = CORPUS[0]
    assert trecho.nome == "Alcaparras, na sua despensa"
    assert CORPUS[1].nome == "Azeite de oliva, na despensa da senhora"
    assert trecho.texto.startswith("Alcaparras, na despensa da senhora: Tem 2 kg")
    assert "assar" in CORPUS[2].indexavel


@pytest.mark.parametrize(
    ("argumentos", "mensagem"),
    [
        (("x", "moveis", None, "f", "c", "corpo"), "tipo de trecho desconhecido"),
        ((" ", "despensa", None, "f", "c", "corpo"), "sem id"),
        (("x", "despensa", None, "f", "c", " "), "sem texto"),
    ],
)
def test_trecho_invalido(argumentos: tuple[str, ...], mensagem: str) -> None:
    with pytest.raises(ValueError, match=mensagem):
        Trecho(*argumentos)  # type: ignore[arg-type]


def test_ids_repetidos_nao_entram() -> None:
    with pytest.raises(ValueError, match="mesmo id"):
        IndiceDoCorpus([CORPUS[0], CORPUS[0]], Analisador(), NGramas())


# --------------------------------------------------------------------------- #
# A busca
# --------------------------------------------------------------------------- #


def test_acha_o_item_pela_pergunta_dela(indice: IndiceDoCorpus) -> None:
    resultado = indice.buscar("quanto paguei nas alcaparras?")
    assert ids(resultado)[0] == "despensa:alcaparras"
    assert resultado.motivo == ""
    assert not resultado.nada_relevante
    primeiro = resultado.achados[0]
    assert 0 < primeiro.pontuacao <= 1
    assert primeiro.posicao_lexical == 1
    assert primeiro.cobertura == 1.0
    assert resultado.vetorizador == NGramas.nome
    assert len(indice) == len(CORPUS)


def test_o_passo_volta_com_o_cabecalho_da_receita(indice: IndiceDoCorpus) -> None:
    resultado = indice.buscar("o bolo de fubá vai no liquidificador?")
    achado = next(a for a in resultado.achados if a.trecho.pai == "receita:bolo")
    assert achado.texto.startswith("Receita Bolo de fubá, TudoGostoso: Rende 8 porções")
    assert "Bata tudo no liquidificador" in achado.texto
    assert sum(1 for a in resultado.achados if (a.trecho.pai or a.trecho.id) == "receita:bolo") == 1


def test_irmaos_viram_um_trecho_so(indice: IndiceDoCorpus) -> None:
    resultado = indice.buscar("passos do bolo de fubá: liquidificador e forno")
    bolo = next(a for a in resultado.achados if (a.trecho.pai or a.trecho.id) == "receita:bolo")
    assert set(bolo.juntos) <= {"receita:bolo", "receita:bolo:passo-1", "receita:bolo:passo-2"}
    assert bolo.texto.count("Receita Bolo de fubá") >= 2


def test_filtro_por_tipo(indice: IndiceDoCorpus) -> None:
    assert {a.trecho.tipo for a in indice.buscar("forno", tipos=["cozinha"]).achados} == {"cozinha"}
    vazio = indice.buscar("forno", tipos=["cardapio"])
    assert vazio.nada_relevante
    assert vazio.motivo == "nenhum trecho desse tipo"
    with pytest.raises(ValueError, match="tipos desconhecidos"):
        indice.buscar("forno", tipos=["moveis"])


def test_k_entre_um_e_o_maximo(indice: IndiceDoCorpus) -> None:
    assert len(indice.buscar("forno", k=0).achados) == 1
    assert len(indice.buscar("forno", k=99).achados) <= 12


# --------------------------------------------------------------------------- #
# O "não sei"
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pergunta", ["qual a capital da França?", "me conta uma piada", "integral de linha vetorial"]
)
def test_fora_da_plataforma_nao_responde(indice: IndiceDoCorpus, pergunta: str) -> None:
    resultado = indice.buscar(pergunta)
    assert resultado.nada_relevante
    assert resultado.motivo
    assert resultado.evidencia < indice.limiares.evidencia_minima


def test_pergunta_sem_palavra_util(indice: IndiceDoCorpus) -> None:
    resultado = indice.buscar("o que é isso?")
    assert (resultado.nada_relevante, resultado.motivo) == (True, "pergunta sem palavra útil")


def test_na_faixa_do_meio_a_margem_decide(indice: IndiceDoCorpus) -> None:
    candidatos = indice.candidatos("alcaparras azeite trufa")
    assert 0 < candidatos.evidencia < 1
    exigente = Limiares(
        evidencia_minima=0.1, evidencia_segura=0.99, margem_minima=1.1, cobertura_por_trecho=0.1
    )
    assert indice.decidir(candidatos, limiares=exigente).motivo == (
        "nenhum trecho se destaca como resposta"
    )
    tranquilo = Limiares(
        evidencia_minima=0.1, evidencia_segura=0.99, margem_minima=0.0, cobertura_por_trecho=0.1
    )
    assert not indice.decidir(candidatos, limiares=tranquilo).nada_relevante


def test_trecho_que_nao_cobre_a_pergunta_nao_entra(indice: IndiceDoCorpus) -> None:
    candidatos = indice.candidatos("alcaparras")
    ninguem = Limiares(
        evidencia_minima=0.0, evidencia_segura=0.0, margem_minima=0.0, cobertura_por_trecho=1.1
    )
    resultado = indice.decidir(candidatos, limiares=ninguem)
    assert resultado.motivo == "nenhum trecho cobre a pergunta"
    assert resultado.candidatos, "os candidatos continuam no resultado, para a medição"


class Semantico:
    """Um braço semântico falso: a pergunta sobre gelo é parecida com o trecho da geladeira."""

    nome = "semantico-falso"
    semantico = True

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "geladeira" in t or "gelada" in t else [0.0, 1.0] for t in textos]


def test_com_o_modelo_semantico_o_significado_basta() -> None:
    indice = IndiceDoCorpus(CORPUS, Analisador(), Semantico())
    resultado = indice.buscar("onde guardo a comida gelada?")
    assert not resultado.nada_relevante
    assert "conhecimento:geladeira" in ids(resultado)
    assert resultado.similaridade == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# As peças
# --------------------------------------------------------------------------- #


def test_fusao_por_posicao() -> None:
    fundido = fundir_por_posicao([3, 1], [1, 2])
    assert fundido[1] == pytest.approx(1 / 62 + 1 / 61)
    assert fundido[3] == pytest.approx(1 / 61)
    assert fundido[1] > fundido[3] > fundido[2] * 0.99


def test_margem_do_primeiro_sobre_o_segundo() -> None:
    assert _margem([]) == 0.0
    assert _margem([0.0, 0.0]) == 0.0
    assert _margem([2.0]) == 1.0
    assert _margem([4.0, 3.0]) == pytest.approx(0.25)


def test_diversidade_troca_o_quase_igual_pelo_diferente() -> None:
    vetores = [[1.0, 0.0], [0.99, 0.141], [0.0, 1.0]]
    candidatos = [(0, 1.0), (1, 0.95), (2, 0.9)]
    assert escolher_com_diversidade(candidatos, vetores, 2) == [0, 2]
    assert escolher_com_diversidade(candidatos, vetores, 2, lambda_=1.0) == [0, 1]
    por_grupo = escolher_com_diversidade(candidatos, vetores, 1, grupo=lambda _i: "mesmo")
    assert por_grupo == [0]
    assert escolher_com_diversidade([], vetores, 3) == []
