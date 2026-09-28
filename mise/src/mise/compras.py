"""O que falta comprar, quanto isso custa ao prato e quanto sai do bolso dela.

São dois números diferentes, e confundi-los foi o erro que este módulo existe
para não repetir:

- **consumo**: o valor do ingrediente que o prato gasta. Entra no custo do prato
  (o CMV do §2.4). Se a lata de milho custa R$ 6 e a receita usa meia lata, o
  prato consome R$ 3.
- **desembolso**: o que ela paga no mercado. Sai dos R$ 80 do orçamento. Não dá
  para comprar meia lata, então sai R$ 6.

Uma cotação só serve para os dois quando se sabe o que o preço compra ("R$ 6 a
lata", "R$ 50 o quilo"). Sem essa quantidade, a premissa é que o valor é o de
comprar o que a receita pede, e a premissa vai escrita junto com o número, para
o agente confirmar com ela em vez de apresentar como fato.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, TypeVar

from mise.dinheiro import Dinheiro
from mise.erros import DensidadeDesconhecida, QuantidadeInvalida, UnidadeNaoNormalizavel
from mise.unidades import (
    Dimensao,
    Quantidade,
    classificar_medida,
    converter_medida,
    converter_medida_para_volume,
)

T = TypeVar("T")

#: A premissa que acompanha uma cotação sem quantidade.
PREMISSA_SEM_QUANTIDADE = (
    "o valor informado foi tratado como o preço de comprar o que a receita pede; "
    "se for o preço de outra quantidade, a conta muda"
)

#: A premissa de repor o que falta ao preço que ela já pagou.
PREMISSA_PRECO_DA_PLANILHA = (
    "sem cotação, a reposição foi estimada pelo preço que a senhora pagou na compra da despensa"
)


def _chave(texto: str) -> str:
    """Nome normalizado para comparar: sem acento, caixa, espaço nem plural simples."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    chave = " ".join(sem_acento.casefold().split())
    return chave[:-1] if len(chave) > 3 and chave.endswith("s") else chave  # noqa: PLR2004


@dataclass(frozen=True, slots=True)
class Medida:
    """Uma quantidade comparável: massa, volume ou unidades de uma mesma embalagem.

    `embalagem` só existe em contagem de unidade que as tabelas não conhecem
    ("lata", "caixinha", "pacote"). Duas contagens só se comparam quando a
    embalagem é a mesma: 1 lata e 1 pacote não são a mesma coisa.
    """

    quantidade: Quantidade
    embalagem: str = ""

    def compativel(self, outra: Medida) -> bool:
        return (
            self.quantidade.dimensao is outra.quantidade.dimensao
            and self.embalagem == outra.embalagem
        )

    def __str__(self) -> str:
        if self.embalagem:
            return f"{_limpa(self.quantidade.valor)} {self.embalagem}"
        return str(self.quantidade)


def medida(valor: Decimal | float | int, unidade: str, ingrediente: str = "") -> Medida | None:
    """Interpreta "2 xícaras", "1 kg", "1 lata" como `Medida`. `None` se não der.

    Tenta, na ordem: volume puro (líquido custado por litro), a conversão do
    motor (massa direta, peso tabelado, volume com densidade) e, por último,
    a unidade como embalagem contável.
    """
    try:
        bruto = Decimal(str(valor))
    except ArithmeticError:
        return None
    if not bruto.is_finite() or bruto <= 0:
        return None

    dimensao = classificar_medida(unidade)
    if dimensao is None or not unidade.strip():
        embalagem = _chave(unidade)
        return Medida(
            Quantidade(bruto, Dimensao.CONTAGEM), "" if embalagem in _AVULSO else embalagem
        )
    return _convertida(bruto, unidade, ingrediente, dimensao)


#: Unidades que querem dizer "uma peça", sem embalagem que as distinga.
_AVULSO: Final = frozenset({"", "unidade", "un", "und"})


def _convertida(
    bruto: Decimal, unidade: str, ingrediente: str, dimensao: Dimensao
) -> Medida | None:
    liquido = dimensao is Dimensao.VOLUME and _e_liquido(ingrediente)
    try:
        if liquido:
            return Medida(converter_medida_para_volume(bruto, unidade).quantidade)
        return Medida(converter_medida(bruto, unidade, ingrediente).quantidade)
    except (DensidadeDesconhecida, UnidadeNaoNormalizavel, QuantidadeInvalida):
        if dimensao is Dimensao.VOLUME:
            return Medida(converter_medida_para_volume(bruto, unidade).quantidade)
        return None


