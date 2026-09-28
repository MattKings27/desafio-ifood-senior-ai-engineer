"""Os preços de referência: o preço médio em São Paulo do que falta comprar.

A Dona Maria não é perguntada quanto custa o que falta. O preço sai dos
supermercados de São Paulo, lido pelo servidor no catálogo de cada um
(`retrieval.precos`), e cada ingrediente tem várias fontes. As regras:

- **o preço é a média de São Paulo, com as fontes.** Cada fonte é um produto
  num mercado de São Paulo, com o conteúdo da embalagem, o preço, o endereço,
  a data e o trecho literal da resposta da API do mercado. O preço de cada uma
  vira preço da unidade-base (o quilo, o litro, a unidade), e o preço médio em
  São Paulo é a média delas: "média de 3 mercados de São Paulo: R$ 18,95,
  R$ 21,60 e R$ 24,25 o quilo, em 27/09/2026";
- **a fonte fora da curva sai da média.** Com 3 fontes ou mais, a que fica mais
  de 50% longe da mediana (abaixo da metade ou acima de 1,5 vez) não entra na
  conta, e o texto diz qual saiu. Com 2, as duas entram, e também quando
  sobraria menos de duas: aí não se sabe quem está fora;
- **ela compra a embalagem, não o quilo.** O que ela leva é a menor embalagem,
  entre as dos mercados, que cobre o que falta (sem nenhuma que cubra, a maior,
  quantas vezes precisar), pelo preço médio: o preço médio do quilo vezes o
  tamanho da embalagem, no centavo. O vendido a peso (a cenoura, o limão) sai
  na medida certa. A conta é a de sempre (`mise.compras.precificar_falta`);
- **o preço dela sempre vale mais.** A cotação que ela deu e o preço que ela
  pagou na despensa vêm antes; corrigir é dar a cotação dela;
- **sem fonte, não há número.** A referência só vale quando a medida da receita
  se compara com a embalagem: o grama com o grama, a lata com a lata, a unidade
  com a unidade, o tablete com a caixa que diz quantos tabletes tem, a unidade
  pelo peso da tabela do IBGE, ou a colher pelo peso da colher na tabela do
  IBGE (`mise.unidades.medida_de_referencia`). O tempero seco (em pó ou em
  folha) que a receita mede em colher, pitada ou folha leva o pacote menor:
  tempero seco pesa menos que a água, e a colher de chá (5 ml) pesa menos de
  5 g; sem medida nenhuma, ou contado sem peso ("3 pimentas", "1 stick"), a
  conta leva o pacote inteiro, que é o que ela compra, e diz isso;
- **o orçamento continua valendo.** A compra pelo preço médio entra na conta
  dos R$ 80,00 como qualquer outra: o que não cabe não dá.

O arquivo fica ao lado da planilha (`dados/precos_de_referencia.json`), ou onde
`MISE_PRECOS_DE_REFERENCIA` disser. `make conferir-referencias` busca cada fonte
de novo e prova que o nome e o preço continuam na resposta do mercado.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import logging
import os
import statistics
import unicodedata
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from mise.casamento import nucleo_do_nome
from mise.compras import Cotacao, Medida
from mise.dinheiro import CENTAVO, Dinheiro
from mise.unidades import MEDIDAS_VOLUME, Dimensao, Quantidade, medida_de_referencia

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from mise.despensa import Despensa

logger = logging.getLogger(__name__)

#: O arquivo dos preços de referência, ao lado da planilha.
ARQUIVO_DOS_PRECOS: Final = "precos_de_referencia.json"
#: Outro arquivo de preços de referência, no lugar do que fica ao lado da planilha.
VAR_PRECOS: Final = "MISE_PRECOS_DE_REFERENCIA"

#: A fonte que fica mais longe que isto da mediana (em fração dela) sai da média.
DISTANCIA_MAXIMA: Final = Decimal("0.5")
#: Com menos fontes que isto, nenhuma sai: não se sabe qual das duas está fora.
FONTES_PARA_TIRAR: Final = 3

#: O que a unidade da embalagem vale na unidade-base.
_BASE: Final[dict[str, tuple[Dimensao, Decimal]]] = {
    "g": (Dimensao.MASSA, Decimal("0.001")),
    "kg": (Dimensao.MASSA, Decimal(1)),
    "ml": (Dimensao.VOLUME, Decimal("0.001")),
    "l": (Dimensao.VOLUME, Decimal(1)),
    "un": (Dimensao.CONTAGEM, Decimal(1)),
}

#: As embalagens que são a mesma coisa na receita e na prateleira: "1 caixinha
#: de creme de leite" é a caixa da referência; "1 lata" não é.
_EMBALAGENS: Final[dict[str, str]] = {
    "lata": "lata",
    "latinha": "lata",
    "caixa": "caixa",
    "caixinha": "caixa",
    "pacote": "pacote",
    "pacotinho": "pacote",
    "saco": "pacote",
    "saquinho": "pacote",
    "vidro": "vidro",
    "vidrinho": "vidro",
    "sache": "sache",
    "pote": "pote",
    "potinho": "pote",
    "garrafa": "garrafa",
    "garrafinha": "garrafa",
    "bandeja": "bandeja",
    "maco": "maco",
}

#: As embalagens que se dizem no feminino: "pela caixinha", "pelo pacote".
_FEMININAS: Final = frozenset(
    {"caixa", "caixinha", "lata", "latinha", "garrafa", "bandeja", "unidade"}
)

#: Como a embalagem se escreve para ela.
_ESCRITA: Final[dict[str, str]] = {"sache": "sachê", "maco": "maço"}

#: Como se diz a unidade-base no preço médio: "R$ 21,60 o quilo".
_POR_BASE: Final[dict[Dimensao, str]] = {
    Dimensao.MASSA: "o quilo",
    Dimensao.VOLUME: "o litro",
    Dimensao.CONTAGEM: "a unidade",
}

#: As medidas caseiras que a tabela do IBGE pesa, com o volume que o motor dá a elas.
_COLHERES_DO_IBGE: Final[tuple[str, ...]] = ("colher de cha", "colher de sopa", "xicara de cha")


def _chave(texto: str) -> str:
    """Sem acento, sem hífen, em minúscula e com os espaços juntos."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().replace("-", " ").split())


