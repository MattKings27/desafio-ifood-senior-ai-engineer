"""Valor monetário em reais.

`float` não representa R$ 0,10 exatamente. Num motor que soma dezenas de custos
de ingrediente e depois divide por 0,90 para achar o preço, esses erros se
acumulam e aparecem como centavos que não fecham. Aqui tudo é `Decimal`, e
o arredondamento é explícito e só na fronteira: meio para cima na exibição
(`arredondado`, `ROUND_HALF_UP`) e para o centavo de cima em todo piso de
preço (`arredondado_para_cima`, `ROUND_CEILING`). Os cálculos intermediários
preservam a precisão total.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Final

from mise.erros import QuantidadeInvalida

CENTAVO: Final = Decimal("0.01")

#: Dígitos por grupo na separação de milhar do pt-BR (`1.234.567,89`).
_DIGITOS_POR_GRUPO: Final = 3


@dataclass(frozen=True, slots=True, order=True)
class Dinheiro:
    """Um valor em reais. Imutável, exato, formatável em pt-BR."""

    valor: Decimal

    def __post_init__(self) -> None:
        if not self.valor.is_finite():
            raise QuantidadeInvalida(self.valor, "Dinheiro")

    # -- construção ------------------------------------------------------- #

    @classmethod
    def de(cls, valor: Decimal | float | int | str) -> Dinheiro:
        """Constrói a partir de qualquer numérico, passando por `str` para
        não herdar o ruído binário de um `float`."""
        return cls(Decimal(str(valor)))

    @classmethod
    def zero(cls) -> Dinheiro:
        return cls(Decimal("0"))

    # -- aritmética ------------------------------------------------------- #

    def __add__(self, outro: Dinheiro) -> Dinheiro:
        return Dinheiro(self.valor + outro.valor)

    def __sub__(self, outro: Dinheiro) -> Dinheiro:
        return Dinheiro(self.valor - outro.valor)

    def __mul__(self, fator: Decimal | int | float) -> Dinheiro:
        return Dinheiro(self.valor * Decimal(str(fator)))

    __rmul__ = __mul__

    def __truediv__(self, divisor: Decimal | int | float) -> Dinheiro:
        d = Decimal(str(divisor))
        if d == 0:
            raise QuantidadeInvalida(divisor, "Dinheiro: divisão por zero")
        return Dinheiro(self.valor / d)

    def __neg__(self) -> Dinheiro:
        return Dinheiro(-self.valor)

    def __bool__(self) -> bool:
        return self.valor != 0

    # -- apresentação ----------------------------------------------------- #

    def arredondado(self) -> Dinheiro:
        """Arredonda para centavo (meio-para-cima, como se faz com preço)."""
        return Dinheiro(self.valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))

    def arredondado_para_cima(self) -> Dinheiro:
        """Arredonda para o centavo de cima. É o arredondamento de todo piso.

        Custo que vira base de preço e preço mínimo não podem descer: com o
        meio-para-cima, R$ 8,68 ÷ 0,90 = R$ 9,6444… vira R$ 9,64, e a R$ 9,64 ela
        recebe R$ 8,676, menos do que gastou. O "mínimo sem prejuízo" dava
        prejuízo em quase metade dos custos possíveis.
        """
        return Dinheiro(self.valor.quantize(CENTAVO, rounding=ROUND_CEILING))

    @property
    def centavos(self) -> int:
        """Valor em centavos inteiros, útil para comparações exatas."""
        return int(self.arredondado().valor * 100)

    def __str__(self) -> str:
        """Formata em pt-BR: `R$ 1.234,56`."""
        q = self.arredondado().valor
        sinal = "-" if q < 0 else ""
        inteiro, _, frac = f"{abs(q):.2f}".partition(".")
        grupos: list[str] = []
        while len(inteiro) > _DIGITOS_POR_GRUPO:
            grupos.insert(0, inteiro[-_DIGITOS_POR_GRUPO:])
            inteiro = inteiro[:-_DIGITOS_POR_GRUPO]
        grupos.insert(0, inteiro)
        return f"{sinal}R$ {'.'.join(grupos)},{frac}"

    def __repr__(self) -> str:
        return f"Dinheiro({self.valor})"


def soma(valores: object) -> Dinheiro:
    """Soma um iterável de `Dinheiro` começando do zero."""
    total = Dinheiro.zero()
    for v in valores:  # type: ignore[attr-defined]
        total = total + v
    return total
