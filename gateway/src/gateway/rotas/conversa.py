"""As rotas da conversa com o agente (contratos/web/LEIA.md, "Conversa").

    GET    /api/conversas                               lista e a atual
    POST   /api/conversas                               conversa nova (vira a atual)
    GET    /api/conversas/{id}                          mensagens e o turno em andamento
    PATCH  /api/conversas/{id}                          título, ou marcar como atual
    DELETE /api/conversas/{id}                          apaga, com as mensagens
    POST   /api/conversas/{id}/turnos                   202 {turno_id}; 409 {turno_id}
    GET    /api/conversas/{id}/turnos/{t}               estado do turno
    GET    /api/conversas/{id}/turnos/{t}/eventos       SSE, com retomada
    POST   /api/conversas/{id}/turnos/{t}/parar         pede para parar
    GET    /api/chat/estado                             o agente atende agora?

O envelope é o de sempre (`{ok, dados, erro, categoria, pergunta}`); os status
próprios são 202 (turno aceito), 404 (`ausente`), 409 (`ocupado`, com o
`turno_id` que está rodando), 422 (`uso`) e 429 (`regra`, com `Retry-After`).

O SSE não usa o campo `event:`: cada evento é `id: <seq>` e `data: {JSON}`, com
o `tipo` dentro. Quem reconecta manda `Last-Event-ID` (o `EventSource` faz isso
sozinho) ou `?desde=`. Quando não há mais nada a mandar, a resposta é 204, que
faz o `EventSource` parar de reconectar.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gateway.conversa import ErroDaConversa, Pedido, ServicoDeConversa
from gateway.rotas._comum import RespostaPadrao

#: Os cabeçalhos do SSE: sem cache e sem compressão no caminho (o proxy do Next
#: comprime sem `no-transform`), e sem buffer no nginx.
CABECALHOS_DO_SSE: Final = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}

#: O maior pedaço de uma ação de card, em JSON: botão não carrega texto longo.
TAMANHO_DA_ACAO: Final = 2000

roteador = APIRouter(tags=["conversa"])


def servico_da(requisicao: Request) -> ServicoDeConversa:
    servico: ServicoDeConversa = requisicao.app.state.conversa
    return servico


Servico = Annotated[ServicoDeConversa, Depends(servico_da)]


# --------------------------------------------------------------------------- #
# Corpos                                                                       #
# --------------------------------------------------------------------------- #


class NovaConversaBody(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)


class AlterarConversaBody(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)
    atual: bool | None = None


class ContextoBody(BaseModel):
    """O que ela está vendo na tela. Dado não confiável: o backend confere o id."""

    tela: str | None = Field(default=None, max_length=40)
    tipo: str = Field(min_length=1, max_length=40)
    id: str = Field(default="", max_length=200)
    rotulo: str | None = Field(default=None, max_length=200)


class AcaoBody(BaseModel):
    """A ação de um botão de card: `responder`, `decidir` ou `avaliar`, com os campos dela."""

    model_config = ConfigDict(extra="allow")

    tipo: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _pequena(self) -> AcaoBody:
        if len(json.dumps(self.model_dump(), default=str)) > TAMANHO_DA_ACAO:
            raise ValueError("ação grande demais")
        return self


class TurnoBody(BaseModel):
    """Uma mensagem dela. O limite de 4 mil caracteres é conferido com a frase para ela."""

    texto: str = Field(max_length=20_000)
    contexto: ContextoBody | None = None
    acao: AcaoBody | None = None
    id_cliente: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")


# --------------------------------------------------------------------------- #
# Respostas                                                                    #
# --------------------------------------------------------------------------- #


def _envelope(dados: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=RespostaPadrao(dados=dados).model_dump())


def _recusa(erro: ErroDaConversa) -> JSONResponse:
    envelope = RespostaPadrao(
        ok=False, dados=erro.dados, erro=erro.mensagem, categoria=erro.categoria
    )
    return JSONResponse(
        status_code=erro.status, content=envelope.model_dump(), headers=erro.cabecalhos
    )


def _desde(cabecalho: str | None, consulta: int | None) -> int:
    """O último `seq` que o cliente viu: o maior entre `Last-Event-ID` e `?desde=`."""
    visto = consulta or 0
    if cabecalho is not None and cabecalho.strip().isdigit():
        visto = max(visto, int(cabecalho.strip()))
    return max(0, visto)


# --------------------------------------------------------------------------- #
# Conversas                                                                    #
# --------------------------------------------------------------------------- #


@roteador.get("/api/conversas", response_model=RespostaPadrao)
async def listar_conversas(servico: Servico) -> JSONResponse:
    return _envelope(servico.listar())


@roteador.post("/api/conversas", response_model=RespostaPadrao)
async def criar_conversa(servico: Servico, corpo: NovaConversaBody | None = None) -> JSONResponse:
    return _envelope(servico.criar(corpo.titulo if corpo else None))


@roteador.get("/api/conversas/{conversa_id}", response_model=RespostaPadrao)
async def detalhar_conversa(conversa_id: str, servico: Servico) -> JSONResponse:
    try:
        return _envelope(servico.detalhar(conversa_id))
    except ErroDaConversa as erro:
        return _recusa(erro)


@roteador.patch("/api/conversas/{conversa_id}", response_model=RespostaPadrao)
async def alterar_conversa(
    conversa_id: str, corpo: AlterarConversaBody, servico: Servico
) -> JSONResponse:
    try:
        return _envelope(servico.alterar(conversa_id, titulo=corpo.titulo, atual=corpo.atual))
    except ErroDaConversa as erro:
        return _recusa(erro)


@roteador.delete("/api/conversas/{conversa_id}", response_model=RespostaPadrao)
async def apagar_conversa(conversa_id: str, servico: Servico) -> JSONResponse:
    try:
        return _envelope(await servico.apagar(conversa_id))
    except ErroDaConversa as erro:
        return _recusa(erro)


# --------------------------------------------------------------------------- #
# Turnos                                                                       #
# --------------------------------------------------------------------------- #


@roteador.post("/api/conversas/{conversa_id}/turnos", response_model=RespostaPadrao)
async def iniciar_turno(conversa_id: str, corpo: TurnoBody, servico: Servico) -> JSONResponse:
    pedido = Pedido(
        texto=corpo.texto,
        id_cliente=corpo.id_cliente,
        contexto=corpo.contexto.model_dump() if corpo.contexto else None,
        acao=corpo.acao.model_dump() if corpo.acao else None,
    )
    try:
        turno_id = await servico.iniciar_turno(conversa_id, pedido)
    except ErroDaConversa as erro:
        return _recusa(erro)
    return _envelope({"turno_id": turno_id}, status=202)


@roteador.get("/api/conversas/{conversa_id}/turnos/{turno_id}", response_model=RespostaPadrao)
async def estado_do_turno(conversa_id: str, turno_id: str, servico: Servico) -> JSONResponse:
    try:
        return _envelope(servico.estado_do_turno(conversa_id, turno_id))
    except ErroDaConversa as erro:
        return _recusa(erro)


@roteador.get("/api/conversas/{conversa_id}/turnos/{turno_id}/eventos")
async def eventos_do_turno(
    conversa_id: str,
    turno_id: str,
    servico: Servico,
    desde: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID", max_length=20),
) -> Response:
    try:
        fluxo = servico.assinar(conversa_id, turno_id, _desde(last_event_id, desde))
    except ErroDaConversa as erro:
        return _recusa(erro)
    if fluxo is None:
        return Response(status_code=204, headers={"Cache-Control": "no-cache, no-transform"})
    return StreamingResponse(fluxo, media_type="text/event-stream", headers=CABECALHOS_DO_SSE)


@roteador.post(
    "/api/conversas/{conversa_id}/turnos/{turno_id}/parar", response_model=RespostaPadrao
)
async def parar_turno(conversa_id: str, turno_id: str, servico: Servico) -> JSONResponse:
    try:
        status, dados = await servico.parar(conversa_id, turno_id)
    except ErroDaConversa as erro:
        return _recusa(erro)
    return _envelope(dados, status=status)


# --------------------------------------------------------------------------- #
# Estado do chat                                                               #
# --------------------------------------------------------------------------- #


@roteador.get("/api/chat/estado", response_model=RespostaPadrao)
async def estado_do_chat(servico: Servico) -> JSONResponse:
    """O agente atende agora? Sempre 200: fora do ar é `disponivel: false`, não erro."""
    return _envelope(await servico.estado_do_chat())


__all__ = ["CABECALHOS_DO_SSE", "roteador", "servico_da"]
