"""Um turno do agente, lido do `--format stream-json` do Hermes.

O Hermes emite uma linha JSON por evento: `system/init` com modelo e sessão,
`tool_use` e `tool_result` pareados por `tool_call_id`, `text` com a prosa, e um
`result` final com uso de tokens e duração. Este módulo transforma essas linhas
num `Turno` imutável, que é o que as asserções dos cenários leem.

Sem `result` não há turno: significa que o processo morreu no meio, e tratar
isso como "o agente respondeu vazio" esconderia exatamente a falha que importa.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

#: Prefixo que o Hermes põe nas ferramentas vindas do servidor MCP `mise`.
PREFIXO_DO_MOTOR = "mcp__mise__"


class ProtocoloInvalido(ValueError):
    """A saída do Hermes não fecha um turno."""


@dataclass(frozen=True)
class Chamada:
    """Uma chamada de ferramenta com o que entrou e o que voltou."""

    ferramenta: str
    entrada: dict[str, Any]
    saida: str = ""
    erro: bool = False
    duracao_ms: int | None = None
    #: `tool_call_id` do provedor; é por ele que a saída é achada no `state.db`.
    ident: str = ""

    @property
    def do_motor(self) -> str | None:
        """O nome curto quando a ferramenta é do motor; `None` quando não é."""
        if self.ferramenta.startswith(PREFIXO_DO_MOTOR):
            return self.ferramenta.removeprefix(PREFIXO_DO_MOTOR)
        return None

    def e(self, nome: str) -> bool:
        """Casa pelo nome completo (`web_search`) ou curto do motor (`calcular_cmv`).

        `registrar_gosto|registrar_avaliacao_da_receita` aceita qualquer uma: para
        quando duas ferramentas gravam a mesma coisa no mesmo lugar.
        """
        return any(n in (self.ferramenta, self.do_motor) for n in nome.split("|"))


@dataclass(frozen=True)
class Uso:
    """Tokens do turno, com cache separado: é ele que decide o custo real."""

    entrada: int = 0
    saida: int = 0
    cache_leitura: int = 0
    cache_escrita: int = 0


@dataclass(frozen=True)
class Turno:
    """O que ela disse, o que o agente fez e o que respondeu."""

    pergunta: str
    resposta: str
    sessao: str
    modelo: str
    codigo_saida: int
    duracao_ms: int
    uso: Uso
    chamadas: tuple[Chamada, ...] = field(default_factory=tuple)
    linhas_ignoradas: int = 0

    @classmethod
    def de_json(cls, dados: dict[str, Any]) -> Turno:
        """O turno de volta de uma transcrição salva, para julgar de novo sem rodar."""
        return cls(
            pergunta=dados["pergunta"],
            resposta=dados["resposta"],
            sessao=dados["sessao"],
            modelo=dados["modelo"],
            codigo_saida=dados["codigo_saida"],
            duracao_ms=dados["duracao_ms"],
            uso=Uso(**dados["uso"]),
            chamadas=tuple(
                Chamada(
                    ferramenta=c["ferramenta"],
                    entrada=c["entrada"],
                    saida=c["saida"],
                    erro=c["erro"],
                    duracao_ms=c["duracao_ms"],
                    ident=c.get("id", ""),
                )
                for c in dados["chamadas"]
            ),
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "pergunta": self.pergunta,
            "resposta": self.resposta,
            "sessao": self.sessao,
            "modelo": self.modelo,
            "codigo_saida": self.codigo_saida,
            "duracao_ms": self.duracao_ms,
            "uso": vars(self.uso),
            "chamadas": [
                {
                    "id": c.ident,
                    "ferramenta": c.ferramenta,
                    "entrada": c.entrada,
                    "saida": c.saida,
                    "erro": c.erro,
                    "duracao_ms": c.duracao_ms,
                }
                for c in self.chamadas
            ],
        }


def _inteiro(valor: Any) -> int:
    return int(valor) if isinstance(valor, int | float) else 0


def _evento(linha: str) -> dict[str, Any] | None:
    """Um evento do protocolo, ou `None` para o que escapou do `-Q` (aviso, banner)."""
    try:
        evento = json.loads(linha)
    except json.JSONDecodeError:
        return None
    return evento if isinstance(evento, dict) else None


def ler_turno(pergunta: str, linhas: Iterable[str]) -> Turno:
    """Monta o turno a partir das linhas do stdout, na ordem em que vieram."""
    modelo = sessao = ""
    textos: list[str] = []
    ordem: list[str] = []
    usos: dict[str, dict[str, Any]] = {}
    resultados: dict[str, dict[str, Any]] = {}
    final: dict[str, Any] | None = None
    ignoradas = 0

    for linha in linhas:
        if not linha.strip():
            continue
        evento = _evento(linha)
        if evento is None:
            ignoradas += 1
            continue

        tipo = evento.get("type")
        if tipo == "system" and evento.get("subtype") == "init":
            modelo = str(evento.get("model") or "")
            sessao = str(evento.get("session_id") or "")
        elif tipo == "text":
            textos.append(str(evento.get("text") or ""))
        elif tipo == "tool_use":
            ident = str(evento.get("tool_call_id") or f"sem-id:{len(ordem)}")
            ordem.append(ident)
            usos[ident] = evento
        elif tipo == "tool_result":
            resultados[str(evento.get("tool_call_id") or "")] = evento
        elif tipo == "result":
            final = evento
        else:
            ignoradas += 1

    if final is None:
        raise ProtocoloInvalido(
            f"a saída do Hermes terminou sem o evento 'result' ({len(ordem)} chamadas lidas)"
        )

    chamadas = []
    for ident in ordem:
        uso, res = usos[ident], resultados.get(ident, {})
        entrada = uso.get("input")
        chamadas.append(
            Chamada(
                ferramenta=str(uso.get("name") or ""),
                entrada=entrada if isinstance(entrada, dict) else {},
                saida=str(res.get("output") or ""),
                erro=bool(res.get("is_error")),
                duracao_ms=_inteiro(res["duration_ms"]) if "duration_ms" in res else None,
                ident="" if ident.startswith("sem-id:") else ident,
            )
        )

    tokens = final.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    return Turno(
        pergunta=pergunta,
        resposta=str(final.get("text") or "".join(textos)).strip(),
        sessao=str(final.get("session_id") or sessao),
        modelo=modelo,
        codigo_saida=_inteiro(final.get("exit_code")),
        duracao_ms=_inteiro(final.get("duration_ms")),
        uso=Uso(
            entrada=_inteiro(tokens.get("input")),
            saida=_inteiro(tokens.get("output")),
            cache_leitura=_inteiro(tokens.get("cache_read")),
            cache_escrita=_inteiro(tokens.get("cache_write")),
        ),
        chamadas=tuple(chamadas),
        linhas_ignoradas=ignoradas,
    )
