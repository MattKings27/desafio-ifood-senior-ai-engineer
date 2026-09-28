"""O preço preliminar de uma receita e as premissas que ela pode editar.

- `GET /api/receitas/{slug}/estimativa`: a forma de
  `contratos/web/estimativa.json`, sempre rotulada "preliminar", e a rota do
  card `preco_preliminar`. A receita que a conferência bloqueia recusa, com o
  motivo (categoria `regra`); a que não existe dá 404 (`ausente`).
- `GET /api/parametros/{nome}` e `PUT /api/parametros/{nome}`: uma premissa, na
  forma de `estimativa.json#premissas[]`. O `PUT` recebe `{valor}`: um número
  grava o valor dela; `null` apaga, e a premissa volta ao padrão com fonte (ou
  a faltar, quando não há padrão). Pedido e resposta em
  `contratos/web/parametro-escrita.json`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from mise import parametros
from mise.estimativa import estimar, receita_da_estimativa
from pydantic import BaseModel, StrictFloat, StrictInt

from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder

roteador = APIRouter()


class ValorDoParametro(BaseModel):
    """O valor que ela informou: número, ou `null` para voltar ao padrão.

    Tipos estritos: `"1,20"` não é número, e `true` também não.
    """

    valor: StrictInt | StrictFloat | None = None


@roteador.get("/api/receitas/{slug}/estimativa", response_model=RespostaPadrao)
def estimativa_da_receita(slug: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """O preço preliminar da receita, com as linhas, as premissas e os três preços."""

    def montar() -> dict[str, Any]:
        receita = receita_da_estimativa(sessao, slug, None)
        return estimar(sessao, receita, slug=slug)

    return responder(montar)


@roteador.get("/api/parametros/{nome}", response_model=RespostaPadrao)
def ler_parametro(nome: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """Uma premissa do preço preliminar, com a origem e a fonte."""

    def montar() -> dict[str, Any]:
        parametros.parametro(nome)
        return parametros.ler(sessao.dossie)[nome].para_json(sessao.dossie.agora())

    return responder(montar)


@roteador.put("/api/parametros/{nome}", response_model=RespostaPadrao)
def mudar_parametro(nome: str, corpo: ValorDoParametro, sessao: SessaoDaApp) -> RespostaPadrao:
    """Grava o valor que ela informou, ou volta ao padrão com `null`."""

    def montar() -> dict[str, Any]:
        premissa = parametros.definir(sessao.dossie, nome, corpo.valor, sessao.canal.value)
        return premissa.para_json(sessao.dossie.agora())

    return responder(montar)


__all__ = ["roteador"]