def _numero(valor: Decimal) -> str:
    n = valor.normalize()
    if n == n.to_integral_value():
        return str(n.quantize(Decimal(1)))
    return f"{n:f}".replace(".", ",")


def _lista(itens: Sequence[str]) -> str:
    """ "a, b e c"."""
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


@dataclass(frozen=True, slots=True)
class FonteDoPreco:
    """O preço de um produto num mercado de São Paulo, com a prova de onde saiu."""

    site: str
    #: O nome do produto como o mercado escreve ("Creme de Leite Piracanjuba 200g").
    produto: str
    preco: Dinheiro
    quantidade: Decimal
    #: `g`, `kg`, `ml`, `L` ou `un`.
    unidade: str
    #: A página do produto, para ela abrir.
    url: str
    data: dt.date
    #: O campo da resposta que tem o preço e o trecho literal dele.
    campo: str
    trecho: str
    #: A consulta da API do mercado que prova o preço (com a região do CEP).
    api: str = ""
    #: Vendido a peso: o preço é o do quilo.
    a_granel: bool = False

    @property
    def base(self) -> Quantidade:
        """O conteúdo na unidade-base: 0,2 kg, 0,9 L, 6 unidades."""
        dimensao, fator = _BASE[self.unidade.casefold()]
        return Quantidade(self.quantidade * fator, dimensao)

    @property
    def por_base(self) -> Decimal:
        """O preço do quilo, do litro ou da unidade, sem arredondar."""
        return self.preco.valor / self.base.valor

    @property
    def data_texto(self) -> str:
        return f"{self.data:%d/%m/%Y}"

    @property
    def preco_texto(self) -> str:
        """ "R$ 3,79 por 200 g", "R$ 3,69 por 6 unidades", ou "R$ 8,99 o quilo" (a peso)."""
        if self.a_granel:
            return f"{self.preco} o quilo"
        if self.base.dimensao is Dimensao.CONTAGEM:
            unidades = "unidade" if self.quantidade == 1 else "unidades"
            return f"{self.preco} por {_numero(self.quantidade)} {unidades}"
        return f"{self.preco} por {_numero(self.quantidade)} {self.unidade}"


