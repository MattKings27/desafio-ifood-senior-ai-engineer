"""O que cada passo da receita pede, conferido contra a cozinha dela.

O portão (`mise.viabilidade`) decide o prato inteiro, e a decisão continua sendo
só dele: nada aqui muda veredito. O portão lê daqui o que os passos dizem e só
eles sabem dizer (o tempo com o fogo ligado, em `mise.tempo`; a panela a mais ao
mesmo tempo; o frio), e este módulo mostra **onde** está cada exigência, que é o
que a tela e a conversa precisam para ela conferir e contestar ("esse passo é na
panela, não no forno"):

- **os requisitos de cada passo**: a taxonomia varre um passo por vez e guarda o
  trecho que denunciou a exigência (`Deteccao.evidencia`), que a receita inteira
  joga fora ao virar conjunto de ids;
- **o que vem do nome ou dos ingredientes**, num balde à parte: "Frango assado"
  pede forno mesmo que o preparo não diga;
- **os limites de cada passo**: quanto tempo no fogo ou no forno, a temperatura,
  as horas de geladeira, "de um dia para o outro" e a panela a mais ao mesmo
  tempo ("em outra panela"), que disputa boca do fogão.

Cada requisito vai marcado com o estado dele no perfil dela (tem, não tem, ainda
não perguntei, e se é só suposto), com os mesmos ids que o portão confere: um
requisito aparece aqui só se a receita o carrega, então o que o passo mostra é o
que o portão decide. As palavras de contexto das técnicas ("bife" para ponto de
carne) valem para a receita inteira, como valem para o portão.

As perguntas do portão ganham as opções de resposta (`perguntas_com_opcoes`):
"Tenho / Não tenho / Não sei", "Faço / Não faço / Não sei", ou o número com a
faixa. "Não sei" é resposta de verdade e nunca vira "não tem".
"""

from __future__ import annotations

import bisect
import functools
import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.perfil import (
    CASAS_DAS_HORAS,
    FORMATOS_OPERACIONAIS,
    PASSO_DAS_HORAS,
    FormatoDaRestricao,
    PerfilCozinha,
    Posse,
    TipoDeCampo,
    contagem,
)
from mise.taxonomia import (
    EQUIPAMENTOS,
    EQUIPAMENTOS_POR_ID,
    OLHAR_ANTES,
    TECNICAS,
    TECNICAS_POR_ID,
    TIRADO_DE,
    Deteccao,
    ResultadoDeteccao,
    detectar,
)
from mise.tempo import MinutosAtivos, OrigemDoTempo

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from mise.receita import Receita
    from mise.viabilidade import Avaliacao, Pergunta, PesoPedido


class TipoDeRequisito(StrEnum):
    EQUIPAMENTO = "equipamento"
    TECNICA = "tecnica"


class OrigemDoRequisito(StrEnum):
    """De onde veio um requisito que nenhum passo menciona."""

    NOME = "nome"
    """ "Frango assado" pede forno."""
    INGREDIENTES = "ingredientes"
    """ "1 pacote de massa folhada" acusa massa folhada."""
    RECEITA = "receita"
    """Declarado por quem montou a receita, sem trecho que o denuncie."""


class TipoDeLimite(StrEnum):
    """Os limites que um passo impõe à rotina dela."""

    TEMPO = "tempo"
    """Tempo com o fogo, o forno ou o aparelho ligado."""
    GELADEIRA = "geladeira"
    CONGELADOR = "congelador"
    DESCANSO = "descanso"
    """Descansar, crescer, esfriar, marinar: tempo de espera, fora do frio."""
    DE_UM_DIA_PARA_O_OUTRO = "de_um_dia_para_o_outro"
    TEMPERATURA = "temperatura"
    OUTRA_PANELA = "outra_panela"
    """Uma panela a mais ao mesmo tempo: mais uma boca do fogão."""


@dataclass(frozen=True, slots=True)
class Requisito:
    """Um equipamento ou técnica que a receita pede, com o estado dele na cozinha dela."""

    tipo: TipoDeRequisito
    id: str
    nome: str
    estado: Posse
    suposto: bool
    """Está como "tem" só porque qualquer cozinha tem; ninguém perguntou a ela."""
    evidencia: str
    """O trecho que a taxonomia achou (`Deteccao.evidencia`), já normalizado."""
    trecho: str = ""
    """As palavras exatas do texto original que denunciaram a exigência."""
    substituto: str | None = None
    """O equipamento que ela tem e resolve este, quando este ela não tem ou não disse."""

    @property
    def conferido(self) -> bool:
        """O portão confere este item? Sempre: o que toda cozinha tem, também.

        O pressuposto passa como suposto enquanto ela não disser nada; o "não
        tenho" dela bloqueia e o "não sei" vira pergunta. O campo continua na
        forma do passo para quem já o lê, e diz que o estado mostrado decide.
        """
        return True

    @property
    def rotulo_estado(self) -> str:
        """O estado dito para ela, sem jargão."""
        if self.substituto is not None:
            return f"a senhora resolve com {EQUIPAMENTOS_POR_ID[self.substituto].nome.lower()}"
        if self.suposto:
            return "suposto"
        if self.estado is Posse.DESCONHECIDO:
            return "ainda não perguntei"
        de_ter = self.tipo is TipoDeRequisito.EQUIPAMENTO
        if self.estado is Posse.TEM:
            return "a senhora tem" if de_ter else "a senhora faz"
        return "a senhora não tem" if de_ter else "a senhora não faz"

    def para_json(self) -> dict[str, Any]:
        substituto = (
            {"id": self.substituto, "nome": EQUIPAMENTOS_POR_ID[self.substituto].nome}
            if self.substituto is not None
            else None
        )
        return {
            "tipo": self.tipo.value,
            "id": self.id,
            "nome": self.nome,
            "estado": self.estado.value,
            "suposto": self.suposto,
            "evidencia": self.evidencia,
            "trecho": self.trecho,
            "rotulo_estado": self.rotulo_estado,
            "substituto": substituto,
            "conferido": self.conferido,
        }


@dataclass(frozen=True, slots=True)
class RequisitoDaReceita:
    """Um requisito que nenhum passo menciona, com a origem dele."""

    requisito: Requisito
    origem: OrigemDoRequisito

    def para_json(self) -> dict[str, Any]:
        return {**self.requisito.para_json(), "origem": self.origem.value}


@dataclass(frozen=True, slots=True)
class Limite:
    """Um limite do passo: tempo, frio, temperatura ou panela a mais."""

    tipo: TipoDeLimite
    texto: str
    """Dito para ela: "20 min no fogo", "4 h na geladeira", "forno a 180 °C"."""
    trecho: str
    """As palavras do passo de onde o limite saiu: "por 20 minutos"."""
    minutos: int | None = None
    """Numa faixa ("30 a 40 minutos"), o maior: é o que ela precisa reservar."""
    graus: int | None = None
    equipamento: str | None = None
    """O que fica ligado ou ocupado nesse tempo (fogão, forno, geladeira), se o passo diz."""

    def para_json(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo.value,
            "minutos": self.minutos,
            "graus": self.graus,
            "texto": self.texto,
            "trecho": self.trecho,
            "equipamento": self.equipamento,
        }


@dataclass(frozen=True, slots=True)
class PassoAvaliado:
    """Um passo do modo de preparo, com o que ele pede e os limites que impõe."""

    ordem: int
    texto: str
    requisitos: tuple[Requisito, ...] = ()
    limites: tuple[Limite, ...] = ()
    #: A seção da página em que o passo está ("Massa", "Cobertura"); `None`
    #: quando a página não dá nome a ela. A tela põe o título antes do primeiro
    #: passo de cada seção, como a página mostra.
    secao: str | None = None

    def para_json(self) -> dict[str, Any]:
        return {
            "ordem": self.ordem,
            "texto": self.texto,
            "secao": self.secao,
            "requisitos": [r.para_json() for r in self.requisitos],
            "limites": [limite.para_json() for limite in self.limites],
        }


@dataclass(frozen=True, slots=True)
class PassosDaReceita:
    """A receita passo a passo, e o que ela pede sem que passo nenhum diga."""

    passos: tuple[PassoAvaliado, ...]
    requisitos_da_receita: tuple[RequisitoDaReceita, ...] = ()

    def onde(self, id_: str) -> tuple[int, ...]:
        """Os passos que pedem o item, ou pedem algo que ele substitui (a air fryer do forno)."""
        return tuple(
            passo.ordem
            for passo in self.passos
            if any(r.id == id_ or id_ in _substitutos(r) for r in passo.requisitos)
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "passos": [p.para_json() for p in self.passos],
            "requisitos_da_receita": [r.para_json() for r in self.requisitos_da_receita],
        }


# --------------------------------------------------------------------------- #
# Requisitos
# --------------------------------------------------------------------------- #


