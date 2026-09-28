"""Transporte A2A: cartão do agente e JSON-RPC.

A especificação A2A define o cartão em `/.well-known/agent-card.json` e o
transporte em JSON-RPC 2.0. O que está implementado aqui é o subconjunto que esta
colaboração precisa (`message/send` síncrono), e o cartão **declara isso**:
`streaming: false`, `pushNotifications: false`.

Anunciar capacidade que não se tem é o jeito mais rápido de quebrar o par em vez
do próprio: o cliente escolhe o caminho pelo cartão, e se o cartão mente, a falha
acontece do lado dele.
"""

from __future__ import annotations

import uuid
from decimal import InvalidOperation
from typing import Any, Final

from fastapi import FastAPI
from pydantic import BaseModel, Field

from auditor.cartao import NOME, cartao
from auditor.conferencia import conferir

#: Códigos de erro do JSON-RPC 2.0. Usar os padrões em vez de inventar é o que
#: permite um cliente genérico tratar a falha sem conhecer este servidor.
ERRO_REQUISICAO_INVALIDA: Final = -32600
ERRO_METODO_NAO_ENCONTRADO: Final = -32601
ERRO_PARAMETRO_INVALIDO: Final = -32602


class Requisicao(BaseModel):
    """Envelope JSON-RPC 2.0."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


def _erro(identificador: Any, codigo: int, mensagem: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identificador, "error": {"code": codigo, "message": mensagem}}


def _resultado(identificador: Any, dados: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identificador, "result": dados}


def _prato_dos_parametros(params: dict[str, Any]) -> dict[str, Any] | None:
    """Extrai o prato de uma mensagem A2A.

    A mensagem carrega `parts`, e a parte de dados vem em `data`. Aceitar também
    o prato direto em `params` é conveniência para quem chama sem montar o
    envelope inteiro, documentada e não acidental.
    """
    mensagem = params.get("message")
    if isinstance(mensagem, dict):
        for parte in mensagem.get("parts") or []:
            if isinstance(parte, dict):
                dados = parte.get("data")
                if isinstance(dados, dict):
                    return dict(dados)
    prato = params.get("prato")
    if isinstance(prato, dict):
        return dict(prato)
    return None


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Auditor de conta (A2A)",
        description=(
            "Par independente que recalcula CMV e preço. Não importa nada do "
            "motor de propósito: conferir com o mesmo código não é auditoria."
        ),
        version="1.0.0",
    )

    @app.get("/.well-known/agent-card.json")
    def cartao_do_agente() -> dict[str, Any]:
        """Onde a especificação A2A manda procurar."""
        return cartao()

    @app.post("/a2a")
    def jsonrpc(requisicao: Requisicao) -> dict[str, Any]:
        if requisicao.jsonrpc != "2.0":
            return _erro(requisicao.id, ERRO_REQUISICAO_INVALIDA, "só falo JSON-RPC 2.0")

        if requisicao.method != "message/send":
            return _erro(
                requisicao.id,
                ERRO_METODO_NAO_ENCONTRADO,
                f"método {requisicao.method!r} não implementado; veja o cartão do agente",
            )

        prato = _prato_dos_parametros(requisicao.params)
        if prato is None:
            return _erro(
                requisicao.id,
                ERRO_PARAMETRO_INVALIDO,
                "esperava uma parte de dados com o prato (linhas, cmv, preco, lucro)",
            )

        try:
            veredito = conferir(prato)
        except (InvalidOperation, ValueError, TypeError) as erro:
            return _erro(
                requisicao.id, ERRO_PARAMETRO_INVALIDO, f"número ilegível no prato: {erro}"
            )

        return _resultado(
            requisicao.id,
            {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "role": "agent",
                "parts": [
                    {"kind": "text", "text": str(veredito)},
                    {
                        "kind": "data",
                        "data": {
                            "confere": veredito.confere,
                            "auditor": NOME,
                            "divergencias": [
                                {
                                    "campo": d.campo,
                                    "apresentado": str(d.apresentado),
                                    "conferido": str(d.conferido),
                                    "diferenca": str(d.diferenca),
                                }
                                for d in veredito.divergencias
                            ],
                            "observacao": veredito.observacao,
                            "da_prejuizo": veredito.da_prejuizo,
                            "aviso": veredito.aviso,
                        },
                    },
                ],
            },
        )

    return app


def main() -> None:
    """Sobe o auditor. Processo separado do motor, de propósito."""
    import os  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        criar_app(),
        host=os.environ.get("AUDITOR_HOST", "127.0.0.1"),
        port=int(os.environ.get("AUDITOR_PORT", "8899")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()


__all__ = ["Requisicao", "criar_app", "main"]
