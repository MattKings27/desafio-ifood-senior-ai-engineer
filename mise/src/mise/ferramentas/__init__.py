"""As ferramentas do motor, um módulo por área.

Cada módulo expõe `registrar(servidor, sessao)`, que declara as ferramentas da
sua área no `MCPServer`. `mise.mcp_server.construir_servidor` percorre
`REGISTRADORES` na ordem abaixo.

Uma área por arquivo para que quem acrescenta uma ferramenta mexa no arquivo da
área e numa linha daqui, e não num servidor de mil e quinhentas linhas que todo
mundo edita ao mesmo tempo. Ferramenta nova também entra em `politica.ESCOPOS`
(allowlist do gateway), no conjunto fixado de `test_ferramentas_registradas`,
nas instruções do agente e nas frases e cartões do gateway.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from mise.ferramentas import (
    avaliacoes,
    cardapio,
    conhecimento,
    descoberta,
    despensa,
    estimativa,
    orcamento,
    perfil,
    preco,
    receitas,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao

#: Declara as ferramentas de uma área no servidor, sobre a sessão em curso.
Registrador = Callable[["MCPServer", "Sessao"], None]

REGISTRADORES: Final[tuple[Registrador, ...]] = (
    despensa.registrar,
    perfil.registrar,
    receitas.registrar,
    descoberta.registrar,
    avaliacoes.registrar,
    preco.registrar,
    estimativa.registrar,
    conhecimento.registrar,
    orcamento.registrar,
    cardapio.registrar,
)

__all__ = ["REGISTRADORES", "Registrador"]
