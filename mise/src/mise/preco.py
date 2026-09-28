"""Precificação para delivery com taxa sobre a venda.

A regra do desafio: a plataforma fica com 10% do preço de venda, então de um
preço `P` a Dona Maria recebe `0,90 · P`. Daí saem as duas fórmulas do enunciado:

    preço mínimo para não perder dinheiro:   P >= CMV / 0,90
    lucro da Dona Maria:                     L  = 0,90·P - CMV

Há uma leitura dessas fórmulas que vale explicitar, porque é o que torna a
conversa com ela útil. Definindo **food cost** como `f = CMV / P` (a fração do
preço que vira ingrediente), o lucro se reescreve:

    L = 0,90·P - CMV = CMV · (0,90 − f) / f

Ou seja: o lucro não depende do preço em si, depende de **quanto do preço é
ingrediente**. E o ponto de equilíbrio aparece sozinho: `L = 0` exatamente
quando `f = 0,90`. Qualquer prato cujo ingrediente custe mais de 90% do preço
dá prejuízo, por mais alto que o preço pareça.

Trabalhamos com food cost em vez de markup porque é a linguagem real de
operação de cozinha, e porque ele responde direto a pergunta que interessa:
"de cada R$ 10 que o cliente paga, quanto sobra pra mim?".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from mise.dinheiro import Dinheiro
from mise.erros import QuantidadeInvalida

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

#: Taxa da plataforma sobre a venda, conforme o enunciado.
TAXA_PLATAFORMA: Final = Decimal("0.10")

#: Fração do preço que sobra para a Dona Maria depois da taxa.
RETENCAO: Final = Decimal("1") - TAXA_PLATAFORMA


@dataclass(frozen=True, slots=True)
class Cenario:
    """Um ponto de preço com toda a conta aberta."""

    nome: str
    descricao: str
    preco: Dinheiro
    cmv: Dinheiro
    taxa: Decimal

    @property
    def valor_da_taxa(self) -> Dinheiro:
        """Quanto a plataforma retém deste pedido."""
        return self.preco * self.taxa

    @property
    def recebe(self) -> Dinheiro:
        """Quanto entra no bolso da Dona Maria antes de descontar o ingrediente."""
        return self.preco - self.valor_da_taxa

    @property
    def lucro(self) -> Dinheiro:
        """O que sobra de fato, por porção vendida."""
        return self.recebe - self.cmv

    @property
    def food_cost(self) -> Decimal:
        """Fração do preço que é ingrediente. Acima de 0,90 dá prejuízo."""
        if self.preco.valor == 0:
            return Decimal("0")
        return self.cmv.valor / self.preco.valor

    @property
    def margem_sobre_preco(self) -> Decimal:
        """Lucro como fração do preço de venda."""
        if self.preco.valor == 0:
            return Decimal("0")
        return self.lucro.valor / self.preco.valor

    @property
    def multiplo_do_cmv(self) -> Decimal:
        """Quantas vezes o custo do ingrediente o preço representa."""
        if self.cmv.valor == 0:
            return Decimal("0")
        return self.preco.valor / self.cmv.valor

    @property
    def da_prejuizo(self) -> bool:
        return self.lucro.valor < 0

    def explicacao(self) -> str:
        """A conta escrita como se fosse dita em voz alta para ela."""
        return (
            f"Vendendo a {self.preco}: o iFood fica com {self.valor_da_taxa} "
            f"({self.taxa:.0%}), então chegam {self.recebe} pra senhora. "
            f"Tirando {self.cmv} de ingrediente, sobram {self.lucro} limpos por porção. "
            f"Isso é {self.margem_sobre_preco:.0%} do que o cliente paga."
        )


@dataclass(frozen=True, slots=True)
class TabelaDePrecos:
    """O conjunto de cenários oferecido à Dona Maria para ela escolher.

    O enunciado é explícito: propor 2–3 cenários, mostrar a matemática e
    **deixar a Dona Maria decidir**. Esta estrutura não tem "cenário
    recomendado" por escolha de projeto: quem decide o posicionamento do
    próprio negócio é ela.
    """

    cmv: Dinheiro
    preco_minimo: Dinheiro
    cenarios: tuple[Cenario, ...]
    taxa: Decimal = TAXA_PLATAFORMA

    def __iter__(self) -> Iterator[Cenario]:
        return iter(self.cenarios)

    def __len__(self) -> int:
        return len(self.cenarios)

    def explicacao_da_taxa(self) -> str:
        """Por que o preço mínimo não é simplesmente o CMV."""
        return (
            f"O custo de ingrediente é {self.cmv}. Mas não dá pra vender por {self.cmv}: "
            f"o iFood fica com {self.taxa:.0%} de tudo que o cliente paga, então a senhora "
            f"receberia só {self.cmv * RETENCAO} e sairia no prejuízo. "
            f"Pra empatar exatamente, o preço tem que ser {self.cmv} ÷ "
            f"{f'{RETENCAO:.2f}'.replace('.', ',')} = {self.preco_minimo}. "
            "Abaixo disso a senhora paga pra trabalhar."
        )


# --------------------------------------------------------------------------- #
# As fórmulas
# --------------------------------------------------------------------------- #


def preco_minimo(cmv: Dinheiro, taxa: Decimal = TAXA_PLATAFORMA) -> Dinheiro:
    """Ponto de equilíbrio: `P = CMV / (1 − taxa)`. Lucro exatamente zero."""
    _validar_taxa(taxa)
    return cmv / (Decimal("1") - taxa)


def preco_por_food_cost(
    cmv: Dinheiro, food_cost: Decimal, taxa: Decimal = TAXA_PLATAFORMA
) -> Dinheiro:
    """Preço tal que o ingrediente seja `food_cost` do valor pago pelo cliente."""
    _validar_taxa(taxa)
    if not Decimal("0") < food_cost <= Decimal("1"):
        raise QuantidadeInvalida(food_cost, "food cost (esperado entre 0 e 1)")
    return cmv / food_cost


def preco_por_markup(cmv: Dinheiro, markup: Decimal, taxa: Decimal = TAXA_PLATAFORMA) -> Dinheiro:
    """Preço tal que o lucro seja `markup × CMV`, já líquido da taxa."""
    _validar_taxa(taxa)
    if markup < 0:
        raise QuantidadeInvalida(markup, "markup")
    return cmv * (Decimal("1") + markup) / (Decimal("1") - taxa)


def preco_por_margem(cmv: Dinheiro, margem: Decimal, taxa: Decimal = TAXA_PLATAFORMA) -> Dinheiro:
    """Preço tal que o lucro seja `margem` do preço de venda."""
    _validar_taxa(taxa)
    teto = Decimal("1") - taxa
    if not Decimal("0") <= margem < teto:
        raise QuantidadeInvalida(
            margem, f"margem sobre preço (o teto com taxa de {taxa:.0%} é {teto:.2f})"
        )
    return cmv / (teto - margem)


def lucro_em(preco: Dinheiro, cmv: Dinheiro, taxa: Decimal = TAXA_PLATAFORMA) -> Dinheiro:
    """`L = (1 − taxa)·P - CMV`."""
    _validar_taxa(taxa)
    return preco * (Decimal("1") - taxa) - cmv


# --------------------------------------------------------------------------- #
# Geração dos cenários
# --------------------------------------------------------------------------- #

#: Food costs de referência de restaurante: o ingrediente entre 30% e 40% do preço.
#: É régua de custo, não pesquisa de preço: o motor não sabe o que a vizinhança
#: dela cobra, e a descrição não pode dar a entender que sabe.
FOOD_COSTS_PADRAO: Final[tuple[tuple[str, str, Decimal], ...]] = (
    (
        "Conservador",
        "preço mais baixo, ganha menos por prato mas atrai mais pedido",
        Decimal("0.40"),
    ),
    (
        "Equilibrado",
        "o meio-termo: o ingrediente fica em cerca de um terço do preço",
        Decimal("0.35"),
    ),
    (
        "Premium",
        "preço mais alto, ganha mais por prato mas vende para menos gente",
        Decimal("0.30"),
    ),
)


def montar_cenarios(
    cmv: Dinheiro,
    taxa: Decimal = TAXA_PLATAFORMA,
    food_costs: Sequence[tuple[str, str, Decimal]] = FOOD_COSTS_PADRAO,
) -> TabelaDePrecos:
    """Monta a tabela de preços a apresentar para a Dona Maria escolher.

    >>> from mise.dinheiro import Dinheiro
    >>> t = montar_cenarios(Dinheiro.de("8.68"))
    >>> str(t.preco_minimo)
    'R$ 9,65'
    >>> [str(c.preco) for c in t]
    ['R$ 21,70', 'R$ 24,80', 'R$ 28,93']
    """
    _validar_taxa(taxa)
    if cmv.valor <= 0:
        raise QuantidadeInvalida(cmv.valor, "CMV (deve ser positivo)")

    cenarios = tuple(
        Cenario(
            nome=nome,
            descricao=descricao,
            preco=preco_por_food_cost(cmv, f, taxa).arredondado(),
            cmv=cmv,
            taxa=taxa,
        )
        for nome, descricao, f in food_costs
    )
    return TabelaDePrecos(
        cmv=cmv,
        preco_minimo=preco_minimo(cmv, taxa).arredondado_para_cima(),
        cenarios=cenarios,
        taxa=taxa,
    )


def sensibilidade(
    cmv: Dinheiro,
    preco: Dinheiro,
    variacao: Decimal = Decimal("0.20"),
    taxa: Decimal = TAXA_PLATAFORMA,
) -> dict[str, Dinheiro | Decimal | bool]:
    """E se o insumo subir? Quanto de alta o preço atual aguenta antes de zerar.

    Resiliência de margem é a pergunta que ninguém faz até o frango subir.
    """
    _validar_taxa(taxa)
    cmv_maior = cmv * (Decimal("1") + variacao)
    lucro_atual = lucro_em(preco, cmv, taxa)
    lucro_depois = lucro_em(preco, cmv_maior, taxa)

    # Alta percentual do CMV que zera o lucro, mantido o preço.
    cmv_de_equilibrio = preco * (Decimal("1") - taxa)
    folga = (cmv_de_equilibrio.valor / cmv.valor - Decimal("1")) if cmv.valor > 0 else Decimal("0")

    return {
        "variacao_testada": variacao,
        "cmv_original": cmv,
        "cmv_com_alta": cmv_maior.arredondado(),
        "lucro_original": lucro_atual.arredondado(),
        "lucro_com_alta": lucro_depois.arredondado(),
        "ainda_lucrativo": lucro_depois.valor > 0,
        "folga_ate_zerar": folga,
    }


def _validar_taxa(taxa: Decimal) -> None:
    if not Decimal("0") <= taxa < Decimal("1"):
        raise QuantidadeInvalida(taxa, "taxa da plataforma (esperado entre 0 e 1)")


__all__ = [
    "FOOD_COSTS_PADRAO",
    "RETENCAO",
    "TAXA_PLATAFORMA",
    "Cenario",
    "TabelaDePrecos",
    "lucro_em",
    "montar_cenarios",
    "preco_minimo",
    "preco_por_food_cost",
    "preco_por_margem",
    "preco_por_markup",
    "sensibilidade",
]
