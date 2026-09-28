"""O perfil da cozinha da Dona Maria: o que ela tem, sabe e aguenta.

A decisão de projeto mais importante deste módulo é a **lógica de três valores**:

    TEM · NÃO TEM · DESCONHECIDO

Um sistema de dois valores obriga a escolher entre dois erros. Se ausência de
informação vale "não tem", o agente bloqueia pratos que ela poderia fazer e
vira um chato inútil. Se vale "tem", ele deixa ela comprar ingrediente para uma
receita que ela não consegue produzir, exatamente o que o enunciado proíbe.

`DESCONHECIDO` é o que permite ao motor devolver `FALTA_INFO` com a pergunta
exata, em vez de adivinhar. É a diferença entre um agente que pergunta e um
agente que chuta.

Segundo detalhe: equipamentos e técnicas marcados como **pressupostos** na
taxonomia já começam como `TEM`. Perguntar "a senhora tem faca?" para uma
cozinheira de mão cheia é ofensivo e gasta a paciência dela justamente antes
das perguntas que decidem alguma coisa. Mas suposto não é certeza: quando ela
mesma diz que não tem fogão, o portão bloqueia as receitas de fogão.

Terceiro: "não sei" é uma resposta, e não é "não tem". `sem_resposta` deixa o
item em aberto (`DESCONHECIDO`), inclusive o pressuposto: voltar o fogão ao
"tem" suposto seria responder por ela. O portão pergunta de novo quando uma
receita precisar do item.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.erros import ErroDeUso, VocabularioDesconhecido
from mise.taxonomia import (
    EQUIPAMENTOS,
    EQUIPAMENTOS_POR_ID,
    TECNICAS,
    TECNICAS_POR_ID,
    equipamento,
    tecnica,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def contagem(n: int, singular: str, plural: str) -> str:
    """ "1 receita", "0 receitas", "2 receitas": em português, só o um vai no singular.

    Todo texto com número que chega a ela ou ao agente passa por aqui. "1
    respondidos" num resumo é o tipo de descuido que faz a tela parecer feita às
    pressas, e o plural montado na tela seria mais um lugar formatando texto.
    """
    return f"{n} {singular if n == 1 else plural}"


class Gosto(StrEnum):
    """Se a Dona Maria gosta de fazer um prato.

    É de três valores pela mesma razão que `Posse` é: "ela não disse" não é
    "ela não gosta". Tratar silêncio como recusa descartaria prato viável sem
    ela ter opinado, que é o oposto do que o §2.1 do desafio pede: ele manda
    apresentar as candidatas e **perguntar** se ela gosta de cozinhar aquilo.

    E gosto bloqueia de verdade. Não é preferência a ser ponderada junto do
    resto: um prato que ela não gosta de fazer não entra no cardápio por mais
    barato que o CMV saia. Quem cozinha é ela, todo dia.
    """

    GOSTA = "gosta"
    NAO_GOSTA = "nao_gosta"
    DESCONHECIDO = "desconhecido"

    @property
    def resolvido(self) -> bool:
        return self is not Gosto.DESCONHECIDO

    @property
    def bloqueia(self) -> bool:
        return self is Gosto.NAO_GOSTA


class Posse(StrEnum):
    """Estado de conhecimento sobre um equipamento ou técnica."""

    TEM = "tem"
    NAO_TEM = "nao_tem"
    DESCONHECIDO = "desconhecido"

    @property
    def resolvido(self) -> bool:
        """Já sabemos a resposta: não precisa perguntar."""
        return self is not Posse.DESCONHECIDO

    @property
    def bloqueia(self) -> bool:
        """Impede a produção de forma definitiva."""
        return self is Posse.NAO_TEM


@dataclass(frozen=True, slots=True)
class RestricoesOperacionais:
    """Os limites físicos da cozinha dela.

    Cada campo é `None` enquanto não perguntamos: mesma lógica de três valores,
    só que para números.
    """

    bocas_fogao: int | None = None
    """Quantas panelas ela consegue tocar ao mesmo tempo."""

    tempo_max_por_fornada_min: int | None = None
    """Quanto tempo ela topa gastar numa leva de produção."""

    espaco_geladeira_litros: int | None = None
    """Quanto cabe de preparo pronto. Zero bloqueia receita que precisa descansar."""

    porcoes_por_fornada: int | None = None
    """Quantas marmitas ela monta numa leva. Perguntado, e de propósito fora do portão.

    Receita que rende mais porções do que ela monta de uma vez não é receita
    impossível: ela faz em duas levas, ou meia receita, e o custo de cada porção
    não muda. Bloquear por isso descartaria prato viável; perguntar em toda
    receita seria uma pergunta que não decide nada, e o portão só pergunta o que
    decide. O número serve ao planejamento (quantas levas por dia) e à conta de
    mão de obra por porção, não à pergunta "ela consegue fazer?".
    """

    tem_gas_sobrando: bool | None = None
    """Botijão é custo e é risco de acabar no meio do pedido."""

    energia_aparelhos_simultaneos: int | None = None
    """Quantos aparelhos de alta potência a instalação dela aguenta juntos.

    O enunciado lista energia entre as restrições operacionais, e é a mais fácil
    de esquecer porque não aparece na receita: forno elétrico e batedeira ligados
    ao mesmo tempo derrubam o disjuntor de muita casa, e a descoberta acontece no
    meio da produção.
    """

    def pendencias(self) -> tuple[str, ...]:
        """Quais restrições ainda não foram levantadas.

        As quatro que o §2.2 nomeia (energia, gás, espaço na geladeira e tempo),
        mais bocas de fogão e porções por fornada, que são consequência das
        mesmas perguntas.
        """
        faltando = []
        if self.bocas_fogao is None:
            faltando.append("bocas_fogao")
        if self.tempo_max_por_fornada_min is None:
            faltando.append("tempo_max_por_fornada_min")
        if self.porcoes_por_fornada is None:
            faltando.append("porcoes_por_fornada")
        if self.tem_gas_sobrando is None:
            faltando.append("tem_gas_sobrando")
        if self.espaco_geladeira_litros is None:
            faltando.append("espaco_geladeira_litros")
        if self.energia_aparelhos_simultaneos is None:
            faltando.append("energia_aparelhos_simultaneos")
        return tuple(faltando)

    @property
    def completo(self) -> bool:
        return not self.pendencias()


PERGUNTAS_OPERACIONAIS: Final[dict[str, str]] = {
    "bocas_fogao": "Seu fogão tem quantas bocas? Isso limita quantas panelas andam juntas.",
    "tempo_max_por_fornada_min": (
        "Quanto tempo a senhora consegue ficar cozinhando de uma vez, sem se estressar ou cansar?"
    ),
    "porcoes_por_fornada": "Quantas marmitas a senhora consegue montar numa leva só?",
    "espaco_geladeira_litros": (
        "Como está o espaço na geladeira? Cabe guardar preparo pronto, "
        "em litros mais ou menos? Pode chutar."
    ),
    "energia_aparelhos_simultaneos": (
        "Quantos aparelhos de alta potência a senhora consegue ligar ao mesmo "
        "tempo sem cair o disjuntor? Forno elétrico, air fryer, batedeira."
    ),
    "tem_gas_sobrando": "Como está o botijão de gás? Tem reserva?",
}


class TipoDeCampo(StrEnum):
    """Como uma restrição é respondida na tela: um número inteiro, horas ou sim/não.

    `HORAS` é o tempo por cozinhada: ela responde em horas ("2", "1,5") e o
    dossiê guarda minutos, a unidade da conta do portão.
    """

    INTEIRO = "inteiro"
    HORAS = "horas"
    SIM_NAO = "sim_nao"


@dataclass(frozen=True, slots=True)
class FormatoDaRestricao:
    """O tipo, a unidade e a faixa de uma restrição, para a tela perguntar e conferir.

    A faixa é de conversa, não de física: serve para recusar um "80 bocas"
    digitado ou entendido errado antes de ele bloquear receita, não para dizer o
    que existe. Vale para as duas portas, a tela e a conversa: a resposta fora da
    faixa volta com a mensagem, e o agente pergunta de novo.

    `minimo` e `maximo` estão na unidade guardada no dossiê. No tempo por
    cozinhada (`HORAS`) são minutos, e a tela recebe a faixa em horas
    (`faixa_em_horas`).
    """

    tipo: TipoDeCampo
    unidade: str = ""
    minimo: int | None = None
    maximo: int | None = None

    def conferir(self, valor: object) -> int | bool | None:
        """O valor como a tela manda, no tipo guardado, ou erro de uso dito para ela.

        `None` é "não sei". No tempo por cozinhada, a tela manda horas (1,5) e o
        que volta são minutos (90).
        """
        if valor is None:
            return None
        if self.tipo is TipoDeCampo.SIM_NAO:
            if isinstance(valor, bool):
                return valor
            raise ErroDeUso("a resposta aqui é sim ou não", recebido=valor)
        if self.tipo is TipoDeCampo.HORAS:
            return self.no_limite(minutos_das_horas(valor))
        numero = _inteiro_de(valor)
        if numero is None:
            raise ErroDeUso("a resposta aqui é um número inteiro", recebido=valor)
        return self.no_limite(numero)

    def no_limite(self, numero: int) -> int:
        """O número guardado (em minutos, no tempo) dentro da faixa; senão a recusa para ela."""
        if (self.minimo is not None and numero < self.minimo) or (
            self.maximo is not None and numero > self.maximo
        ):
            if self.tipo is TipoDeCampo.HORAS:
                raise ErroDeUso(
                    f"esse tempo precisa ficar entre {horas_texto(self.minimo or 0)} e "
                    f"{horas_texto(self.maximo or 0)}",
                    recebido=horas_texto(numero),
                )
            raise ErroDeUso(
                f"esse número precisa ficar entre {self.minimo} e {self.maximo} {self.unidade}",
                recebido=numero,
            )
        return numero

    def faixa_em_horas(self) -> tuple[Decimal, Decimal]:
        """A faixa do tempo por cozinhada em horas, como a tela pergunta (0,5 a 12)."""
        return em_horas(self.minimo or 0), em_horas(self.maximo or 0)


#: De quanto em quanto o + e o − da tela andam no tempo por cozinhada, em horas.
PASSO_DAS_HORAS: Final = Decimal("0.5")

#: Quantas casas a tela aceita nas horas: 1,25 hora é uma hora e quinze minutos.
CASAS_DAS_HORAS: Final = 2

_MINUTOS_POR_HORA: Final = 60

#: Três minutos são 0,05 hora: múltiplo de três é hora exata com duas casas.
_MINUTOS_DE_CINCO_CENTESIMOS: Final = 3

#: "1,5 hora", "2 horas": o plural começa em dois.
_PLURAL_A_PARTIR_DE: Final = 2

#: "2", "1,5", "1.5": o número dela, com vírgula ou ponto.
_NUMERO: Final = r"\d+(?:[.,]\d+)?"

#: Os números por extenso que alguém diz de um tempo curto.
_POR_EXTENSO: Final[dict[str, str]] = {
    "um": "1",
    "uma": "1",
    "dois": "2",
    "duas": "2",
    "tres": "3",
    "quatro": "4",
    "cinco": "5",
    "seis": "6",
    "sete": "7",
    "oito": "8",
    "nove": "9",
    "dez": "10",
    "onze": "11",
    "doze": "12",
}


def em_horas(minutos: int) -> Decimal:
    """Os minutos guardados em horas, com duas casas: 90 vira 1,5; 100 vira 1,67."""
    return (Decimal(minutos) / _MINUTOS_POR_HORA).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def horas_texto(minutos: int) -> str:
    """O tempo dito para ela: "2 horas", "1,5 hora", "meia hora", "1 hora e 40 minutos".

    Em horas quando a conta é exata com até duas casas (90 minutos são 1,5
    hora); senão em horas e minutos, para não arredondar o que ela disse. Abaixo
    de duas, "hora" fica no singular, como se fala: "1,5 hora".
    """
    horas, resto = divmod(minutos, _MINUTOS_POR_HORA)
    if minutos == _MINUTOS_POR_HORA // 2:
        return "meia hora"
    if resto == 0:
        return f"{horas} {_hora(horas)}"
    if minutos % _MINUTOS_DE_CINCO_CENTESIMOS == 0:
        valor = Decimal(minutos) / _MINUTOS_POR_HORA
        return f"{f'{valor.normalize():f}'.replace('.', ',')} {_hora(valor)}"
    em_minutos = f"{resto} {'minuto' if resto == 1 else 'minutos'}"
    return f"{horas} {_hora(horas)} e {em_minutos}" if horas else em_minutos


def _hora(quantas: Decimal | int) -> str:
    return "hora" if quantas < _PLURAL_A_PARTIR_DE else "horas"


def minutos_das_horas(valor: object) -> int:
    """As horas que a tela manda (2, 1.5) em minutos inteiros, com arredondamento comercial."""
    if isinstance(valor, bool) or not isinstance(valor, int | float | Decimal):
        raise ErroDeUso("a resposta aqui é quantas horas, como 2 ou 1,5", recebido=valor)
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ErroDeUso("a resposta aqui é quantas horas, como 2 ou 1,5", recebido=valor)
    horas = Decimal(str(valor))
    if horas <= 0:
        raise ErroDeUso("o tempo precisa ser maior que zero", recebido=valor)
    return int((horas * _MINUTOS_POR_HORA).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:  # pragma: no cover (a expressão só deixa passar número)
        raise ErroDeUso("não entendi esse tempo", recebido=texto) from None


def minutos_ditos(resposta: str) -> int:
    """O tempo como ela disse, em minutos: horas por padrão, minutos só quando ela diz.

    "2", "2 horas", "1,5 hora", "1h30", "1 hora e meia", "meia hora", "uma hora
    e 20 minutos", "90 minutos". Um número sozinho é em horas, porque é assim
    que a pergunta pede. O que não dá para entender é recusado, e não adivinhado.
    """
    texto = unicodedata.normalize("NFKD", resposta).encode("ascii", "ignore").decode().lower()
    texto = " ".join(texto.replace("hrs", "h").replace("hr", "h").split())
    for palavra, numero in _POR_EXTENSO.items():
        texto = re.sub(rf"\b{palavra}\b", numero, texto)
    texto = re.sub(r"\bmeia hora\b", "0,5 hora", texto)
    horas = re.fullmatch(
        rf"(?P<h>{_NUMERO})\s*(?:h|horas?)"
        rf"(?:\s*(?:e\s*)?(?:(?P<meia>meia)|(?P<m>\d+)\s*(?:min|minutos?)?))?",
        texto,
    )
    if horas is not None:
        minutos = _decimal(horas["h"]) * _MINUTOS_POR_HORA
        if horas["meia"]:
            minutos += _MINUTOS_POR_HORA // 2
        elif horas["m"]:
            minutos += Decimal(horas["m"])
        return int(minutos.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    so_minutos = re.fullmatch(rf"(?P<m>{_NUMERO})\s*(?:min|minutos?)", texto)
    if so_minutos is not None:
        return int(_decimal(so_minutos["m"]).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if re.fullmatch(_NUMERO, texto):
        return minutos_das_horas(_decimal(texto))
    raise ErroDeUso(
        "não entendi esse tempo; diga em horas, como 2 horas ou 1,5 hora", recebido=resposta
    )


#: Como cada restrição aparece na tela. As chaves são as de `PERGUNTAS_OPERACIONAIS`.
FORMATOS_OPERACIONAIS: Final[dict[str, FormatoDaRestricao]] = {
    "bocas_fogao": FormatoDaRestricao(TipoDeCampo.INTEIRO, "bocas", 1, 8),
    # Guardado em minutos (a conta do portão), perguntado e mostrado em horas.
    "tempo_max_por_fornada_min": FormatoDaRestricao(TipoDeCampo.HORAS, "horas", 30, 720),
    "porcoes_por_fornada": FormatoDaRestricao(TipoDeCampo.INTEIRO, "porções", 1, 500),
    # Zero é resposta de verdade: "não sobra espaço" bloqueia o que precisa gelar.
    "espaco_geladeira_litros": FormatoDaRestricao(TipoDeCampo.INTEIRO, "litros", 0, 1000),
    "energia_aparelhos_simultaneos": FormatoDaRestricao(TipoDeCampo.INTEIRO, "aparelhos", 0, 10),
    "tem_gas_sobrando": FormatoDaRestricao(TipoDeCampo.SIM_NAO),
}


def _inteiro_de(valor: object) -> int | None:
    """Número inteiro, aceitando `4.0`; nunca `True`, que em Python também é inteiro."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and math.isfinite(valor) and valor.is_integer():
        return int(valor)
    return None


