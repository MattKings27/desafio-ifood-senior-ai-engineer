"""Normalização de unidades: a ponte entre a planilha e as receitas da web.

Há dois problemas distintos aqui, e confundi-los é a causa dos erros de custo.

**1. Unidades de compra (planilha).** A aba `Precos` mistura unidades limpas
(`kg`, `L`) com embalagens opacas (`balde 2kg`, `un 500ml`, `un 400g`). O custo
unitário ingênuo (`preço ÷ quantidade`) erra em 6 dos 37 itens, porque trata
"1 balde" como se fosse 1 kg:

    Alcaparras   R$ 82,00 / 1 "balde 2kg"  ->  ingênuo R$ 82,00/un   vs  correto R$ 41,00/kg
    Adoçante     R$  1,90 / 1 "un 100ml"   ->  ingênuo R$  1,90/un   vs  correto R$ 19,00/L

**2. Medidas culinárias (receitas).** A web fala em "1 xícara", "2 colheres de
sopa". A planilha custa em kg/L. Tratar ml como g superestima farinha de trigo
em +89%, porque a densidade aparente dela é ~0,53 g/ml, não 1,0.

Tudo converge para três dimensões-base: massa em **kg**, volume em **L**,
contagem em **un**. Somar grandezas de dimensões diferentes é erro de tipo.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from mise.erros import (
    DensidadeDesconhecida,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
    UnidadesIncompativeis,
)


class Dimensao(StrEnum):
    """As três grandezas em que tudo é medido."""

    MASSA = "kg"
    VOLUME = "L"
    CONTAGEM = "un"


@dataclass(frozen=True, slots=True, order=False)
class Quantidade:
    """Uma grandeza já normalizada para a unidade-base da sua dimensão.

    Imutável e dimensionalmente segura: somar massa com volume levanta
    `UnidadesIncompativeis` em vez de produzir um número silenciosamente errado.
    """

    valor: Decimal
    dimensao: Dimensao

    def __post_init__(self) -> None:
        if not self.valor.is_finite():
            raise QuantidadeInvalida(self.valor, "Quantidade")
        if self.valor < 0:
            raise QuantidadeInvalida(self.valor, "Quantidade (negativa)")

    def __add__(self, outra: Quantidade) -> Quantidade:
        self._exigir_mesma_dimensao(outra)
        return Quantidade(self.valor + outra.valor, self.dimensao)

    def __sub__(self, outra: Quantidade) -> Quantidade:
        self._exigir_mesma_dimensao(outra)
        return Quantidade(self.valor - outra.valor, self.dimensao)

    def __mul__(self, fator: Decimal | int) -> Quantidade:
        return Quantidade(self.valor * Decimal(str(fator)), self.dimensao)

    def __truediv__(self, divisor: Decimal | int) -> Quantidade:
        d = Decimal(str(divisor))
        if d == 0:
            raise QuantidadeInvalida(divisor, "divisão por zero")
        return Quantidade(self.valor / d, self.dimensao)

    def __lt__(self, outra: Quantidade) -> bool:
        self._exigir_mesma_dimensao(outra)
        return self.valor < outra.valor

    def __le__(self, outra: Quantidade) -> bool:
        self._exigir_mesma_dimensao(outra)
        return self.valor <= outra.valor

    def _exigir_mesma_dimensao(self, outra: Quantidade) -> None:
        if self.dimensao is not outra.dimensao:
            raise UnidadesIncompativeis(self.dimensao.value, outra.dimensao.value)

    def __str__(self) -> str:
        return f"{_limpa(self.valor)} {self.dimensao.value}"


# --------------------------------------------------------------------------- #
# 1. Unidades de compra: o que a planilha escreve
# --------------------------------------------------------------------------- #

#: Símbolos de massa/volume e seu fator para a unidade-base.
_FATOR_BASE: Final[dict[str, tuple[Dimensao, Decimal]]] = {
    "kg": (Dimensao.MASSA, Decimal("1")),
    "g": (Dimensao.MASSA, Decimal("0.001")),
    "mg": (Dimensao.MASSA, Decimal("0.000001")),
    "l": (Dimensao.VOLUME, Decimal("1")),
    "ml": (Dimensao.VOLUME, Decimal("0.001")),
}

#: Captura a massa/volume embutida num rótulo de embalagem: "balde 2kg", "un 500ml".
_EMBALAGEM = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<sym>kg|mg|g|ml|l)\b",
    re.IGNORECASE,
)

#: Rótulos que significam "uma peça, conteúdo não declarado".
_CONTAGEM_PURA: Final[frozenset[str]] = frozenset(
    {"un", "und", "unid", "unidade", "unidades", "pc", "pct", "peca", "peça", "duzia", "dúzia"}
)


@dataclass(frozen=True, slots=True)
class UnidadeCompra:
    """O resultado de interpretar a coluna `Unidade` da planilha.

    `conteudo_por_embalagem` é `None` quando o rótulo é opaco (um "un" sem massa),
    caso em que o custo por quilo é **indedutível** e vira pergunta.
    """

    rotulo_original: str
    dimensao: Dimensao
    conteudo_por_embalagem: Quantidade | None
    derivacao: str

    @property
    def opaca(self) -> bool:
        """True quando não sabemos quanto há dentro da embalagem."""
        return self.conteudo_por_embalagem is None


def interpretar_unidade_compra(rotulo: str) -> UnidadeCompra:
    """Interpreta o rótulo de unidade da planilha.

    >>> interpretar_unidade_compra("kg").dimensao
    <Dimensao.MASSA: 'kg'>
    >>> str(interpretar_unidade_compra("balde 2kg").conteudo_por_embalagem)
    '2 kg'
    >>> interpretar_unidade_compra("un").opaca
    True
    """
    if not rotulo or not rotulo.strip():
        raise UnidadeNaoNormalizavel(rotulo)

    bruto = rotulo.strip()
    normalizado = _sem_acento(bruto).lower()

    # Caso 1: a unidade já é a própria base ("kg", "L").
    if normalizado in _FATOR_BASE:
        dimensao, fator = _FATOR_BASE[normalizado]
        return UnidadeCompra(
            rotulo_original=bruto,
            dimensao=dimensao,
            conteudo_por_embalagem=Quantidade(fator, dimensao),
            derivacao=f"{bruto!r} é a própria unidade-base ({dimensao.value})",
        )

    # Caso 2: embalagem com conteúdo declarado ("balde 2kg", "un 500ml").
    if achado := _EMBALAGEM.search(normalizado):
        numero = Decimal(achado.group("num").replace(",", "."))
        if numero <= 0:
            raise QuantidadeInvalida(numero, f"embalagem {bruto!r}")
        dimensao, fator = _FATOR_BASE[achado.group("sym").lower()]
        conteudo = Quantidade(numero * fator, dimensao)
        return UnidadeCompra(
            rotulo_original=bruto,
            dimensao=dimensao,
            conteudo_por_embalagem=conteudo,
            derivacao=(
                f"{bruto!r} declara {achado.group('num')}{achado.group('sym')} "
                f"por embalagem = {conteudo}"
            ),
        )

    # Caso 3: contagem pura, peça sem conteúdo declarado.
    if normalizado in _CONTAGEM_PURA:
        return UnidadeCompra(
            rotulo_original=bruto,
            dimensao=Dimensao.CONTAGEM,
            conteudo_por_embalagem=None,
            derivacao=f"{bruto!r} conta peças; o conteúdo não está declarado",
        )

    raise UnidadeNaoNormalizavel(bruto)


# --------------------------------------------------------------------------- #
# 2. Medidas culinárias: o que as receitas escrevem
# --------------------------------------------------------------------------- #

#: Medidas de volume usadas em receitas brasileiras, em mililitros.
#: Padrão doméstico BR: xícara de chá = 240 ml, copo americano = 200 ml.
MEDIDAS_VOLUME: Final[dict[str, Decimal]] = {
    "xicara": Decimal("240"),
    "xicara de cha": Decimal("240"),
    "xicara cha": Decimal("240"),
    "copo": Decimal("200"),
    "copo americano": Decimal("200"),
    "copo de requeijao": Decimal("240"),
    # Colher sem dizer qual, em receita brasileira, é a de sopa, como a xícara
    # sem dizer é a de chá. Sem isto, "2 colheres de óleo" virava um ingrediente
    # chamado "colheres de óleo".
    "colher": Decimal("15"),
    "colher de sopa": Decimal("15"),
    "colher sopa": Decimal("15"),
    "colher de sobremesa": Decimal("10"),
    "colher de cha": Decimal("5"),
    "colher cha": Decimal("5"),
    "colher de cafe": Decimal("2"),
    "pitada": Decimal("0.3"),
    # "Um fio de azeite": estimativa de cozinha, duas colheres de chá. O custo é
    # de centavos, mas zero ele não é, e "a gosto" o apagaria da conta.
    "fio": Decimal("10"),
    "ml": Decimal("1"),
    "litro": Decimal("1000"),
    "l": Decimal("1000"),
}

#: Medidas que já são massa, em gramas.
MEDIDAS_MASSA: Final[dict[str, Decimal]] = {
    "g": Decimal("1"),
    "grama": Decimal("1"),
    "gramas": Decimal("1"),
    "kg": Decimal("1000"),
    "quilo": Decimal("1000"),
}


@dataclass(frozen=True, slots=True)
class FonteDaMedida:
    """De onde veio uma medida caseira: a tabela, a data da conferência e o endereço."""

    titulo: str
    url: str
    verificado_em: dt.date
    #: Como a tela diz a fonte, curta: "referência de medidas do IBGE".
    curto: str = "medidas do IBGE"


#: A tabela de medidas caseiras que a nutrição brasileira usa, publicada pelo
#: IBGE com a POF 2008-2009 (compilada de Pinheiro e outros, "Tabela para
#: avaliação de consumo alimentar em medidas caseiras"). `make
#: conferir-referencias` baixa a planilha e acha cada linha citada, letra por letra.
TABELA_DE_MEDIDAS_DO_IBGE: Final = FonteDaMedida(
    titulo=(
        "IBGE, Pesquisa de Orçamentos Familiares 2008-2009: Tabela de Medidas Referidas "
        "para os Alimentos Consumidos no Brasil"
    ),
    url=(
        "https://ftp.ibge.gov.br/Orcamentos_Familiares/"
        "Pesquisa_de_Orcamentos_Familiares_2008_2009/"
        "Tabela_de_Medidas_Referidas_para_os_Alimentos_Consumidos_no_Brasil/tabelamedidas_bd.zip"
    ),
    verificado_em=dt.date(2026, 9, 27),
)

#: O peso das porções da tabela de composição do Departamento de Agricultura dos
#: Estados Unidos (FoodData Central, SR Legacy, abril de 2018), para o que a
#: tabela do IBGE não diz (a pitada de pimenta-do-reino, a colher de chá de
#: páprica, a xícara de extrato de tomate). Cada linha citada é a do arquivo
#: `food_portion.csv` cruzada com a descrição de `food.csv`: "id | alimento |
#: quantidade | medida | gramas". A "cup" é a xícara (236,6 ml, contra 240 ml da
#: xícara brasileira: 1,4% de diferença, bem abaixo da incerteza de uma medida
#: caseira), a "tbsp" é a colher de sopa e a "tsp", a de chá.
TABELA_DE_PORCOES_DO_USDA: Final = FonteDaMedida(
    titulo=(
        "USDA FoodData Central, SR Legacy (abril de 2018): peso das porções dos alimentos "
        "(food_portion.csv)"
    ),
    url=("https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"),
    verificado_em=dt.date(2026, 9, 27),
    curto="medidas do USDA",
)

#: A incerteza de uma medida caseira da tabela: uma cebola média não é a cebola dela.
INCERTEZA_DA_MEDIDA_CASEIRA: Final = Decimal("0.15")


@dataclass(frozen=True, slots=True)
class MedidaDeReferencia:
    """Quanto pesa uma medida caseira de um ingrediente, pela tabela do IBGE.

    `trecho` é a linha da planilha como a conferência a lê: as células com
    valor, separadas por " | ". `medida` vazia é uma unidade do ingrediente
    ("1 cebola"); `ingredientes` são os nomes que a receita usa para ele, sem
    acento e em minúscula.
    """

    ingredientes: tuple[str, ...]
    medida: str
    gramas: Decimal
    #: Como a conta diz o que foi pesado: "cebola média", "colher de sopa de margarina".
    descricao: str
    trecho: str
    fonte: FonteDaMedida = TABELA_DE_MEDIDAS_DO_IBGE
    #: A medida de uma classe de ingredientes, quando a fonte não diz a deste: a
    #: regra dita, e a linha da fonte (`trecho`) é a base dela. Vazia na medida
    #: que a fonte diz do próprio ingrediente.
    classe: str = ""


def _usda(
    ingredientes: tuple[str, ...],
    medida: str,
    gramas: str,
    descricao: str,
    trecho: str,
    *,
    classe: str = "",
) -> MedidaDeReferencia:
    return MedidaDeReferencia(
        ingredientes, medida, Decimal(gramas), descricao, trecho, TABELA_DE_PORCOES_DO_USDA, classe
    )


def _ibge(
    ingredientes: tuple[str, ...], medida: str, gramas: str, descricao: str, trecho: str
) -> MedidaDeReferencia:
    return MedidaDeReferencia(ingredientes, medida, Decimal(gramas), descricao, trecho)


#: O peso de uma unidade de cada item contado, e de cada medida caseira que a
#: densidade não resolve. Só entra o que a tabela do IBGE diz; o que ela não
#: diz (a folha de louro, a colher de sopa de alcaparras) continua virando
#: pergunta a ela.
MEDIDAS_DE_REFERENCIA: Final[tuple[MedidaDeReferencia, ...]] = (
    _ibge(
        ("ovo", "ovos"),
        "",
        "45",
        "ovo médio",
        "7803301 | OVO DE GALINHA | 99 | NAO SE APLICA | 103 | UNIDADE | 103 | UNIDADE | 45 | 1"
        " | Ovo de galinha cozido - unidade média",
    ),
    _ibge(
        ("dente de alho", "dente"),
        "",
        "4.4",
        "dente de alho",
        "6706201 | ALHO | 99 | NAO SE APLICA | 103 | UNIDADE | 103 | UNIDADE | 4.4 | 14"
        " | Alho - unidade",
    ),
    _ibge(
        ("cebola", "cebola media"),
        "",
        "70",
        "cebola média",
        "6705701 | CEBOLA | 1 | CRU(A) | 103 | UNIDADE | 96 | RODELA | 70 | 1"
        " | Cebola - unidade média",
    ),
    _ibge(
        ("tomate", "tomate medio"),
        "",
        "100",
        "tomate médio",
        "6705101 | TOMATE | 99 | NAO SE APLICA | 103 | UNIDADE | 96 | RODELA | 100 | 1"
        " | Tomate - unidade média",
    ),
    _ibge(
        ("batata", "batata media"),
        "",
        "140",
        "batata média",
        "6400101 | BATATA INGLESA | 99 | NAO SE APLICA | 103 | UNIDADE | 103 | UNIDADE | 140 | 1"
        " | Batata inglesa cozida - unidade média",
    ),
    _ibge(
        ("cenoura",),
        "",
        "120",
        "cenoura média",
        "6401201 | CENOURA | 1 | CRU(A) | 103 | UNIDADE | 16 | COLHER DE SOPA | 120 | 1"
        " | Cenoura crua - unidade média",
    ),
    _ibge(
        ("limao",),
        "",
        "84",
        "limão",
        "6802001 | LIMAO (COMUM, GALEGO, ETC) | 99 | NAO SE APLICA | 103 | UNIDADE | 103"
        " | UNIDADE | 84 | 2 | Limão - unidade",
    ),
    _ibge(
        ("pimentao", "pimentao verde", "pimentao vermelho", "pimentao amarelo"),
        "",
        "55",
        "pimentão médio",
        "6704501 | PIMENTAO | 99 | NAO SE APLICA | 103 | UNIDADE | 96 | RODELA | 55 | 1"
        " | Pimentão - unidade média",
    ),
    _ibge(
        ("peito de frango", "peito de galinha"),
        "",
        "180",
        "peito de frango médio",
        "7800401 | PEITO DE GALINHA OU FRANGO | 1 | CRU(A) | 103 | UNIDADE | 81 | PEDACO | 180"
        " | 1 | Frango assado - peito médio",
    ),
    _ibge(
        ("azeitona", "azeitona verde"),
        "",
        "4",
        "azeitona verde média",
        "7700101 | AZEITONA | 99 | NAO SE APLICA | 103 | UNIDADE | 103 | UNIDADE | 4 | 1"
        " | Azeitona - unidade média verde",
    ),
    _ibge(
        ("extrato de tomate", "massa de tomate"),
        "colher de sopa",
        "20",
        "colher de sopa de extrato de tomate",
        "7004701 | MASSA DE TOMATE | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 16"
        " | COLHER DE SOPA | 20 | 1 | Molho de tomate - colher de sopa",
    ),
    _ibge(
        ("alcaparras", "alcaparra"),
        "colher de sobremesa",
        "13",
        "colher de sobremesa de alcaparras",
        "7002401 | ALCAPARRA EM CONSERVA | 99 | NAO SE APLICA | 15 | COLHER DE SOBREMESA | 68"
        " | GRAMA | 13 | 1 | Ervilha enlatada - colher de sobremesa cheia",
    ),
    _ibge(
        ("alcaparras", "alcaparra"),
        "colher de cha",
        "6.5",
        "colher de chá de alcaparras",
        "7002401 | ALCAPARRA EM CONSERVA | 99 | NAO SE APLICA | 14 | COLHER DE CHA | 68"
        " | GRAMA | 6.5 | 1 | Ervilha enlatada - 1/2 colher de sobremesa cheia",
    ),
    _ibge(
        ("leite condensado",),
        "colher de sopa",
        "15",
        "colher de sopa de leite condensado",
        "7900901 | LEITE CONDENSADO | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 16"
        " | COLHER DE SOPA | 15 | 1 | Leite condensado - colher de sopa",
    ),
    _ibge(
        ("leite condensado",),
        "xicara de cha",
        "200",
        "xícara de leite condensado",
        "7900901 | LEITE CONDENSADO | 99 | NAO SE APLICA | 106 | XICARA DE CHA | 16"
        " | COLHER DE SOPA | 200 | 1 | xícara de chá",
    ),
    _ibge(
        ("margarina",),
        "colher de sopa",
        "32",
        "colher de sopa de margarina",
        "7901602 | MARGARINA COM OU SEM SAL | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 86"
        " | PONTA DE FACA | 32 | 1 | Margarina - colher de sopa cheia",
    ),
    _ibge(
        ("margarina",),
        "colher de cha",
        "8",
        "colher de chá de margarina",
        "7901602 | MARGARINA COM OU SEM SAL | 99 | NAO SE APLICA | 14 | COLHER DE CHA | 86"
        " | PONTA DE FACA | 8 | 1 | Margarina - colher de chá cheia",
    ),
    _ibge(
        ("requeijao", "requeijao cremoso"),
        "colher de sopa",
        "30",
        "colher de sopa de requeijão",
        "7902901 | REQUEIJAO | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 86 | PONTA DE FACA"
        " | 30 | 1 | Requeijão - colher de sopa cheia",
    ),
    _ibge(
        ("azeitona", "azeitona verde", "azeitonas"),
        "colher de sopa",
        "25",
        "colher de sopa de azeitona",
        "7700101 | AZEITONA | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 103 | UNIDADE | 25"
        " | 14 | Azeitona - colher de sopa",
    ),
    _ibge(
        ("ervilha", "ervilhas", "ervilha em conserva"),
        "colher de sopa",
        "27",
        "colher de sopa de ervilha",
        "7700201 | ERVILHA EM CONSERVA | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 16"
        " | COLHER DE SOPA | 27 | 1 | Ervilha enlatada - colher de sopa cheia",
    ),
    _ibge(
        ("milho", "milho verde", "milho verde em conserva"),
        "colher de sopa",
        "24",
        "colher de sopa de milho verde",
        "7700401 | MILHO VERDE EM CONSERVA | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 16"
        " | COLHER DE SOPA | 24 | 1 | Milho verde enlatado - colher de sopa",
    ),
    _ibge(
        ("pimenta do reino", "pimenta do reino moida", "pimenta do reino em po"),
        "colher de cha",
        "1.5",
        "colher de chá de pimenta-do-reino",
        "7006101 | PIMENTA EM PO | 99 | NAO SE APLICA | 14 | COLHER DE CHA | 15"
        " | COLHER DE SOBREMESA | 1.5 | 14 | Pimenta em pó - colher de chá",
    ),
    _ibge(
        ("maionese", "maionese tradicional"),
        "colher de sopa",
        "27",
        "colher de sopa de maionese",
        "7004301 | MAIONESE (MOLHO) | 99 | NAO SE APLICA | 16 | COLHER DE SOPA | 86"
        " | PONTA DE FACA | 27 | 1 | Maionese - colher de sopa cheia",
    ),
    _ibge(
        ("maionese", "maionese tradicional"),
        "colher de cha",
        "6",
        "colher de chá de maionese",
        "7004301 | MAIONESE (MOLHO) | 99 | NAO SE APLICA | 14 | COLHER DE CHA | 86"
        " | PONTA DE FACA | 6 | 1 | Maionese - colher de chá cheia",
    ),
    # A linguiça da tabela é qualquer uma (de porco, de boi, mista): o gomo
    # cru. A calabresa e a fininha não têm linha própria, e ficam de fora.
    _ibge(
        ("linguica", "linguica defumada"),
        "",
        "60",
        "gomo de linguiça",
        "8102204 | LINGUICA (SUINA, BOVINA, MISTA, ETC) | 1 | CRU(A) | 67 | GOMO | 81"
        " | PEDACO | 60 | 1 | Lingüiça - gomo",
    ),
    _ibge(
        ("banana da terra",),
        "",
        "100",
        "banana-da-terra grande",
        "6801017 | PACOVA | 99 | NAO SE APLICA | 103 | UNIDADE | 103 | UNIDADE | 100 | 1"
        " | Banana-da-terra - unidade grande",
    ),
    # O que a tabela do IBGE não diz, pela tabela de porções do USDA.
    _usda(
        ("pimenta do reino", "pimenta do reino moida", "pimenta do reino em po"),
        "pitada",
        "0.1",
        "pitada de pimenta-do-reino",
        "170931 | Spices, pepper, black | 1 | dash | 0.1",
    ),
    _usda(
        ("paprica", "paprica doce", "paprica defumada", "paprica picante"),
        "colher de cha",
        "2.3",
        "colher de chá de páprica",
        "171329 | Spices, paprika | 1 | tsp | 2.3",
    ),
    _usda(
        ("extrato de tomate", "massa de tomate"),
        "xicara de cha",
        "262",
        "xícara de extrato de tomate",
        "170459 | Tomato products, canned, paste, without salt added (Includes foods for "
        "USDA's Food Distribution Program) | 1 | cup | 262",
    ),
    _usda(
        ("damasco", "damasco seco", "damascos"),
        "xicara de cha",
        "130",
        "xícara de damasco seco",
        "173941 | Apricots, dried, sulfured, uncooked | 1 | cup, halves | 130",
    ),
    _usda(
        ("farinha de amendoa", "farinha de amendoas", "amendoa moida"),
        "xicara de cha",
        "95",
        "xícara de amêndoa moída",
        "170567 | Nuts, almonds | 1 | cup, ground | 95",
    ),
    _usda(
        ("salsinha", "salsa", "cheiro verde", "salsinha cheiro verde"),
        "colher de sopa",
        "3.8",
        "colher de sopa de salsinha",
        "170416 | Parsley, fresh | 1 | tbsp | 3.8",
    ),
    _usda(
        ("alcaparras", "alcaparra"),
        "colher de sopa",
        "8.6",
        "colher de sopa de alcaparras",
        "172238 | Capers, canned | 1 | tbsp, drained | 8.6",
    ),
    _usda(
        ("coco ralado",),
        "xicara de cha",
        "93",
        "xícara de coco ralado",
        "168586 | Nuts, coconut meat, dried (desiccated), sweetened, shredded | 1 | "
        "cup, shredded | 93",
    ),
    # Classes: quando nenhuma fonte diz o peso deste ingrediente, a de um da mesma
    # classe, com a regra dita. É estimativa, e a conta fica do lado de cima.
    _usda(
        ("folha de louro", "louro", "folha de salvia", "folha de manjericao"),
        "",
        "0.5",
        "folha de louro, pela classe das folhas de erva",
        "172232 | Basil, fresh | 5 | leaves | 2.5",
        classe=(
            "folha de erva: a folha de manjericão fresco pesa 0,5 g na tabela do USDA; a "
            "de louro seca é mais leve, e a conta fica do lado de cima"
        ),
    ),
    _usda(
        ("ramo de alecrim", "ramo de tomilho", "ramo de salsinha", "ramo de manjericao"),
        "",
        "1",
        "ramo de erva, pela classe dos raminhos",
        "170416 | Parsley, fresh | 10 | sprigs | 10",
        classe="ramo de erva fresca: 10 raminhos de salsinha pesam 10 g na tabela do USDA",
    ),
    _usda(
        ("pimenta ardida", "pimenta dedo de moca", "pimenta malagueta", "pimenta vermelha"),
        "",
        "14",
        "pimenta ardida, pela classe das pimentas frescas",
        "168576 | Peppers, jalapeno, raw | 1 | pepper | 14",
        classe="pimenta ardida fresca: a pimenta jalapeño pesa 14 g na tabela do USDA",
    ),
    _usda(
        ("bacon", "bacon em cubos", "toucinho"),
        "xicara de cha",
        "205",
        "xícara de bacon em cubinhos, pela classe da gordura de porco",
        "171401 | Lard | 1 | cup | 205",
        classe=(
            "toucinho em cubinhos: a xícara de banha pesa 205 g na tabela do USDA, e o "
            "bacon em cubinhos, com o ar entre os cubos, pesa menos; a conta fica do lado de cima"
        ),
    ),
    MedidaDeReferencia(
        ("couve", "maco de couve", "couve manteiga", "maco de couve manteiga"),
        "",
        Decimal(200),
        "maço de couve, pela classe das verduras de folha",
        "6700101 | ALFACE | 99 | NAO SE APLICA | 77 | MACO | 34 | FOLHA | 200 | 1"
        " | Alface - unidade média",
        classe=(
            "maço de verdura de folha: o maço de alface pesa 200 g na tabela do IBGE; a "
            "couve se vende em maço, e uma couve na receita é o maço"
        ),
    ),
    MedidaDeReferencia(
        ("couro do bacon", "couro de bacon", "couro de porco", "toucinho"),
        "",
        Decimal(10),
        "pedaço de couro de bacon, pela classe do pedaço de toucinho",
        "7103801 | TOUCINHO | 99 | NAO SE APLICA | 81 | PEDACO | 81 | PEDACO | 10 | 4"
        " | Considerou - se a medida de 10g de bacon",
        classe="pedaço de toucinho: o pedaço pesa 10 g na tabela do IBGE",
    ),
    MedidaDeReferencia(
        ("cominho", "cominho em po", "cominho moido"),
        "colher de cha",
        Decimal("1.5"),
        "colher de chá de cominho em pó, pela classe dos temperos em pó",
        "7006101 | PIMENTA EM PO | 99 | NAO SE APLICA | 14 | COLHER DE CHA | 15"
        " | COLHER DE SOBREMESA | 1.5 | 14 | Pimenta em pó - colher de chá",
        classe="tempero em pó: a colher de chá de pimenta em pó pesa 1,5 g na tabela do IBGE",
    ),
)

#: As medidas contadas que a leitura reconhece ("3 ovos", "2 dentes de alho",
#: "2 folhas de louro"). Nem toda tem peso conhecido: a folha de louro não tem.
MEDIDAS_CONTADAS: Final[frozenset[str]] = frozenset(
    {
        "ovo",
        "dente de alho",
        "dente",
        "cebola",
        "cebola media",
        "tomate",
        "tomate medio",
        "batata",
        "batata media",
        "cenoura",
        "limao",
        "folha de louro",
    }
)

#: O peso de uma unidade das medidas contadas que a tabela do IBGE diz, em gramas.
PESOS_UNITARIOS: Final[dict[str, Decimal]] = {
    nome: m.gramas
    for m in MEDIDAS_DE_REFERENCIA
    if not m.medida
    for nome in m.ingredientes
    if nome in MEDIDAS_CONTADAS
}

#: Cada medida caseira da tabela pelo ingrediente e pela medida, com a linha que a prova.
_MEDIDA_CASEIRA: Final[dict[tuple[str, str], MedidaDeReferencia]] = {
    (nome, m.medida): m for m in MEDIDAS_DE_REFERENCIA for nome in m.ingredientes
}

#: Como a receita escreve a medida, e como a tabela a chama.
_MEDIDA_DA_TABELA: Final[dict[str, str]] = {
    "": "",
    "un": "",
    "und": "",
    "unidade": "",
    "colher": "colher de sopa",
    "colher sopa": "colher de sopa",
    "colher de sopa": "colher de sopa",
    "colher cha": "colher de cha",
    "colher de cha": "colher de cha",
    "colher de sobremesa": "colher de sobremesa",
    "xicara": "xicara de cha",
    "xicara cha": "xicara de cha",
    "xicara de cha": "xicara de cha",
    "pitada": "pitada",
}


def medida_de_referencia(medida: str, ingrediente: str) -> MedidaDeReferencia | None:
    """A medida caseira da tabela do IBGE para esta medida deste ingrediente, se há.

    `medida` vazia (ou "unidade") é uma unidade do ingrediente; uma medida
    contada ("cebola", "dente de alho") é ela mesma. O nome do ingrediente
    casa inteiro, sem acento: "tomate cereja" não é "tomate".
    """
    chave_medida = _sem_acento(medida).lower().strip()
    chave_ingrediente = " ".join(_sem_acento(ingrediente).lower().replace("-", " ").split())
    if chave_medida in MEDIDAS_CONTADAS:
        achada = _MEDIDA_CASEIRA.get((chave_medida, ""))
        return achada if achada is not None else None
    da_tabela = _MEDIDA_DA_TABELA.get(chave_medida)
    if da_tabela is None:
        return None
    direta = _MEDIDA_CASEIRA.get((chave_ingrediente, da_tabela)) or (
        _MEDIDA_CASEIRA.get((chave_ingrediente[:-1], da_tabela))
        if chave_ingrediente.endswith("s")
        else None
    )
    return direta or _pelo_nucleo(ingrediente, da_tabela)


def _pelo_nucleo(ingrediente: str, medida: str) -> MedidaDeReferencia | None:
    """A medida pelo núcleo do nome: "4 linguicinhas defumadas" é a linguiça defumada da tabela."""
    from mise.casamento import nucleo_do_nome  # noqa: PLC0415

    nucleo = nucleo_do_nome(ingrediente)
    if not nucleo:
        return None
    return next(
        (
            m
            for m in MEDIDAS_DE_REFERENCIA
            if m.medida == medida and nucleo in {nucleo_do_nome(n) for n in m.ingredientes}
        ),
        None,
    )


#: Densidade aparente (g/ml) por ingrediente. É "aparente" porque farinha
#: peneirada e farinha compactada diferem, e por isso guardamos a incerteza.
#: Sem isto, "1 xícara de farinha" custaria +89% a mais do que deveria.
DENSIDADES: Final[dict[str, tuple[Decimal, Decimal]]] = {
    # ingrediente -> (densidade média, incerteza relativa)
    "farinha de trigo": (Decimal("0.53"), Decimal("0.12")),
    "farinha de mandioca": (Decimal("0.65"), Decimal("0.10")),
    "farinha de rosca": (Decimal("0.45"), Decimal("0.12")),
    "fuba": (Decimal("0.68"), Decimal("0.08")),
    "polenta": (Decimal("0.68"), Decimal("0.08")),
    "amido de milho": (Decimal("0.52"), Decimal("0.10")),
    "acucar": (Decimal("0.85"), Decimal("0.05")),
    "acucar refinado": (Decimal("0.85"), Decimal("0.05")),
    "acucar mascavo": (Decimal("0.80"), Decimal("0.10")),
    "sal": (Decimal("1.20"), Decimal("0.05")),
    "arroz": (Decimal("0.85"), Decimal("0.05")),
    "feijao": (Decimal("0.80"), Decimal("0.06")),
    "leite": (Decimal("1.03"), Decimal("0.02")),
    "leite integral": (Decimal("1.03"), Decimal("0.02")),
    "agua": (Decimal("1.00"), Decimal("0.01")),
    "oleo": (Decimal("0.92"), Decimal("0.02")),
    "oleo de soja": (Decimal("0.92"), Decimal("0.02")),
    "azeite": (Decimal("0.91"), Decimal("0.02")),
    "azeite de oliva extra virgem": (Decimal("0.91"), Decimal("0.02")),
    "vinagre": (Decimal("1.01"), Decimal("0.02")),
    "aceto balsamico": (Decimal("1.05"), Decimal("0.03")),
    "manteiga": (Decimal("0.91"), Decimal("0.04")),
    "creme de leite": (Decimal("1.01"), Decimal("0.03")),
    "chantilly": (Decimal("0.50"), Decimal("0.15")),
    "queijo ralado": (Decimal("0.40"), Decimal("0.18")),
    "queijo parmesao ralado": (Decimal("0.40"), Decimal("0.18")),
    "leite em po": (Decimal("0.55"), Decimal("0.10")),
    "leite ninho em po": (Decimal("0.55"), Decimal("0.10")),
    "chocolate em po": (Decimal("0.45"), Decimal("0.12")),
    "amendoa fatiada": (Decimal("0.38"), Decimal("0.15")),
    "canela em po": (Decimal("0.45"), Decimal("0.12")),
    "acafrao em po": (Decimal("0.55"), Decimal("0.12")),
    "curcuma": (Decimal("0.55"), Decimal("0.12")),
}


@dataclass(frozen=True, slots=True)
class MedidaConvertida:
    """Conversão de uma medida de receita para a unidade-base, com auditoria.

    `incerteza_relativa` propaga para o CMV: quando é alta, o motor mostra faixa
    em vez de fingir precisão de centavo.
    """

    quantidade: Quantidade
    derivacao: str
    incerteza_relativa: Decimal
    #: A medida caseira da tabela do IBGE que fez a conta, quando foi ela: é o
    #: que ela pode corrigir com o peso da cozinha dela.
    referencia: MedidaDeReferencia | None = None

    @property
    def confiavel(self) -> bool:
        """Incerteza baixa o suficiente para exibir um número único."""
        return self.incerteza_relativa <= Decimal("0.10")


def converter_medida(
    valor: Decimal | float | int,
    medida: str,
    ingrediente: str = "",
) -> MedidaConvertida:
    """Converte "2 colheres de sopa de óleo" em uma `Quantidade` de base.

    A ordem de tentativa importa: massa direta (sem ambiguidade) -> a medida
    caseira da tabela do IBGE (o peso de uma unidade, a colher de sopa de
    margarina) -> volume (exige densidade do ingrediente).

    >>> c = converter_medida(1, "xicara", "farinha de trigo")
    >>> str(c.quantidade)
    '0.1272 kg'
    """
    quantidade_bruta = Decimal(str(valor))
    if quantidade_bruta < 0 or not quantidade_bruta.is_finite():
        raise QuantidadeInvalida(valor, f"medida {medida!r}")

    chave_medida = _sem_acento(medida).lower().strip()
    chave_ingrediente = _sem_acento(ingrediente).lower().strip()

    # Massa declarada diretamente: nada a inferir.
    if fator_g := MEDIDAS_MASSA.get(chave_medida):
        gramas = quantidade_bruta * fator_g
        return MedidaConvertida(
            quantidade=Quantidade(gramas / Decimal("1000"), Dimensao.MASSA),
            derivacao=(
                f"{_limpa(quantidade_bruta)} {_medida_escrita(medida, quantidade_bruta)} "
                f"= {_limpa(gramas)} g"
            ),
            incerteza_relativa=Decimal("0"),
        )

    # Itens contados e medidas caseiras que a tabela do IBGE diz: o peso de
    # uma cebola, a colher de sopa de margarina. Vale mais que a densidade
    # achada por pedaço do nome ("leite" no "leite condensado").
    caseira = medida_de_referencia(medida, ingrediente)
    if caseira is not None:
        return _pela_tabela(quantidade_bruta, medida, caseira)

    # Volume: só converte para massa se soubermos a densidade.
    if (ml_por_medida := MEDIDAS_VOLUME.get(chave_medida)) is not None:
        mililitros = quantidade_bruta * ml_por_medida
        densidade = _buscar_densidade(chave_ingrediente)

        if densidade is None:
            # Líquidos custados por litro não precisam de densidade.
            raise DensidadeDesconhecida(ingrediente or "(ingrediente não informado)", medida)

        g_por_ml, incerteza = densidade
        gramas = mililitros * g_por_ml
        return MedidaConvertida(
            quantidade=Quantidade(gramas / Decimal("1000"), Dimensao.MASSA),
            derivacao=(
                f"{_limpa(quantidade_bruta)} {_medida_escrita(medida, quantidade_bruta)} "
                f"= {_limpa(mililitros)} ml × {_limpa(g_por_ml)} g/ml = {_limpa(gramas)} g"
            ),
            incerteza_relativa=incerteza,
        )

    raise UnidadeNaoNormalizavel(medida, ingrediente or None)


def _pela_tabela(quantidade: Decimal, medida: str, caseira: MedidaDeReferencia) -> MedidaConvertida:
    """A medida em gramas pela tabela do IBGE, com a incerteza de medida caseira."""
    gramas = quantidade * caseira.gramas
    if caseira.medida:
        escrita = f"{_limpa(quantidade)} {_medida_escrita(medida, quantidade)}"
        conta = f"{escrita} × {_limpa(caseira.gramas)} g"
    else:
        conta = f"{_limpa(quantidade)} × {_limpa(caseira.gramas)} g"
    return MedidaConvertida(
        quantidade=Quantidade(gramas / Decimal("1000"), Dimensao.MASSA),
        derivacao=(
            f"{conta} ({caseira.descricao}, pela referência de {caseira.fonte.curto}) "
            f"= {_limpa(gramas)} g"
        ),
        incerteza_relativa=INCERTEZA_DA_MEDIDA_CASEIRA,
        referencia=caseira,
    )


def classificar_medida(medida: str) -> Dimensao | None:
    """Que grandeza a medida de uma receita expressa?

    Existe porque a dimensão da despensa **não** basta para decidir como
    custear. "Cobertura de chocolate" é vendida por peça, mas a receita pede
    "200 g": tratar 200 como contagem produziria 200 embalagens. A medida da
    receita é que manda; a dimensão da despensa só diz se dá para atender.

    Devolve `None` quando a medida não é reconhecida.
    """
    chave = _sem_acento(medida).lower().strip()
    if not chave:
        return Dimensao.CONTAGEM
    if chave in MEDIDAS_MASSA:
        return Dimensao.MASSA
    if chave in MEDIDAS_VOLUME:
        return Dimensao.VOLUME
    if chave in MEDIDAS_CONTADAS:
        return Dimensao.CONTAGEM
    return None


def converter_medida_para_volume(
    valor: Decimal | float | int,
    medida: str,
) -> MedidaConvertida:
    """Converte uma medida de volume mantendo-a em litros (sem densidade).

    Usada para ingredientes que a planilha custa por litro (óleo, leite), onde
    converter para massa seria um desvio desnecessário e imprecisão gratuita.
    """
    quantidade_bruta = Decimal(str(valor))
    chave = _sem_acento(medida).lower().strip()
    ml_por_medida = MEDIDAS_VOLUME.get(chave)
    if ml_por_medida is None:
        raise UnidadeNaoNormalizavel(medida)

    mililitros = quantidade_bruta * ml_por_medida
    return MedidaConvertida(
        quantidade=Quantidade(mililitros / Decimal("1000"), Dimensao.VOLUME),
        derivacao=(
            f"{_limpa(quantidade_bruta)} {_medida_escrita(medida, quantidade_bruta)} "
            f"= {_limpa(mililitros)} ml"
        ),
        incerteza_relativa=Decimal("0.02"),
    )


def _buscar_densidade(chave: str) -> tuple[Decimal, Decimal] | None:
    """Busca densidade por nome exato e depois pelo nome que aparece inteiro, palavra por palavra.

    "sal" não está em "salsinha": achar densidade por pedaço de palavra deu à
    salsinha a densidade do sal, e uma colher de sopa dela pesava 18 g.
    """
    if direto := DENSIDADES.get(chave):
        return direto
    candidatos = [
        (nome, d)
        for nome, d in DENSIDADES.items()
        if re.search(rf"\b{re.escape(nome)}\b", chave)
        or re.search(rf"\b{re.escape(chave)}\b", nome)
    ]
    if not candidatos:
        return None
    # O nome mais longo é o mais específico: "queijo parmesao ralado" > "queijo ralado".
    return max(candidatos, key=lambda par: len(par[0]))[1]


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #


def _sem_acento(texto: str) -> str:
    """Remove acentos preservando as letras: "açúcar" vira "acucar"."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _limpa(valor: Decimal) -> str:
    """Formata Decimal como se escreve no Brasil: vírgula, sem zeros à direita.

    É o texto da conta que ela lê na tela e que o agente repete: "0,5 kg", não
    "0.5 kg". O número guardado continua Decimal; só a escrita é daqui.
    """
    normalizado = valor.normalize()
    if normalizado == normalizado.to_integral_value():
        return str(normalizado.quantize(Decimal("1")))
    return f"{normalizado:f}".replace(".", ",")


