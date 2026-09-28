"""As peças da busca que não dependem de corpus: BM25, n-gramas com hash e a fusão.

A busca da plataforma (`retrieval.corpus`) monta o índice híbrido com estas
peças:

- **BM25** implementado aqui, e não importado: são sessenta linhas, ficam
  testáveis e poupam uma dependência;
- **n-gramas de caractere com hash**, o braço vetorial determinístico: não é
  embedding neural, e o nome diz isso. Aproxima variação de palavra e erro de
  digitação, não depende de nada e dá o mesmo vetor em qualquer máquina, que é o
  que o CI precisa. O modelo multilíngue, quando está instalado, entra no lugar
  dele pela mesma interface (`retrieval.corpus.vetores`);
- **Reciprocal Rank Fusion**, que junta os dois braços pela posição.

A base de fatos escritos à mão que morava aqui saiu: os fatos não tinham página
que os provasse. A base de hoje (`retrieval.corpus.conhecimento`) traz o trecho
literal de cada página, e a conferência prova que ele continua lá.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Final, Protocol

#: Parâmetros clássicos do BM25. `k1` controla a saturação de frequência: uma
#: palavra que aparece dez vezes não vale dez vezes mais que uma. `b` controla a
#: normalização por tamanho, para documento longo não vencer só por ser longo.
K1: Final = 1.5
B: Final = 0.75

#: Constante da Reciprocal Rank Fusion. 60 é o valor do artigo original
#: (Cormack et al., 2009) e existe para amortecer o topo: sem ela, o primeiro
#: colocado de uma lista domina a fusão inteira.
K_RRF: Final = 60

#: Dimensão do vetor de n-gramas. Potência de dois por conveniência do módulo.
DIMENSAO: Final = 256

#: Tamanho do n-grama de caractere. Três cobre radical de palavra em português
#: sem explodir o vocabulário.
N_GRAMA: Final = 3

#: Palavras que não discriminam nada em português e só somam ruído ao BM25.
VAZIAS: Final[frozenset[str]] = frozenset(
    (
        "a",
        "as",
        "o",
        "os",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "para",
        "com",
        "sem",
        "e",
        "ou",
        "mas",
        "que",
        "se",
        "ao",
        "aos",
        "é",
        "sao",
        "ser",
        "tem",
        "ter",
        "tenho",
        "posso",
        "pode",
        "quanto",
        "quantos",
        "qual",
        "quais",
        "como",
        "quando",
        "onde",
        "muito",
        "mais",
        "menos",
        "meu",
        "minha",
    )
)

_PALAVRA = re.compile(r"[a-z0-9]+")


def normalizar(texto: str) -> str:
    """Minúscula e sem acento. "Açafrão" e "acafrao" são a mesma busca."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def tokenizar(texto: str) -> list[str]:
    """Palavras significativas, sem acento e sem as vazias."""
    return [p for p in _PALAVRA.findall(normalizar(texto)) if p not in VAZIAS and len(p) > 1]


# --------------------------------------------------------------------------- #
# Braço lexical: BM25                                                          #
# --------------------------------------------------------------------------- #


class BM25:
    """Okapi BM25, implementado aqui em vez de importado.

    São sessenta linhas, ficam testáveis, e removem uma dependência de um
    repositório que quer ser clonado e executado sem cerimônia.
    """

    def __init__(self, documentos: list[list[str]]) -> None:
        self.documentos = documentos
        self.n = len(documentos)
        self.tamanhos = [len(d) for d in documentos]
        self.tamanho_medio = sum(self.tamanhos) / self.n if self.n else 0.0
        self.frequencias = [Counter(d) for d in documentos]

        aparicoes: Counter[str] = Counter()
        for doc in documentos:
            aparicoes.update(set(doc))
        self.idf = {
            termo: math.log(1 + (self.n - qtd + 0.5) / (qtd + 0.5))
            for termo, qtd in aparicoes.items()
        }

    def pontuar(self, consulta: list[str]) -> list[float]:
        notas = [0.0] * self.n
        for i, freq in enumerate(self.frequencias):
            tamanho = self.tamanhos[i] or 1
            for termo in consulta:
                if (f := freq.get(termo, 0)) == 0:
                    continue
                numerador = f * (K1 + 1)
                denominador = f + K1 * (1 - B + B * tamanho / (self.tamanho_medio or 1))
                notas[i] += self.idf.get(termo, 0.0) * numerador / denominador
        return notas


# --------------------------------------------------------------------------- #
# Braço vetorial                                                               #
# --------------------------------------------------------------------------- #


class Vetorizador(Protocol):
    """A interface que permite trocar o braço vetorial sem mexer na fusão."""

    def vetorizar(self, texto: str) -> list[float]: ...


class NGramasHasheados:
    """Vetor de n-gramas de caractere projetado por hashing.

    **Não é embedding neural, e o nome diz isso.** É o truque de hashing clássico:
    cada n-grama de três caracteres vira um índice por hash estável, e o vetor
    acumula contagem normalizada. Captura semelhança morfológica e tolera erro de
    digitação, que é o que importa num corpus pequeno de português de cozinha.

    O hash é SHA-1 truncado em vez de `hash()` porque o `hash()` do Python é
    aleatorizado por processo: o mesmo texto daria vetores diferentes entre
    execuções, e busca não determinística é impossível de testar.
    """

    def vetorizar(self, texto: str) -> list[float]:
        limpo = normalizar(texto)
        vetor = [0.0] * DIMENSAO
        for palavra in limpo.split():
            preenchida = f" {palavra} "
            for i in range(len(preenchida) - N_GRAMA + 1):
                pedaco = preenchida[i : i + N_GRAMA]
                digest = hashlib.sha1(pedaco.encode()).digest()
                vetor[int.from_bytes(digest[:4], "big") % DIMENSAO] += 1.0
        norma = math.sqrt(sum(v * v for v in vetor))
        return [v / norma for v in vetor] if norma else vetor


def cosseno(a: list[float], b: list[float]) -> float:
    """Ambos já vêm normalizados, então o produto escalar é o cosseno."""
    return sum(x * y for x, y in zip(a, b, strict=True))


# --------------------------------------------------------------------------- #
# Fusão e reranqueamento                                                       #
# --------------------------------------------------------------------------- #


def fundir_por_rrf(
    lexical: list[tuple[int, float]], vetorial: list[tuple[int, float]]
) -> dict[int, tuple[float, int | None, int | None]]:
    """Reciprocal Rank Fusion.

    Funde por **posição**, não por pontuação, e é essa a razão de existir: a nota
    do BM25 é ilimitada e a do cosseno vive entre -1 e 1. Somar as duas daria
    peso arbitrário a quem tem escala maior; normalizar exigiria conhecer a
    distribuição de antemão. Posição não tem esse problema.
    """
    fundido: dict[int, tuple[float, int | None, int | None]] = {}

    for posicao, (indice, _) in enumerate(lexical, start=1):
        nota, _, pv = fundido.get(indice, (0.0, None, None))
        fundido[indice] = (nota + 1 / (K_RRF + posicao), posicao, pv)

    for posicao, (indice, _) in enumerate(vetorial, start=1):
        nota, pl, _ = fundido.get(indice, (0.0, None, None))
        fundido[indice] = (nota + 1 / (K_RRF + posicao), pl, posicao)

    return fundido


__all__ = [
    "BM25",
    "DIMENSAO",
    "K_RRF",
    "N_GRAMA",
    "VAZIAS",
    "NGramasHasheados",
    "Vetorizador",
    "cosseno",
    "fundir_por_rrf",
    "normalizar",
    "tokenizar",
]
