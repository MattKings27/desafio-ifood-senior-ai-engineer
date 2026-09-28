"""A conferência propriamente dita, escrita do zero.

**A regra que organiza este arquivo: não importar nada do `mise`.**

É contraintuitivo e é o ponto inteiro. Reaproveitar `mise.preco.preco_minimo`
aqui faria o auditor confirmar a fórmula usando a própria fórmula, e um erro de
sinal, de arredondamento ou de ordem de operação passaria pelos dois lados sem
deixar rastro.

A independência custa duplicação, e a duplicação é o produto: a conta abaixo foi
escrita lendo o enunciado, não o código do motor. Se as duas divergirem, uma das
duas está errada, e é exatamente isso que se quer descobrir.

Do enunciado, literalmente:

    Preço mínimo para não perder dinheiro:  P >= CMV / 0,90
    Lucro da Dona Maria:                    0,90·P - CMV
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Final

#: Taxa da plataforma sobre a venda, conforme o §2.4.
TAXA: Final = Decimal("0.10")

#: Quanto sobra para ela. Escrito como subtração e não como 0,90 literal para o
#: leitor ver de onde o número vem.
RETENCAO: Final = Decimal("1") - TAXA

#: Divergência tolerada. Um centavo cobre arredondamento legítimo entre duas
#: implementações; mais que isso é fórmula diferente, não ruído.
TOLERANCIA: Final = Decimal("0.01")

CENTAVO: Final = Decimal("0.01")


def _arredondar(valor: Decimal) -> Decimal:
    """Meio para cima, como se arredonda dinheiro no Brasil."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _reais(valor: Decimal) -> str:
    """R$ 1.234,56: o aviso pode chegar à Dona Maria, e ela lê vírgula decimal."""
    return "R$ " + f"{_arredondar(valor):,.2f}".translate(str.maketrans(",.", ".,"))


@dataclass(frozen=True, slots=True)
class Divergencia:
    """Uma conta que não bate, com os dois valores lado a lado."""

    campo: str
    apresentado: Decimal
    conferido: Decimal

    @property
    def diferenca(self) -> Decimal:
        return abs(self.apresentado - self.conferido)

    def __str__(self) -> str:
        return (
            f"{self.campo}: o motor diz R$ {self.apresentado:.2f}, "
            f"eu calculo R$ {self.conferido:.2f} "
            f"(diferença de R$ {self.diferenca:.2f})"
        )


@dataclass(frozen=True, slots=True)
class Veredito:
    """O resultado da conferência.

    `confere` diz se a conta bate. `da_prejuizo` e `aviso` dizem outra coisa:
    que o preço, com a conta certa, deixa a Dona Maria no vermelho. Isso não é
    divergência e não segura o preço; é o aviso de uma escolha que é dela.
    """

    confere: bool
    divergencias: tuple[Divergencia, ...] = ()
    observacao: str = ""
    da_prejuizo: bool = False
    aviso: str = ""

    def __str__(self) -> str:
        if self.confere:
            return f"confere; {self.aviso}" if self.aviso else "confere"
        return "não confere: " + "; ".join(str(d) for d in self.divergencias)


def conferir_cmv(linhas: list[dict[str, object]], total_apresentado: Decimal) -> Veredito:
    """A soma das linhas tem que fechar com o total.

    Parece trivial e não é: o total já saiu errado neste repositório porque a
    compra complementar era somada **por fora** das linhas. Quem somasse o que
    via na tela chegaria a outro número e não teria como descobrir de onde vinha
    a diferença.
    """
    if not linhas:
        return Veredito(False, observacao="nenhuma linha para conferir")

    soma = Decimal(0)
    for linha in linhas:
        bruto = linha.get("custo")
        if bruto is None:
            return Veredito(
                False, observacao=f"linha {linha.get('ingrediente')!r} sem custo declarado"
            )
        soma += Decimal(str(bruto))

    soma = _arredondar(soma)
    esperado = _arredondar(total_apresentado)
    if abs(soma - esperado) > TOLERANCIA:
        return Veredito(False, (Divergencia("total do CMV", esperado, soma),))
    somam = "linha soma" if len(linhas) == 1 else "linhas somam"
    return Veredito(True, observacao=f"{len(linhas)} {somam} {soma}")