@dataclass(frozen=True, slots=True)
class PrecoDeReferencia:
    """O preço médio em São Paulo de um ingrediente, com as fontes que o provam.

    `pacote` é o tamanho da embalagem que ela compra, na unidade-base, escolhido
    para o que falta (`na_compra`); sem ele, vale a menor embalagem das fontes.
    """

    ingrediente: str
    #: Os nomes que a receita usa para este produto, e só para ele.
    nomes: tuple[str, ...]
    #: "caixinha", "pacote", "lata", "quilo" (vendido a peso) ou "unidade".
    embalagem: str
    fontes: tuple[FonteDoPreco, ...]
    #: Palavras que dizem que é outro produto: "creme de leite fresco" não é a caixinha.
    evitar: tuple[str, ...] = ()
    #: Na embalagem de várias unidades ("caixa com 6 tabletes"), o que é cada uma:
    #: "tablete", "sachê". A receita que pede "2 tabletes" leva 2 das 6 da caixa.
    cada: str = ""
    #: O que ela precisa saber do produto ("a pimenta ardida mais comum é a dedo-de-moça").
    nota: str = ""
    #: Tempero seco (em pó ou em folha): a colher e a pitada cabem no pacote menor.
    tempero_seco: bool = False
    pacote: Decimal | None = None
    #: O que a conta supôs da medida, quando a receita não disse o bastante.
    suposicao: str = ""

    # -- as fontes e a média ------------------------------------------------ #

    @property
    def dimensao(self) -> Dimensao:
        return self.fontes[0].base.dimensao

    @property
    def mediana(self) -> Decimal:
        return Decimal(statistics.median(f.por_base for f in self.fontes))

    def _longe(self, fonte: FonteDoPreco) -> bool:
        mediana = self.mediana
        return abs(fonte.por_base - mediana) > DISTANCIA_MAXIMA * mediana

    def _fora(self, fonte: FonteDoPreco) -> bool:
        """Mais de 50% longe da mediana, com 3 fontes ou mais, e sobrando pelo menos 2."""
        if len(self.fontes) < FONTES_PARA_TIRAR:
            return False
        ficam = sum(1 for f in self.fontes if not self._longe(f))
        return ficam >= FONTES_PARA_TIRAR - 1 and self._longe(fonte)

    @property
    def na_media(self) -> tuple[FonteDoPreco, ...]:
        """As fontes que entram na média: sem a que fica mais de 50% longe da mediana."""
        return tuple(f for f in self.fontes if not self._fora(f))

    @property
    def fora_da_media(self) -> tuple[FonteDoPreco, ...]:
        return tuple(f for f in self.fontes if self._fora(f))

    @property
    def preco_medio(self) -> Decimal:
        """A média do preço do quilo (do litro, da unidade) nas fontes que entram."""
        validas = self.na_media
        return sum((f.por_base for f in validas), Decimal(0)) / len(validas)

    @property
    def preco_medio_texto(self) -> str:
        """ "R$ 21,60 o quilo"."""
        return f"{Dinheiro(self.preco_medio)} {self.por_base_texto}"

    @property
    def por_base_texto(self) -> str:
        """ "o quilo", "o litro", "a unidade", "o tablete": como se diz a unidade-base."""
        if self.dimensao is Dimensao.CONTAGEM and self.cada:
            artigo = "a" if self.cada in ("unidade", "caixa") else "o"
            return f"{artigo} {_ESCRITA.get(_chave(self.cada), self.cada)}"
        return _POR_BASE[self.dimensao]

    @property
    def data(self) -> dt.date:
        return max(f.data for f in self.na_media)

    @property
    def data_texto(self) -> str:
        return f"{self.data:%d/%m/%Y}"

    @property
    def media_texto(self) -> str:
        """A conta da média, com os preços do quilo de cada mercado e a data.

        "média de 3 mercados de São Paulo: R$ 18,95, R$ 21,60 e R$ 24,25 o quilo, em 27/09/2026".
        """
        validas = self.na_media
        precos = _lista([str(Dinheiro(f.por_base)) for f in validas])
        datas = sorted({f.data for f in validas})
        quando = (
            f"em {datas[0]:%d/%m/%Y}"
            if len(datas) == 1
            else f"entre {datas[0]:%d/%m/%Y} e {datas[-1]:%d/%m/%Y}"
        )
        if len(validas) == 1:
            texto = (
                f"preço de 1 mercado de São Paulo ({validas[0].site}): "
                f"{precos} {self.por_base_texto}, {quando}"
            )
        else:
            texto = (
                f"média de {len(validas)} mercados de São Paulo: "
                f"{precos} {self.por_base_texto}, {quando}"
            )
        fora = self.fora_da_media
        if fora:
            saiu = _lista(
                [f"{f.site} ({Dinheiro(f.por_base)} {self.por_base_texto})" for f in fora]
            )
            texto += f"; fora da média, por ficar mais de 50% longe da mediana: {saiu}"
        return texto

    # -- a embalagem que ela compra ----------------------------------------- #

    @property
    def a_granel(self) -> bool:
        """Vendido a peso: ela leva o quanto precisa, sem arredondar para o quilo inteiro."""
        return self.embalagem == "quilo" or all(f.a_granel for f in self.na_media)

    @property
    def tamanhos(self) -> tuple[Decimal, ...]:
        """Os tamanhos de embalagem das fontes da média, na unidade-base, do menor ao maior."""
        if self.a_granel:
            return (Decimal(1),)
        return tuple(sorted({f.base.valor for f in self.na_media if not f.a_granel}))

    @property
    def tamanho(self) -> Decimal:
        return self.pacote if self.pacote is not None else self.tamanhos[0]

    @property
    def por(self) -> Medida:
        """O que o preço compra: a embalagem que ela leva (0,2 kg, 0,9 L, 6 unidades)."""
        return Medida(Quantidade(self.tamanho, self.dimensao))

    @property
    def preco(self) -> Dinheiro:
        """O preço da embalagem pelo preço médio: o do quilo vezes o tamanho, no centavo."""
        valor = (self.preco_medio * self.tamanho).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        return Dinheiro(valor)

    @property
    def cotacao(self) -> Cotacao:
        return Cotacao(self.preco, self.por, origem="referencia", a_granel=self.a_granel)

    def na_compra(self, falta: Medida | None) -> PrecoDeReferencia:
        """A mesma referência com a embalagem que ela compra para o que falta.

        A menor embalagem que cobre o que falta; sem nenhuma que cubra, a
        maior, quantas vezes precisar. Sem saber quanto falta, a menor.
        """
        tamanhos = self.tamanhos
        if falta is None or not falta.compativel(Medida(Quantidade(Decimal(1), self.dimensao))):
            return replace(self, pacote=tamanhos[0])
        precisa = falta.quantidade.valor
        cobrem = [t for t in tamanhos if t >= precisa]
        return replace(self, pacote=cobrem[0] if cobrem else tamanhos[-1])

    @property
    def _da_embalagem(self) -> FonteDoPreco:
        """A fonte que vende a embalagem que ela compra (a primeira, se nenhuma vende)."""
        validas = self.na_media
        return next((f for f in validas if f.base.valor == self.tamanho), validas[0])

    @property
    def produto(self) -> str:
        return self._da_embalagem.produto

    @property
    def url(self) -> str:
        return self._da_embalagem.url

    @property
    def site(self) -> str:
        """Quem dá o preço: "mercado de São Paulo" (a média), ou o mercado da fonte única."""
        validas = self.na_media
        return validas[0].site if len(validas) == 1 else "mercado de São Paulo"

    @property
    def quantidade(self) -> Decimal:
        """O tamanho da embalagem na unidade que ela lê (200 g, 1 kg, 900 ml, 6)."""
        if self.dimensao is not Dimensao.CONTAGEM and self.tamanho < 1:
            return self.tamanho * 1000
        return self.tamanho

    @property
    def unidade(self) -> str:
        if self.dimensao is Dimensao.CONTAGEM:
            return "un"
        if self.tamanho < 1:
            return "g" if self.dimensao is Dimensao.MASSA else "ml"
        return "kg" if self.dimensao is Dimensao.MASSA else "L"

    @property
    def embalagem_texto(self) -> str:
        """ "caixinha de 200 g", "quilo", "unidade", "lata de 395 g", "caixa com 6 tabletes"."""
        if self.embalagem in ("quilo", "unidade") and self.quantidade == 1:
            return self.embalagem
        escrita = _ESCRITA.get(_chave(self.embalagem), self.embalagem)
        if self.cada:
            varias = self.cada if self.quantidade == 1 else f"{self.cada}s"
            return f"{escrita} com {_numero(self.quantidade)} {varias}"
        if self.dimensao is Dimensao.CONTAGEM:
            if self.quantidade == 1:
                return escrita
            return f"{escrita} com {_numero(self.quantidade)} unidades"
        unidade = "L" if self.unidade == "L" else self.unidade
        return f"{escrita} de {_numero(self.quantidade)} {unidade}"

    @property
    def preco_texto(self) -> str:
        """ "R$ 4,32 pela caixinha de 200 g, preço médio em São Paulo, 27/09/2026"."""
        pela = "pela" if self.embalagem in _FEMININAS else "pelo"
        validas = self.na_media
        onde = f"no {validas[0].site}" if len(validas) == 1 else "preço médio em São Paulo"
        return f"{self.preco} {pela} {self.embalagem_texto}, {onde}, {self.data_texto}"

    @property
    def titulo(self) -> str:
        """ "preço médio em São Paulo", ou "preço em São Paulo" com uma fonte só."""
        return "preço médio em São Paulo" if len(self.na_media) > 1 else "preço em São Paulo"

    @property
    def texto(self) -> str:
        """A frase que acompanha todo número que sai daqui."""
        pela = "pela" if self.embalagem in _FEMININAS else "pelo"
        partes = [f"{self.titulo}: {self.preco} {pela} {self.embalagem_texto} ({self.media_texto})"]
        if self.nota:
            partes.append(self.nota)
        if self.suposicao:
            partes.append(self.suposicao)
        partes.append("a senhora pode corrigir")
        return "; ".join(partes)

    # -- o nome e a medida da receita --------------------------------------- #

    def casa(self, nome: str) -> bool:
        """O nome da receita é este produto? Pelo nome inteiro, ou pelo núcleo sem o que evitar."""
        chave = _chave(nome)
        if any(f" {_chave(palavra)} " in f" {chave} " for palavra in self.evitar):
            return False
        chaves = {_chave(n) for n in self.nomes}
        if chave in chaves or (chave.endswith("s") and chave[:-1] in chaves):
            return True
        nucleo = nucleo_do_nome(nome)
        return bool(nucleo) and nucleo in {nucleo_do_nome(n) for n in self.nomes}

    def na_embalagem(self, falta: Medida | None, nome: str) -> Medida | None:
        """O que falta, numa medida que se compara com a da embalagem; `None` se não dá.

        A medida igual passa como está. A embalagem da receita igual à da
        referência ("1 lata" de milho, a lata menor das fontes) vira o conteúdo
        dela. A unidade vira gramas, e os gramas viram unidades, pelo peso da
        tabela do IBGE; a colher vira gramas pelo peso da colher na tabela. O
        resto não se compara.
        """
        if falta is None:
            return None
        if falta.compativel(self.por):
            return falta
        if falta.quantidade.dimensao is Dimensao.CONTAGEM and falta.embalagem:
            if self.cada and _chave(falta.embalagem).rstrip("s") == _chave(self.cada).rstrip("s"):
                # "2 tabletes" da caixa com 6: são 2 das unidades que ela conta.
                return Medida(Quantidade(falta.quantidade.valor, Dimensao.CONTAGEM))
            return self._pela_embalagem(falta)
        if falta.quantidade.dimensao is Dimensao.VOLUME:
            return self._pela_colher(falta, nome)
        return self._pelo_peso(falta, nome)

    def _pela_embalagem(self, falta: Medida) -> Medida | None:
        """ "1 lata" de milho é a lata da referência, quando ela é uma lata."""
        mesma = _EMBALAGENS.get(_chave(falta.embalagem))
        if mesma is None or mesma != _EMBALAGENS.get(_chave(self.embalagem)):
            return None
        por = Quantidade(self.tamanhos[0], self.dimensao)
        return Medida(Quantidade(falta.quantidade.valor * por.valor, por.dimensao))

    def _pelo_peso(self, falta: Medida, nome: str) -> Medida | None:
        """A unidade em gramas, ou os gramas em unidades, pelo peso da tabela do IBGE."""
        peso = medida_de_referencia("", nome) or medida_de_referencia("", self.ingrediente)
        de, para = falta.quantidade.dimensao, self.dimensao
        if peso is None or {de, para} != {Dimensao.CONTAGEM, Dimensao.MASSA}:
            return None
        quilos = peso.gramas / Decimal(1000)
        valor = falta.quantidade.valor
        return Medida(
            Quantidade(valor * quilos if de is Dimensao.CONTAGEM else valor / quilos, para)
        )

    def _pela_colher(self, falta: Medida, nome: str) -> Medida | None:
        """O volume em gramas, pelo peso da colher (ou da xícara) na tabela do IBGE.

        Sem a colher na tabela, o tempero seco pesa no máximo o que a água pesa:
        a colher de chá (5 ml) leva até 5 g, e o pacote menor cobre, se tem mais.
        """
        if self.dimensao is not Dimensao.MASSA:
            return None
        mililitros = falta.quantidade.valor * 1000
        for medida in _COLHERES_DO_IBGE:
            peso = medida_de_referencia(medida, nome) or medida_de_referencia(
                medida, self.ingrediente
            )
            if peso is not None:
                por_ml = peso.gramas / MEDIDAS_VOLUME[medida]
                return Medida(Quantidade(mililitros * por_ml / 1000, Dimensao.MASSA))
        if self.tempero_seco and mililitros / 1000 <= self.tamanhos[0]:
            return Medida(Quantidade(mililitros / 1000, Dimensao.MASSA))
        return None

    def _suposicao(self, falta: Medida | None, medida: Medida | None, nome: str) -> str:
        """O que a conta supôs, dito para ela; `""` quando a medida veio de fonte."""
        if falta is None:
            return (
                "a receita não diz quanto vai, e a conta leva o pacote inteiro, "
                "que é o que a senhora compra"
            )
        if medida is None:
            quantas = _numero(falta.quantidade.valor)
            return (
                f"a receita pede {quantas} e não diz quanto pesa; a conta leva o pacote "
                "inteiro, que é o que a senhora compra"
            )
        if (
            medida is not None
            and falta.quantidade.dimensao is Dimensao.VOLUME
            and self.dimensao is Dimensao.MASSA
            and not any(
                medida_de_referencia(m, nome) or medida_de_referencia(m, self.ingrediente)
                for m in _COLHERES_DO_IBGE
            )
        ):
            gramas = _numero((medida.quantidade.valor * 1000).normalize())
            return (
                f"a medida da receita pesa até {gramas} g, porque o tempero seco pesa "
                "menos que a água, e a conta usa esse peso"
            )
        return ""