def avaliar_passos(receita: Receita, perfil: PerfilCozinha) -> PassosDaReceita:
    """Cada passo com os requisitos e os limites dele, marcados com o perfil dela."""
    contexto = _texto_da_receita(receita)
    passos: list[PassoAvaliado] = []
    nos_passos: set[str] = set()
    secoes = receita.secao_de_cada_passo
    for ordem, texto in enumerate(receita.modo_preparo, start=1):
        requisitos = _requisitos_do_texto(texto, contexto, receita, perfil)
        nos_passos.update(r.id for r in requisitos)
        passos.append(
            PassoAvaliado(ordem, texto, requisitos, extrair_limites(texto), secoes[ordem - 1])
        )
    return PassosDaReceita(
        tuple(passos), _requisitos_da_receita(receita, perfil, contexto, nos_passos)
    )


def _texto_da_receita(receita: Receita) -> str:
    """O mesmo texto que `Receita.com_exigencias_detectadas` varre: nome, passos e ingredientes."""
    return " ".join(
        (receita.nome, *receita.modo_preparo, *(i.texto_original for i in receita.ingredientes))
    )


def _requisitos_do_texto(
    texto: str, contexto: str, receita: Receita, perfil: PerfilCozinha
) -> tuple[Requisito, ...]:
    """Os requisitos que a taxonomia acha no texto, só os que a receita carrega."""
    achado = detectar(texto, contexto=contexto)
    original = _Texto(texto)
    return tuple(
        [
            _requisito(TipoDeRequisito.EQUIPAMENTO, d, original, perfil)
            for d in achado.equipamentos
            if d.id in receita.equipamentos
        ]
        + [
            _requisito(TipoDeRequisito.TECNICA, d, original, perfil)
            for d in achado.tecnicas
            if d.id in receita.tecnicas
        ]
    )


def _requisitos_da_receita(
    receita: Receita, perfil: PerfilCozinha, contexto: str, nos_passos: set[str]
) -> tuple[RequisitoDaReceita, ...]:
    """O que a receita pede e nenhum passo diz: do nome, dos ingredientes ou declarado."""
    ingredientes = " ".join(i.texto_original for i in receita.ingredientes)
    fontes = (
        (OrigemDoRequisito.NOME, _Texto(receita.nome), detectar(receita.nome, contexto=contexto)),
        (
            OrigemDoRequisito.INGREDIENTES,
            _Texto(ingredientes),
            detectar(ingredientes, contexto=contexto),
        ),
    )
    resultado: list[RequisitoDaReceita] = []
    for tipo, vocabulario, exigidos in (
        (TipoDeRequisito.EQUIPAMENTO, [e.id for e in EQUIPAMENTOS], receita.equipamentos),
        (TipoDeRequisito.TECNICA, [t.id for t in TECNICAS], receita.tecnicas),
    ):
        for id_ in vocabulario:
            if id_ not in exigidos or id_ in nos_passos:
                continue
            resultado.append(_de_onde_veio(tipo, id_, fontes, perfil))
    return tuple(resultado)


def _de_onde_veio(
    tipo: TipoDeRequisito,
    id_: str,
    fontes: Sequence[tuple[OrigemDoRequisito, _Texto, ResultadoDeteccao]],
    perfil: PerfilCozinha,
) -> RequisitoDaReceita:
    for origem, original, achado in fontes:
        deteccoes = achado.equipamentos if tipo is TipoDeRequisito.EQUIPAMENTO else achado.tecnicas
        for deteccao in deteccoes:
            if deteccao.id == id_:
                return RequisitoDaReceita(_requisito(tipo, deteccao, original, perfil), origem)
    nome = (
        EQUIPAMENTOS_POR_ID[id_] if tipo is TipoDeRequisito.EQUIPAMENTO else TECNICAS_POR_ID[id_]
    ).nome
    declarado = _requisito(tipo, Deteccao(id_, nome, ""), None, perfil)
    return RequisitoDaReceita(declarado, OrigemDoRequisito.RECEITA)


def _requisito(
    tipo: TipoDeRequisito, deteccao: Deteccao, original: _Texto | None, perfil: PerfilCozinha
) -> Requisito:
    id_ = deteccao.id
    substituto: str | None = None
    if tipo is TipoDeRequisito.EQUIPAMENTO:
        estado = perfil.tem_equipamento(id_)
        padroes = EQUIPAMENTOS_POR_ID[id_].palavras
        if estado is not Posse.TEM:
            posse, alternativa = perfil.tem_equipamento_ou_substituto(id_)
            substituto = alternativa if posse is Posse.TEM else None
    else:
        estado = perfil.domina_tecnica(id_)
        padroes = TECNICAS_POR_ID[id_].padroes
    return Requisito(
        tipo=tipo,
        id=id_,
        nome=deteccao.nome,
        estado=estado,
        suposto=perfil.suposto(id_),
        evidencia=deteccao.evidencia,
        trecho=original.primeiro(padroes) if original is not None else "",
        substituto=substituto,
    )


def _substitutos(requisito: Requisito) -> tuple[str, ...]:
    if requisito.tipo is TipoDeRequisito.EQUIPAMENTO:
        return EQUIPAMENTOS_POR_ID[requisito.id].substitutos
    return ()


# --------------------------------------------------------------------------- #
# O texto original por trás do normalizado
# --------------------------------------------------------------------------- #


class _Texto:
    """Um texto como a taxonomia o compara, sem perder o caminho de volta ao original.

    A taxonomia casa padrões em minúsculas, sem acento e com espaço único. Para
    mostrar a ela as palavras que ela escreveu ("Pré-aqueça", não "pre-aqueca"),
    cada caractere normalizado lembra de que posição do original veio.
    """

    __slots__ = ("normalizado", "origem", "original")

    def __init__(self, original: str) -> None:
        saida: list[str] = []
        origem: list[int] = []
        em_espaco = False
        for posicao, caractere in enumerate(original):
            if caractere.isspace():
                if not em_espaco:
                    saida.append(" ")
                    origem.append(posicao)
                    em_espaco = True
                continue
            for parte in unicodedata.normalize("NFD", caractere.lower()):
                if unicodedata.category(parte) != "Mn":
                    saida.append(parte)
                    origem.append(posicao)
                    em_espaco = False
        self.original = original
        self.normalizado = "".join(saida)
        self.origem = tuple(origem)

    def trecho(self, inicio: int, fim: int) -> str:
        """O pedaço do original que corresponde a `normalizado[inicio:fim]`."""
        return self.original[self.origem[inicio] : self.origem[fim - 1] + 1]

    def primeiro(self, padroes: Iterable[str]) -> str:
        """O trecho original do primeiro padrão que casa, na ordem da taxonomia."""
        for padrao in padroes:
            if casou := _palavra(padrao).search(self.normalizado):
                return self.trecho(casou.start(), casou.end())
        return ""