def conferir_preco(cmv: Decimal, preco: Decimal, lucro_apresentado: Decimal) -> Veredito:
    """As duas fórmulas do §2.4, recalculadas do enunciado.

    `P >= CMV / 0,90` e `lucro = 0,90·P - CMV`.

    Só a conta que não bate é divergência, e só ela segura o preço. Preço
    abaixo do mínimo com a conta certa é escolha dela: o enunciado manda deixar
    a Dona Maria decidir. O auditor confere se ela perde dinheiro e avisa
    (`da_prejuizo`, `aviso`), mas não recusa. Recusar fazia o aceite abaixo do
    mínimo, que a ferramenta promete ser dela, falhar sempre que o auditor
    estava ligado, isto é, sempre.
    """
    # O mínimo exibido sobe para o centavo de cima, e a checagem de prejuízo não
    # arredonda nem tolera nada: com um centavo de tolerância, o preço que deixa
    # a Dona Maria no vermelho em toda venda passava sem aviso.
    minimo = (cmv / RETENCAO).quantize(CENTAVO, rounding=ROUND_CEILING)
    da_prejuizo = RETENCAO * preco < cmv
    aviso = (
        f"abaixo do mínimo sem prejuízo: a {_reais(preco)} ela perde dinheiro em cada "
        f"venda; o mínimo é {_reais(minimo)}"
        if da_prejuizo
        else ""
    )

    lucro = _arredondar(RETENCAO * preco - cmv)
    if abs(lucro - _arredondar(lucro_apresentado)) > TOLERANCIA:
        divergencia = Divergencia("lucro", _arredondar(lucro_apresentado), lucro)
        return Veredito(False, (divergencia,), da_prejuizo=da_prejuizo, aviso=aviso)
    return Veredito(
        True,
        observacao=f"mínimo R$ {minimo:.2f}, lucro R$ {lucro:.2f} a R$ {preco:.2f}",
        da_prejuizo=da_prejuizo,
        aviso=aviso,
    )


def conferir(prato: dict[str, object]) -> Veredito:
    """Confere um prato inteiro: CMV e preço.

    As linhas fecham com `total_das_linhas`, e o preço é conferido sobre `cmv`,
    o custo que foi para o preço. Num custo exato os dois são o mesmo número, e
    quem manda só `cmv` é conferido assim. Numa faixa, o preço sai do topo, que
    inclui a incerteza e não é soma de linhas: comparar as linhas com o topo
    segurava um preço certo. O topo não pode é ficar abaixo do que as linhas
    somam, porque aí o mínimo sairia de um custo menor que o de verdade.
    """
    linhas = prato.get("linhas")
    if not isinstance(linhas, list):
        return Veredito(False, observacao="prato sem lista de linhas")

    cmv = Decimal(str(prato.get("cmv", "0")))
    total_das_linhas = Decimal(str(prato.get("total_das_linhas", cmv)))
    do_cmv = conferir_cmv(linhas, total_das_linhas)
    if not do_cmv.confere:
        return do_cmv
    if cmv < total_das_linhas:
        divergencia = Divergencia("custo usado no preço", cmv, total_das_linhas)
        return Veredito(False, (divergencia,))
    if cmv > total_das_linhas:
        do_cmv = Veredito(
            True, observacao=f"{do_cmv.observacao}; o preço parte de {cmv:.2f}, o topo da faixa"
        )

    if (preco := prato.get("preco")) is None:
        return do_cmv

    do_preco = conferir_preco(cmv, Decimal(str(preco)), Decimal(str(prato.get("lucro", "0"))))
    if not do_preco.confere:
        return do_preco

    return Veredito(
        True,
        observacao=f"{do_cmv.observacao}; {do_preco.observacao}",
        da_prejuizo=do_preco.da_prejuizo,
        aviso=do_preco.aviso,
    )


__all__ = [
    "RETENCAO",
    "TAXA",
    "TOLERANCIA",
    "Divergencia",
    "Veredito",
    "conferir",
    "conferir_cmv",
    "conferir_preco",
]