@dataclass(frozen=True, slots=True)
class PrecosDeReferencia:
    """Os preços de referência conhecidos, na ordem do arquivo."""

    precos: tuple[PrecoDeReferencia, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.precos)

    def __add__(self, outros: PrecosDeReferencia) -> PrecosDeReferencia:
        return PrecosDeReferencia(self.precos + outros.precos)

    def de(self, nome: str) -> tuple[PrecoDeReferencia, ...]:
        """Os preços deste produto, o principal primeiro."""
        return tuple(p for p in self.precos if p.casa(nome))

    def cotar(
        self, nome: str, falta: Medida | None
    ) -> tuple[PrecoDeReferencia, Medida | None] | None:
        """O preço que cota esta falta, já com a embalagem que ela compra, e a falta nela.

        Com mais de uma embalagem do mesmo produto, vale a que a receita pede
        ("1 lata de creme de leite", a lata); senão, a primeira que se compara.
        O tempero seco sem medida nenhuma volta com a falta `None`: a conta leva
        o pacote inteiro.
        """
        candidatos = [(p, p.na_embalagem(falta, nome)) for p in self.de(nome)]
        validos = [(p, medida) for p, medida in candidatos if medida is not None]
        if not validos:
            seco = next((p for p in self.de(nome) if p.tempero_seco), None)
            contada = falta is not None and falta.quantidade.dimensao is Dimensao.CONTAGEM
            if seco is not None and (falta is None or contada):
                return self._escolhida(seco, falta, None, nome)
            return None
        if falta is not None and falta.embalagem:
            pedida = _EMBALAGENS.get(_chave(falta.embalagem))
            for preco, medida in validos:
                if _EMBALAGENS.get(_chave(preco.embalagem)) == pedida:
                    return self._escolhida(preco, falta, medida, nome)
        preco, medida = validos[0]
        return self._escolhida(preco, falta, medida, nome)

    @staticmethod
    def _escolhida(
        preco: PrecoDeReferencia, falta: Medida | None, medida: Medida | None, nome: str
    ) -> tuple[PrecoDeReferencia, Medida | None]:
        escolhido = replace(
            preco.na_compra(medida), suposicao=preco._suposicao(falta, medida, nome)
        )
        return escolhido, medida


