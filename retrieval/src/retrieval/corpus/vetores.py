"""O braço vetorial da busca: um modelo multilíngue, ou os n-gramas quando ele não está.

**O modelo.** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
pelo FastEmbed (ONNX, sem PyTorch), 384 dimensões. Ele aproxima perguntas que
não dividem palavra com o trecho ("o feijão estraga rápido?" e "feijão cozido
dura cinco dias na geladeira"), que é o que a busca por palavra não faz.

**Preguiçoso.** Nada aqui importa o FastEmbed ao carregar o módulo: o servidor
do agente precisa conectar em segundos, e a imagem do motor sobe sem rede.
O modelo carrega na primeira consulta que precisar dele. No modo automático
ele só é usado se já estiver baixado (`local_files_only`); sem o pacote, sem o
modelo ou sem rede, a busca segue com os n-gramas, e diz qual braço usou.

**Cache.** O vetor de um texto não muda enquanto o texto e o modelo não mudam.
`.estado/vetores.db` guarda cada vetor pela chave sha256(modelo + texto): o
índice é refeito quando a despensa muda, e só os trechos novos passam pelo
modelo.

**Os n-gramas.** O vetorizador de n-gramas de caractere com hash
(`retrieval.indice.NGramasHasheados`) é determinístico, não depende de nada e
aproxima variação de palavra e erro de digitação. É o que roda nos testes e no
CI, e a ablação do conjunto dourado mede a diferença entre os dois.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import math
import os
import sqlite3
import threading
from array import array
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Final, Protocol

from retrieval.indice import NGramasHasheados

logger = logging.getLogger(__name__)

#: O modelo multilíngue da busca semântica.
MODELO_SEMANTICO: Final = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

#: Nome do vetorizador de n-gramas, que entra na chave do cache como o do modelo.
NOME_NGRAMAS: Final = "ngramas-hasheados-256"

#: Qual braço vetorial usar: `auto` (o modelo, se já estiver baixado), `neural`
#: (o modelo, baixando se precisar) ou `ngramas`.
VARIAVEL_DO_VETORIZADOR: Final = "SABOR_VETORIZADOR"

#: Onde o FastEmbed guarda o modelo baixado, dentro da pasta de estado.
PASTA_DOS_MODELOS: Final = "modelos"

#: O arquivo do cache de vetores, dentro da pasta de estado.
ARQUIVO_DO_CACHE: Final = "vetores.db"


class Vetorizador(Protocol):
    """O que a busca precisa de um braço vetorial."""

    @property
    def nome(self) -> str:
        """O que identifica o modelo (entra na chave do cache)."""

    @property
    def semantico(self) -> bool:
        """O cosseno dele mede significado (modelo), ou só forma de palavra (n-gramas)?"""

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        """Um vetor normalizado para cada texto, na mesma ordem."""


def normalizado(vetor: Iterable[float]) -> list[float]:
    """O vetor com norma 1 (o produto escalar vira cosseno); o nulo fica nulo."""
    valores = [float(v) for v in vetor]
    norma = math.sqrt(sum(v * v for v in valores))
    return [v / norma for v in valores] if norma else valores


def cosseno(a: Sequence[float], b: Sequence[float]) -> float:
    """Os dois já normalizados: o produto escalar é o cosseno."""
    return sum(x * y for x, y in zip(a, b, strict=True))


class NGramas:
    """Os n-gramas de caractere com hash: determinísticos e sem dependência."""

    nome = NOME_NGRAMAS
    semantico = False

    def __init__(self) -> None:
        self._base = NGramasHasheados()

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        return [self._base.vetorizar(t) for t in textos]


#: Monta o modelo do FastEmbed: `(nome do modelo, pasta, só local) -> objeto com .embed`.
Carregador = Callable[[str, str, bool], Any]


def _carregar_fastembed(modelo: str, pasta: str, so_local: bool) -> Any:
    """O `TextEmbedding` do FastEmbed, importado só agora."""
    fastembed = importlib.import_module("fastembed")
    return fastembed.TextEmbedding(model_name=modelo, cache_dir=pasta, local_files_only=so_local)


class FastEmbed:
    """O modelo multilíngue pelo FastEmbed, carregado na primeira vez que for usado."""

    semantico = True

    def __init__(
        self,
        pasta: Path,
        *,
        modelo: str = MODELO_SEMANTICO,
        so_local: bool = True,
        carregar: Carregador = _carregar_fastembed,
    ) -> None:
        self.nome = modelo
        self._pasta = pasta
        self._so_local = so_local
        self._carregar = carregar
        self._modelo: Any = None
        self._trava = threading.Lock()

    @property
    def carregado(self) -> bool:
        return self._modelo is not None

    def _garantir(self) -> Any:
        with self._trava:
            if self._modelo is None:
                self._pasta.mkdir(parents=True, exist_ok=True)
                self._modelo = self._carregar(self.nome, str(self._pasta), self._so_local)
            return self._modelo

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        if not textos:
            return []
        modelo = self._garantir()
        return [normalizado(v) for v in modelo.embed(list(textos))]


class CacheDeVetores:
    """Os vetores já calculados, em SQLite, pela chave sha256(modelo + texto)."""

    def __init__(self, caminho: Path | None) -> None:
        self._caminho = caminho
        self._memoria: dict[str, list[float]] = {}
        self._trava = threading.Lock()
        if caminho is not None:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            with self._conectar() as conexao:
                conexao.execute(
                    "CREATE TABLE IF NOT EXISTS vetores "
                    "(chave TEXT PRIMARY KEY, vetor BLOB NOT NULL)"
                )

    def _conectar(self) -> sqlite3.Connection:
        assert self._caminho is not None
        return sqlite3.connect(self._caminho, timeout=5)

    @staticmethod
    def chave(modelo: str, texto: str) -> str:
        return hashlib.sha256(f"{modelo}\n{texto}".encode()).hexdigest()

    def buscar(self, chaves: Sequence[str]) -> dict[str, list[float]]:
        """Os vetores que o cache tem, das chaves pedidas."""
        with self._trava:
            achados = {c: self._memoria[c] for c in chaves if c in self._memoria}
            faltam = [c for c in chaves if c not in achados]
            if faltam and self._caminho is not None:
                with self._conectar() as conexao:
                    for inicio in range(0, len(faltam), 500):
                        lote = faltam[inicio : inicio + 500]
                        marcas = ",".join("?" for _ in lote)
                        consulta = f"SELECT chave, vetor FROM vetores WHERE chave IN ({marcas})"
                        for chave, bruto in conexao.execute(consulta, lote):
                            vetor = array("f")
                            vetor.frombytes(bruto)
                            achados[chave] = self._memoria[chave] = list(vetor)
            return achados

    def guardar(self, vetores: dict[str, list[float]]) -> None:
        with self._trava:
            self._memoria.update(vetores)
            if self._caminho is None or not vetores:
                return
            with self._conectar() as conexao:
                conexao.executemany(
                    "INSERT OR REPLACE INTO vetores (chave, vetor) VALUES (?, ?)",
                    [(c, array("f", v).tobytes()) for c, v in vetores.items()],
                )


class ComCache:
    """Um vetorizador que só calcula o que o cache ainda não tem."""

    def __init__(self, base: Vetorizador, cache: CacheDeVetores) -> None:
        self.base = base
        self.cache = cache

    @property
    def nome(self) -> str:
        return self.base.nome

    @property
    def semantico(self) -> bool:
        return self.base.semantico

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        chaves = [CacheDeVetores.chave(self.nome, t) for t in textos]
        prontos = self.cache.buscar(chaves)
        faltam = list(dict.fromkeys(c for c in chaves if c not in prontos))
        if faltam:
            por_chave = dict(zip(chaves, textos, strict=True))
            novos = self.base.vetorizar([por_chave[c] for c in faltam])
            calculados = dict(zip(faltam, novos, strict=True))
            self.cache.guardar(calculados)
            prontos = {**prontos, **calculados}
        return [prontos[c] for c in chaves]


def modo_escolhido() -> str:
    """O modo pedido pela variável de ambiente: `auto`, `neural` ou `ngramas`."""
    modo = os.environ.get(VARIAVEL_DO_VETORIZADOR, "auto").strip().lower()
    return modo if modo in {"auto", "neural", "ngramas"} else "auto"


def vetorizador_padrao(
    pasta_do_estado: Path | None,
    *,
    modo: str | None = None,
    carregar: Carregador = _carregar_fastembed,
) -> Vetorizador:
    """O braço vetorial da plataforma, com cache, escolhido pelo modo.

    - `ngramas`: sempre os n-gramas;
    - `neural`: o modelo, baixando se ainda não estiver na pasta;
    - `auto`: o modelo só se o pacote existir e o modelo já estiver baixado.

    A escolha acontece aqui, mas o modelo só carrega no primeiro `vetorizar`:
    quem cai para os n-gramas por falta do modelo é `ComFallback`.
    """
    escolhido = modo or modo_escolhido()
    cache = CacheDeVetores(pasta_do_estado / ARQUIVO_DO_CACHE if pasta_do_estado else None)
    ngramas = ComCache(NGramas(), cache)
    if escolhido == "ngramas" or pasta_do_estado is None:
        return ngramas
    if escolhido == "auto" and importlib.util.find_spec("fastembed") is None:
        return ngramas
    modelo = FastEmbed(
        pasta_do_estado / PASTA_DOS_MODELOS, so_local=escolhido == "auto", carregar=carregar
    )
    return ComFallback(ComCache(modelo, cache), ngramas)


class ComFallback:
    """O modelo; se ele não carregar, os n-gramas, para sempre neste processo.

    O `nome` e o `semantico` só se decidem na primeira vetorização: antes disso,
    ninguém sabe se o modelo está baixado, e perguntar exigiria carregá-lo.
    """

    def __init__(self, principal: Vetorizador, reserva: Vetorizador) -> None:
        self._principal = principal
        self._reserva = reserva
        self._escolhido: Vetorizador | None = None

    @property
    def escolhido(self) -> Vetorizador:
        return self._escolhido or self._principal

    @property
    def nome(self) -> str:
        return self.escolhido.nome

    @property
    def semantico(self) -> bool:
        return self.escolhido.semantico

    def vetorizar(self, textos: Sequence[str]) -> list[list[float]]:
        if self._escolhido is None:
            try:
                vetores = self._principal.vetorizar(textos)
            except Exception as erro:  # qualquer falha do modelo cai para a reserva
                logger.warning(
                    "o modelo de busca semântica não carregou (%s); sigo com os n-gramas",
                    erro,
                )
                self._escolhido = self._reserva
            else:
                self._escolhido = self._principal
                return vetores
        return self._escolhido.vetorizar(textos)


__all__ = [
    "ARQUIVO_DO_CACHE",
    "MODELO_SEMANTICO",
    "NOME_NGRAMAS",
    "PASTA_DOS_MODELOS",
    "VARIAVEL_DO_VETORIZADOR",
    "CacheDeVetores",
    "ComCache",
    "ComFallback",
    "FastEmbed",
    "NGramas",
    "Vetorizador",
    "cosseno",
    "modo_escolhido",
    "normalizado",
    "vetorizador_padrao",
]