@dataclass(frozen=True, slots=True)
class PerfilCozinha:
    """Tudo que sabemos sobre a capacidade produtiva da Dona Maria.

    Imutável: cada resposta dela produz um perfil novo. Isso torna o histórico
    auditável e impede que uma parte do sistema mude o perfil por baixo de outra.
    """

    equipamentos: dict[str, Posse] = field(default_factory=dict)
    tecnicas: dict[str, Posse] = field(default_factory=dict)
    restricoes: RestricoesOperacionais = field(default_factory=RestricoesOperacionais)
    #: Ids de equipamento e técnica que ELA respondeu. O resto que está como
    #: "tem" é pressuposto de qualquer cozinha, e o agente não pode dizer que
    #: ela disse o que ninguém perguntou.
    confirmados: frozenset[str] = frozenset()

    @classmethod
    def inicial(cls) -> PerfilCozinha:
        """Perfil de partida: só o que é razoável pressupor de qualquer cozinha."""
        return cls(
            equipamentos={
                e.id: (Posse.TEM if e.pressuposto else Posse.DESCONHECIDO) for e in EQUIPAMENTOS
            },
            tecnicas={t.id: (Posse.TEM if t.pressuposta else Posse.DESCONHECIDO) for t in TECNICAS},
            restricoes=RestricoesOperacionais(),
        )

    # -- consultas -------------------------------------------------------- #

    def tem_equipamento(self, id_: str) -> Posse:
        equipamento(id_)  # valida o vocabulário
        return self.equipamentos.get(id_, Posse.DESCONHECIDO)

    def domina_tecnica(self, id_: str) -> Posse:
        tecnica(id_)
        return self.tecnicas.get(id_, Posse.DESCONHECIDO)

    def tem_equipamento_ou_substituto(self, id_: str) -> tuple[Posse, str | None]:
        """Resolve o equipamento considerando substitutos aceitáveis.

        Air fryer resolve boa parte do que o forno faria. Vale checar antes de
        bloquear um prato, e devolvemos qual substituto salvou, para o agente
        poder explicar.
        """
        direto = self.tem_equipamento(id_)
        if direto is Posse.TEM:
            return Posse.TEM, None

        for substituto in equipamento(id_).substitutos:
            if self.tem_equipamento(substituto) is Posse.TEM:
                return Posse.TEM, substituto

        if direto is Posse.NAO_TEM:
            # Só é bloqueio definitivo se todos os substitutos também foram negados.
            desconhecidos = [
                s
                for s in equipamento(id_).substitutos
                if self.tem_equipamento(s) is Posse.DESCONHECIDO
            ]
            return (Posse.DESCONHECIDO if desconhecidos else Posse.NAO_TEM), None

        return Posse.DESCONHECIDO, None

    # -- atualizações (sempre devolvem um perfil novo) --------------------- #

    def com_equipamento(self, id_: str, posse: Posse) -> PerfilCozinha:
        """O que ela respondeu sobre um equipamento. Conta como confirmado por ela."""
        equipamento(id_)
        return replace(
            self,
            equipamentos={**self.equipamentos, id_: posse},
            confirmados=self.confirmados | {id_},
        )

    def com_tecnica(self, id_: str, posse: Posse) -> PerfilCozinha:
        """O que ela respondeu sobre uma técnica. Conta como confirmado por ela."""
        tecnica(id_)
        return replace(
            self, tecnicas={**self.tecnicas, id_: posse}, confirmados=self.confirmados | {id_}
        )

    def pressuposto(self, id_: str) -> bool:
        """Está como "tem" porque qualquer cozinha tem, não porque ela disse."""
        return id_ not in self.confirmados

    def suposto(self, id_: str) -> bool:
        """Está como "tem" e ninguém perguntou: a tela não pode pintar isso como resposta dela."""
        posse = self.equipamentos.get(id_) or self.tecnicas.get(id_)
        return posse is Posse.TEM and self.pressuposto(id_)

    def sem_resposta(self, id_: str) -> PerfilCozinha:
        """Ela disse "não sei": o item fica em aberto.

        Equipamento e técnica ficam `DESCONHECIDO` e saem de `confirmados` (a
        agente não pode dizer que ela respondeu "tenho"). Vale também para o que
        qualquer cozinha tem: "não sei se tenho fogão" voltava a "tem", suposto,
        e o portão liberava receita de fogão sem ninguém saber se havia fogão.
        Agora o portão pergunta de novo quando uma receita precisar do item. A
        restrição volta a `None`, e o portão pergunta quando uma receita depender
        dela.
        """
        if id_ in EQUIPAMENTOS_POR_ID:
            return replace(
                self,
                equipamentos={**self.equipamentos, id_: Posse.DESCONHECIDO},
                confirmados=self.confirmados - {id_},
            )
        if id_ in TECNICAS_POR_ID:
            return replace(
                self,
                tecnicas={**self.tecnicas, id_: Posse.DESCONHECIDO},
                confirmados=self.confirmados - {id_},
            )
        if id_ in PERGUNTAS_OPERACIONAIS:
            return self.com_restricao(id_, None)
        raise VocabularioDesconhecido(
            "item da cozinha",
            id_,
            (*EQUIPAMENTOS_POR_ID, *TECNICAS_POR_ID, *PERGUNTAS_OPERACIONAIS),
        )

    def com_equipamentos(self, itens: Iterable[tuple[str, Posse]]) -> PerfilCozinha:
        """Muitas respostas de uma vez. Como `com_equipamento`, contam como ditas por ela."""
        novos = dict(self.equipamentos)
        ditos: set[str] = set()
        for id_, posse in itens:
            equipamento(id_)
            novos[id_] = posse
            ditos.add(id_)
        return replace(self, equipamentos=novos, confirmados=self.confirmados | ditos)

    def com_tecnicas(self, itens: Iterable[tuple[str, Posse]]) -> PerfilCozinha:
        """Muitas respostas de uma vez. Como `com_tecnica`, contam como ditas por ela."""
        novas = dict(self.tecnicas)
        ditas: set[str] = set()
        for id_, posse in itens:
            tecnica(id_)
            novas[id_] = posse
            ditas.add(id_)
        return replace(self, tecnicas=novas, confirmados=self.confirmados | ditas)

    def com_restricao(self, campo: str, valor: int | bool | None) -> PerfilCozinha:
        if campo not in PERGUNTAS_OPERACIONAIS:
            raise VocabularioDesconhecido(
                "restrição operacional", campo, tuple(PERGUNTAS_OPERACIONAIS)
            )
        alteracao: dict[str, Any] = {campo: valor}
        return replace(self, restricoes=replace(self.restricoes, **alteracao))

    # -- panorama --------------------------------------------------------- #

    @property
    def equipamentos_conhecidos(self) -> frozenset[str]:
        """Ids que ela confirmou ter."""
        return frozenset(i for i, p in self.equipamentos.items() if p is Posse.TEM)

    @property
    def tecnicas_dominadas(self) -> frozenset[str]:
        return frozenset(i for i, p in self.tecnicas.items() if p is Posse.TEM)

    @property
    def equipamentos_ausentes(self) -> frozenset[str]:
        return frozenset(i for i, p in self.equipamentos.items() if p is Posse.NAO_TEM)

    @property
    def tecnicas_ausentes(self) -> frozenset[str]:
        return frozenset(i for i, p in self.tecnicas.items() if p is Posse.NAO_TEM)

    @property
    def equipamentos_em_aberto(self) -> frozenset[str]:
        return frozenset(i for i, p in self.equipamentos.items() if p is Posse.DESCONHECIDO)

    @property
    def tecnicas_em_aberto(self) -> frozenset[str]:
        return frozenset(i for i, p in self.tecnicas.items() if p is Posse.DESCONHECIDO)

    @property
    def completude(self) -> float:
        """Fração do perfil já levantada, de 0 a 1.

        Serve para a interface mostrar progresso e para o agente saber quando
        parar de perguntar, não para bloquear nada. Conta como levantado o que
        o portão não precisa mais perguntar: o que ela respondeu e o que é
        pressuposto. Quem quer só o que ela respondeu usa `fracao_respondida`.

        As restrições contam todas as seis. A conta antiga somava `3 −
        pendências` contra 3 no total: com as seis em aberto, a parte das
        restrições saía −3, e responder três delas não movia a barra.
        """
        campos = len(PERGUNTAS_OPERACIONAIS)
        total = len(self.equipamentos) + len(self.tecnicas) + campos
        resolvidos = (
            sum(1 for p in self.equipamentos.values() if p.resolvido)
            + sum(1 for p in self.tecnicas.values() if p.resolvido)
            + (campos - len(self.restricoes.pendencias()))
        )
        return resolvidos / total

    @property
    def respondidos(self) -> int:
        """Equipamentos e técnicas que ela mesma respondeu, tenha ou não."""
        return len(self.confirmados)

    @property
    def supostos(self) -> int:
        """Os que estão como "tem" só porque qualquer cozinha tem."""
        return sum(1 for i in self.equipamentos_conhecidos if self.pressuposto(i)) + sum(
            1 for i in self.tecnicas_dominadas if self.pressuposto(i)
        )

    @property
    def em_aberto(self) -> int:
        return len(self.equipamentos_em_aberto) + len(self.tecnicas_em_aberto)

    @property
    def fracao_respondida(self) -> float:
        """Quanto dos equipamentos e técnicas ela mesma respondeu, de 0 a 1, com 4 casas."""
        total = len(EQUIPAMENTOS_POR_ID) + len(TECNICAS_POR_ID)
        return round(self.respondidos / total, 4)

    def resumo_para_a_tela(self, nao_sabe: int = 0) -> str:
        """A mesma conta de `resumo`, dita para ela: "1 respondido pela senhora · …".

        `nao_sabe` é quantos dos em aberto ela respondeu "não sei" (o perfil não
        guarda isso; vem do histórico). "Não sei" é resposta dela: sai à parte, e
        só o resto é "ainda não perguntei".
        """
        partes = [
            f"{contagem(self.respondidos, 'respondido', 'respondidos')} pela senhora",
            contagem(self.supostos, "suposto", "supostos"),
        ]
        if nao_sabe:
            partes.append(f"{nao_sabe} que a senhora não sabe")
        partes.append(f"{self.em_aberto - nao_sabe} ainda não perguntei")
        return " · ".join(partes)

    def progresso_para_a_tela(self) -> str:
        """ "1 de 63 respondidos pela senhora": a conta de `fracao_respondida`, em texto."""
        total = len(EQUIPAMENTOS_POR_ID) + len(TECNICAS_POR_ID)
        return f"{self.respondidos} de {total} respondidos pela senhora"

    def resumo(self) -> str:
        """Uma linha para o log e para a memória do agente.

        Separa o que ela respondeu do que é suposto. Contar suposição como
        resposta fazia um perfil sem resposta nenhuma aparecer "21% levantado".
        """
        return (
            f"{contagem(self.respondidos, 'respondido', 'respondidos')} por ela · "
            f"{contagem(self.supostos, 'suposto', 'supostos')} de qualquer cozinha · "
            f"{self.em_aberto} em aberto"
        )

    # -- serialização ----------------------------------------------------- #

    def para_dict(self) -> dict[str, object]:
        return {
            "equipamentos": {i: p.value for i, p in sorted(self.equipamentos.items())},
            "tecnicas": {i: p.value for i, p in sorted(self.tecnicas.items())},
            "restricoes": {
                "bocas_fogao": self.restricoes.bocas_fogao,
                "tempo_max_por_fornada_min": self.restricoes.tempo_max_por_fornada_min,
                "espaco_geladeira_litros": self.restricoes.espaco_geladeira_litros,
                "porcoes_por_fornada": self.restricoes.porcoes_por_fornada,
                "tem_gas_sobrando": self.restricoes.tem_gas_sobrando,
                "energia_aparelhos_simultaneos": self.restricoes.energia_aparelhos_simultaneos,
            },
            "confirmados": sorted(self.confirmados),
        }

    @classmethod
    def de_dict(cls, dados: dict[str, object]) -> PerfilCozinha:
        equipamentos_brutos = _exigir_dict(dados, "equipamentos")
        tecnicas_brutas = _exigir_dict(dados, "tecnicas")
        restricoes_brutas = _exigir_dict(dados, "restricoes")

        base = cls.inicial()
        equipamentos = dict(base.equipamentos)
        for id_, valor in equipamentos_brutos.items():
            if id_ in EQUIPAMENTOS_POR_ID:
                equipamentos[id_] = Posse(valor)
        tecnicas = dict(base.tecnicas)
        for id_, valor in tecnicas_brutas.items():
            if id_ in TECNICAS_POR_ID:
                tecnicas[id_] = Posse(valor)

        return cls(
            equipamentos=equipamentos,
            tecnicas=tecnicas,
            restricoes=RestricoesOperacionais(
                bocas_fogao=_inteiro(restricoes_brutas.get("bocas_fogao")),
                tempo_max_por_fornada_min=_inteiro(
                    restricoes_brutas.get("tempo_max_por_fornada_min")
                ),
                espaco_geladeira_litros=_inteiro(restricoes_brutas.get("espaco_geladeira_litros")),
                porcoes_por_fornada=_inteiro(restricoes_brutas.get("porcoes_por_fornada")),
                tem_gas_sobrando=_booleano(restricoes_brutas.get("tem_gas_sobrando")),
                energia_aparelhos_simultaneos=_inteiro(
                    restricoes_brutas.get("energia_aparelhos_simultaneos")
                ),
            ),
            # Dossiê de antes deste campo: tudo que foi gravado conta como dito
            # por ela, que é o que aquela versão supunha.
            confirmados=frozenset(
                _lista_de_ids(dados.get("confirmados"))
                if "confirmados" in dados
                else [*equipamentos_brutos, *tecnicas_brutas]
            ),
        )


def _lista_de_ids(bruto: object) -> list[str]:
    if not isinstance(bruto, list):
        return []
    return [str(i) for i in bruto]


def _exigir_dict(dados: dict[str, object], campo: str) -> dict[str, Any]:
    """Aceita ausência e `None`, mas recusa qualquer outro tipo.

    `dados.get(campo) or {}` mascararia uma lista vazia, que é dado malformado
    e não ausência de dado.
    """
    valor = dados.get(campo)
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ValueError(
            f"perfil malformado: {campo!r} deve ser objeto, veio {type(valor).__name__}"
        )
    return valor


def _inteiro(valor: object) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def _booleano(valor: object) -> bool | None:
    return valor if isinstance(valor, bool) else None


__all__ = [
    "FORMATOS_OPERACIONAIS",
    "PERGUNTAS_OPERACIONAIS",
    "FormatoDaRestricao",
    "PerfilCozinha",
    "Posse",
    "RestricoesOperacionais",
    "TipoDeCampo",
    "contagem",
]
