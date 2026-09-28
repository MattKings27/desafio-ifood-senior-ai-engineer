"""As prateleiras da despensa: em que categoria cada item fica.

A tela filtra a despensa por categoria ("Carnes e ovos", "Laticínios") e a
agente fala da despensa do mesmo jeito. As categorias são dados, não conta:
estão aqui numa tabela fixa, e não são adivinhadas a cada leitura.

- **Os 37 itens da planilha** têm a categoria escrita à mão, pelo id (o slug do
  nome), e ao lado dela o artigo do nome ("o creme", "a couve"), que as frases
  para ela usam (`mise.genero`). É uma lista fechada, conferida em teste: nenhum
  item da planilha cai em "Outros".
- **Um item que ela acrescenta** leva a categoria que ela escolheu na tela. Sem
  escolha (pela conversa, por exemplo), a categoria sai das palavras do nome: a
  palavra mais específica ganha ("creme de leite" é laticínio antes de "leite";
  "milho verde" é conserva antes de "milho"). Sem palavra conhecida, "Outros".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Categoria:
    """Uma prateleira: o id que a tela filtra e o nome que ela lê."""

    id: str
    rotulo: str


#: As categorias, na ordem em que a tela as mostra.
CATEGORIAS: Final[tuple[Categoria, ...]] = (
    Categoria("proteinas", "Carnes e ovos"),
    Categoria("graos", "Grãos, farinhas e massas"),
    Categoria("hortifruti", "Hortifrúti"),
    Categoria("laticinios", "Laticínios"),
    Categoria("temperos", "Temperos e condimentos"),
    Categoria("oleos", "Óleos e azeites"),
    Categoria("conservas", "Conservas e molhos"),
    Categoria("confeitaria", "Confeitaria"),
    Categoria("outros", "Outros"),
)

POR_ID: Final[dict[str, Categoria]] = {c.id: c for c in CATEGORIAS}

#: A categoria de quem não se encaixa em nenhuma outra.
OUTROS: Final = POR_ID["outros"]

#: Os 37 itens da planilha da Dona Maria, pelo id: a categoria e o artigo do nome
#: ("o", "a", "os", "as"), os dois escritos à mão. O artigo não sai da terminação
#: da palavra: é "o creme", "a couve", "o leite ninho", "as alcaparras".
_PLANILHA: Final[dict[str, tuple[str, str]]] = {
    "arroz-branco-tipo-1": ("graos", "o"),
    "feijao-carioquinha": ("graos", "o"),
    "feijao-preto": ("graos", "o"),
    "peito-de-frango": ("proteinas", "o"),
    "carne-moida-patinho": ("proteinas", "a"),
    "carne-de-panela-acem": ("proteinas", "a"),
    "miolo-de-alcatra": ("proteinas", "o"),
    "bacon": ("proteinas", "o"),
    "ovos": ("proteinas", "os"),
    "farinha-de-trigo": ("graos", "a"),
    "farinha-de-mandioca": ("graos", "a"),
    "macarrao-espaguete": ("graos", "o"),
    "polenta-fuba": ("graos", "a"),
    "batata": ("hortifruti", "a"),
    "queijo-mussarela": ("laticinios", "o"),
    "queijo-parmesao-ralado": ("laticinios", "o"),
    "tomate": ("hortifruti", "o"),
    "cebola": ("hortifruti", "a"),
    "alho": ("hortifruti", "o"),
    "oleo-de-soja": ("oleos", "o"),
    "manteiga": ("laticinios", "a"),
    "sal": ("temperos", "o"),
    "acucar": ("confeitaria", "o"),
    "leite-integral": ("laticinios", "o"),
    "couve": ("hortifruti", "a"),
    "salsinha-cheiro-verde": ("hortifruti", "a"),
    "caldo-de-carne-tempero": ("temperos", "o"),
    "acafrao-em-po-curcuma": ("temperos", "o"),
    "alcaparras": ("conservas", "as"),
    "amendoa-fatiada": ("confeitaria", "a"),
    "chantilly": ("confeitaria", "o"),
    "leite-ninho-em-po": ("laticinios", "o"),
    "cobertura-de-chocolate": ("confeitaria", "a"),
    "azeite-de-oliva-extra-virgem": ("oleos", "o"),
    "aceto-balsamico": ("temperos", "o"),
    "canela-em-po": ("temperos", "a"),
    "adocante-liquido": ("confeitaria", "o"),
}

#: A categoria de cada um dos 37 itens da planilha, pelo id.
DA_PLANILHA: Final[dict[str, str]] = {id_: categoria for id_, (categoria, _) in _PLANILHA.items()}

#: O artigo do nome de cada um dos 37 itens da planilha, pelo id.
ARTIGO_DA_PLANILHA: Final[dict[str, str]] = {id_: artigo for id_, (_, artigo) in _PLANILHA.items()}

#: As palavras que dizem a categoria de um item novo, sem acento e em minúsculas.
PALAVRAS: Final[dict[str, tuple[str, ...]]] = {
    "proteinas": (
        "frango",
        "carne",
        "boi",
        "porco",
        "suino",
        "linguica",
        "calabresa",
        "bacon",
        "presunto",
        "peito",
        "coxa",
        "sobrecoxa",
        "file",
        "alcatra",
        "patinho",
        "acem",
        "costela",
        "cupim",
        "maminha",
        "picanha",
        "peixe",
        "tilapia",
        "camarao",
        "ovo",
        "ovos",
        "salsicha",
        "hamburguer",
    ),
    "graos": (
        "arroz",
        "feijao",
        "lentilha",
        "grao de bico",
        "farinha",
        "fuba",
        "polenta",
        "macarrao",
        "espaguete",
        "massa",
        "aveia",
        "trigo",
        "milho",
        "amido",
        "tapioca",
        "cuscuz",
        "flocao",
        "pao",
    ),
    "hortifruti": (
        "batata",
        "tomate",
        "cebola",
        "alho",
        "couve",
        "alface",
        "cenoura",
        "abobrinha",
        "abobora",
        "pimentao",
        "salsinha",
        "cebolinha",
        "cheiro verde",
        "coentro",
        "limao",
        "laranja",
        "banana",
        "maca",
        "mandioca",
        "aipim",
        "chuchu",
        "berinjela",
        "repolho",
        "brocolis",
        "espinafre",
        "rucula",
        "pepino",
        "beterraba",
        "inhame",
        "quiabo",
        "vagem",
        "maracuja",
        "morango",
        "abacaxi",
        "mamao",
        "fruta",
        "verdura",
        "legume",
    ),
    "laticinios": (
        "leite",
        "queijo",
        "requeijao",
        "iogurte",
        "manteiga",
        "creme de leite",
        "nata",
        "mussarela",
        "parmesao",
        "ricota",
        "cream cheese",
        "margarina",
    ),
    "temperos": (
        "sal",
        "pimenta",
        "oregano",
        "cominho",
        "colorau",
        "paprica",
        "canela",
        "cravo",
        "noz moscada",
        "louro",
        "caldo",
        "tempero",
        "acafrao",
        "curcuma",
        "curry",
        "vinagre",
        "aceto",
        "mostarda",
        "alecrim",
        "tomilho",
        "manjericao",
    ),
    "oleos": ("oleo", "azeite", "gordura", "banha"),
    "conservas": (
        "alcaparra",
        "alcaparras",
        "azeitona",
        "palmito",
        "milho verde",
        "ervilha",
        "extrato de tomate",
        "molho",
        "atum",
        "sardinha",
        "conserva",
        "ketchup",
        "maionese",
        "shoyu",
    ),
    "confeitaria": (
        "acucar",
        "adocante",
        "chocolate",
        "cacau",
        "chantilly",
        "amendoa",
        "castanha",
        "nozes",
        "coco",
        "leite condensado",
        "fermento",
        "gelatina",
        "granulado",
        "baunilha",
        "essencia",
        "doce de leite",
        "mel",
        "cobertura",
    ),
}

_NAO_ALFANUM: Final = re.compile(r"[^a-z0-9]+")


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento, só letras e números separados por um espaço."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c)).lower()
    return " ".join(_NAO_ALFANUM.sub(" ", sem_acento).split())


def id_do_nome(nome: str) -> str:
    """O id estável de um item da planilha: o slug do nome.

    >>> id_do_nome("Carne moída (patinho)")
    'carne-moida-patinho'
    """
    decomposto = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c)).lower()
    return _NAO_ALFANUM.sub("-", sem_acento).strip("-")


def categoria(id_: str) -> Categoria:
    """A categoria pelo id; id desconhecido é "Outros"."""
    return POR_ID.get(id_, OUTROS)


def valida(id_: str) -> bool:
    """O id é de uma categoria que a tela conhece?"""
    return id_ in POR_ID


def pelo_nome(nome: str) -> Categoria:
    """A categoria de um item novo, pelas palavras do nome: a mais específica ganha.

    "Creme de leite" casa "leite" (laticínio) e "creme de leite" (laticínio);
    "Leite condensado" casa "leite" e "leite condensado", e a de duas palavras,
    confeitaria, ganha. As palavras casam inteiras: "sal" não casa "salsinha".
    """
    alvo = f" {_normalizar(nome)} "
    melhor: tuple[int, int] = (0, 0)
    escolhida = OUTROS
    for id_, palavras in PALAVRAS.items():
        for palavra in palavras:
            especificidade = (len(palavra.split()), len(palavra))
            # Empate fica com a categoria que vem antes: a ordem de PALAVRAS.
            if f" {palavra} " in alvo and especificidade > melhor:
                melhor, escolhida = especificidade, POR_ID[id_]
    return escolhida


def do_item(id_: str, nome: str) -> Categoria:
    """A categoria de um item: a da planilha, se for um dos 37; senão, pelo nome."""
    fixa = DA_PLANILHA.get(id_)
    return POR_ID[fixa] if fixa is not None else pelo_nome(nome)


__all__ = [
    "ARTIGO_DA_PLANILHA",
    "CATEGORIAS",
    "DA_PLANILHA",
    "OUTROS",
    "PALAVRAS",
    "POR_ID",
    "Categoria",
    "categoria",
    "do_item",
    "id_do_nome",
    "pelo_nome",
    "valida",
]
