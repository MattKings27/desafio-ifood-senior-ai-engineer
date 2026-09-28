"""A linha que traz só o nome de um tempero vai a gosto: a convenção da receita brasileira.

Receita brasileira escreve "Sal", "Sal e pimenta-do-reino", "Azeite",
"Cheiro-verde" ou "Orégano" na lista de ingredientes, sem número e sem "a
gosto", e quer dizer exatamente isso: a gosto. Ler essas linhas como "não
entendi" segurava a receita inteira numa pergunta sobre o sal.

A regra mora aqui, no motor, e não só na leitura da página, porque vale para
dois caminhos: a linha que a leitura interpreta agora (`retrieval.quantidades`)
e a receita que já estava guardada no catálogo com a linha marcada como não
lida (`Receita.de_dict`), que passa a valer a gosto sem precisar buscar a
página de novo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Os temperos que a receita brasileira lista só pelo nome, sem quantidade, e
#: que por convenção vão a gosto. Escritos sem acento, em minúscula e com
#: espaço no lugar do hífen. A lista é fechada de propósito: "Milho",
#: "Ervilha", "Alho amassado" ou "Caldo de galinha" sem número pedem uma
#: quantidade que muda a compra e o custo, e continuam virando pergunta;
#: "temperos de sua preferência" também, porque não diz nem qual tempero é.
TEMPEROS_A_GOSTO: Final[frozenset[str]] = frozenset(
    {
        "sal",
        "sal refinado",
        "sal grosso",
        "sal marinho",
        "flor de sal",
        "pimenta",
        "pimenta do reino",
        "pimenta preta",
        "pimenta branca",
        "pimenta calabresa",
        "azeite",
        "azeite de oliva",
        "azeite extra virgem",
        "azeite de oliva extra virgem",
        "oleo",
        "cheiro verde",
        "salsinha",
        "salsa",
        "cebolinha",
        "coentro",
        "oregano",
        "manjericao",
        "alecrim",
        "tomilho",
        "louro",
        "folha de louro",
        "noz moscada",
        "cominho",
        "colorau",
        "paprica",
        "paprica doce",
        "paprica defumada",
        "acafrao",
        "curcuma",
        "canela",
        "cravo",
        "cravo da india",
    }
)

#: O que vem depois do nome do tempero e não muda o tempero: "salsinha picada",
#: "pimenta-do-reino moída", "orégano seco", "canela em pó".
_QUALIFICADORES: Final[tuple[str, ...]] = (
    "picado",
    "picada",
    "picados",
    "picadas",
    "picadinho",
    "picadinha",
    "fresco",
    "fresca",
    "frescos",
    "frescas",
    "seco",
    "seca",
    "secos",
    "secas",
    "moido",
    "moida",
    "ralado",
    "ralada",
    "em po",
    "em flocos",
    "em folhas",
)

#: O que separa um tempero do outro na mesma linha: "sal, pimenta e orégano".
_ENTRE_TEMPEROS: Final = re.compile(r"\s*(?:[,;/+&]|\be\b|\bou\b)\s*")
#: "Cheiro-verde (salsinha e cebolinha)": o parêntese só explica o tempero.
_PARENTESE: Final = re.compile(r"\([^)]*\)")

#: A observação da linha lida como "a gosto" pela convenção, e não pela receita.
A_GOSTO_POR_CONVENCAO: Final = "a gosto, a receita não diz quanto"


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _sem_qualificador(parte: str) -> str:
    """ "pimenta do reino moida" vira "pimenta do reino"; "folhas de louro", "folha de louro"."""
    palavras = parte.split()
    tirou = True
    while tirou and palavras:
        tirou = False
        for qualificador in _QUALIFICADORES:
            tamanho = len(qualificador.split())
            if len(palavras) > tamanho and " ".join(palavras[-tamanho:]) == qualificador:
                palavras = palavras[:-tamanho]
                tirou = True
                break
    tempero = " ".join(palavras)
    if tempero not in TEMPEROS_A_GOSTO and palavras and palavras[0].endswith("s"):
        singular = " ".join([palavras[0][:-1], *palavras[1:]])
        if singular in TEMPEROS_A_GOSTO:
            return singular
    return tempero


def so_tempero(texto: str) -> bool:
    """A linha traz só nomes de tempero, sem número: "Sal", "Sal e pimenta-do-reino", "Azeite".

    Todo pedaço da linha tem que ser um tempero de `TEMPEROS_A_GOSTO`: "Sal e
    milho" não é, e a linha com número diz quanto vai.
    """
    limpo = _PARENTESE.sub(" ", _sem_acento(texto)).replace("-", " ").strip(" .;:!")
    if not limpo or re.search(r"\d", limpo):
        return False
    partes = [" ".join(p.split()) for p in _ENTRE_TEMPEROS.split(limpo)]
    partes = [p for p in partes if p]
    return bool(partes) and all(_sem_qualificador(p) in TEMPEROS_A_GOSTO for p in partes)


__all__ = ["A_GOSTO_POR_CONVENCAO", "TEMPEROS_A_GOSTO", "so_tempero"]
