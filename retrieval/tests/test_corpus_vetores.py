"""O braço vetorial: n-gramas determinísticos, o modelo carregado só quando usado, o cache e a reserva."""

from __future__ import annotations

import sys
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from retrieval.corpus import vetores
from retrieval.corpus.vetores import (
    NOME_NGRAMAS,
    CacheDeVetores,
    ComCache,
    ComFallback,
    FastEmbed,
    NGramas,
    cosseno,
    modo_escolhido,
    normalizado,
    vetorizador_padrao,
)


class ModeloFalso:
    """O que o FastEmbed devolve: um `.embed` que gera vetores (numpy, na vida real)."""

    def __init__(self) -> None:
        self.textos: list[str] = []

    def embed(self, textos: list[str]) -> Any:
        self.textos.extend(textos)
        for texto in textos:
            yield [float(len(texto)), 1.0, 0.0]


class Contador:
    """Um vetorizador que conta quantos textos passaram por ele."""

    nome = "contador"
    semantico = False

    def __init__(self) -> None:
        self.vistos: list[str] = []

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        self.vistos.extend(textos)
        return [[float(len(t)), 0.0] for t in textos]


class Quebrado:
    nome = "quebrado"
    semantico = True

    def vetorizar(self, _textos: Sequence[str]) -> list[list[float]]:
        raise OSError("modelo não baixado e sem rede")


def test_normalizado_e_cosseno() -> None:
    assert normalizado([3, 4]) == [0.6, 0.8]
    assert normalizado([0, 0]) == [0.0, 0.0]
    assert cosseno([0.6, 0.8], [0.6, 0.8]) == pytest.approx(1.0)


def test_ngramas_deterministicos_e_normalizados() -> None:
    a, b = NGramas().vetorizar(["farinha de trigo", "farinha de trigo"])
    assert a == b
    assert sum(x * x for x in a) == pytest.approx(1.0)
    assert NGramas.nome == NOME_NGRAMAS
    assert NGramas.semantico is False


def test_o_modelo_so_carrega_na_primeira_vez_que_e_usado(tmp_path: Path) -> None:
    chamadas: list[tuple[str, str, bool]] = []
    modelo = ModeloFalso()

    def carregar(nome: str, pasta: str, so_local: bool) -> ModeloFalso:
        chamadas.append((nome, pasta, so_local))
        return modelo

    fastembed = FastEmbed(tmp_path / "modelos", carregar=carregar)
    assert not fastembed.carregado
    assert chamadas == []
    assert fastembed.vetorizar([]) == []
    assert chamadas == [], "pedir nada não carrega o modelo"
    v = fastembed.vetorizar(["abc"])
    assert fastembed.carregado
    assert len(chamadas) == 1
    assert v == [normalizado([3.0, 1.0, 0.0])]
    fastembed.vetorizar(["de novo"])
    assert len(chamadas) == 1, "carrega uma vez só"
    assert chamadas[0][2] is True, "no padrão, só o que já está baixado"
    assert (tmp_path / "modelos").is_dir()
    assert fastembed.semantico is True


def test_o_carregador_de_verdade_importa_o_fastembed_so_na_hora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recebido: dict[str, Any] = {}

    class TextEmbedding:
        def __init__(self, **argumentos: Any) -> None:
            recebido.update(argumentos)

    falso = types.ModuleType("fastembed")
    falso.TextEmbedding = TextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", falso)
    vetores._carregar_fastembed("modelo-x", str(tmp_path), True)
    assert recebido == {
        "model_name": "modelo-x",
        "cache_dir": str(tmp_path),
        "local_files_only": True,
    }


def test_cache_em_memoria_e_em_disco(tmp_path: Path) -> None:
    chave = CacheDeVetores.chave("modelo", "texto")
    assert chave != CacheDeVetores.chave("outro", "texto")
    em_memoria = CacheDeVetores(None)
    em_memoria.guardar({chave: [0.5, 0.25]})
    assert em_memoria.buscar([chave, "falta"]) == {chave: [0.5, 0.25]}

    caminho = tmp_path / "estado" / "vetores.db"
    CacheDeVetores(caminho).guardar({chave: [0.5, 0.25]})
    CacheDeVetores(caminho).guardar({})
    assert CacheDeVetores(caminho).buscar([chave, "falta"]) == {chave: [0.5, 0.25]}


def test_com_cache_so_calcula_o_que_falta(tmp_path: Path) -> None:
    base = Contador()
    com_cache = ComCache(base, CacheDeVetores(tmp_path / "v.db"))
    assert (com_cache.nome, com_cache.semantico) == ("contador", False)
    primeira = com_cache.vetorizar(["a", "bb", "a"])
    assert base.vistos == ["a", "bb"], "o mesmo texto duas vezes é calculado uma"
    segunda = ComCache(base, CacheDeVetores(tmp_path / "v.db")).vetorizar(["bb", "ccc"])
    assert base.vistos == ["a", "bb", "ccc"]
    assert primeira[1] == segunda[0]


def test_reserva_quando_o_modelo_nao_carrega(caplog: pytest.LogCaptureFixture) -> None:
    reserva = Contador()
    vetorizador = ComFallback(Quebrado(), reserva)
    assert (vetorizador.nome, vetorizador.semantico) == ("quebrado", True)
    assert vetorizador.vetorizar(["x"]) == [[1.0, 0.0]]
    assert (vetorizador.nome, vetorizador.semantico) == ("contador", False)
    assert "n-gramas" in caplog.text
    vetorizador.vetorizar(["y"])
    assert reserva.vistos == ["x", "y"]


def test_o_modelo_que_carrega_fica() -> None:
    principal = Contador()
    vetorizador = ComFallback(principal, NGramas())
    vetorizador.vetorizar(["x"])
    vetorizador.vetorizar(["y"])
    assert principal.vistos == ["x", "y"]
    assert vetorizador.escolhido is principal


@pytest.mark.parametrize(
    ("valor", "modo"), [(None, "auto"), ("NEURAL", "neural"), ("ngramas", "ngramas"), ("x", "auto")]
)
def test_modo_pela_variavel(monkeypatch: pytest.MonkeyPatch, valor: str | None, modo: str) -> None:
    if valor is None:
        monkeypatch.delenv("SABOR_VETORIZADOR", raising=False)
    else:
        monkeypatch.setenv("SABOR_VETORIZADOR", valor)
    assert modo_escolhido() == modo


def test_vetorizador_padrao_por_modo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert vetorizador_padrao(tmp_path, modo="ngramas").nome == NOME_NGRAMAS
    assert vetorizador_padrao(None, modo="neural").nome == NOME_NGRAMAS

    monkeypatch.setattr(vetores.importlib.util, "find_spec", lambda _nome: None)
    assert vetorizador_padrao(tmp_path, modo="auto").nome == NOME_NGRAMAS

    monkeypatch.setattr(vetores.importlib.util, "find_spec", lambda _nome: object())
    vistos: list[bool] = []

    def carregar(_nome: str, _pasta: str, so_local: bool) -> ModeloFalso:
        vistos.append(so_local)
        return ModeloFalso()

    automatico = vetorizador_padrao(tmp_path, modo="auto", carregar=carregar)
    assert isinstance(automatico, ComFallback)
    automatico.vetorizar(["x"])
    neural = vetorizador_padrao(tmp_path, modo="neural", carregar=carregar)
    neural.vetorizar(["y"])
    assert vistos == [True, False], "no automático, nunca baixa; no neural, baixa se precisar"
    assert neural.semantico is True