#: Como cada medida se escreve para ela: com acento, e no plural a partir de
#: duas. O vocabulário das tabelas acima é chave de busca, sem acento; "2
#: xicara" na conta da tela parecia defeito, e era.
_ESCRITA: Final[dict[str, tuple[str, str]]] = {
    "xicara": ("xícara", "xícaras"),
    "xicara de cha": ("xícara de chá", "xícaras de chá"),
    "xicara cha": ("xícara de chá", "xícaras de chá"),
    "copo": ("copo", "copos"),
    "copo americano": ("copo americano", "copos americanos"),
    "copo de requeijao": ("copo de requeijão", "copos de requeijão"),
    "colher": ("colher", "colheres"),
    "colher de sopa": ("colher de sopa", "colheres de sopa"),
    "colher sopa": ("colher de sopa", "colheres de sopa"),
    "colher de sobremesa": ("colher de sobremesa", "colheres de sobremesa"),
    "colher de cha": ("colher de chá", "colheres de chá"),
    "colher cha": ("colher de chá", "colheres de chá"),
    "colher de cafe": ("colher de café", "colheres de café"),
    "pitada": ("pitada", "pitadas"),
    "fio": ("fio", "fios"),
    "litro": ("litro", "litros"),
    "quilo": ("quilo", "quilos"),
    "grama": ("grama", "gramas"),
}


#: Em português o plural começa no dois: "1,5 xícara", "2 xícaras".
_PLURAL_A_PARTIR_DE: Final = Decimal(2)


#: As medidas que pedem artigo feminino: "uma xícara", "uma colher".
_FEMININAS: Final = ("xicara", "colher", "pitada", "lata", "caixa", "fatia", "folha")


def medida_com_artigo(medida: str) -> str:
    """ "uma colher de sopa", "uma xícara de chá", "um copo americano": uma medida, falada."""
    chave = _sem_acento(medida).lower().strip()
    escrita = _medida_escrita(medida, Decimal(1)).strip() or "medida"
    artigo = "uma" if chave.startswith(_FEMININAS) or not chave else "um"
    return f"{artigo} {escrita}"


def _medida_escrita(medida: str, quantidade: Decimal) -> str:
    """A medida como se escreve: "1 xícara", "2 xícaras", "1,5 colher de sopa"."""
    formas = _ESCRITA.get(_sem_acento(medida).lower().strip())
    if formas is None:
        return medida
    return formas[1] if quantidade >= _PLURAL_A_PARTIR_DE else formas[0]
