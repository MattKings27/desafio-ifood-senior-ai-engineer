"""O trecho: a menor unidade da plataforma que o agente pode citar.

Cada parte do site vira trechos (um item da despensa, um equipamento da
cozinha, o cabeçalho de uma receita, cada passo dela, uma compra, um fato da
base de cozinha). O trecho sabe três coisas que a resposta precisa:

- **de onde veio** (`fonte`), para ela conferir;
- **que tela o mostra** (`rota`), para o chip "De onde eu tirei isso" abrir no
  lugar certo; `None` só na base de conhecimento de cozinha, que não tem tela;
- **em que contexto ele está** (`cabecalho`), escrito por código e não por modelo:
  "Receita Frango xadrez, tudogostoso.com.br, passo 3 de 7:". Um passo solto
  ("junte o molho e mexa") não diz de que receita é; com o cabeçalho, a busca
  acha o passo certo e o agente sabe o que está lendo. É a técnica de
  recuperação contextual, feita de forma determinística: sem custo e sem risco
  de o resumo inventar alguma coisa.

Um trecho pode ter um pai (`pai`): o passo aponta para o cabeçalho da receita.
Quando a busca acha o passo, a resposta leva junto o cabeçalho, para o
agente saber rendimento, fonte e situação da receita sem outra consulta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

#: As partes da plataforma, que são também o filtro `tipos` da consulta.
TIPOS: Final[tuple[str, ...]] = (
    "despensa",
    "cozinha",
    "receita",
    "avaliacao",
    "cardapio",
    "orcamento",
    "conhecimento",
)


@dataclass(frozen=True, slots=True)
class Trecho:
    """Um pedaço citável da plataforma, com a fonte e a tela que o mostra."""

    id: str
    tipo: str
    rota: str | None
    fonte: str
    cabecalho: str
    corpo: str
    #: O trecho maior de onde este saiu (o cabeçalho da receita, para um passo).
    pai: str | None = None
    #: A posição dentro do pai, para os filhos voltarem na ordem em que aparecem.
    ordem: int = 0
    #: Palavras que ela usaria para perguntar e o texto não diz ("marmita").
    #: Entram só na busca por palavra, nunca no texto devolvido.
    palavras: tuple[str, ...] = field(default=())
    #: O nome curto do registro, para o chip de fonte ("Óleo de soja", "Forno").
    #: Sem ele, vale o cabeçalho sem os dois pontos.
    rotulo: str = ""

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo de trecho desconhecido: {self.tipo!r}")
        if not self.id.strip():
            raise ValueError("trecho sem id")
        if not self.corpo.strip():
            raise ValueError(f"trecho {self.id!r} sem texto")

    @property
    def nome(self) -> str:
        """O nome curto do registro: o `rotulo`, ou o cabeçalho sem os dois pontos."""
        return self.rotulo or self.cabecalho.rstrip(": ")

    @property
    def texto(self) -> str:
        """O que o agente lê: o cabeçalho e o corpo."""
        return f"{self.cabecalho} {self.corpo}".strip()

    @property
    def indexavel(self) -> str:
        """O que a busca lê: o texto e as palavras de apoio."""
        return " ".join((self.texto, *self.palavras))


__all__ = ["TIPOS", "Trecho"]
