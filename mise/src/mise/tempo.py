"""O tempo que uma receita prende a senhora e o fogão, por cozinhada.

A conferência compara o tempo ATIVO dos passos (fogo, forno ou aparelho
ligado, e as mãos dela ocupadas) com o tempo por cozinhada que ela informou; as
esperas passivas (descanso, geladeira, congelador, de um dia para o outro) não
contam. O preço preliminar usa o mesmo número para a mão de obra.

A conta pelos passos mora em `mise.passos.minutos_ativos(receita)`, que devolve
um `MinutosAtivos`:

- com tempo nos passos, `origem` é `passos`, `ativos` é a soma dos tempos
  ativos e `passivos` a das esperas, e `derivacao` mostra a conta ("pelos
  passos, 40 + 50 = 90 minutos no fogo");
- sem tempo nos passos, vale o tempo que a página declara
  (`MinutosAtivos.pelo_tempo_declarado`), marcado como premissa;
- sem tempo nenhum, `MinutosAtivos.desconhecido()`: a conferência pergunta, e
  a estimativa deixa a mão de obra de fora, sinalizada.

Este módulo tem só a forma do resultado e os dois casos que não dependem dos
passos, para a estimativa e o preço preliminar não dependerem de `mise.passos`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OrigemDoTempo(StrEnum):
    """De onde saiu o tempo ativo."""

    PASSOS = "passos"
    """A soma dos tempos ativos dos passos da receita."""
    TEMPO_DECLARADO = "tempo_declarado"
    """O tempo que a página declara, quando os passos não dizem."""
    DESCONHECIDO = "desconhecido"
    """Nem os passos nem a página dizem."""


@dataclass(frozen=True, slots=True)
class MinutosAtivos:
    """Quanto tempo a receita prende a senhora e o fogão, por cozinhada, e de onde veio."""

    #: Minutos de fogo e de trabalho; `None` quando não dá para saber.
    ativos: int | None
    #: Minutos de espera que não prendem ninguém: descanso, geladeira, congelador.
    passivos: int = 0
    origem: OrigemDoTempo = OrigemDoTempo.DESCONHECIDO
    #: A conta dita para ela, que vai para o motivo da conferência e para a mão de obra.
    derivacao: str = ""

    def __post_init__(self) -> None:
        if (self.ativos is not None and self.ativos < 0) or self.passivos < 0:
            raise ValueError("tempo não pode ser negativo")
        if (self.ativos is None) != (self.origem is OrigemDoTempo.DESCONHECIDO):
            raise ValueError("só o tempo desconhecido vem sem minutos")

    @property
    def conhecido(self) -> bool:
        return self.ativos is not None

    @classmethod
    def desconhecido(cls) -> MinutosAtivos:
        """Nem os passos nem a página dizem quanto tempo a receita leva."""
        return cls(None, 0, OrigemDoTempo.DESCONHECIDO, "a receita não diz quanto tempo leva")

    @classmethod
    def pelo_tempo_declarado(cls, minutos: int | None) -> MinutosAtivos:
        """Sem tempo nos passos, vale o tempo que a página declara, marcado como premissa."""
        if minutos is None or minutos <= 0:
            return cls.desconhecido()
        return cls(
            minutos,
            0,
            OrigemDoTempo.TEMPO_DECLARADO,
            f"os passos não dizem o tempo; a receita declara {minutos} min, "
            "e a conta usa esse número",
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "ativos": self.ativos,
            "passivos": self.passivos,
            "origem": self.origem.value,
            "derivacao": self.derivacao,
        }


__all__ = ["MinutosAtivos", "OrigemDoTempo"]