# --------------------------------------------------------------------------- #
# O arquivo                                                                    #
# --------------------------------------------------------------------------- #


def _fonte_do_registro(bruto: Mapping[str, Any]) -> FonteDoPreco:
    """Uma fonte do arquivo, conferida: sem prova, sem preço positivo ou sem medida, é recusada."""
    textos = {
        campo: str(bruto.get(campo) or "").strip()
        for campo in ("produto", "unidade", "url", "site", "data", "campo", "trecho")
    }
    faltam = sorted(campo for campo, valor in textos.items() if not valor)
    if faltam:
        raise ValueError(f"falta {', '.join(faltam)}")
    api = str(bruto.get("api") or "").strip()
    for endereco in (textos["url"], api or "https://"):
        if not endereco.startswith("https://"):
            raise ValueError("a página e a consulta precisam ser https")
    if textos["unidade"].casefold() not in _BASE:
        raise ValueError(f"unidade desconhecida: {textos['unidade']!r}")
    try:
        preco = Decimal(str(bruto["preco"]))
        quantidade = Decimal(str(bruto["quantidade"]))
    except (KeyError, InvalidOperation) as erro:
        raise ValueError("preço ou quantidade que não é número") from erro
    if not (preco.is_finite() and preco > 0 and quantidade.is_finite() and quantidade > 0):
        raise ValueError("preço e quantidade precisam ser positivos")
    try:
        no_trecho = Decimal(textos["trecho"].rsplit(":", 1)[-1].strip())
    except InvalidOperation as erro:
        raise ValueError("o trecho da resposta precisa terminar no preço") from erro
    if no_trecho != preco:
        raise ValueError("o trecho da resposta precisa ter o preço")
    return FonteDoPreco(
        site=textos["site"],
        produto=textos["produto"],
        preco=Dinheiro(preco),
        quantidade=quantidade,
        unidade=textos["unidade"],
        url=textos["url"],
        data=dt.date.fromisoformat(textos["data"]),
        campo=textos["campo"],
        trecho=textos["trecho"],
        api=api,
        a_granel=bool(bruto.get("a_granel")),
    )


