"""O cardápio: os pratos que ela aceitou, com o preço, o lucro e o histórico.

- `GET /api/cardapio` (`contratos/web/cardapio.json`): os pratos aceitos, cada
  um com o preço dela, o que chega depois da taxa, o custo e o lucro da porção
  refeitos com a despensa de agora (e a conta escrita); o resumo com a linha
  dos R$ 80,00; os pratos que ela não quer; e as decisões em frases dela. É
  também a rota do card `decisao` da conversa.
- `POST /api/cardapio/{prato}/desfazer`: volta o prato ao que era antes da
  última decisão; devolve o cardápio como ficou, com a frase (`texto`).
- `PUT /api/cardapio/{prato}/notas {texto}`: as notas dela sobre o prato, as
  mesmas da receita; texto vazio apaga.

`{prato}` é o nome do prato (sem ligar para caixa e acento) ou o id da receita.
As frases e as contas moram em `gateway.cardapio`.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Header
from mise.avaliacoes import TAMANHO_DAS_NOTAS
from pydantic import BaseModel, Field

from gateway.cardapio import cardapio as montar_cardapio
from gateway.cardapio import desfazer, gravar_notas
from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder

#: Tamanho máximo de uma chave de idempotência vinda da tela.
TAMANHO_DA_CHAVE: Final = 200

roteador = APIRouter(tags=["cardapio"])

ChaveDoCabecalho = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1, max_length=TAMANHO_DA_CHAVE),
]


class NotasBody(BaseModel):
    """As notas dela sobre um prato; texto vazio apaga."""

    texto: str = Field(default="", max_length=TAMANHO_DAS_NOTAS)


@roteador.get("/api/cardapio", response_model=RespostaPadrao)
def ler_cardapio(sessao: SessaoDaApp) -> RespostaPadrao:
    """Os pratos aceitos com a conta de agora, o resumo, os que ela não quer e as decisões."""
    return responder(lambda: montar_cardapio(sessao))


@roteador.post("/api/cardapio/{prato}/desfazer", response_model=RespostaPadrao)
def desfazer_decisao(
    prato: str, sessao: SessaoDaApp, idempotency_key: ChaveDoCabecalho = None
) -> RespostaPadrao:
    """Desfaz a última decisão do prato: o prato volta ao que era antes, e o registro continua."""
    return responder(lambda: desfazer(sessao, prato, chave=idempotency_key))


@roteador.put("/api/cardapio/{prato}/notas", response_model=RespostaPadrao)
def anotar(prato: str, corpo: NotasBody, sessao: SessaoDaApp) -> RespostaPadrao:
    """As notas dela sobre o prato (as mesmas da receita)."""
    return responder(lambda: gravar_notas(sessao, prato, corpo.texto))


__all__ = ["roteador"]
