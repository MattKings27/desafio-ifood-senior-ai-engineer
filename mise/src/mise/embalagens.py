"""O peso da embalagem que a planilha não diz, estimado por uma página de supermercado.

A planilha dela diz "Cobertura de chocolate · 1 · un · R$ 79,90": o preço da
embalagem, sem o peso. Dividir o preço por "1" e tratar como 1 kg já deu um
custo de R$ 15.980,00 uma vez; perguntar o peso a ela é o que a plataforma não
faz mais. O peso sai da página de um produto de supermercado de São Paulo, o
da mesma categoria com o preço mais perto do que ela pagou, e as regras são as
do preço de referência (`mise.referencias`):

- **é estimativa, e diz de onde veio**: "cerca de 1 kg (estimativa: a embalagem
  de cobertura de chocolate com o preço mais perto dos R$ 79,90 que a senhora
  pagou é a de 1 kg, Cobertura Garoto Chocolate Ao Leite 1kg, R$ 71,30 no
  Carrefour, 27/09/2026; a senhora pode corrigir)";
- **o que ela disser vale mais**: o peso que ela informa (`informar_embalagem`)
  troca a estimativa, e a conta passa a ser a dela;
- **sem página, não há número**: o item que não está aqui fica sem custo por
  quilo, e a receita que pede o peso dele fica de fora, sem pergunta.

`make conferir-referencias` busca cada página de novo e prova que o produto, o
tamanho no nome e o preço continuam lá.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from mise.dinheiro import Dinheiro
from mise.unidades import Dimensao, Quantidade

if TYPE_CHECKING:
    from collections.abc import Iterable


def _chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().replace("-", " ").split())


@dataclass(frozen=True, slots=True)
class EmbalagemDeReferencia:
    """O peso de uma embalagem, lido no nome do produto de uma página de supermercado."""

    #: Os nomes do item na despensa que esta embalagem estima.
    itens: tuple[str, ...]
    produto: str
    quantidade: Decimal
    #: `g`, `kg`, `ml` ou `L`.
    unidade: str
    preco: Dinheiro
    url: str
    site: str
    data: dt.date
    #: O campo do JSON-LD com o preço e o trecho literal dele.
    campo: str
    trecho: str

    @property
    def conteudo(self) -> Quantidade:
        fator = {"g": Decimal("0.001"), "kg": Decimal(1), "ml": Decimal("0.001"), "l": Decimal(1)}
        dimensao = Dimensao.MASSA if self.unidade.casefold() in ("g", "kg") else Dimensao.VOLUME
        return Quantidade(self.quantidade * fator[self.unidade.casefold()], dimensao)

    @property
    def conteudo_texto(self) -> str:
        from mise.despensa_json import quantidade_texto  # noqa: PLC0415

        return quantidade_texto(self.conteudo)

    @property
    def data_texto(self) -> str:
        return f"{self.data:%d/%m/%Y}"

    def texto(self, nome: str, pago: Dinheiro) -> str:
        """A frase que acompanha o peso estimado, com a fonte e o convite a corrigir."""
        return (
            f"cerca de {self.conteudo_texto} (estimativa: a embalagem de {nome.lower()} com o "
            f"preço mais perto dos {pago} que a senhora pagou é a de {self.conteudo_texto}, "
            f"{self.produto}, {self.preco} no {self.site}, {self.data_texto}; a senhora pode "
            "corrigir)"
        )

    def casa(self, nome: str) -> bool:
        return _chave(nome) in {_chave(i) for i in self.itens}


#: As embalagens de referência conhecidas. A cobertura de chocolate da planilha
#: custou R$ 79,90: nas páginas de supermercado de São Paulo, a barra de 500 g
#: sai por volta de R$ 50,00, a de 2,1 kg passa de R$ 160,00, e a de 1 kg é a
#: que tem o preço mais perto do que ela pagou.
EMBALAGENS_DE_REFERENCIA: Final[tuple[EmbalagemDeReferencia, ...]] = (
    EmbalagemDeReferencia(
        itens=("Cobertura de chocolate", "Chocolate para cobertura"),
        produto="Cobertura Garoto Chocolate Ao Leite 1kg",
        quantidade=Decimal(1),
        unidade="kg",
        preco=Dinheiro(Decimal("71.3")),
        url="https://www.carrefour.com.br/cobertura-garoto-chocolate-ao-leite-1kg-mp951902793/p",
        site="Carrefour",
        data=dt.date(2026, 9, 27),
        campo="offers.price",
        trecho='"price":71.3',
    ),
)


def embalagem_de_referencia(
    nome: str, embalagens: Iterable[EmbalagemDeReferencia] = EMBALAGENS_DE_REFERENCIA
) -> EmbalagemDeReferencia | None:
    """A embalagem de referência do item da despensa com este nome, se há."""
    return next((e for e in embalagens if e.casa(nome)), None)


__all__ = ["EMBALAGENS_DE_REFERENCIA", "EmbalagemDeReferencia", "embalagem_de_referencia"]
