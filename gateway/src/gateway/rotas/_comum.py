"""O que toda rota da API compartilha: o envelope, o dinheiro, a sessão e os erros.

Estava tudo dentro de `http.criar_app`, e cada roteador novo teria de copiar.
Copiado, o envelope diverge: uma rota devolve `categoria: "uso"` onde a outra
devolve `"regra"` para o mesmo erro, e a tela trata os dois de um jeito só.

**Envelope.** Toda rota devolve `{ok, dados, erro, categoria, pergunta}`. Erro
do motor não é exceção para a tela: vai no envelope, com HTTP 200 e `ok: false`,
porque na maior parte das vezes é uma pergunta para ela ("quanto vem na
embalagem?"), não uma falha. A exceção é a categoria `ausente` (o item, a
receita ou a conversa não existe), que sai com HTTP 404 e o mesmo envelope, para
a tela mostrar "não encontrado".

**Sessão.** Há uma por app, em `app.state.sessao`, a mesma das rotas antigas de
`http.py`. Um roteador a recebe declarando `sessao: SessaoDaApp`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Final

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from mise.erros import Ausente, ErroDeDados, ErroDeRegra, ErroMise
from mise.mcp_server import Sessao
from pydantic import BaseModel

#: Categorias que saem com status HTTP próprio. As outras vão com 200 e `ok: false`.
STATUS_POR_CATEGORIA: Final[dict[str, int]] = {"ausente": 404}


class RespostaPadrao(BaseModel):
    """Envelope único: a web app trata sucesso e erro do mesmo jeito."""

    ok: bool = True
    dados: Any = None
    erro: str | None = None
    categoria: str | None = None
    pergunta: str | None = None


class RespostaDeErro(Exception):
    """Um envelope de erro que sai com status diferente de 200 (ex.: `ausente`, 404).

    É levantada por `responder` e vira resposta no tratador que `criar_app`
    registra: a rota continua declarando que devolve `RespostaPadrao`.
    """

    def __init__(self, resposta: RespostaPadrao, status: int) -> None:
        super().__init__(resposta.erro or "")
        self.resposta = resposta
        self.status = status


def categoria_de(erro: ErroMise) -> str:
    """A categoria que diz à tela o que fazer: perguntar, recusar, corrigir ou "não existe"."""
    if isinstance(erro, Ausente):
        return "ausente"
    if isinstance(erro, ErroDeDados):
        return "dado"
    if isinstance(erro, ErroDeRegra):
        return "regra"
    return "uso"


def envelope_de_erro(erro: ErroMise) -> RespostaPadrao:
    """O erro do motor no envelope, com a pergunta que destrava quando houver."""
    return RespostaPadrao(
        ok=False,
        erro=erro.mensagem,
        categoria=categoria_de(erro),
        pergunta=getattr(erro, "pergunta", None) or None,
    )


def responder(montar: Callable[[], Any]) -> RespostaPadrao:
    """Executa e converte erro de domínio em envelope, nunca em stack trace."""
    try:
        return RespostaPadrao(dados=montar())
    except ErroMise as erro:
        resposta = envelope_de_erro(erro)
        status = STATUS_POR_CATEGORIA.get(resposta.categoria or "")
        if status is not None:
            raise RespostaDeErro(resposta, status) from erro
        return resposta


async def tratar_resposta_de_erro(_requisicao: Request, erro: Exception) -> JSONResponse:
    """O tratador que `criar_app` registra para `RespostaDeErro`."""
    assert isinstance(erro, RespostaDeErro)
    return JSONResponse(status_code=erro.status, content=erro.resposta.model_dump())


def _dinheiro(valor: Any) -> dict[str, Any]:
    """Todo valor vai com número e com o texto já formatado em pt-BR.

    A interface nunca formata moeda: formatar em dois lugares é como pt-BR e
    en-US acabam na mesma tela.
    """
    return {"valor": float(valor.arredondado().valor), "texto": str(valor)}


def sessao_da(requisicao: Request) -> Sessao:
    """A sessão do app: a mesma para as rotas de `http.py` e para as dos roteadores."""
    sessao: Sessao = requisicao.app.state.sessao
    return sessao


#: Parâmetro de rota que recebe a sessão: `def rota(sessao: SessaoDaApp) -> ...`.
SessaoDaApp = Annotated[Sessao, Depends(sessao_da)]

__all__ = [
    "STATUS_POR_CATEGORIA",
    "RespostaDeErro",
    "RespostaPadrao",
    "SessaoDaApp",
    "_dinheiro",
    "categoria_de",
    "envelope_de_erro",
    "responder",
    "sessao_da",
    "tratar_resposta_de_erro",
]