@functools.cache
def _palavra(padrao: str) -> re.Pattern[str]:
    """Palavra inteira, como a taxonomia casa: "asse" não é pedaço de "passe"."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(padrao)}(?![a-z0-9])")


# --------------------------------------------------------------------------- #
# Limites
# --------------------------------------------------------------------------- #

_POR_EXTENSO: Final[dict[str, int]] = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "doze": 12,
    "quinze": 15,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
}
_QTD: Final = r"(?:\d+(?:[.,]\d+)?|" + "|".join(sorted(_POR_EXTENSO, key=len, reverse=True)) + ")"
_HORA: Final = r"(?:horas?|hs?)"
_MINUTO: Final = r"(?:minutos?|mins?)"
_DIA: Final = r"(?:dias?)"
_SEP: Final = r"(?:a|ate|ou|-|–)"

#: Duração, da forma mais específica para a mais simples: "1 a 1 hora e meia",
#: "1 hora e meia", "meia hora", "1 hora e 30 minutos", "1h30", "entre 30 e 40
#: minutos", "30 a 40 minutos", "20 minutos", "2 dias". Segundos ficam de fora:
#: não pesam na rotina.
_DURACAO: Final = re.compile(
    r"(?<![a-z0-9])(?:"
    rf"(?P<fm_a>{_QTD})\s*{_SEP}\s*(?P<fm_b>{_QTD})\s*{_HORA}\s+e\s+meia"
    rf"|(?P<meia_h>{_QTD})\s*{_HORA}\s+e\s+meia"
    r"|(?P<meia>meia)\s+hora"
    rf"|(?P<hm_h>{_QTD})\s*{_HORA}\s*e\s*(?P<hm_m>{_QTD})\s*{_MINUTO}"
    rf"|(?P<hc_h>\d+)\s*h\s*(?P<hc_m>\d{{2}})(?:\s*(?:{_MINUTO}|m))?"
    rf"|entre\s+(?P<ea>{_QTD})\s+e\s+(?P<eb>{_QTD})\s*(?P<eu>{_HORA}|{_MINUTO}|{_DIA})"
    rf"|(?P<fa>{_QTD})\s*{_SEP}\s*(?P<fb>{_QTD})\s*(?P<fu>{_HORA}|{_MINUTO}|{_DIA})"
    rf"|(?P<n>{_QTD})\s*(?P<u>{_HORA}|{_MINUTO}|{_DIA})"
    r")(?![a-z0-9])"
)

#: "180 °C", "180ºC", "180°", "180 graus", "180 C", "-18 °C". O "1º" de "1º passo"
#: não é temperatura: sem o "c", só a partir de 30 graus.
_GRAUS: Final = re.compile(
    r"(?<![\d.,])(?P<sinal>[-−–]\s?)?(?:"
    r"(?P<a>\d{1,3})\s*[°º]\s*(?P<ac>c(?:elsius)?)?"
    r"|(?P<b>\d{1,3})\s*graus(?:\s+celsius)?"
    r"|(?P<c>\d{2,3})\s*c"
    r")(?![a-z0-9])"
)
_GRAUS_SEM_C_A_PARTIR_DE: Final = 30
_MINUTOS_POR_HORA: Final = 60
_MINUTOS_POR_DIA: Final = 24 * 60
_GRAUS_DE_FORNO: Final = (60, 300)
_GRAUS_MAXIMO: Final = 300
_GRAUS_MINIMO: Final = -40

_DE_UM_DIA_PARA_O_OUTRO: Final = re.compile(
    r"(?<![a-z])(?:de um dia (?:para|pro|pra) (?:o )?outro|da noite para o dia"
    r"|durante a noite|a noite (?:toda|inteira)|por uma noite|overnight"
    r"|na vespera|no dia anterior|um dia antes)(?![a-z])"
)

_OUTRA_PANELA: Final = re.compile(
    r"(?<![a-z])(?:"
    r"(?:em uma|em|numa|n)\s*outra\s+(?:panela|frigideira|cacarola|leiteira|boca)"
    r"|(?:em uma|em|numa)\s+segunda\s+(?:panela|frigideira)"
    r"|(?:em uma|em|numa)\s+(?:panela|frigideira|cacarola|leiteira)\s+"
    r"(?:separada|a parte|diferente)"
    r")(?![a-z])"
)

#: O que liga duas durações numa faixa: "45 minutos a 1 hora".
_SEPARADORES: Final = frozenset({"a", "ate", "ou", "-", "–"})

#: A âncora colada depois da duração manda nela: "por 30 min na geladeira",
#: "20 minutos no forno". Entre as duas, só uma preposição (ou nada, quando o
#: padrão já traz a dele, como "na panela"); "30 minutos e leve à geladeira" não é.
_COLADA: Final = frozenset({"", "na", "no", "em", "num", "numa"})

#: O que, logo antes, diz que o aparelho deixou de contar: "retire do forno",
#: "tire o frango da geladeira", "desligue o fogo", "fora da geladeira". É a
#: mesma regra da taxonomia, para o passo e a exigência dizerem a mesma coisa.
_DESLIGADO: Final = TIRADO_DE
_OLHAR_ANTES: Final = OLHAR_ANTES

#: O frio que é só uma possibilidade ("se sobrar, pode congelar") não ocupa a
#: geladeira da produção: é dica de guardar, não passo da receita.
_TALVEZ: Final = re.compile(r"(?<![a-z])(?:pode|podem|da para)\s+$")

#: Duração dita como antecedência ("30 minutos antes de assar"): é espera até o
#: passo seguinte, não tempo daquele aparelho.
_ANTECEDENCIA: Final = re.compile(r"^\s*(?:antes|depois)(?![a-z])")


class _Classe(IntEnum):
    """Que tipo de palavra diz onde o tempo corre. A ordem desempata a mesma distância."""

    FRIO = 0
    """Geladeira e congelador."""
    ESPERA = 1
    """Descansar, crescer, esfriar, marinar: tempo parado, fora do frio."""
    CALOR = 2
    """Aparelho que esquenta: fogão (e o que vai nele), forno, air fryer, micro-ondas."""
    APARELHO = 3
    """Aparelho que não esquenta: liquidificador, batedeira, mixer, processador."""
    VERBO_DE_FOGAO = 4
    """Verbo que só se faz no fogão: refogue, frite, ferva, cozinhe."""
    VERBO_DE_CALOR = 5
    """Verbo de calor que vale para vários aparelhos: aqueça, derreta."""


_FORTES: Final = frozenset({_Classe.FRIO, _Classe.ESPERA, _Classe.CALOR})
_VERBOS: Final = frozenset({_Classe.VERBO_DE_FOGAO, _Classe.VERBO_DE_CALOR})
#: O que não acende fogo nem liga aparelho: o tempo que corre nelas é espera.
_PARADAS: Final = frozenset({_Classe.FRIO, _Classe.ESPERA})

#: O que fica ligado num passo, e como dizer isso a ela. Panela, frigideira e
#: pressão vão ao fogão: é o fogão que gasta o gás nesse tempo.
_FONTES: Final[dict[str, tuple[str, str, _Classe]]] = {
    "fogao": ("fogao", "no fogo", _Classe.CALOR),
    "panela_funda": ("fogao", "no fogo", _Classe.CALOR),
    "frigideira": ("fogao", "na frigideira", _Classe.CALOR),
    "frigideira_antiaderente": ("fogao", "na frigideira", _Classe.CALOR),
    "panela_pressao": ("fogao", "na pressão", _Classe.CALOR),
    "banho_maria": ("fogao", "em banho-maria", _Classe.CALOR),
    "forno": ("forno", "no forno", _Classe.CALOR),
    "forno_eletrico": ("forno_eletrico", "no forno elétrico", _Classe.CALOR),
    "air_fryer": ("air_fryer", "na air fryer", _Classe.CALOR),
    "microondas": ("microondas", "no micro-ondas", _Classe.CALOR),
    "chapa": ("chapa", "na chapa", _Classe.CALOR),
    "churrasqueira": ("churrasqueira", "na churrasqueira", _Classe.CALOR),
    "liquidificador": ("liquidificador", "no liquidificador", _Classe.APARELHO),
    "batedeira": ("batedeira", "na batedeira", _Classe.APARELHO),
    "mixer": ("mixer", "no mixer", _Classe.APARELHO),
    "processador": ("processador", "no processador", _Classe.APARELHO),
}

#: Os que têm termostato: a temperatura do passo é a deles.
_COM_TEMPERATURA: Final[dict[str, str]] = {
    "forno": "forno",
    "forno_eletrico": "forno elétrico",
    "air_fryer": "air fryer",
}

#: Verbos que só se fazem no fogão: "cozinhe por 20 minutos" é tempo de fogão,
#: mesmo sem dizer "fogão".
_NO_FOGAO: Final = (
    "cozinhe",
    "cozinhar",
    "cozinhando",
    "cozimento",
    "ferva",
    "ferver",
    "fervendo",
    "fervura",
    "refogue",
    "refogar",
    "frite",
    "fritar",
    "doure",
    "dourar",
    "mexa",
    "mexendo",
    "apure",
    "apurar",
    "reduza",
    "reduzir",
    "engrosse",
    "engrossar",
    "fogo",
)
#: Verbos de calor que servem a mais de um aparelho: sem aparelho na frase, é o fogão.
_COM_CALOR: Final = ("aqueca", "aquecer", "derreta", "derreter")
_NA_GELADEIRA: Final = (
    "geladeira",
    "refrigerador",
    "refrigere",
    "refrigerar",
    "gelar",
    "gele",
    "gelando",
)
_NO_CONGELADOR: Final = ("congelador", "freezer", "congele", "congelar")
#: Esperas fora do frio, e como dizer cada uma: "1 h crescendo", "8 h de molho".
_EM_ESPERA: Final[dict[str, str]] = {
    "descansar": "de descanso",
    "descanse": "de descanso",
    "descansando": "de descanso",
    "repousar": "de descanso",
    "repouse": "de descanso",
    "espere": "de espera",
    "aguarde": "de espera",
    "crescer": "crescendo",
    "cresca": "crescendo",
    "fermentar": "crescendo",
    "fermente": "crescendo",
    "dobrar de volume": "crescendo",
    "dobre de volume": "crescendo",
    "esfriar": "esfriando",
    "esfrie": "esfriando",
    "amornar": "esfriando",
    "marinar": "marinando",
    "marine": "marinando",
    "tomar gosto": "marinando",
    "hidratar": "de molho",
    "hidrate": "de molho",
    "de molho": "de molho",
}


@dataclass(frozen=True, slots=True)
class _Ancora:
    """Uma palavra do passo que diz onde o tempo corre: "forno", "geladeira", "descanse"."""

    inicio: int
    fim: int
    tipo: TipoDeLimite
    fonte: str | None
    frase: str
    classe: _Classe

    def distancia(self, inicio: int, fim: int) -> int:
        if self.fim <= inicio:
            return inicio - self.fim
        if self.inicio >= fim:
            return self.inicio - fim
        return 0


def _ancoras(normalizado: str) -> list[_Ancora]:
    """As âncoras do texto, menos as do aparelho que o passo manda desligar ou tirar."""
    ancoras: list[_Ancora] = []

    def marcar(
        palavras: Iterable[str], tipo: TipoDeLimite, fonte: str | None, frase: str, classe: _Classe
    ) -> None:
        for palavra in palavras:
            for casou in _palavra(palavra).finditer(normalizado):
                antes = normalizado[max(0, casou.start() - _OLHAR_ANTES) : casou.start()]
                if _DESLIGADO.search(antes):
                    continue
                if classe is _Classe.FRIO and _TALVEZ.search(antes):
                    continue
                ancoras.append(_Ancora(casou.start(), casou.end(), tipo, fonte, frase, classe))

    for id_, (fonte, frase, classe) in _FONTES.items():
        marcar(EQUIPAMENTOS_POR_ID[id_].padroes, TipoDeLimite.TEMPO, fonte, frase, classe)
    marcar(_NO_FOGAO, TipoDeLimite.TEMPO, "fogao", "no fogo", _Classe.VERBO_DE_FOGAO)
    marcar(_COM_CALOR, TipoDeLimite.TEMPO, "fogao", "no fogo", _Classe.VERBO_DE_CALOR)
    marcar(
        (*_NA_GELADEIRA, *EQUIPAMENTOS_POR_ID["geladeira"].padroes),
        TipoDeLimite.GELADEIRA,
        "geladeira",
        "na geladeira",
        _Classe.FRIO,
    )
    marcar(
        (*_NO_CONGELADOR, *EQUIPAMENTOS_POR_ID["freezer"].padroes),
        TipoDeLimite.CONGELADOR,
        "freezer",
        "no congelador",
        _Classe.FRIO,
    )
    for palavra, frase in _EM_ESPERA.items():
        marcar((palavra,), TipoDeLimite.DESCANSO, None, frase, _Classe.ESPERA)
    return ancoras


def _mais_perto(ancoras: Iterable[_Ancora], inicio: int, fim: int) -> _Ancora | None:
    """A âncora mais perto do trecho; no empate, a de antes, a mais longa, e o frio primeiro.

    A mais longa desempata "forno" e "forno elétrico", que começam no mesmo lugar.
    """
    return min(
        ancoras,
        key=lambda a: (a.distancia(inicio, fim), a.inicio >= fim, a.inicio - a.fim, a.classe),
        default=None,
    )


class _Divisoes:
    """Onde cada frase e cada oração do passo terminam, contadas no texto original.

    Ponto e vírgula fecha a frase sempre. Ponto, exclamação e interrogação só
    quando o que vem depois começa com maiúscula, ou quando o passo acaba: "aprox.
    40 minutos" e "1.5 hora" continuam na mesma frase. A vírgula fecha a oração,
    menos a de um número ("1,5 hora").
    """

    __slots__ = ("_frases", "_oracoes", "_origem")

    def __init__(self, texto: _Texto) -> None:
        original = texto.original
        self._frases = [
            m.start() for m in re.finditer(r"[.;!?]", original) if _fecha_frase(original, m.start())
        ]
        virgulas = [m.start() for m in re.finditer(r",(?!\d)", original)]
        self._oracoes = sorted({*self._frases, *virgulas})
        self._origem = texto.origem

    def frase(self, posicao: int) -> int:
        return bisect.bisect_right(self._frases, self._origem[posicao])

    def oracao(self, posicao: int) -> int:
        return bisect.bisect_right(self._oracoes, self._origem[posicao])


def _fecha_frase(original: str, posicao: int) -> bool:
    if original[posicao] == ";":
        return True
    resto = original[posicao + 1 :].lstrip()
    return not resto or resto[0].isupper()


def _onde_corre(
    ancoras: Sequence[_Ancora], divisoes: _Divisoes, normalizado: str, inicio: int, fim: int
) -> _Ancora | None:
    """A âncora que manda numa duração, da mais forte para a mais fraca.

    1. a que vem colada depois dela ("por 30 min na geladeira");
    2. aparelho que esquenta, frio ou espera antes dela, na mesma oração ("leve ao
       forno e cozinhe por 30 minutos" é forno);
    3. verbo que só se faz no fogão antes dela, na mesma oração;
    4. aparelho que esquenta, frio ou espera antes, em outra oração da frase ("no
       micro-ondas, derreta o chocolate por 1 minuto");
    5. verbo de calor que serve a vários aparelhos ("aqueça", "derreta");
    6. aparelho que não esquenta ("bata no liquidificador por 3 minutos");
    7. o que vem depois dela, na oração e depois na frase.

    Descansar na geladeira é frio: quando a espera vence e o frio vem antes dela
    na oração ("leve à geladeira para descansar"), vale o frio.
    """
    frase = divisoes.frase(inicio)
    oracao = divisoes.oracao(inicio)
    na_frase = [a for a in ancoras if divisoes.frase(a.inicio) == frase]
    na_oracao = [a for a in na_frase if divisoes.oracao(a.inicio) == oracao]
    antes = [a for a in na_oracao if a.fim <= inicio]
    depois = [a for a in na_oracao if a.inicio >= fim]

    colada = [
        a
        for a in depois
        if a.classe not in _VERBOS and normalizado[fim : a.inicio].strip() in _COLADA
    ]
    niveis = (
        colada,
        [a for a in antes if a.classe in _FORTES],
        [a for a in antes if a.classe is _Classe.VERBO_DE_FOGAO],
        [a for a in na_frase if a.classe in _FORTES and a.fim <= inicio],
        [a for a in antes if a.classe is _Classe.VERBO_DE_CALOR],
        [a for a in antes if a.classe is _Classe.APARELHO],
        [a for a in depois if a.classe not in _VERBOS],
        depois,
        na_frase,
    )
    for candidatas in niveis:
        escolhida = _mais_perto(candidatas, inicio, fim)
        if escolhida is None:
            continue
        if escolhida.tipo is TipoDeLimite.DESCANSO:
            frio = [a for a in na_oracao if a.classe is _Classe.FRIO and a.fim <= escolhida.inicio]
            if frio:
                return max(frio, key=lambda a: a.fim)
        return escolhida
    return None


def _termostato(
    ancoras: Sequence[_Ancora], divisoes: _Divisoes, inicio: int, fim: int
) -> _Ancora | None:
    """O aparelho de uma temperatura: o forno ou a air fryer da oração, senão o da frase."""
    frase = divisoes.frase(inicio)
    oracao = divisoes.oracao(inicio)
    com_termostato = [
        a for a in ancoras if a.fonte in _COM_TEMPERATURA and divisoes.frase(a.inicio) == frase
    ]
    na_oracao = [a for a in com_termostato if divisoes.oracao(a.inicio) == oracao]
    return _mais_perto(na_oracao, inicio, fim) or _mais_perto(com_termostato, inicio, fim)


def _frio_da_frase(
    ancoras: Sequence[_Ancora], divisoes: _Divisoes, inicio: int, fim: int
) -> _Ancora | None:
    """A geladeira ou o congelador de "de um dia para o outro": o da oração, senão o da frase."""
    frase = divisoes.frase(inicio)
    oracao = divisoes.oracao(inicio)
    frios = [a for a in ancoras if a.classe is _Classe.FRIO and divisoes.frase(a.inicio) == frase]
    na_oracao = [a for a in frios if divisoes.oracao(a.inicio) == oracao]
    return _mais_perto(na_oracao, inicio, fim) or _mais_perto(frios, inicio, fim)


@functools.lru_cache(maxsize=4096)
def extrair_limites(texto: str) -> tuple[Limite, ...]:
    """Os limites de um passo, na ordem em que aparecem no texto.

    Guardado por texto: o portão e a tela leem os mesmos passos várias vezes a
    cada avaliação, e o resultado é imutável.
    """
    fonte = _Texto(texto)
    normalizado = fonte.normalizado
    ancoras = _ancoras(normalizado)
    divisoes = _Divisoes(fonte)
    limites: list[tuple[int, Limite]] = []

    # O "um dia" de "de um dia para o outro" não é uma duração de um dia.
    pernoites = [(m.start(), m.end()) for m in _DE_UM_DIA_PARA_O_OUTRO.finditer(normalizado)]
    for inicio, fim, faixa in _duracoes(normalizado):
        if any(inicio < ate and de < fim for de, ate in pernoites):
            continue
        antecedencia = bool(_ANTECEDENCIA.match(normalizado[fim:]))
        # "30 minutos antes de assar": o forno de depois não manda nessa meia hora.
        candidatas = [a for a in ancoras if a.fim <= inicio] if antecedencia else ancoras
        ancora = _onde_corre(candidatas, divisoes, normalizado, inicio, fim)
        limite = _limite_de_tempo(faixa, ancora, fonte.trecho(inicio, fim), espera=antecedencia)
        limites.append((inicio, limite))

    for casou in _GRAUS.finditer(normalizado):
        graus = _graus(casou)
        if graus is None:
            continue
        ancora = _termostato(ancoras, divisoes, casou.start(), casou.end())
        onde = f"{_COM_TEMPERATURA[ancora.fonte]} a " if ancora and ancora.fonte else ""
        limites.append(
            (
                casou.start(),
                Limite(
                    TipoDeLimite.TEMPERATURA,
                    f"{onde}{graus} °C",
                    fonte.trecho(casou.start(), casou.end()),
                    graus=graus,
                    equipamento=ancora.fonte if ancora else None,
                ),
            )
        )

    for casou in _DE_UM_DIA_PARA_O_OUTRO.finditer(normalizado):
        frio = _frio_da_frase(ancoras, divisoes, casou.start(), casou.end())
        limites.append(
            (
                casou.start(),
                Limite(
                    TipoDeLimite.DE_UM_DIA_PARA_O_OUTRO,
                    f"de um dia para o outro, {frio.frase}" if frio else "de um dia para o outro",
                    fonte.trecho(casou.start(), casou.end()),
                    equipamento=frio.fonte if frio else None,
                ),
            )
        )

    for casou in _OUTRA_PANELA.finditer(normalizado):
        limites.append(
            (
                casou.start(),
                Limite(
                    TipoDeLimite.OUTRA_PANELA,
                    "mais uma boca do fogão ao mesmo tempo",
                    fonte.trecho(casou.start(), casou.end()),
                    equipamento="fogao",
                ),
            )
        )

    limites.sort(key=lambda par: par[0])
    return tuple(limite for _, limite in limites)


def _duracoes(normalizado: str) -> list[tuple[int, int, tuple[int, int]]]:
    """As durações do texto, (início, fim, (mínimo, máximo)).

    Duas durações ligadas só por "a", "até", "ou" ou hífen são uma faixa: "45
    minutos a 1 hora e 15 minutos" é um tempo só, de 45 a 75 minutos. Com
    "entre" antes da primeira, o "e" também liga: "entre 40 minutos e 1 hora".
    """
    duracoes: list[tuple[int, int, tuple[int, int]]] = []
    for casou in _DURACAO.finditer(normalizado):
        faixa = _minutos_da_duracao(casou)
        if faixa is None:
            continue
        if duracoes and _ligadas(normalizado, duracoes[-1][0], duracoes[-1][1], casou.start()):
            inicio, _, (menor, maior) = duracoes.pop()
            duracoes.append((inicio, casou.end(), (min(menor, faixa[0]), max(maior, faixa[1]))))
            continue
        duracoes.append((casou.start(), casou.end(), faixa))
    return duracoes


def _ligadas(normalizado: str, inicio_anterior: int, fim_anterior: int, inicio: int) -> bool:
    entre = normalizado[fim_anterior:inicio].strip()
    if entre in _SEPARADORES:
        return True
    return entre == "e" and normalizado[:inicio_anterior].rstrip().endswith("entre")


def _limite_de_tempo(
    faixa: tuple[int, int], ancora: _Ancora | None, trecho: str, *, espera: bool = False
) -> Limite:
    """O limite de uma duração. Sem âncora, é tempo solto; dita como antecedência, é espera."""
    de, ate = faixa
    duracao = _faixa_texto(de, ate)
    if ancora is None:
        if espera:
            return Limite(TipoDeLimite.DESCANSO, f"{duracao} de espera", trecho, minutos=ate)
        return Limite(TipoDeLimite.TEMPO, duracao, trecho, minutos=ate)
    return Limite(
        ancora.tipo, f"{duracao} {ancora.frase}", trecho, minutos=ate, equipamento=ancora.fonte
    )


def _minutos_da_duracao(casou: re.Match[str]) -> tuple[int, int] | None:
    """(mínimo, máximo) em minutos. Numa duração simples os dois são iguais."""
    g = casou.groupdict()
    if g["fm_a"] is not None:
        menor = _quantia(g["fm_a"]) * _MINUTOS_POR_HORA
        maior = _quantia(g["fm_b"]) * _MINUTOS_POR_HORA + 30
        return _em_ordem(_inteiro(menor), _inteiro(maior))
    if g["ea"] is not None:
        return _faixa(g["ea"], g["eb"], g["eu"])
    if g["fa"] is not None:
        return _faixa(g["fa"], g["fb"], g["fu"])
    if g["meia_h"] is not None:
        total = _quantia(g["meia_h"]) * _MINUTOS_POR_HORA + 30
    elif g["meia"] is not None:
        total = Decimal(30)
    elif g["hm_h"] is not None:
        total = _quantia(g["hm_h"]) * _MINUTOS_POR_HORA + _quantia(g["hm_m"])
    elif g["hc_h"] is not None:
        total = Decimal(g["hc_h"]) * _MINUTOS_POR_HORA + Decimal(g["hc_m"])
    else:
        total = _em_minutos(g["n"], g["u"])
    minutos = _inteiro(total)
    return (minutos, minutos) if minutos > 0 else None


def _faixa(de: str, ate: str, unidade: str) -> tuple[int, int] | None:
    return _em_ordem(_inteiro(_em_minutos(de, unidade)), _inteiro(_em_minutos(ate, unidade)))


def _em_ordem(um: int, outro: int) -> tuple[int, int] | None:
    menor, maior = sorted((um, outro))
    return (menor, maior) if maior > 0 else None


def _em_minutos(quantia: str, unidade: str) -> Decimal:
    valor = _quantia(quantia)
    if unidade.startswith("d"):
        return valor * _MINUTOS_POR_DIA
    return valor * _MINUTOS_POR_HORA if unidade.startswith("h") else valor


def _quantia(texto: str) -> Decimal:
    if texto in _POR_EXTENSO:
        return Decimal(_POR_EXTENSO[texto])
    return Decimal(texto.replace(",", "."))


def _inteiro(valor: Decimal) -> int:
    return int(valor.to_integral_value(rounding=ROUND_HALF_UP))


def _graus(casou: re.Match[str]) -> int | None:
    g = casou.groupdict()
    negativo = g["sinal"] is not None
    if g["a"] is not None:
        graus = int(g["a"])
        if g["ac"] is None and graus < _GRAUS_SEM_C_A_PARTIR_DE:
            return None
    elif g["b"] is not None:
        graus = int(g["b"])
    else:
        # "180 C", sem o grau: só na faixa do forno, e nunca abaixo de zero.
        graus = int(g["c"])
        minimo, maximo = _GRAUS_DE_FORNO
        return graus if not negativo and minimo <= graus <= maximo else None
    graus = -graus if negativo else graus
    return graus if _GRAUS_MINIMO <= graus <= _GRAUS_MAXIMO else None


def _duracao_texto(minutos: int) -> str:
    if minutos >= _MINUTOS_POR_DIA and minutos % _MINUTOS_POR_DIA == 0:
        return contagem(minutos // _MINUTOS_POR_DIA, "dia", "dias")
    if minutos < _MINUTOS_POR_HORA:
        return f"{minutos} min"
    horas, resto = divmod(minutos, _MINUTOS_POR_HORA)
    return f"{horas} h" if resto == 0 else f"{horas} h {resto} min"


def _faixa_texto(de: int, ate: int) -> str:
    if de == ate:
        return _duracao_texto(ate)
    if ate < _MINUTOS_POR_HORA:
        return f"{de} a {ate} min"
    if de % _MINUTOS_POR_DIA == 0 and ate % _MINUTOS_POR_DIA == 0:
        return f"{de // _MINUTOS_POR_DIA} a {ate // _MINUTOS_POR_DIA} dias"
    if de % _MINUTOS_POR_HORA == 0 and ate % _MINUTOS_POR_HORA == 0:
        return f"{de // _MINUTOS_POR_HORA} a {ate // _MINUTOS_POR_HORA} h"
    return f"{_duracao_texto(de)} a {_duracao_texto(ate)}"


# --------------------------------------------------------------------------- #
# O que o portão lê dos passos
# --------------------------------------------------------------------------- #


def passos_com_outra_panela(receita: Receita) -> tuple[int, ...]:
    """Os passos que põem mais uma panela no fogo ao mesmo tempo ("em outra panela")."""
    return tuple(
        ordem
        for ordem, texto in enumerate(receita.modo_preparo, start=1)
        if any(limite.tipo is TipoDeLimite.OUTRA_PANELA for limite in extrair_limites(texto))
    )


def passos_com_frio(receita: Receita) -> tuple[int, ...]:
    """Os passos que levam à geladeira ou ao congelador, com ou sem tempo dito.

    "Leve à geladeira até firmar" não tem duração, e ocupa a geladeira do mesmo
    jeito. "Retire da geladeira" não ocupa: a âncora do que sai do aparelho não
    conta (`_DESLIGADO`).
    """
    return tuple(
        ordem for ordem, texto in enumerate(receita.modo_preparo, start=1) if _pede_frio(texto)
    )


@functools.lru_cache(maxsize=4096)
def _pede_frio(texto: str) -> bool:
    return any(a.classe is _Classe.FRIO for a in _ancoras(_Texto(texto).normalizado))


def passos_com_fogo_ou_aparelho(receita: Receita) -> tuple[int, ...]:
    """Os passos que acendem o fogo ou ligam um aparelho, com ou sem tempo dito.

    Conta o aparelho que esquenta, o que não esquenta (liquidificador, batedeira)
    e o verbo de fogo ("refogue", "derreta", "mexa"). Frio e espera não contam.
    """
    return tuple(
        ordem for ordem, texto in enumerate(receita.modo_preparo, start=1) if _liga_algo(texto)
    )


#: O aparelho citado como referência ("antes de assar", "depois de levar ao
#: forno") é do passo seguinte: o passo em si não o liga.
_REFERENCIA: Final = re.compile(r"(?<![a-z])(?:antes|depois)\s+de\s+(?:[a-z]+\s+){0,2}$")


@functools.lru_cache(maxsize=4096)
def _liga_algo(texto: str) -> bool:
    normalizado = _Texto(texto).normalizado
    return any(
        a.classe not in _PARADAS
        and not _REFERENCIA.search(normalizado[max(0, a.inicio - _OLHAR_ANTES) : a.inicio])
        for a in _ancoras(normalizado)
    )


# --------------------------------------------------------------------------- #
# O tempo ativo
# --------------------------------------------------------------------------- #

#: O que vai ao fogão, para o tempo de cozimento declarado contar como tempo no fogo.
VAI_AO_FOGAO: Final[frozenset[str]] = frozenset(
    {"fogao", "panela_pressao", "frigideira", "frigideira_antiaderente", "panela_funda"}
)

#: Equipamentos que não acendem fogo nem ligam na tomada. Todo o resto conta
#: como fogo ou aparelho: um equipamento novo na taxonomia fica do lado seguro.
EQUIPAMENTOS_SEM_FOGO: Final[frozenset[str]] = frozenset(
    {
        "ralador",
        "peneira",
        "rolo_massa",
        "fouet",
        "saco_confeitar",
        "espremedor",
        "geladeira",
        "freezer",
        "balanca",
        "faca",
        "tabua",
    }
)

#: Técnicas feitas sem fogo. Toda outra conta como fogo, pelo mesmo motivo.
TECNICAS_SEM_FOGO: Final[frozenset[str]] = frozenset(
    {
        "empanar",
        "massa_fresca",
        "sovar_pao",
        "massa_folhada",
        "massa_podre",
        "emulsao",
        "merengue",
        "desossar",
        "limpar_peixe",
    }
)

#: Os limites de espera: o tempo deles não prende ninguém ao fogão.
_ESPERAS: Final = frozenset(
    {TipoDeLimite.GELADEIRA, TipoDeLimite.CONGELADOR, TipoDeLimite.DESCANSO}
)

#: Onde o tempo ativo corre, dito para ela, pelo que o passo deixa ligado.
_ONDE: Final[dict[str, str]] = {
    "fogao": "no fogo",
    "forno": "no forno",
    "forno_eletrico": "no forno",
    "air_fryer": "na air fryer",
    "microondas": "no micro-ondas",
    "chapa": "na chapa",
    "churrasqueira": "na churrasqueira",
}
_ONDE_MISTURADO: Final = "com o fogo ou o aparelho ligado"


def _limites_dos_passos(receita: Receita) -> Iterator[tuple[int, Limite]]:
    """Cada limite de cada passo, com a ordem do passo."""
    for ordem, texto in enumerate(receita.modo_preparo, start=1):
        for limite in extrair_limites(texto):
            yield ordem, limite


def _tempos_ativos(receita: Receita) -> Iterator[tuple[int, Limite]]:
    """Os limites de tempo com fogo, forno ou aparelho ligado, com a ordem do passo."""
    for ordem, limite in _limites_dos_passos(receita):
        if limite.tipo is TipoDeLimite.TEMPO and limite.minutos:
            yield ordem, limite


@dataclass(frozen=True, slots=True)
class _Tempos:
    """O que os passos dizem do tempo: quanto cada passo liga algo, e o que fica sem dizer."""

    por_passo: tuple[tuple[int, int], ...]
    """`(ordem, minutos)` de cada passo com tempo de fogo, forno ou aparelho ligado."""
    passivos: int
    """Minutos de espera (descanso, geladeira, congelador), fora da conta."""
    sem_tempo: tuple[int, ...]
    """Passos que acendem fogo ou ligam aparelho e não dizem por quanto tempo."""

    @property
    def soma(self) -> int:
        return sum(minutos for _, minutos in self.por_passo)


def _ler_tempos(receita: Receita) -> _Tempos:
    por_passo: dict[int, int] = {}
    passivos = 0
    for ordem, limite in _limites_dos_passos(receita):
        if limite.tipo is TipoDeLimite.TEMPO and limite.minutos:
            por_passo[ordem] = por_passo.get(ordem, 0) + limite.minutos
        elif limite.tipo in _ESPERAS and limite.minutos:
            passivos += limite.minutos
    sem_tempo = tuple(o for o in passos_com_fogo_ou_aparelho(receita) if o not in por_passo)
    return _Tempos(tuple(por_passo.items()), passivos, sem_tempo)


def minutos_ativos(receita: Receita) -> MinutosAtivos:
    """Quanto tempo a receita deixa o fogo, o forno ou um aparelho ligado (`mise.tempo`).

    O limite que ela dá ("quanto tempo a senhora consegue ficar cozinhando de uma
    vez") é de fogo aceso, e as esperas não pesam nele: marinar na geladeira,
    descansar a massa, deixar de um dia para o outro. Comparar o tempo total da
    receita com esse limite bloqueava o frango que marina a noite inteira e assa
    em 40 minutos.

    Quando todo passo que acende fogo ou liga aparelho diz o tempo, soma esses
    tempos (`ativos`) e, à parte, os das esperas (`passivos`); a `derivacao` é a
    conta que ela confere ("pelos passos, 40 + 50 = 90 minutos no fogo"). Dois
    passos que correm juntos contam os dois: com uma boca só é assim que ela faz
    (com duas, o portão confere também a conta com as panelas juntas).

    Quando algum desses passos não diz o tempo ("cozinhe até desmanchar"), a
    soma dos outros é só um mínimo. Aí vale o tempo de cozimento que a receita
    declara (o `cookTime`), que cobre a receita inteira; sem ele, ou com ele
    menor que o mínimo, o tempo é desconhecido. O tempo de preparo e o total
    declarados não entram: o primeiro não é fogo, o segundo soma as esperas.
    Receita que não acende fogo nem liga aparelho, nos passos, nos equipamentos
    e nas técnicas, tem zero de tempo ativo.
    """
    tempos = _ler_tempos(receita)
    soma = tempos.soma
    cozimento = receita.tempo_cozimento_min
    if tempos.por_passo and not tempos.sem_tempo:
        return MinutosAtivos(
            soma, tempos.passivos, OrigemDoTempo.PASSOS, _conta_dos_passos(receita, tempos)
        )
    if cozimento and cozimento >= soma:
        if not tempos.por_passo:
            return MinutosAtivos.pelo_tempo_declarado(cozimento)
        return MinutosAtivos(
            cozimento,
            tempos.passivos,
            OrigemDoTempo.TEMPO_DECLARADO,
            f"os passos dizem {soma} minutos, e {quais_passos(tempos.sem_tempo)} não "
            f"{_diz(tempos.sem_tempo)} o tempo; a receita declara {cozimento} minutos de "
            "cozimento, e a conta usa esse número",
        )
    if tempos.por_passo:
        return MinutosAtivos(
            None,
            tempos.passivos,
            OrigemDoTempo.DESCONHECIDO,
            f"pelos passos, pelo menos {soma} minutos {onde_corre(receita)}, e "
            f"{quais_passos(tempos.sem_tempo)} não {_diz(tempos.sem_tempo)} o tempo",
        )
    if receita.modo_preparo and _nada_liga(receita):
        return MinutosAtivos(
            0,
            tempos.passivos,
            OrigemDoTempo.PASSOS,
            "pelos passos, nada vai ao fogo nem liga aparelho",
        )
    return MinutosAtivos.desconhecido()


def _diz(ordens: Sequence[int]) -> str:
    return "diz" if len(ordens) == 1 else "dizem"


def _conta_dos_passos(receita: Receita, tempos: _Tempos) -> str:
    """ "pelos passos, 40 + 50 = 90 minutos no fogo", ou "pelo passo 2, são 90 minutos no forno"."""
    onde = onde_corre(receita)
    if len(tempos.por_passo) == 1:
        ((ordem, minutos),) = tempos.por_passo
        return f"pelo passo {ordem}, são {minutos} minutos {onde}"
    parcelas = " + ".join(str(minutos) for _, minutos in tempos.por_passo)
    return f"pelos passos, {parcelas} = {tempos.soma} minutos {onde}"


def _sobreposto(tempos: _Tempos, outras: Sequence[int]) -> int:
    """Quanto some da soma com cada "outra panela" correndo junto da panela do passo de antes."""
    minutos = dict(tempos.por_passo)
    ordens = sorted(minutos)
    economia = 0
    for ordem in outras:
        anteriores = [o for o in ordens if o < ordem]
        if ordem in minutos and anteriores:
            economia += min(minutos[ordem], minutos[anteriores[-1]])
    return economia


def minutos_com_panelas_juntas(receita: Receita) -> int | None:
    """O tempo ativo pelos passos com cada "outra panela" acesa junto da panela de antes.

    É o tempo de quem tem duas bocas e faz as duas partes ao mesmo tempo. `None`
    quando não há outra panela, ou quando algum passo não diz o tempo.
    """
    outras = passos_com_outra_panela(receita)
    tempos = _ler_tempos(receita)
    if not outras or not tempos.por_passo or tempos.sem_tempo:
        return None
    return tempos.soma - _sobreposto(tempos, outras)


def minimo_pelos_passos(receita: Receita, *, panelas_juntas: bool) -> tuple[int, str]:
    """O que os passos que dizem o tempo já somam, com a conta: o mínimo de fogo da receita.

    Serve quando algum passo não diz o tempo: se só o que está dito já passa do
    limite dela, não dá, qualquer que seja o resto. Com `panelas_juntas`, cada
    "outra panela" corre junto da de antes, que é o menor tempo possível.
    """
    tempos = _ler_tempos(receita)
    if not tempos.por_passo:
        return 0, ""
    outras = passos_com_outra_panela(receita) if panelas_juntas else ()
    minimo = tempos.soma - _sobreposto(tempos, outras)
    juntas = ", com as duas panelas ao mesmo tempo," if minimo < tempos.soma else ""
    falta = (
        f" e {quais_passos(tempos.sem_tempo)} não {_diz(tempos.sem_tempo)} o tempo"
        if tempos.sem_tempo
        else ""
    )
    return minimo, (
        f"pelos passos, só o que eles dizem já soma {minimo} minutos {onde_corre(receita)}"
        f"{juntas}{falta}"
    )


def _nada_liga(receita: Receita) -> bool:
    """Nem os passos, nem os equipamentos, nem as técnicas da receita pedem fogo ou aparelho."""
    return (
        receita.equipamentos <= EQUIPAMENTOS_SEM_FOGO
        and receita.tecnicas <= TECNICAS_SEM_FOGO
        and not passos_com_fogo_ou_aparelho(receita)
    )


def minutos_no_fogo(receita: Receita) -> int | None:
    """Quanto tempo a receita fica no fogão, que é o que gasta o botijão.

    Dos passos, só o tempo que corre no fogão (panela, frigideira, pressão,
    banho-maria): o do forno elétrico, da air fryer e do liquidificador não gasta
    gás. Sem tempo nenhum nos passos, o tempo de cozimento declarado, quando a
    receita vai ao fogão. `None` quando não dá para saber.
    """
    ativos = minutos_ativos(receita)
    if ativos.origem is OrigemDoTempo.PASSOS:
        return sum(
            limite.minutos or 0
            for _, limite in _tempos_ativos(receita)
            if limite.equipamento == "fogao"
        )
    if ativos.origem is OrigemDoTempo.TEMPO_DECLARADO and receita.equipamentos & VAI_AO_FOGAO:
        return ativos.ativos
    # Sem o tempo inteiro, o que os passos dizem de fogão já é um mínimo de gás.
    no_fogao = sum(
        limite.minutos or 0
        for _, limite in _tempos_ativos(receita)
        if limite.equipamento == "fogao"
    )
    return no_fogao or None


def onde_corre(receita: Receita) -> str:
    """Onde o tempo ativo dos passos corre: "no fogo", "no forno", "no fogo e no forno".

    Sem tempo nos passos, a frase é a de quem não sabe onde: "no fogo ou no forno".
    """
    fontes = {limite.equipamento for _, limite in _tempos_ativos(receita)}
    if not fontes:
        return "no fogo ou no forno"
    frases = {_ONDE.get(fonte or "", _ONDE_MISTURADO) for fonte in fontes}
    if len(frases) == 1:
        return frases.pop()
    if frases == {"no fogo", "no forno"}:
        return "no fogo e no forno"
    return _ONDE_MISTURADO


def quais_passos(ordens: Sequence[int], *, artigo: bool = True) -> str:
    """ "o passo 2", "os passos 2 e 4", "os passos 1, 3 e 5": para os motivos e avisos.

    Sem `artigo`, para citar entre parênteses: "(passo 2)", "(passos 2 e 4)".
    """
    if len(ordens) == 1:
        texto = f"passo {ordens[0]}"
        return f"o {texto}" if artigo else texto
    texto = f"passos {', '.join(str(o) for o in ordens[:-1])} e {ordens[-1]}"
    return f"os {texto}" if artigo else texto


# --------------------------------------------------------------------------- #
# Perguntas com as opções de resposta
# --------------------------------------------------------------------------- #

_NAO_SEI: Final = {"rotulo": "Não sei", "resposta": "nao_sei"}
_OPCOES_DE_EQUIPAMENTO: Final = (
    {"rotulo": "Tenho", "resposta": "sim"},
    {"rotulo": "Não tenho", "resposta": "nao"},
    _NAO_SEI,
)
_OPCOES_DE_TECNICA: Final = (
    {"rotulo": "Faço", "resposta": "sim"},
    {"rotulo": "Não faço", "resposta": "nao"},
    _NAO_SEI,
)
_OPCOES_SIM_OU_NAO: Final = (
    {"rotulo": "Sim", "resposta": "sim"},
    {"rotulo": "Não", "resposta": "nao"},
    _NAO_SEI,
)
#: "A receita pede alcatra. É o seu miolo de alcatra?": a resposta volta na receita.
_OPCOES_DO_MESMO_ITEM: Final = (
    {"rotulo": "É, sim", "resposta": "sim"},
    {"rotulo": "Não é", "resposta": "nao"},
)
_OPCOES_DE_GOSTO: Final = (
    {"rotulo": "Gosto de fazer", "resposta": "gosta"},
    {"rotulo": "Não gosto", "resposta": "nao_gosta"},
    _NAO_SEI,
)

#: O rendimento é da receita, não da cozinha: a resposta volta com a receita.
_ENTRADA_DO_RENDIMENTO: Final = {"tipo": "inteiro", "unidade": "porções", "min": 1, "max": 500}

#: O tempo no fogo também é da receita: a resposta volta nela, em `tempo_cozimento_min`.
_ENTRADA_DO_TEMPO_DA_RECEITA: Final = {
    "tipo": "inteiro",
    "unidade": "minutos",
    "min": 1,
    "max": _MINUTOS_POR_DIA,
}

#: As respostas que voltam dentro da receita, e não para o perfil da cozinha.
ENTRADAS_DA_RECEITA: Final[dict[str, dict[str, Any]]] = {
    "rendimento_porcoes": _ENTRADA_DO_RENDIMENTO,
    "tempo_cozimento_min": _ENTRADA_DO_TEMPO_DA_RECEITA,
}


def como_responder(pergunta: Pergunta) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """As opções de resposta de uma pergunta do portão e, quando é número, a faixa.

    `resposta` de cada opção é o que `registrar_resposta` (e `POST /api/resposta`)
    entende. Pergunta sem opção fechada (o modo de preparo, o preço do que falta)
    vem com `entrada: {"tipo": "texto"}`: ela responde com as palavras dela. O
    rendimento e o tempo no fogo são da receita (`ENTRADAS_DA_RECEITA`): vêm com
    a faixa do número, e a resposta volta dentro da receita. O peso de uma linha
    cuja medida não se converte (`entrada_do_peso`) também.
    """
    # O portão importa este módulo; importar o dele só aqui evita o ciclo.
    from mise.viabilidade import TipoRestricao  # noqa: PLC0415

    if pergunta.peso is not None:
        return [], entrada_do_peso(pergunta.peso)
    fechadas = _opcoes_fechadas(pergunta)
    if fechadas is not None:
        return [dict(o) for o in fechadas], None
    if pergunta.tipo is TipoRestricao.OPERACIONAL and pergunta.campo in FORMATOS_OPERACIONAIS:
        return [dict(_NAO_SEI)], entrada_da_restricao(FORMATOS_OPERACIONAIS[pergunta.campo])
    if pergunta.campo in ENTRADAS_DA_RECEITA:
        return [], dict(ENTRADAS_DA_RECEITA[pergunta.campo])
    return [], {"tipo": "texto"}


def entrada_da_restricao(formato: FormatoDaRestricao) -> dict[str, Any]:
    """Como a tela pede o número de um limite da rotina: a unidade e a faixa.

    O tempo por cozinhada é pedido em horas, com vírgula ("1,5"), de meia em meia
    hora no + e no −; o motor guarda em minutos.
    """
    if formato.tipo is TipoDeCampo.HORAS:
        menor, maior = formato.faixa_em_horas()
        return {
            "tipo": formato.tipo.value,
            "unidade": formato.unidade,
            "min": float(menor),
            "max": float(maior),
            "passo": float(PASSO_DAS_HORAS),
            "casas": CASAS_DAS_HORAS,
        }
    return {
        "tipo": formato.tipo.value,
        "unidade": formato.unidade,
        "min": formato.minimo,
        "max": formato.maximo,
    }


def entrada_do_peso(peso: PesoPedido) -> dict[str, Any]:
    """Como a tela pede o peso de uma linha: um número em gramas (ou quilos) e de quanto é.

    `peso_de` traz as duas leituras quando a linha pede mais (ou menos) de uma
    unidade: o peso de uma ("1 colher de sopa") ou o da linha inteira ("2
    colheres de sopa"). Com uma unidade só, as duas são a mesma, e vem `None`.
    """
    from mise.receita import IngredienteReceita  # noqa: PLC0415
    from mise.receitas_json import na_receita  # noqa: PLC0415

    def escrito(quantidade: Decimal) -> str:
        return na_receita(IngredienteReceita("", "", quantidade, peso.medida))

    peso_de = (
        None
        if peso.quantidade == 1
        else {"cada": escrito(Decimal(1)), "tudo": escrito(peso.quantidade)}
    )
    return {"tipo": "peso", "unidade": "g", "peso_de": peso_de}


def _opcoes_fechadas(pergunta: Pergunta) -> tuple[dict[str, str], ...] | None:
    """As opções de botão, quando a resposta é uma escolha: ter, fazer, gostar, sim ou não."""
    # O portão importa este módulo; importar o dele só aqui evita o ciclo.
    from mise.viabilidade import AssuntoDaPergunta, TipoRestricao  # noqa: PLC0415

    tipo, campo = pergunta.tipo, pergunta.campo
    if pergunta.assunto is AssuntoDaPergunta.MESMO_INGREDIENTE:
        return _OPCOES_DO_MESMO_ITEM
    if tipo is TipoRestricao.EQUIPAMENTO and campo in EQUIPAMENTOS_POR_ID:
        return _OPCOES_DE_EQUIPAMENTO
    if tipo is TipoRestricao.TECNICA and campo in TECNICAS_POR_ID:
        return _OPCOES_DE_TECNICA
    if tipo is TipoRestricao.GOSTO:
        return _OPCOES_DE_GOSTO
    formato = FORMATOS_OPERACIONAIS.get(campo) if tipo is TipoRestricao.OPERACIONAL else None
    if formato is not None and formato.tipo is TipoDeCampo.SIM_NAO:
        return _OPCOES_SIM_OU_NAO
    return None


def perguntas_com_opcoes(
    perguntas: Iterable[Pergunta], passos: PassosDaReceita | None = None
) -> list[dict[str, Any]]:
    """As perguntas do portão como a tela as desenha: com as opções e os passos que as pedem.

    Mesma ordem e mesmos campos de `_avaliacao_json` (`tipo`, `campo`, `texto`,
    `motivo`), mais `assunto` (do que a pergunta trata, para a tela não ler o
    texto), `compras` (no preço do que falta comprar, cada ingrediente e quanto a
    receita pede), `opcoes`, `entrada` e `passos`.
    """
    # O portão importa este módulo; importar o dele só aqui evita o ciclo.
    from mise.receitas_json import medida_texto  # noqa: PLC0415
    from mise.viabilidade import TipoRestricao, assunto_da  # noqa: PLC0415

    saida: list[dict[str, Any]] = []
    for pergunta in perguntas:
        opcoes, entrada = como_responder(pergunta)
        do_perfil = pergunta.tipo in (TipoRestricao.EQUIPAMENTO, TipoRestricao.TECNICA)
        saida.append(
            {
                "tipo": pergunta.tipo.name.lower(),
                "assunto": assunto_da(pergunta).value,
                "campo": pergunta.campo,
                "texto": pergunta.texto,
                "motivo": pergunta.motivo,
                # Quanto falta de cada um, com o mesmo texto de `falta_comprar` no detalhe.
                "compras": [
                    {
                        "ingrediente": falta.nome,
                        "quantidade_texto": (
                            medida_texto(falta.falta)
                            if falta.falta is not None
                            else falta.quantidade_texto
                        ),
                    }
                    for falta in pergunta.compras
                ],
                "opcoes": opcoes,
                "entrada": entrada,
                "passos": list(passos.onde(pergunta.campo)) if passos and do_perfil else [],
            }
        )
    return saida


# --------------------------------------------------------------------------- #
# O que a avaliação de uma receita ganha
# --------------------------------------------------------------------------- #


def exigencias(receita: Receita) -> dict[str, list[str]]:
    """Os nomes do que a receita pede, em ordem alfabética: o `exige` da avaliação."""
    return {
        "equipamentos": sorted(EQUIPAMENTOS_POR_ID[i].nome for i in receita.equipamentos),
        "tecnicas": sorted(TECNICAS_POR_ID[i].nome for i in receita.tecnicas),
    }


def detalhar(receita: Receita, perfil: PerfilCozinha, avaliacao: Avaliacao) -> dict[str, Any]:
    """O que `avaliar_receita` e `/api/avaliar` devolvem além do parecer do portão.

    `perguntas` substitui a lista do parecer pela mesma lista com as opções;
    `exige` são os nomes do que a receita pede; `por_passo` é a receita passo a
    passo (`passos[]` e `requisitos_da_receita[]`, a forma de
    `contratos/web/receita.json`). `pode_aceitar`, `falta_para_aceitar` e
    `confirmar_a_cozinha` são os de `receita.json#checklist`: o aceite pede a
    conferência liberada, o gosto e o que toda cozinha tem confirmado por ela.
    `perfil` tem de ser o mesmo que a avaliação usou.
    """
    # A certeza importa o portão, que importa este módulo: só aqui, para não virar ciclo.
    from mise.certeza import Acao, confirmacao_json, pressupostos_da_receita  # noqa: PLC0415
    from mise.checklist import o_que_falta_para_aceitar  # noqa: PLC0415

    passos = avaliar_passos(receita, perfil)
    supostos = pressupostos_da_receita(receita, perfil)
    pode_aceitar = avaliacao.permite_precificar and not supostos
    return {
        "perguntas": perguntas_com_opcoes(avaliacao.perguntas, passos),
        "exige": exigencias(receita),
        "por_passo": passos.para_json(),
        # O aceite pede também a cozinha confirmada: a pergunta, uma só, e o que falta.
        "pode_aceitar": pode_aceitar,
        "falta_para_aceitar": (
            [] if pode_aceitar else o_que_falta_para_aceitar(receita, avaliacao, supostos)
        ),
        "confirmar_a_cozinha": confirmacao_json(receita, perfil, Acao.ACEITAR),
    }


__all__ = [
    "ENTRADAS_DA_RECEITA",
    "EQUIPAMENTOS_SEM_FOGO",
    "TECNICAS_SEM_FOGO",
    "VAI_AO_FOGAO",
    "Limite",
    "OrigemDoRequisito",
    "PassoAvaliado",
    "PassosDaReceita",
    "Requisito",
    "RequisitoDaReceita",
    "TipoDeLimite",
    "TipoDeRequisito",
    "avaliar_passos",
    "como_responder",
    "detalhar",
    "entrada_da_restricao",
    "exigencias",
    "extrair_limites",
    "minimo_pelos_passos",
    "minutos_ativos",
    "minutos_com_panelas_juntas",
    "minutos_no_fogo",
    "onde_corre",
    "passos_com_fogo_ou_aparelho",
    "passos_com_frio",
    "passos_com_outra_panela",
    "perguntas_com_opcoes",
    "quais_passos",
]
