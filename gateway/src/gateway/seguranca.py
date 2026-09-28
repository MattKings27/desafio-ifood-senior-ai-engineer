"""A API só atende quem está nesta máquina, e só escreve a pedido da própria tela.

A API do motor não tem login: quem fala com ela escreve no dossiê da Dona Maria
e, pelo chat, põe o agente para trabalhar (e gastar). O que a protege:

- **Escuta só em 127.0.0.1.** `gateway.http.main` usa `MISE_HTTP_HOST`, que por
  padrão é `127.0.0.1`. A imagem Docker escuta em 0.0.0.0 dentro do container,
  mas o compose publica a porta só em 127.0.0.1. Abrir para a rede é decisão
  explícita, e aí `MISE_HOSTS` precisa listar o nome por onde ela é chamada.
- **Host confiável** (`TrustedHostMiddleware`): o cabeçalho `Host` tem que ser
  `localhost` ou `127.0.0.1` (mais o que `MISE_HOSTS` acrescentar). É a defesa
  contra DNS rebinding: um site que faz o próprio domínio apontar para
  127.0.0.1 chega aqui com `Host: site-do-atacante`, e leva 400. As sondas de
  saúde (`/saude/*`) ficam de fora: o Kubernetes chama pelo IP do pod, e elas
  só leem.
- **Origem confiável para escrever**: POST, PUT, PATCH e DELETE com um `Origin`
  fora da lista (`MISE_CORS`, a mesma do CORS: http://localhost:3000 e
  http://127.0.0.1:3000) levam 403. Pedido sem `Origin` passa: é o servidor do
  Next, o `curl` ou um teste, e não um navegador. Navegador sempre manda
  `Origin` numa escrita entre sites, que é de onde viria a falsificação.
- **Corpo de tamanho razoável**: acima de 1 MB (`Content-Length`), 413.
- **Mensagens de chat contadas** (`LimiteDeTaxa`): cerca de 10 por minuto por
  conversa, e 4 mil caracteres por mensagem (`TAMANHO_DA_MENSAGEM`).
"""

from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Final

from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

VAR_HOSTS: Final = "MISE_HOSTS"
VAR_ORIGENS: Final = "MISE_CORS"
HOSTS_PADRAO: Final = ("localhost", "127.0.0.1")
ORIGENS_PADRAO: Final = ("http://localhost:3000", "http://127.0.0.1:3000")

#: Os métodos que escrevem: só a tela (ou quem não é navegador) pode.
METODOS_DE_ESCRITA: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: As sondas de saúde, que o orquestrador chama pelo IP e que só leem.
PREFIXO_DAS_SONDAS: Final = "/saude/"

#: O maior corpo que uma escrita pode mandar.
TAMANHO_DO_CORPO: Final = 1024 * 1024

#: O maior texto de uma mensagem dela para o agente.
TAMANHO_DA_MENSAGEM: Final = 4000

#: Quantas mensagens por conversa, e em quanto tempo.
MENSAGENS_POR_JANELA: Final = 10
JANELA_DAS_MENSAGENS_S: Final = 60.0


def _lista(bruto: str) -> list[str]:
    return [item.strip() for item in bruto.split(",") if item.strip()]


def hosts_permitidos(ambiente: Mapping[str, str] | None = None) -> list[str]:
    """`localhost` e `127.0.0.1`, mais os de `MISE_HOSTS` (separados por vírgula)."""
    amb = os.environ if ambiente is None else ambiente
    return list(dict.fromkeys([*HOSTS_PADRAO, *_lista(amb.get(VAR_HOSTS, ""))]))


def origens_permitidas(ambiente: Mapping[str, str] | None = None) -> list[str]:
    """As origens do navegador que podem escrever: `MISE_CORS`, como o CORS."""
    amb = os.environ if ambiente is None else ambiente
    return _lista(amb.get(VAR_ORIGENS, "")) or list(ORIGENS_PADRAO)


def _recusa(status: int, mensagem: str) -> JSONResponse:
    """O envelope de sempre (`gateway.rotas._comum.RespostaPadrao`), escrito à mão.

    À mão porque este módulo fica por baixo das rotas: importar o envelope de lá
    puxaria o pacote de rotas inteiro, que depende deste.
    """
    envelope = {
        "ok": False,
        "dados": None,
        "erro": mensagem,
        "categoria": "regra",
        "pergunta": None,
    }
    return JSONResponse(status_code=status, content=envelope)


class HostConfiavel(TrustedHostMiddleware):
    """O `TrustedHostMiddleware` do Starlette, sem barrar as sondas de saúde."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).startswith(PREFIXO_DAS_SONDAS):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class OrigemConfiavel:
    """Recusa a escrita que vem de um navegador em outra origem, e o corpo grande demais."""

    def __init__(
        self, app: ASGIApp, origens: list[str], tamanho_do_corpo: int = TAMANHO_DO_CORPO
    ) -> None:
        self.app = app
        self.origens = frozenset(origens)
        self.tamanho_do_corpo = tamanho_do_corpo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in METODOS_DE_ESCRITA:
            await self.app(scope, receive, send)
            return
        cabecalhos = Headers(scope=scope)
        origem = cabecalhos.get("origin")
        if origem is not None and origem not in self.origens:
            resposta = _recusa(403, "Este pedido não veio da tela do Sabor da Maria.")
            await resposta(scope, receive, send)
            return
        tamanho = cabecalhos.get("content-length", "")
        if tamanho.isdigit() and int(tamanho) > self.tamanho_do_corpo:
            await _recusa(413, "O pedido veio grande demais.")(scope, receive, send)
            return
        await self.app(scope, receive, send)


def configurar(app: FastAPI, ambiente: Mapping[str, str] | None = None) -> None:
    """Liga a origem e o host confiáveis. O host fica por fora: é o primeiro a conferir."""
    app.add_middleware(OrigemConfiavel, origens=origens_permitidas(ambiente))
    app.add_middleware(HostConfiavel, allowed_hosts=hosts_permitidos(ambiente))


class LimiteDeTaxa:
    """Janela móvel: no máximo `maximo` pedidos por chave em `janela_s` segundos."""

    def __init__(
        self,
        maximo: int = MENSAGENS_POR_JANELA,
        janela_s: float = JANELA_DAS_MENSAGENS_S,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.maximo = maximo
        self.janela_s = janela_s
        self._relogio = relogio
        self._pedidos: dict[str, deque[float]] = {}

    def espera(self, chave: str) -> float | None:
        """Conta o pedido e devolve `None`; se passou do limite, não conta e diz quanto esperar."""
        agora = self._relogio()
        fila = self._pedidos.setdefault(chave, deque())
        while fila and agora - fila[0] >= self.janela_s:
            fila.popleft()
        if len(fila) >= self.maximo:
            return max(0.0, self.janela_s - (agora - fila[0]))
        fila.append(agora)
        return None

    def esquecer(self, chave: str) -> None:
        self._pedidos.pop(chave, None)


__all__ = [
    "HOSTS_PADRAO",
    "JANELA_DAS_MENSAGENS_S",
    "MENSAGENS_POR_JANELA",
    "METODOS_DE_ESCRITA",
    "ORIGENS_PADRAO",
    "TAMANHO_DA_MENSAGEM",
    "TAMANHO_DO_CORPO",
    "HostConfiavel",
    "LimiteDeTaxa",
    "OrigemConfiavel",
    "configurar",
    "hosts_permitidos",
    "origens_permitidas",
]