def _preco_do_registro(bruto: Mapping[str, Any]) -> PrecoDeReferencia:
    """Um preço do arquivo, com as fontes conferidas; sem fonte que valha, é recusado.

    O registro antigo, de uma fonte só (o produto no próprio registro), vale
    como uma fonte.
    """
    ingrediente = str(bruto.get("ingrediente") or "").strip()
    embalagem = str(bruto.get("embalagem") or "").strip()
    if not ingrediente or not embalagem:
        raise ValueError("falta o ingrediente ou a embalagem")
    brutas = bruto.get("fontes")
    lista = [bruto] if brutas is None else [f for f in brutas if isinstance(f, dict)]
    fontes: list[FonteDoPreco] = []
    for fonte in lista:
        try:
            fontes.append(_fonte_do_registro(fonte))
        except ValueError as erro:
            logger.warning("fonte recusada (%s, %s): %s", ingrediente, fonte.get("site"), erro)
    if not fontes:
        raise ValueError("nenhuma fonte com prova")
    dimensoes = {f.base.dimensao for f in fontes}
    if len(dimensoes) != 1:
        raise ValueError("as fontes medem coisas diferentes (peso, volume, unidade)")
    cada = str(bruto.get("cada") or "").strip()
    if cada and dimensoes != {Dimensao.CONTAGEM}:
        raise ValueError("só a embalagem contada em unidades diz o que é cada uma")
    nomes = tuple(str(n) for n in bruto.get("nomes") or () if str(n).strip())
    return PrecoDeReferencia(
        ingrediente=ingrediente,
        nomes=nomes or (ingrediente,),
        embalagem=embalagem,
        fontes=tuple(fontes),
        evitar=tuple(str(p) for p in bruto.get("evitar") or ()),
        cada=cada,
        nota=str(bruto.get("nota") or "").strip(),
        tempero_seco=bool(bruto.get("tempero_seco")),
    )


