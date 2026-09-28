"""Como se fala o nome de um item: o gênero, o artigo e as contrações.

"Anotei creme de leite" é português capenga; "Anotei o creme de leite" é como ela
fala. O artigo depende do gênero do substantivo que manda no nome, o núcleo: a
primeira palavra, antes de " de ", " com " ou " em " ("creme", em "Creme de
leite"). A terminação da palavra não diz o gênero: é "o creme", "a couve", "a
carne", "o leite". Então:

- os 37 itens da planilha têm o artigo escrito à mão em `mise.categorias`, ao
  lado da categoria;
- um item que ela acrescenta leva o gênero do núcleo, num léxico curto dos
  substantivos de comida mais comuns; o plural sai do singular ("ovos" é o
  plural de "ovo");
- fora do léxico o gênero é desconhecido, e a frase é escrita de um jeito que
  não precisa de artigo ("Anotei na despensa: trufa branca."), em vez de chutar.

As frases usam o `NomeFalado` de `falar(nome)`: o nome no meio da frase, com o
artigo e com as contrações certas (do/da, no/na, pelo/pela, ao/à).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mise import categorias


class Genero(StrEnum):
    """O gênero e o número do nome, pelo artigo que ele pede."""

    MASCULINO = "o"
    FEMININO = "a"
    MASCULINO_PLURAL = "os"
    FEMININO_PLURAL = "as"

    @property
    def plural(self) -> bool:
        return self in (Genero.MASCULINO_PLURAL, Genero.FEMININO_PLURAL)

    @property
    def feminino(self) -> bool:
        return self in (Genero.FEMININO, Genero.FEMININO_PLURAL)

    def contrair(self, preposicao: str) -> str:
        """A preposição com o artigo: de → do/da/dos/das, em → no/na, por → pelo/pela, a → ao/à."""
        if preposicao == "de":
            return f"d{self.value}"
        if preposicao == "em":
            return f"n{self.value}"
        if preposicao == "por":
            return f"pel{self.value}"
        if preposicao == "a":
            return {"o": "ao", "a": "à", "os": "aos", "as": "às"}[self.value]
        raise ValueError(f"preposição sem contração: {preposicao!r}")

    def flexionar(self, masculino: str) -> str:
        """Um particípio ou adjetivo concordando com o nome: "comprado" → "compradas"."""
        raiz = masculino[:-1] if masculino.endswith("o") else masculino
        return raiz + {"o": "o", "a": "a", "os": "os", "as": "as"}[self.value]


def _palavras(texto: str) -> tuple[str, ...]:
    return tuple(texto.split())


#: Os substantivos de comida mais comuns, no singular e sem acento, com o gênero.
#: É o núcleo do nome de um item novo que decide o artigo.
LEXICO: Final[dict[str, Genero]] = {
    **dict.fromkeys(
        _palavras(
            "abacate abacaxi acafrao acem aceto achocolatado acucar adocante agriao aipim"
            " alecrim alho amendoim amido arroz atum azeite bacalhau bacon bicarbonato bife"
            " biscoito bolo brocolis cacau cafe caldo camarao champignon chantilly cha charque"
            " chocolate chuchu coco coentro cogumelo colorau cominho confeito corante cravo"
            " creme cupim cuscuz doce espaguete espinafre extrato farelo feijao fermento file"
            " frango fuba gengibre gergelim grao granulado hamburguer inhame iogurte jilo"
            " ketchup leite limao lombo louro macarrao mamao manjericao maracuja mel melao"
            " milho miolo molho morango musculo nabo oleo oregano ovo palmito pao parmesao"
            " patinho peito pepino pernil peru peixe pimentao polvilho porco presunto pudim"
            " queijo quiabo rabanete refrigerante repolho requeijao sagu sal salame salmao"
            " shoyu suco tempero tofu tomate toucinho trigo vinagre vinho"
        ),
        Genero.MASCULINO,
    ),
    **dict.fromkeys(
        _palavras(
            "abobora abobrinha acelga agua alcaparra alcatra alface ameixa amendoa asa aveia"
            " avela azeitona banana banha baunilha berinjela beterraba bolacha calabresa calda"
            " canela carne castanha cebola cebolinha cenoura cerveja clara coalhada cobertura"
            " costela couve coxa curcuma ervilha erva escarola essencia farinha farofa fecula"
            " folha fraldinha fruta gelatina geleia gema goiaba goiabada gordura granola"
            " hortela laranja lentilha levedura linguica lula maca maionese mandioca"
            " mandioquinha manga manteiga margarina massa melancia merluza moela mortadela"
            " mostarda mucarela mussarela nata noz paprica pasta pera pescada picanha pimenta"
            " polenta polpa ricota rosca rucula salsa salsicha salsinha sardinha semente soja"
            " sopa sobrecoxa tapioca tilapia torta trufa uva vagem verdura"
        ),
        Genero.FEMININO,
    ),
}


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def nucleo(nome: str) -> str:
    """O substantivo que manda no nome: a primeira palavra, antes de " de ", " com " ou " em ".

    Sem acento e em minúsculas: "Creme de leite" → "creme", "Milho verde em lata"
    → "milho", "Pimenta-do-reino" → "pimenta-do-reino".
    """
    texto = " ".join(_sem_acento(nome).lower().split())
    for separador in (" de ", " com ", " em "):
        texto = texto.split(separador, 1)[0]
    palavras = ["".join(c for c in p if c.isalpha() or c == "-") for p in texto.split()]
    return next((p.strip("-") for p in palavras if p.strip("-")), "")


def _singulares(palavra: str) -> tuple[str, ...]:
    """As formas de singular que um plural pode ter: "limoes" → "limao", "nozes" → "noz"."""
    formas: list[str] = []
    if palavra.endswith(("oes", "aes")):
        formas.append(palavra[:-3] + "ao")
    if palavra.endswith(("res", "zes", "ses")):
        formas.append(palavra[:-2])
    if palavra.endswith("s"):
        formas.append(palavra[:-1])
    return tuple(formas)


def genero_do_nucleo(palavra: str) -> Genero | None:
    """O gênero de um núcleo pelo léxico: direto, pela parte antes do hífen, ou pelo singular."""
    for candidata in dict.fromkeys((palavra, palavra.split("-", 1)[0])):
        if candidata in LEXICO:
            return LEXICO[candidata]
        for singular in _singulares(candidata):
            if singular in LEXICO:
                feminino = LEXICO[singular].feminino
                return Genero.FEMININO_PLURAL if feminino else Genero.MASCULINO_PLURAL
    return None


def genero_do_nome(nome: str) -> Genero | None:
    """O gênero do nome de um item: o da planilha, se for um dos 37; senão, o do núcleo."""
    artigo = categorias.ARTIGO_DA_PLANILHA.get(categorias.id_do_nome(nome))
    if artigo is not None:
        return Genero(artigo)
    return genero_do_nucleo(nucleo(nome))


def _minuscula(nome: str) -> str:
    """No meio da frase, "Cobertura de chocolate" vira "cobertura de chocolate"; sigla fica."""
    primeira = nome.split(" ", 1)[0]
    if len(primeira) > 1 and primeira.isupper():
        return nome
    return nome[:1].lower() + nome[1:]


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


@dataclass(frozen=True, slots=True)
class NomeFalado:
    """O nome de um item pronto para entrar numa frase, com o gênero, se ele é conhecido."""

    nome: str
    genero: Genero | None

    @property
    def conhecido(self) -> bool:
        return self.genero is not None

    @property
    def plural(self) -> bool:
        return self.genero is not None and self.genero.plural

    @property
    def minusculo(self) -> str:
        """O nome no meio da frase, sem artigo: "cobertura de chocolate"."""
        return _minuscula(" ".join(self.nome.split()))

    @property
    def maiusculo(self) -> str:
        """O nome no começo da frase, sem artigo: "Trufa branca"."""
        return _maiuscula(self.minusculo)

    def com_artigo(self, *, maiuscula: bool = False) -> str | None:
        """ "o creme de leite", "as alcaparras"; `None` quando o gênero não é conhecido."""
        if self.genero is None:
            return None
        texto = f"{self.genero.value} {self.minusculo}"
        return _maiuscula(texto) if maiuscula else texto

    def contraido(self, preposicao: str) -> str | None:
        """ "do creme de leite", "na cobertura", "pelas alcaparras"; `None` sem o gênero."""
        if self.genero is None:
            return None
        return f"{self.genero.contrair(preposicao)} {self.minusculo}"

    def de(self) -> str:
        """ "da cobertura de chocolate", ou "de tahine": com "de", o nome sozinho também serve."""
        return self.contraido("de") or f"de {self.minusculo}"

    def verbo(self, singular: str, plural: str) -> str:
        """O verbo concordando com o nome; sem saber o número, o singular."""
        return plural if self.plural else singular


def falar(nome: str) -> NomeFalado:
    """O nome de um item com o gênero que se sabe dele."""
    return NomeFalado(nome, genero_do_nome(nome))


__all__ = [
    "LEXICO",
    "Genero",
    "NomeFalado",
    "falar",
    "genero_do_nome",
    "genero_do_nucleo",
    "nucleo",
]
