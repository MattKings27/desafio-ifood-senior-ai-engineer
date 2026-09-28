"""Os roteadores da API, um por área da tela.

Cada área nova (despensa, receitas, cozinha, preço, cardápio, conversa,
imagens, os dados dela) mora num módulo deste pacote, com um `APIRouter`, e
entra aqui com uma linha em `ROTEADORES`. Assim quem acrescenta rotas mexe no módulo da área e numa
linha daqui, e não na função de oitocentas linhas de `http.py`.

`gateway.http.criar_app` inclui os roteadores ANTES das rotas antigas de
`http.py`: numa rota repetida, vale a do roteador. A versão nova de uma rota
(`GET /api/cardapio` ampliado, por exemplo) substitui a antiga assim que entra;
a antiga sai de `http.py` no mesmo PR, para não ficar código que ninguém chama.

O que as rotas compartilham (o envelope, o dinheiro, a sessão e a categoria
`ausente`, que sai com 404) está em `gateway.rotas._comum`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from gateway.rotas import (
    atividades,
    cardapio,
    conversa,
    dados,
    despensa,
    estimativa,
    imagens,
    perfil,
    receitas,
    visao_geral,
)

if TYPE_CHECKING:
    from fastapi import APIRouter

#: Os roteadores incluídos por `criar_app`, em ordem. Rota nova entra no
#: módulo da área dela, sem mexer neste registro.
ROTEADORES: Final[tuple[APIRouter, ...]] = (
    despensa.roteador,
    perfil.roteador,
    conversa.roteador,
    receitas.roteador,
    imagens.roteador,
    estimativa.roteador,
    visao_geral.roteador,
    cardapio.roteador,
    atividades.roteador,
    dados.roteador,
)

__all__ = ["ROTEADORES"]
