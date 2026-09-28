"""Latência, erro e saturação, agregados para quem opera.

Trace responde "por que **esta** requisição demorou". Métrica responde "o sistema
está bem?". São perguntas diferentes e precisam de estruturas diferentes: guardar
todo trace para calcular p99 sai caro e chega tarde.

Três decisões que valem explicação:

**Percentil, não média.** Média de latência esconde a cauda, e é a cauda que o
usuário sente. Um p50 de 200 ms com p99 de 9 s é um sistema em que uma pessoa a
cada cem espera nove segundos, e a média diria 300 ms.

**Janela deslizante limitada.** Guardar toda amostra cresce sem limite num
processo que roda por semanas. A janela fixa troca precisão histórica por memória
previsível, que é o certo para um número que se olha em tempo real.

**Exposição em texto Prometheus, sem dependência.** O formato é texto simples, e
implementá-lo custa menos do que arrastar um cliente inteiro, ainda mais numa
aplicação que já expõe HTTP.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Final

#: Amostras por série. 2048 cobre horas de tráfego de conversa e cabe em poucos
#: megabytes mesmo com dezenas de ferramentas.
JANELA: Final = 2048


@dataclass(slots=True)
class Serie:
    """Uma série de durações, com os percentis que importam."""

    nome: str
    amostras: deque[float] = field(default_factory=lambda: deque(maxlen=JANELA))
    erros: int = 0
    total: int = 0

    def registrar(self, duracao_ms: float, *, erro: bool = False) -> None:
        self.amostras.append(duracao_ms)
        self.total += 1
        if erro:
            self.erros += 1

    def percentil(self, p: float) -> float:
        """Interpolação linear entre as amostras vizinhas.

        Sem interpolação, com poucas amostras o p99 salta entre dois valores e
        parece instável quando o sistema não está.
        """
        if not self.amostras:
            return 0.0
        ordenadas = sorted(self.amostras)
        if len(ordenadas) == 1:
            return ordenadas[0]
        posicao = (len(ordenadas) - 1) * p
        baixo, alto = math.floor(posicao), math.ceil(posicao)
        if baixo == alto:
            return ordenadas[int(posicao)]
        peso = posicao - baixo
        return ordenadas[baixo] * (1 - peso) + ordenadas[alto] * peso

    @property
    def p50(self) -> float:
        return self.percentil(0.50)

    @property
    def p95(self) -> float:
        return self.percentil(0.95)

    @property
    def p99(self) -> float:
        return self.percentil(0.99)

    @property
    def taxa_de_erro(self) -> float:
        return self.erros / self.total if self.total else 0.0

    def __str__(self) -> str:
        return (
            f"{self.nome}: {self.total} chamada(s), "
            f"p50 {self.p50:.0f}ms · p95 {self.p95:.0f}ms · p99 {self.p99:.0f}ms · "
            f"erro {self.taxa_de_erro:.1%}"
        )


class Registro:
    """O conjunto de séries do processo.

    Tem trava porque a API HTTP roda endpoints síncronos num threadpool: sem ela,
    dois handlers registrando ao mesmo tempo corrompem a contagem silenciosamente,
    que é o pior jeito de uma métrica estar errada.
    """

    def __init__(self) -> None:
        self._series: dict[str, Serie] = {}
        self._trava = threading.Lock()

    def registrar(self, nome: str, duracao_ms: float, *, erro: bool = False) -> None:
        with self._trava:
            self._series.setdefault(nome, Serie(nome)).registrar(duracao_ms, erro=erro)

    def serie(self, nome: str) -> Serie | None:
        with self._trava:
            return self._series.get(nome)

    def todas(self) -> tuple[Serie, ...]:
        with self._trava:
            return tuple(sorted(self._series.values(), key=lambda s: s.p95, reverse=True))

    def mais_lentas(self, n: int = 3) -> tuple[Serie, ...]:
        """As séries com pior p95: o começo de qualquer investigação de latência."""
        return self.todas()[:n]

    def limpar(self) -> None:
        """Zera todas as séries.

        Existe para teste. Um global de processo sem como zerar obriga cada teste
        a conviver com o que os anteriores deixaram, e foi exatamente assim que
        um teste de taxa de erro passou a medir 0,2 em vez de 1,0, porque outra
        requisição bem-sucedida já estava na mesma série.

        Em produção ninguém chama: métrica de processo acumula por design.
        """
        with self._trava:
            self._series.clear()

    def prometheus(self) -> str:
        """Exposição no formato de texto do Prometheus.

        Escrito à mão porque o formato é simples e um cliente inteiro seria mais
        dependência do que valor numa aplicação que já serve HTTP.
        """
        linhas: list[str] = [
            "# HELP sabor_ferramenta_duracao_ms Duração das chamadas ao motor",
            "# TYPE sabor_ferramenta_duracao_ms summary",
        ]
        for s in self.todas():
            rotulo = s.nome.replace('"', '\\"')
            serie = "sabor_ferramenta_duracao_ms"
            for q, valor in (("0.5", s.p50), ("0.95", s.p95), ("0.99", s.p99)):
                rotulos = f'ferramenta="{rotulo}",quantile="{q}"'
                linhas.append(f"{serie}{{{rotulos}}} {valor:.2f}")
            linhas.append(f'sabor_ferramenta_duracao_ms_count{{ferramenta="{rotulo}"}} {s.total}')

        linhas.extend(
            [
                "# HELP sabor_ferramenta_erros_total Chamadas que falharam",
                "# TYPE sabor_ferramenta_erros_total counter",
            ]
        )
        for s in self.todas():
            rotulo = s.nome.replace('"', '\\"')
            linhas.append(f'sabor_ferramenta_erros_total{{ferramenta="{rotulo}"}} {s.erros}')
        return "\n".join(linhas) + "\n"

    def resumo(self) -> str:
        if not self._series:
            return "nenhuma chamada registrada"
        return "\n".join(str(s) for s in self.todas())


#: Registro do processo. Global porque métrica é estado de processo, não de
#: requisição, e injetá-lo em toda função custaria mais do que compra.
REGISTRO: Final = Registro()


__all__ = ["JANELA", "REGISTRO", "Registro", "Serie"]
