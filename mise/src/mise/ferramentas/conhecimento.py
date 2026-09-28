"""A consulta à plataforma inteira: despensa, cozinha, receitas, cardápio, orçamento e cozinha.

`consultar_conhecimento` busca no corpus da plataforma (`mise.corpus`), que
junta o que cada tela mostra e a base de conhecimento de cozinha com fonte. A
busca é híbrida (por palavra e por significado), fundida por posição e com o
portão do "não sei": sem trecho que sustente a resposta, volta vazia e diz
isso. Devolver o "menos pior" com fonte seria pior do que não responder.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from mise.erros import ErroDeUso
from mise.serializacao import _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def consultar(
    sessao: Sessao, pergunta: str, tipos: list[str] | None = None, k: int = 6
) -> dict[str, Any]:
    """A resposta da consulta, na forma de `contratos/web/conhecimento.json`."""
    from retrieval.corpus import K_MAXIMO, TIPOS  # noqa: PLC0415

    from mise.corpus import corpus_da_sessao  # noqa: PLC0415

    if not pergunta.strip():
        raise ErroDeUso("informe a pergunta")
    if tipos is not None:
        desconhecidos = sorted(set(tipos) - set(TIPOS))
        if desconhecidos:
            raise ErroDeUso(
                "tipo de trecho desconhecido",
                recebido=", ".join(desconhecidos),
                validos=", ".join(TIPOS),
            )
    return corpus_da_sessao(sessao).consultar(pergunta, tipos, max(1, min(k, K_MAXIMO)))


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """A busca na plataforma inteira, com fonte e rota de cada trecho."""

    @servidor.tool()
    @protegido
    async def consultar_conhecimento(
        pergunta: str, tipos: list[str] | None = None, k: int = 6
    ) -> str:
        """Busca na plataforma inteira e na base de cozinha, com a fonte de cada trecho.

        Use para responder o que está em alguma tela (o que ela tem na despensa
        e quanto pagou, o que a cozinha dela tem, o que uma receita pede passo a
        passo, o que ela decidiu, o que sobrou dos complementos) e para
        conhecimento de cozinha (técnica, conservação, segurança, embalagem,
        preço), que só pode ser dito com fonte.

        `tipos` limita a busca a partes da plataforma: `despensa`, `cozinha`,
        `receita`, `avaliacao`, `cardapio`, `orcamento`, `conhecimento`. `k` é
        quantos trechos voltam, no máximo (padrão 6).

        Devolve `trechos` (cada um com `id`, `tipo`, `rota`, `fonte`, `texto` e
        `pontuacao`), `nada_relevante` e `texto`. Repasse só o que os trechos
        dizem e cite a fonte. Com `nada_relevante`, diga que não sabe e ofereça
        procurar na internet: não responda de memória. Conta nova (custo de
        receita, preço, soma) sai das ferramentas de conta; do trecho, só o
        valor que já está escrito nele.
        """
        return _resposta(await asyncio.to_thread(consultar, sessao, pergunta, tipos, k))


__all__ = ["consultar", "registrar"]
