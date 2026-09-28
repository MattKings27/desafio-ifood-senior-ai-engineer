"""Avaliação da receita: o gosto, as estrelas e as notas dela sobre um prato.

É a mesma avaliação da página da receita, feita pela conversa: se ela gosta
de fazer, de uma a cinco estrelas em sabor, facilidade, tempo, entrega e
apelo de venda, e as anotações dela. A pontuação sai daqui, em Decimal e com
a conta escrita, e nunca do modelo (`mise.avaliacoes`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mise.serializacao import _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """A avaliação que ela faz de uma receita, pela conversa."""

    @servidor.tool()
    @protegido
    async def registrar_avaliacao_da_receita(
        receita_id: str,
        gosta: bool | None = None,
        estrelas: dict[str, int | None] | None = None,
        notas: str | None = None,
    ) -> str:
        """Guarda o que ela achou de uma receita: se gosta, as estrelas e as notas.

        `receita_id` é o id que `buscar_receita_na_web` e `avaliar_receita`
        devolvem. `estrelas` vai de 1 a 5 em `sabor`, `facilidade`, `tempo`,
        `entrega` e `apelo`; o que ela não disse fica de fora, e `null` apaga a
        estrela que ela tinha dado. `gosta` também é a checagem de gosto do
        portão (o mesmo que `registrar_gosto`); sem `gosta`, o gosto fica como
        estava. `notas` troca as anotações dela pelo texto novo.

        Devolve a avaliação como ficou, a pontuação de 0 a 100 com a conta
        (`avaliacao.pontuacao.derivacao`) e a posição no ranking dela. Diga a
        pontuação com a conta, nunca um número seu.
        """
        resposta = sessao.registrar_avaliacao(
            receita_id,
            gosta=gosta,
            muda_o_gosto=gosta is not None,
            estrelas=estrelas,
            notas=notas,
        )
        return _resposta({"registrado": True, "receita_id": resposta["slug"], **resposta})


__all__ = ["registrar"]
