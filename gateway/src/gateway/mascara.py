"""Nenhum valor em reais chega à tela antes de ser conferido.

O agente escreve em pedaços (`assistant.delta`), e o guard-rail do Hermes
só confere o texto no fim do turno. Enquanto isso, o rascunho que a Dona Maria
vê pode trazer um "R$ 7,50" que o modelo calculou de cabeça. Por isso todo
valor do rascunho sai trocado pelo caractere sentinela (`frases.SENTINELA`),
que a tela desenha como "R$ ···"; quando o turno termina, o texto final, já
conferido, substitui o rascunho.

O que conta como valor é o que o guard-rail confere: a expressão `_VALOR` do
plugin (`hermes/plugins/guardrail-numerico`), copiada aqui e comparada com a
dele por teste, mais o dinheiro escrito com a palavra ("6 reais", "1 real"), que
o plugin confere na fala do modelo e aceita na fala dela, com a mesma expressão
daqui (`PADRAO_FALADO`). A `_VALOR` para no terceiro dígito de um milhar sem
ponto ("R$ 1500,00" casa só "R$ 150"); o que sobra colado no sentinela ("0,00")
também some, para nenhum dígito de valor aparecer.

**O valor partido.** "R$ 66" num pedaço e "3,39" no seguinte não podem mostrar
o "66" nem o "3,39". A `MascaraDeValores` trabalha sobre o rascunho acumulado e
segura o fim que ainda pode virar valor: um "R" solto, "R$", "R$ 7,", um número
no fim (pode ganhar "reais"), "4,5 rea". O que vem antes do trecho retido nunca
muda de máscara com o que chegar depois, então sai em definitivo, mascarado.

**O texto final.** Mesmo depois do guard-rail, o backend confere de novo cada
valor contra o que tem procedência na conversa (`retirar_sem_procedencia`): as
saídas do motor, o que ela disse e o que já foi conferido antes. Essa conferência
lê o número inteiro depois do cifrão, então "R$ 1500,00" é conferido como 1500, e
número que não é pt-BR ("R$ 12.5") não tem como ser sustentado: sai.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Final

from gateway.frases import SENTINELA

#: A expressão do guard-rail para valores com cifrão: R$ 1.234,56 · R$ 8,68 · R$ 12.
#: Igual, caractere por caractere, à `_VALOR` do plugin (conferido por teste).
PADRAO_DO_VALOR: Final = r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"

#: O dinheiro escrito com a palavra: qualquer número colado em "reais" ou "real".
#: O milhar ("1.234 reais"), o singular ("1 real") e o número mal escrito ("12.5
#: reais") também contam: somem do rascunho e, sem procedência, do texto final.
PADRAO_FALADO: Final = r"(\d(?:[\d.,]*\d)?)\s*(?:reais|real)\b"

#: Como o plugin lê o dinheiro escrito com a palavra, na fala dela e na do
#: modelo: a `_REAIS_FALADO` dele, com `re.IGNORECASE`, conferida por teste. É a
#: mesma expressão daqui, para os dois conferirem as mesmas quantias.
PADRAO_FALADO_DO_PLUGIN: Final = PADRAO_FALADO

#: "1 em cada 8 reais", "a cada 10 reais": proporção, não quantia. O plugin não
#: confere, e o texto final também não (`_PROPORCAO` do plugin).
PADRAO_DA_PROPORCAO: Final = r"\bcada\s*\Z"

#: O valor com cifrão lido inteiro, para a segunda conferência: o número todo
#: depois do "R$", e não só o pedaço que a `_VALOR` alcança.
PADRAO_DO_VALOR_INTEIRO: Final = r"R\$\s*(\d(?:[\d.,]*\d)?)"

#: O que substitui, no texto final, o valor que nada na conversa sustenta. O
#: mesmo texto do plugin, para a tela desenhar os dois do mesmo jeito.
REDACAO: Final = "[valor retirado]"

#: Arredondamento não é invenção: a mesma tolerância do plugin.
TOLERANCIA: Final = Decimal("0.02")

_VALOR: Final = re.compile(PADRAO_DO_VALOR)
_VALOR_INTEIRO: Final = re.compile(PADRAO_DO_VALOR_INTEIRO)
_FALADO: Final = re.compile(PADRAO_FALADO, re.IGNORECASE)
_PROPORCAO: Final = re.compile(PADRAO_DA_PROPORCAO, re.IGNORECASE)

#: O resto de um valor que a `_VALOR` não alcançou, colado no sentinela: o "0,00"
#: de "R$ 1500,00", o ".5" de "R$ 12.5".
_RESTO_COLADO: Final = re.compile(re.escape(SENTINELA) + r"[\d.,]*\d")

#: Um número em pt-BR: 1.234,56 · 1500 · 4,5. Só ele pode ser sustentado.
_NUMERO_PT_BR: Final = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?")

#: O fim do rascunho que ainda pode crescer para um valor com cifrão:
#: "R", "R$", "R$ ", "R$ 7,", "R$ 1.2", "R$ 1.234,5".
_CAUDA_COM_CIFRAO: Final = re.compile(r"R(?:\$\s*[\d.,]*)?\Z")

#: O fim que ainda pode virar dinheiro falado: um número (com o "R$" antes, se
#: houver) seguido, talvez, do começo de "reais" ou "real": "4,5", "4,5 ", "4,5 rea".
_CAUDA_FALADA: Final = re.compile(
    r"(?:R\$\s*)?\d[\d.,]*\s*(?:r(?:e(?:a(?:is?|l)?)?)?)?\Z", re.IGNORECASE
)


def mascarar(texto: str) -> str:
    """Troca todo valor em reais do texto pelo sentinela, de uma vez.

    O cifrão primeiro: em "R$ 6 reais", o "R$ 6" vira sentinela e o " reais"
    que sobra não tem mais número para casar.
    """
    com_cifrao = _RESTO_COLADO.sub(SENTINELA, _VALOR.sub(SENTINELA, texto))
    return _FALADO.sub(SENTINELA, com_cifrao)


class MascaraDeValores:
    """O rascunho mascarado, entregue aos poucos, sem nunca mostrar um valor partido.

    `alimentar(pedaco)` devolve o trecho novo que já pode ir para a tela (às
    vezes vazio); `finalizar()` devolve o que ficou retido, mascarado. A soma
    de tudo o que saiu é o rascunho inteiro mascarado.

    O corte entre o que sai e o que fica retido só anda para a frente: o trecho
    retido é o sufixo mais longo que ainda pode ser o começo de um valor, e um
    trecho que já não podia deixa de poder com o que vem depois. Por isso cada
    trecho liberado é mascarado sozinho, e o que já saiu nunca muda.
    """

    def __init__(self) -> None:
        self._bruto = ""
        self._corte = 0
        self._saiu: list[str] = []

    @property
    def mascarado(self) -> str:
        """Tudo o que já foi entregue à tela."""
        return "".join(self._saiu)

    @property
    def retido(self) -> str:
        """O fim ainda não entregue: pode ser o começo de um valor."""
        return self._bruto[self._corte :]

    def alimentar(self, pedaco: str) -> str:
        """Acrescenta um pedaço do rascunho e devolve o que já pode ser mostrado."""
        self._bruto += pedaco
        return self._liberar(self._corte_seguro())

    def finalizar(self) -> str:
        """O fim do rascunho: não vem mais nada, então o retido sai, mascarado."""
        return self._liberar(len(self._bruto))

    def _corte_seguro(self) -> int:
        corte = len(self._bruto)
        for cauda in (_CAUDA_COM_CIFRAO, _CAUDA_FALADA):
            achado = cauda.search(self._bruto, self._corte)
            if achado is not None:
                corte = min(corte, achado.start())
        return corte

    def _liberar(self, corte: int) -> str:
        trecho = mascarar(self._bruto[self._corte : corte])
        self._corte = corte
        if trecho:
            self._saiu.append(trecho)
        return trecho


# --------------------------------------------------------------------------- #
# A segunda conferência do texto final                                         #
# --------------------------------------------------------------------------- #


def _decimal(bruto: str) -> Decimal | None:
    """O número em pt-BR como `Decimal`; `None` se não é número em pt-BR ("12.5")."""
    if not _NUMERO_PT_BR.fullmatch(bruto):
        return None
    try:
        return Decimal(bruto.replace(".", "").replace(",", "."))
    except InvalidOperation:  # pragma: no cover (a expressão só deixa passar número)
        return None


def _valores(padrao: re.Pattern[str], texto: str) -> list[Decimal]:
    return [v for v in (_decimal(b) for b in padrao.findall(texto)) if v is not None]


def valores_com_cifrao(texto: str) -> list[Decimal]:
    """Os valores "R$ …" do texto, lidos inteiros: "R$ 1500,00" é 1500."""
    return _valores(_VALOR_INTEIRO, texto)


def valores_falados(texto: str) -> list[Decimal]:
    """O dinheiro falado do texto: "6 reais", "1 real", "1.234,56 reais"."""
    return _valores(_FALADO, texto)


def valores_da_fala(texto: str) -> list[Decimal]:
    """O que ela disse em dinheiro, com ou sem cifrão: tudo isso tem procedência."""
    return valores_com_cifrao(texto) + valores_falados(texto)


def _sustentado(valor: Decimal | None, autorizados: frozenset[Decimal]) -> bool:
    return valor is not None and any(abs(valor - a) <= TOLERANCIA for a in autorizados)


def retirar_sem_procedencia(texto: str, autorizados: Iterable[Decimal]) -> tuple[str, int]:
    """Troca por `REDACAO` todo valor que nada na conversa sustenta; devolve o texto e quantos.

    Confere os valores com cifrão e o dinheiro escrito com a palavra, como o
    guard-rail; a proporção ("1 em cada 8 reais") não é quantia e fica.
    """
    conhecidos = frozenset(autorizados)
    retirados = 0

    def trocar(achado: re.Match[str]) -> str:
        nonlocal retirados
        if _sustentado(_decimal(achado.group(1)), conhecidos):
            return achado.group(0)
        if achado.re is _FALADO and _PROPORCAO.search(achado.string, 0, achado.start()):
            return achado.group(0)
        retirados += 1
        return REDACAO

    texto = _VALOR_INTEIRO.sub(trocar, texto)
    texto = _FALADO.sub(trocar, texto)
    return texto, retirados


__all__ = [
    "PADRAO_DA_PROPORCAO",
    "PADRAO_DO_VALOR",
    "PADRAO_DO_VALOR_INTEIRO",
    "PADRAO_FALADO",
    "PADRAO_FALADO_DO_PLUGIN",
    "REDACAO",
    "TOLERANCIA",
    "MascaraDeValores",
    "mascarar",
    "retirar_sem_procedencia",
    "valores_com_cifrao",
    "valores_da_fala",
    "valores_falados",
]
