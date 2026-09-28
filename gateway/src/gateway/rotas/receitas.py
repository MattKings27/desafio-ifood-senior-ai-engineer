"""As receitas na tela: a grade, o detalhe, o custo, a avaliação e as notas.

- `GET /api/receitas` (`receitas.json`): a aba pedida (`pode_fazer`,
  `falta_resposta`, `ranking` ou `nao_quer`), as contagens de cada aba e a
  situação da descoberta, com os filtros `q`, `usa`, `tempo_max`,
  `so_com_o_que_tenho`, `nota_min` e `ordem`. A receita que a cozinha dela não
  permite não aparece em aba nenhuma.
- `GET /api/receitas/{slug}` (`receita.json`): a receita, a conferência com e
  sem o gosto, cada ingrediente com quanto ela tem, o que falta comprar, os
  passos e a avaliação dela.
- `POST /api/receitas {url}`: a receita que ela traz pelo endereço, lida pelo
  servidor e guardada no catálogo; devolve o detalhe dela.
- `GET /api/receitas/{slug}/custo` (`custo.json`): o custo de uma porção. A
  receita que a conferência não libera é recusada com HTTP 409 e o porquê.
- `GET|PUT /api/receitas/{slug}/avaliacao` e `PUT /api/receitas/{slug}/notas`
  (`avaliacao-escrita.json`, `notas-escrita.json`): a avaliação dela, a
  pontuação com a conta e a posição no ranking.
- `POST /api/receitas/{slug}/resposta {campo, resposta, por_unidade?}`: a
  resposta dela a uma pergunta da própria receita (o rendimento, o tempo no
  fogo, o modo de preparo, quanto vai de uma linha que a leitura não entendeu,
  ou quanto pesa a linha cuja medida não se converte, de uma unidade ou da
  linha inteira), gravada no catálogo como dita por ela; devolve o detalhe,
  conferido de novo.

- `POST /api/receitas/descoberta` (`descoberta-inicio.json`): começa uma rodada
  de descoberta em segundo plano (`gateway.descoberta`) e responde 202 na hora;
  com uma rodada já em andamento, 409 (`ocupado`) com a que está rodando; com a
  busca automática desligada, a recusa com o motivo (`regra`).
- `GET /api/receitas/descoberta/eventos` (SSE, `receitas-descoberta.jsonl`): o
  progresso da rodada, cada receita que entrou e o fim, com retomada por
  `Last-Event-ID` ou `?desde=`; 204 quando não há mais nada a mandar.

Tudo é calculado na leitura, pela mesma conferência da conversa
(`mise.receitas_json`): ler a grade não grava nada, e a grade acompanha a
despensa, a cozinha e o orçamento de agora. As escritas devolvem o recurso
como ficou. Ler a grade também nunca começa uma descoberta: quem começa é a
tela, pelo botão ou na primeira visita com o catálogo vazio.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from mise.erros import ErroMise
from pydantic import BaseModel, Field

from gateway.descoberta import ServicoDeDescoberta
from gateway.rotas._comum import (
    STATUS_POR_CATEGORIA,
    RespostaDeErro,
    RespostaPadrao,
    SessaoDaApp,
    envelope_de_erro,
)
from gateway.rotas.conversa import CABECALHOS_DO_SSE

roteador = APIRouter()

#: O endereço mais longo que se aceita trazer.
TAMANHO_DA_URL: Final = 2000

#: Pedido que a lista não entende (aba ou ordem que não existe) é 422, com o envelope.
_LISTA_RECUSA: Final[Mapping[str, int]] = {"uso": 422}

#: A receita que a conferência não libera não tem custo: 409, com o porquê.
_CUSTO_RECUSA: Final[Mapping[str, int]] = {"regra": 409}

_HTTP_CRIADO: Final = 201


class ReceitaPeloEnderecoBody(BaseModel):
    """O endereço de uma receita na internet, que ela colou na tela."""

    url: str = Field(min_length=8, max_length=TAMANHO_DA_URL)


class AvaliacaoBody(BaseModel):
    """Só o que mudou: `gosta` (`null` é "ainda não disse") e as estrelas (`null` apaga)."""

    gosta: bool | None = None
    estrelas: dict[str, int | None] | None = None


class NotasBody(BaseModel):
    """As anotações dela sobre a receita. Texto vazio apaga."""

    texto: str = Field(default="", max_length=2000)


class RespostaDaReceitaBody(BaseModel):
    """A resposta dela a uma pergunta da própria receita, como a grade pergunta.

    `campo` é o da pergunta: `rendimento_porcoes`, `tempo_cozimento_min`,
    `modo_preparo`, ou o texto da linha (a que a leitura não entendeu, a do
    item parecido, ou a de medida que não se converte). Na de medida, a
    `resposta` é o peso ("300 g", "0,3 kg") e `por_unidade` diz se é o de uma
    unidade (`true`, o que a pergunta pede) ou o da linha inteira (`false`).
    """

    campo: str = Field(min_length=1, max_length=500)
    resposta: str = Field(min_length=1, max_length=2000)
    por_unidade: bool | None = None


def servico_da_descoberta(requisicao: Request) -> ServicoDeDescoberta:
    """A descoberta do app, criada no primeiro uso, com a conversa ao lado."""
    servico: ServicoDeDescoberta | None = getattr(requisicao.app.state, "descoberta", None)
    if servico is None:
        servico = ServicoDeDescoberta.do_ambiente(
            requisicao.app.state.sessao, getattr(requisicao.app.state, "conversa", None)
        )
        requisicao.app.state.descoberta = servico
    return servico


Descoberta = Annotated[ServicoDeDescoberta, Depends(servico_da_descoberta)]


def _desde(cabecalho: str | None, consulta: int | None) -> int:
    """O último `seq` que o cliente viu: o maior entre `Last-Event-ID` e `?desde=`."""
    visto = consulta or 0
    if cabecalho is not None and cabecalho.strip().isdigit():
        visto = max(visto, int(cabecalho.strip()))
    return max(0, visto)


def _responder(
    montar: Callable[[], Any], status: Mapping[str, int] | None = None
) -> RespostaPadrao:
    """O envelope de sempre, com o status próprio de cada rota para as recusas dela."""
    try:
        return RespostaPadrao(dados=montar())
    except ErroMise as erro:
        resposta = envelope_de_erro(erro)
        codigo = {**STATUS_POR_CATEGORIA, **(status or {})}.get(resposta.categoria or "")
        if codigo is not None:
            raise RespostaDeErro(resposta, codigo) from erro
        return resposta


@roteador.get("/api/receitas", response_model=RespostaPadrao)
def listar(
    sessao: SessaoDaApp,
    descoberta: Descoberta,
    *,
    aba: str = "pode_fazer",
    q: str | None = Query(default=None, max_length=120),
    usa: str | None = Query(default=None, max_length=120),
    tempo_max: int | None = Query(default=None, ge=1, le=100_000),
    so_com_o_que_tenho: bool = False,
    nota_min: float | None = Query(default=None, ge=0, le=100),
    ordem: str | None = None,
) -> RespostaPadrao:
    """A grade de receitas: só o que ela consegue fazer, por aba, com os filtros."""
    from mise import receitas_json  # noqa: PLC0415

    def montar() -> dict[str, Any]:
        filtros = receitas_json.Filtros(
            aba=aba,
            q=q,
            usa=usa,
            tempo_max=tempo_max,
            so_com_o_que_tenho=so_com_o_que_tenho,
            nota_min=Decimal(str(nota_min)) if nota_min is not None else None,
            ordem=ordem,
        )
        lista = receitas_json.lista(sessao, filtros)
        # A rodada de agora (ou a última deste processo) vale mais que a contagem do catálogo.
        lista["descoberta"] = descoberta.estado() or lista["descoberta"]
        return lista

    return _responder(montar, _LISTA_RECUSA)


@roteador.post("/api/receitas/descoberta", response_model=RespostaPadrao)
async def descobrir(descoberta: Descoberta) -> JSONResponse:
    """Começa uma rodada de descoberta e responde na hora; a rodada segue sozinha."""
    resposta = await descoberta.iniciar()
    envelope = RespostaPadrao(
        ok=resposta.ok, dados=resposta.dados, erro=resposta.erro, categoria=resposta.categoria
    )
    return JSONResponse(status_code=resposta.status, content=envelope.model_dump())


@roteador.get("/api/receitas/descoberta/eventos")
async def eventos_da_descoberta(
    descoberta: Descoberta,
    execucao: str | None = Query(default=None, max_length=40),
    desde: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID", max_length=20),
) -> Response:
    """O fluxo da rodada pedida (ou da última): progresso, receitas encontradas e o fim."""
    rodada = descoberta.execucao(execucao)
    if rodada is None:
        if execucao is not None:
            envelope = RespostaPadrao(
                ok=False, erro="Não encontrei essa busca de receitas.", categoria="ausente"
            )
            return JSONResponse(status_code=404, content=envelope.model_dump())
        return Response(status_code=204, headers={"Cache-Control": "no-cache, no-transform"})
    fluxo = descoberta.assinar(rodada, _desde(last_event_id, desde))
    if fluxo is None:
        return Response(status_code=204, headers={"Cache-Control": "no-cache, no-transform"})
    return StreamingResponse(fluxo, media_type="text/event-stream", headers=CABECALHOS_DO_SSE)


@roteador.post("/api/receitas", response_model=RespostaPadrao)
def trazer(
    corpo: ReceitaPeloEnderecoBody, sessao: SessaoDaApp, resposta: Response
) -> RespostaPadrao:
    """A receita que ela trouxe pelo endereço: o servidor lê a página e guarda no catálogo."""
    from mise import receitas_json  # noqa: PLC0415
    from mise.catalogo import OrigemNoCatalogo  # noqa: PLC0415

    def montar() -> dict[str, Any]:
        trazida = sessao.receita_da_web(corpo.url, origem=OrigemNoCatalogo.URL_DELA)
        if not trazida["ja_conhecida"]:
            resposta.status_code = _HTTP_CRIADO
        return receitas_json.detalhe(sessao, str(trazida["receita_id"]))

    return _responder(montar)


@roteador.get("/api/receitas/{slug}", response_model=RespostaPadrao)
def detalhar(slug: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """O detalhe: a receita, a conferência, cada ingrediente e a avaliação dela."""
    from mise import receitas_json  # noqa: PLC0415

    return _responder(lambda: receitas_json.detalhe(sessao, slug))


@roteador.get("/api/receitas/{slug}/custo", response_model=RespostaPadrao)
def custo(slug: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """O custo de uma porção, linha a linha; 409 com o porquê quando a conferência não libera."""
    from mise import receitas_json  # noqa: PLC0415

    return _responder(lambda: receitas_json.custo(sessao, slug), _CUSTO_RECUSA)


@roteador.get("/api/receitas/{slug}/avaliacao", response_model=RespostaPadrao)
def avaliacao(slug: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """A avaliação dela, a pontuação com a conta e a posição no ranking."""
    from mise import receitas_json  # noqa: PLC0415

    return _responder(lambda: receitas_json.resposta_da_avaliacao(sessao, slug, anotou=False))


@roteador.put("/api/receitas/{slug}/avaliacao", response_model=RespostaPadrao)
def avaliar(slug: str, corpo: AvaliacaoBody, sessao: SessaoDaApp) -> RespostaPadrao:
    """Grava o gosto e as estrelas que vieram, e devolve a avaliação como ficou."""
    return _responder(
        lambda: sessao.registrar_avaliacao(
            slug,
            gosta=corpo.gosta,
            muda_o_gosto="gosta" in corpo.model_fields_set,
            estrelas=corpo.estrelas,
        )
    )


@roteador.post("/api/receitas/{slug}/resposta", response_model=RespostaPadrao)
def responder(slug: str, corpo: RespostaDaReceitaBody, sessao: SessaoDaApp) -> RespostaPadrao:
    """A resposta dela a uma pergunta da receita; devolve a receita conferida de novo."""
    from mise import receitas_json  # noqa: PLC0415

    def montar() -> dict[str, Any]:
        completa = sessao.responder_sobre_a_receita(
            slug, corpo.campo, corpo.resposta, por_unidade=corpo.por_unidade
        )
        return receitas_json.detalhe(sessao, completa.slug)

    return _responder(montar)


@roteador.put("/api/receitas/{slug}/notas", response_model=RespostaPadrao)
def anotar(slug: str, corpo: NotasBody, sessao: SessaoDaApp) -> RespostaPadrao:
    """Grava as anotações dela sobre a receita."""
    from mise import receitas_json  # noqa: PLC0415

    def montar() -> dict[str, Any]:
        guardada = receitas_json.guardada_por_slug(sessao, slug)
        gravadas = sessao.avaliacoes.gravar(guardada.slug, notas=corpo.texto)
        return receitas_json.resposta_das_notas(sessao, guardada.slug, gravadas)

    return _responder(montar)


__all__ = [
    "AvaliacaoBody",
    "NotasBody",
    "ReceitaPeloEnderecoBody",
    "RespostaDaReceitaBody",
    "roteador",
    "servico_da_descoberta",
]