def precos_do_arquivo(registros: Iterable[Mapping[str, Any]]) -> PrecosDeReferencia:
    """Os preços que passam na conferência; o que não passa fica de fora, com aviso no log."""
    precos: list[PrecoDeReferencia] = []
    for bruto in registros:
        try:
            precos.append(_preco_do_registro(bruto))
        except ValueError as erro:
            logger.warning("preço de referência recusado (%s): %s", bruto.get("ingrediente"), erro)
    return PrecosDeReferencia(tuple(precos))


@functools.lru_cache(maxsize=8)
def ler_precos(caminho: Path) -> PrecosDeReferencia:
    """Os preços do arquivo. Sem arquivo, nenhum: tudo que falta fica sem preço."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return PrecosDeReferencia()
    except (OSError, ValueError):
        logger.warning("não consegui ler os preços de referência em %s", caminho, exc_info=True)
        return PrecosDeReferencia()
    registros = dados.get("precos", []) if isinstance(dados, dict) else []
    return precos_do_arquivo(r for r in registros if isinstance(r, dict))


def caminho_dos_precos(
    despensa: Despensa, ambiente: Mapping[str, str] | None = None
) -> Path | None:
    """`MISE_PRECOS_DE_REFERENCIA`, ou o arquivo ao lado da planilha; `None` sem planilha."""
    amb = os.environ if ambiente is None else ambiente
    explicito = amb.get(VAR_PRECOS, "").strip()
    if explicito:
        return Path(explicito).expanduser()
    if despensa.origem is None:
        return None
    return Path(despensa.origem).parent / ARQUIVO_DOS_PRECOS


def precos_da_despensa(despensa: Despensa) -> PrecosDeReferencia:
    """Os preços de referência que valem para esta despensa (os do arquivo ao lado dela)."""
    caminho = caminho_dos_precos(despensa)
    return ler_precos(caminho.resolve()) if caminho is not None else PrecosDeReferencia()


__all__ = [
    "ARQUIVO_DOS_PRECOS",
    "DISTANCIA_MAXIMA",
    "FONTES_PARA_TIRAR",
    "VAR_PRECOS",
    "FonteDoPreco",
    "PrecoDeReferencia",
    "PrecosDeReferencia",
    "caminho_dos_precos",
    "ler_precos",
    "precos_da_despensa",
    "precos_do_arquivo",
]
