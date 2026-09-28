"""O Início: o próximo passo, as perguntas, os números da consultoria e o que está parado.

Serve `GET /api/visao-geral`, com a forma de `contratos/web/visao-geral.json`:
os indicadores clicáveis (cada um com a rota que abre), o próximo passo dito
para ela, as perguntas da despensa e as da cozinha que seguram receitas, todos
os itens com dinheiro parado, as receitas recomendadas com a forma dos cards da
grade e a prévia do cardápio. É também a rota do card `despensa_resumo` da
conversa. As contas e as frases moram em `gateway.visao_geral`.
"""

from __future__ import annotations

from fastapi import APIRouter

from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder
from gateway.visao_geral import visao_geral

roteador = APIRouter(tags=["visao-geral"])


@roteador.get("/api/visao-geral", response_model=RespostaPadrao)
def ler_visao_geral(sessao: SessaoDaApp) -> RespostaPadrao:
    """A tela inicial numa leitura só."""
    return responder(lambda: visao_geral(sessao))


__all__ = ["roteador"]
