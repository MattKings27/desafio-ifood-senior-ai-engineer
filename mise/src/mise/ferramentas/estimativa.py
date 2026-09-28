"""Preço preliminar: quanto cobrar, com o que se sabe hoje, antes da receita ser conferida.

A conta mora em `mise.estimativa`: o ingrediente da porção, a mão de obra, o
gás ou a energia e a embalagem, cada linha com a premissa e a fonte; o piso sem
prejuízo (custo de produção ÷ 0,90, arredondado para cima) e três preços com a
taxa de 10% aberta. É sempre preliminar: nada aqui grava decisão, e o preço que
vai para o cardápio continua exigindo a receita conferida, pelo
`cenarios_preco`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mise.serializacao import _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao

#: O que o agente faz com a estimativa, dito junto com os números.
ORIENTACAO: Final = (
    "Diga sempre que é um preço preliminar, sem compromisso, e que ele não vai para o "
    "cardápio: o preço final sai de cenarios_preco, depois da receita conferida. Mostre as "
    "premissas que ela pode mudar na tela (o valor da hora, o gás, a embalagem) e o que ainda "
    "falta confirmar. Não some nem refaça conta: use os valores daqui."
)


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """O preço preliminar de uma receita, com as premissas à vista."""

    @servidor.tool()
    @protegido
    async def estimar_preco_preliminar(
        receita_id: str | None = None, prato: str | None = None
    ) -> str:
        """Um preço preliminar para ela ter uma ideia, antes da conferência da receita.

        Informe `receita_id` (o id que `buscar_receita_na_web` e
        `avaliar_receita` devolvem) ou `prato`. Devolve as linhas do custo
        (ingredientes, mão de obra, gás ou energia, embalagem) com as premissas
        e as fontes, o piso sem prejuízo, o mínimo só com o ingrediente e três
        preços com a taxa e o lucro. Sempre diga que é preliminar; o preço final
        passa por `cenarios_preco`. Receita que ela não consegue fazer não tem
        estimativa: a recusa vem com o motivo. Preço e peso não se perguntam a
        ela: vêm com a fonte, ou a receita fica de fora, com o motivo.
        """
        from mise.estimativa import estimar, receita_da_estimativa  # noqa: PLC0415

        receita = receita_da_estimativa(sessao, receita_id, prato)
        dados = estimar(sessao, receita)
        return _resposta({**dados, "receita_id": dados["slug"], "orientacao": ORIENTACAO})


__all__ = ["ORIENTACAO", "registrar"]
