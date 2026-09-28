"""O histórico: tudo o que aconteceu, dito em frases, sem nome de ferramenta.

Serve `GET /api/atividades` (`cursor`, `limite`, `q`, `categoria`, `quem`,
`dia`), com a forma de `contratos/web/atividades.json`: as decisões do
cardápio, as mudanças da despensa, as compras, as respostas sobre a cozinha, o
gosto e as estrelas de cada receita, os preços do que falta comprar, as
receitas que entraram na grade e o que o agente consultou, agrupados por
dia, do mais novo para o mais antigo. As frases e os filtros moram em
`gateway.atividades`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from gateway.atividades import LIMITE_MAXIMO, LIMITE_PADRAO, Filtros, pagina
from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder

roteador = APIRouter(tags=["atividades"])


@roteador.get("/api/atividades", response_model=RespostaPadrao)
def listar_atividades(
    sessao: SessaoDaApp,
    *,
    cursor: Annotated[str | None, Query(max_length=120)] = None,
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_PADRAO,
    q: Annotated[str | None, Query(max_length=80)] = None,
    categoria: Annotated[str | None, Query(max_length=20)] = None,
    quem: Annotated[str | None, Query(max_length=20)] = None,
    dia: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> RespostaPadrao:
    """Uma página do histórico, agrupada por dia, com os filtros que ela escolheu."""
    return responder(
        lambda: pagina(
            sessao,
            Filtros(q=q, categoria=categoria, quem=quem, dia=dia),
            cursor=cursor,
            limite=limite,
        )
    )


__all__ = ["roteador"]
