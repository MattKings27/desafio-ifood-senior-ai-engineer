"""A pauta da descoberta de receitas: o que procurar na internet, e o que já foi lido.

A descoberta roda com um pedido fixo: o agente chama `pauta_de_descoberta`,
pesquisa na internet a partir dela e traz cada página por
`buscar_receita_na_web`. A pauta diz o que procurar primeiro (os pratos
clássicos que a despensa dela já cobre, depois o dinheiro parado sem receita e
os maiores gastos), as buscas prontas e os endereços que já estão no catálogo,
para nenhuma página ser buscada duas vezes. A conta é toda do motor
(`mise.descoberta`), sem modelo no meio.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from mise.serializacao import _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """A pauta que orienta a descoberta de receitas."""

    @servidor.tool()
    @protegido
    async def pauta_de_descoberta() -> str:
        """O que procurar na internet para achar receitas com a despensa dela.

        Devolve, em `buscas`, as pesquisas prontas na ordem: primeiro os pratos
        clássicos cuja base inteira está na despensa dela (`pratos_para_procurar`,
        "receita de feijão tropeiro"), que costumam sair sem compra; depois os
        itens com o motivo (`itens_para_procurar`, "receita com alcaparras": o
        dinheiro parado que nenhuma receita usa, e depois os maiores gastos).
        Traz também os endereços que já estão no catálogo (`urls_conhecidas`,
        que não precisam ser buscados de novo), os sites brasileiros de receita
        mais populares que o servidor lê (`sites_populares`, os preferidos), os
        sites de onde o servidor já leu receita e os limites: no máximo 8
        pesquisas e 20 páginas por descoberta, até 3 de cada pesquisa.

        Não grava nada. Cada página encontrada entra no catálogo só por
        `buscar_receita_na_web`.
        """
        from mise.descoberta import montar_pauta  # noqa: PLC0415

        return _resposta(await asyncio.to_thread(montar_pauta, sessao))


__all__ = ["registrar"]