def _e_liquido(ingrediente: str) -> bool:
    chave = _chave(ingrediente)
    return any(p in chave for p in ("oleo", "leite", "agua", "azeite", "vinagre", "aceto"))


#: O ingrediente é líquido (óleo, leite, água, azeite, vinagre): o volume dele pesa como o dele.
e_liquido: Final = _e_liquido


@dataclass(frozen=True, slots=True)
class Cotacao:
    """Quanto custa comprar um ingrediente e, se ela disse, quanto aquele preço compra."""

    valor: Dinheiro
    por: Medida | None = None
    origem: str = "informado_por_ela"
    #: Vendido a peso (a cenoura, o limão): ela leva o quanto precisa, e o
    #: desembolso é o consumo, sem arredondar para um quilo inteiro.
    a_granel: bool = False


@dataclass(frozen=True, slots=True)
class Comprado:
    """O que ela já comprou para o cardápio. Vira estoque, ao preço que pagou."""

    medida: Medida
    valor: Dinheiro

    @property
    def custo_unitario(self) -> Dinheiro:
        return self.valor / self.medida.quantidade.valor


@dataclass(frozen=True, slots=True)
class PrecoDaFalta:
    """O preço do que falta: quanto o prato consome e quanto ela desembolsa."""

    consumo: Dinheiro
    desembolso: Dinheiro
    derivacao: str
    premissa: str = ""


def precificar_falta(
    falta: Medida | None,
    cotacao: Cotacao | None,
    custo_da_planilha: Dinheiro | None = None,
) -> PrecoDaFalta | None:
    """Consumo e desembolso da quantidade que falta. `None` quando não há preço.

    `custo_da_planilha` é o custo por unidade-base do que ela já tem em casa,
    usado quando falta só uma parte e ninguém cotou a reposição.
    """
    if cotacao is not None:
        if falta is not None and cotacao.por is not None and falta.compativel(cotacao.por):
            por = cotacao.por.quantidade.valor
            unitario = cotacao.valor / por
            consumo = unitario * falta.quantidade.valor
            conta = f"{falta} × {cotacao.valor} por {cotacao.por} = {consumo.arredondado()}"
            if cotacao.a_granel:
                return PrecoDaFalta(consumo=consumo, desembolso=consumo, derivacao=conta)
            embalagens = math.ceil(falta.quantidade.valor / por)
            desembolso = cotacao.valor * embalagens
            return PrecoDaFalta(
                consumo=consumo,
                desembolso=desembolso,
                derivacao=f"{conta}; na compra, {embalagens} × {cotacao.valor} = {desembolso}",
            )
        return PrecoDaFalta(
            consumo=cotacao.valor,
            desembolso=cotacao.valor,
            derivacao=f"cotação de {cotacao.valor}",
            premissa=PREMISSA_SEM_QUANTIDADE,
        )

    if falta is not None and custo_da_planilha is not None:
        valor = custo_da_planilha * falta.quantidade.valor
        return PrecoDaFalta(
            consumo=valor,
            desembolso=valor,
            derivacao=f"{falta} × {custo_da_planilha}/{falta.quantidade.dimensao.value}",
            premissa=PREMISSA_PRECO_DA_PLANILHA,
        )
    return None


def buscar(mapa: Mapping[str, T], nome: str) -> T | None:
    """Acha a entrada pelo nome normalizado ("Leite Condensado" == "leite condensado").

    Sem o nome igual, vale o mesmo produto escrito de outro jeito, pelo núcleo
    do nome (`mise.casamento.nucleo_do_nome`): o preço que ela deu da
    "cenoura" é o das "cenouras médias" de outra receita. Com dois preços do
    mesmo produto, nenhum é escolhido: a pergunta continua.
    """
    alvo = _chave(nome)
    for chave, valor in mapa.items():
        if _chave(chave) == alvo:
            return valor
    from mise.casamento import nucleo_do_nome  # noqa: PLC0415

    nucleo = nucleo_do_nome(nome)
    achados = [valor for chave, valor in mapa.items() if nucleo and nucleo_do_nome(chave) == nucleo]
    return achados[0] if len(achados) == 1 else None


def _limpa(valor: Decimal) -> str:
    n = valor.normalize()
    return str(n.quantize(Decimal("1"))) if n == n.to_integral_value() else f"{n:f}"
