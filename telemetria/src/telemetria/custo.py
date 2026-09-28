"""Custo de uso do modelo, medido a partir do uso real.

A pergunta do 80/20 ("onde está o custo?") só tem resposta com medição. Numa
agente com prompt longo e muitas ferramentas, a maior parte dos tokens nem é
entrada nem saída: é **cache**. A primeira rodada real da Sabor da Maria leu
230 mil tokens do cache e gravou 55 mil, contra 4,5 mil de saída. Uma conta
que só olha entrada e saída erra o custo por ordem de grandeza.

Os preços ficam versionados aqui, com a fonte e a data da tabela, para que
qualquer mudança apareça num diff.

Fonte: referência de preços da API da Anthropic, tabela de 24/06/2026, na skill
`claude-api` do Claude Code. Leitura de cache a 0,1× da entrada, salvo onde a
tabela dá outro valor (Opus 5.5 e Fable 5.1); gravação a 1,25× com vida de
5 minutos e 2× com vida de 1 hora.

A versão anterior deste módulo trazia o Opus 5 a US$ 15 / US$ 75, três vezes o
preço real, atribuído a uma "tabela pública" que não dizia isso, e nenhum preço
de cache. Número de custo com procedência falsa é o mesmo defeito que o projeto
inteiro existe para não cometer com o preço da Dona Maria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

FONTE_DOS_PRECOS: Final = "referência de preços da API da Anthropic, tabela de 24/06/2026"

UM_MILHAO: Final = Decimal("1000000")

#: Multiplicadores da gravação de cache sobre o preço de entrada, por vida útil.
GRAVACAO_DE_CACHE: Final[dict[str, Decimal]] = {"5m": Decimal("1.25"), "1h": Decimal("2")}


@dataclass(frozen=True, slots=True)
class Preco:
    """Dólares por milhão de tokens."""

    entrada: Decimal
    saida: Decimal
    leitura_de_cache: Decimal

    def gravacao_de_cache(self, vida: str = "5m") -> Decimal:
        if vida not in GRAVACAO_DE_CACHE:
            raise ValueError(f"vida de cache desconhecida: {vida!r}; use 5m ou 1h")
        return self.entrada * GRAVACAO_DE_CACHE[vida]


def _preco(entrada: str, saida: str, leitura: str | None = None) -> Preco:
    base = Decimal(entrada)
    return Preco(base, Decimal(saida), Decimal(leitura) if leitura else base / 10)


PRECOS: Final[dict[str, Preco]] = {
    "claude-opus-5-5": _preco("4", "20", "0.20"),
    "claude-opus-5": _preco("5", "25"),
    "claude-sonnet-5": _preco("2", "10"),
    "claude-haiku-4-5": _preco("1", "5"),
    "claude-fable-5-1": _preco("10", "50", "0.25"),
}


class ModeloDesconhecido(KeyError):
    """Preço não cadastrado. Estimar custo com preço chutado é pior que não estimar."""


def preco_de(modelo: str) -> Preco:
    """O preço do modelo, pelo nome mais específico que casar.

    "claude-opus-5-5" tem que achar o Opus 5.5, não o Opus 5: por isso o nome
    mais longo é tentado primeiro. Prefixo de provedor ("anthropic/") é ignorado.
    """
    nome = modelo.rsplit("/", 1)[-1]
    for conhecido in sorted(PRECOS, key=len, reverse=True):
        if nome == conhecido or nome.startswith(conhecido + "-"):
            return PRECOS[conhecido]
    raise ModeloDesconhecido(
        f"sem preço cadastrado para {modelo!r}; conhecidos: {', '.join(sorted(PRECOS))}"
    )


@dataclass(frozen=True, slots=True)
class UsoDeModelo:
    """O que uma chamada ou um turno consumiu, como o provedor informa."""

    modelo: str
    entrada: int = 0
    saida: int = 0
    leitura_de_cache: int = 0
    gravacao_de_cache: int = 0
    vida_do_cache: str = "5m"

    def __post_init__(self) -> None:
        if min(self.entrada, self.saida, self.leitura_de_cache, self.gravacao_de_cache) < 0:
            raise ValueError("contagem de token não pode ser negativa")

    @property
    def tokens(self) -> int:
        return self.entrada + self.saida + self.leitura_de_cache + self.gravacao_de_cache

    def partes_usd(self) -> dict[str, Decimal]:
        """O custo em quatro linhas, para saber qual pesa."""
        p = preco_de(self.modelo)
        return {
            "entrada": Decimal(self.entrada) * p.entrada / UM_MILHAO,
            "saida": Decimal(self.saida) * p.saida / UM_MILHAO,
            "leitura_de_cache": Decimal(self.leitura_de_cache) * p.leitura_de_cache / UM_MILHAO,
            "gravacao_de_cache": (
                Decimal(self.gravacao_de_cache)
                * p.gravacao_de_cache(self.vida_do_cache)
                / UM_MILHAO
            ),
        }

    @property
    def custo_usd(self) -> Decimal:
        return sum(self.partes_usd().values(), Decimal(0))


@dataclass(slots=True)
class Orcamento:
    """Uso acumulado, para responder quais chamadas concentram o custo."""

    usos: list[UsoDeModelo] = field(default_factory=list)

    def registrar(self, uso: UsoDeModelo) -> None:
        self.usos.append(uso)

    @property
    def total_usd(self) -> Decimal:
        return sum((u.custo_usd for u in self.usos), Decimal(0))

    def partes_usd(self) -> dict[str, Decimal]:
        """Entrada, saída e cache somados: onde o dinheiro vai de fato."""
        total: dict[str, Decimal] = {}
        for uso in self.usos:
            for parte, valor in uso.partes_usd().items():
                total[parte] = total.get(parte, Decimal(0)) + valor
        return total

    def por_modelo(self) -> dict[str, Decimal]:
        agrupado: dict[str, Decimal] = {}
        for uso in self.usos:
            agrupado[uso.modelo] = agrupado.get(uso.modelo, Decimal(0)) + uso.custo_usd
        return dict(sorted(agrupado.items(), key=lambda p: p[1], reverse=True))

    def concentracao(self, fatia: float = 0.8) -> list[UsoDeModelo]:
        """As chamadas que somam `fatia` do custo, da mais cara para a menos."""
        if not self.usos:
            return []
        alvo = self.total_usd * Decimal(str(fatia))
        acumulado = Decimal(0)
        escolhidas: list[UsoDeModelo] = []
        for uso in sorted(self.usos, key=lambda u: u.custo_usd, reverse=True):
            escolhidas.append(uso)
            acumulado += uso.custo_usd
            if acumulado >= alvo:
                break
        return escolhidas

    def resumo(self) -> str:
        if not self.usos:
            return "nenhuma chamada de modelo registrada"
        partes = self.partes_usd()
        maior = max(partes, key=lambda k: partes[k])
        return (
            f"{len(self.usos)} chamada(s), US$ {self.total_usd:.4f}; "
            f"a maior parte é {maior.replace('_', ' ')} (US$ {partes[maior]:.4f}); "
            f"{len(self.concentracao())} chamada(s) concentram 80% do custo"
        )


__all__ = [
    "FONTE_DOS_PRECOS",
    "GRAVACAO_DE_CACHE",
    "PRECOS",
    "ModeloDesconhecido",
    "Orcamento",
    "Preco",
    "UsoDeModelo",
    "preco_de",
]
