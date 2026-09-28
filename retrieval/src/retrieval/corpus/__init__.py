"""A plataforma inteira como corpus: trechos com fonte, busca híbrida e o "não sei".

Este pacote não importa o motor. Quem monta os trechos a partir da despensa,
da cozinha, das receitas e do resto é `mise.corpus`; aqui moram a forma do
trecho, o analisador de português, os dois braços da busca, a fusão, a
diversidade, o portão do "não sei" e a base de conhecimento de cozinha com as
páginas que a sustentam.

Nada pesado carrega junto com o pacote: o modelo semântico só carrega na
primeira busca que precisar dele (`retrieval.corpus.vetores`).
"""

from retrieval.corpus.analisador import Analisador, sinonimos_do_casamento
from retrieval.corpus.busca import (
    K_MAXIMO,
    K_PADRAO,
    Achado,
    Candidatos,
    IndiceDoCorpus,
    Limiares,
    ResultadoDaBusca,
)
from retrieval.corpus.conhecimento import Fato, carregar_fatos, trechos_do_conhecimento
from retrieval.corpus.modelo import TIPOS, Trecho
from retrieval.corpus.vetores import NGramas, Vetorizador, vetorizador_padrao

__all__ = [
    "K_MAXIMO",
    "K_PADRAO",
    "TIPOS",
    "Achado",
    "Analisador",
    "Candidatos",
    "Fato",
    "IndiceDoCorpus",
    "Limiares",
    "NGramas",
    "ResultadoDaBusca",
    "Trecho",
    "Vetorizador",
    "carregar_fatos",
    "sinonimos_do_casamento",
    "trechos_do_conhecimento",
    "vetorizador_padrao",
]
