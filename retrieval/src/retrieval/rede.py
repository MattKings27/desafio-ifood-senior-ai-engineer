"""Buscar uma página da internet sem abrir porta para a rede interna.

A URL que chega a `buscar_receita_na_web` vem do modelo, que a leu numa página
ou numa conversa. Sem este módulo, `http://169.254.169.254/` (credenciais da
nuvem), `http://localhost:8777/` (a API do próprio motor) ou um endereço da rede
da casa dela seriam buscados como qualquer receita, e o conteúdo voltaria para
o modelo. E o `urllib` segue redirecionamento sem perguntar para onde: uma
página pública podia mandar a busca para dentro.

A defesa tem três partes, e as três moram no momento da conexão, por onde passa
toda requisição, inclusive cada salto de um redirecionamento:

1. o nome é resolvido uma vez, e **todos** os endereços têm que ser públicos
   (nada de loopback, rede privada, link-local, multicast, reservado);
2. a conexão vai para o endereço que foi validado, não para um nome resolvido
   de novo depois (sem isso, um DNS que responde público na checagem e privado
   na conexão passaria);
3. em HTTPS, o certificado continua conferido contra o nome original.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.request
from collections.abc import Callable
from typing import Any, Final

#: Resolve um nome em endereços IP. Injetável para teste sem rede.
Resolvedor = Callable[[str, int], list[str]]

#: Saltos de redirecionamento aceitos antes de desistir.
MAXIMO_DE_REDIRECIONAMENTOS: Final = 5


class DestinoProibido(Exception):  # noqa: N818
    """O endereço não é público. Buscar lá seria acessar a rede de dentro."""


def resolver_pelo_sistema(host: str, porta: int) -> list[str]:
    infos = socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def endereco_publico(bruto: str) -> bool:
    """O IP é roteável na internet pública?

    `is_global` já recusa privado, loopback, link-local e reservado; multicast
    se recusa à parte. Endereço IPv6 que embute um IPv4 é julgado pelo IPv4.
    """
    ip = ipaddress.ip_address(bruto.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def destino_seguro(host: str, porta: int, resolver: Resolvedor = resolver_pelo_sistema) -> str:
    """O IP público onde conectar, ou `DestinoProibido`.

    Todos os endereços do nome têm que ser públicos: um nome que resolve para
    um IP público e um privado é exatamente o truque de quem quer entrar.
    """
    try:
        enderecos = resolver(host, porta)
    except (socket.gaierror, UnicodeError) as erro:
        raise DestinoProibido(f"não consegui resolver {host!r}: {erro}") from erro
    if not enderecos:
        raise DestinoProibido(f"{host!r} não resolve para endereço nenhum")
    proibidos = [e for e in enderecos if not endereco_publico(e)]
    if proibidos:
        raise DestinoProibido(
            f"{host!r} aponta para endereço que não é público ({', '.join(proibidos)})"
        )
    return enderecos[0]


class _ConexaoHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, *args: Any, resolver: Resolvedor, **kwargs: Any) -> None:
        super().__init__(host, *args, **kwargs)
        self._resolver = resolver

    def connect(self) -> None:
        ip = destino_seguro(self.host, self.port, self._resolver)
        self.sock = socket.create_connection((ip, self.port), self.timeout)


class _ConexaoHTTPS(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        *args: Any,
        resolver: Resolvedor,
        context: ssl.SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        self._contexto = context or ssl.create_default_context()
        super().__init__(host, *args, context=self._contexto, **kwargs)
        self._resolver = resolver

    def connect(self) -> None:
        ip = destino_seguro(self.host, self.port, self._resolver)
        bruto = socket.create_connection((ip, self.port), self.timeout)
        # O certificado é conferido contra o nome, mesmo conectando pelo IP.
        self.sock = self._contexto.wrap_socket(bruto, server_hostname=self.host)


class _ManipuladorHTTP(urllib.request.HTTPHandler):
    def __init__(self, resolver: Resolvedor) -> None:
        super().__init__()
        self._resolver = resolver

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        def conexao(host: str, **kwargs: Any) -> _ConexaoHTTP:
            return _ConexaoHTTP(host, resolver=self._resolver, **kwargs)

        return self.do_open(conexao, req)


class _ManipuladorHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, resolver: Resolvedor) -> None:
        super().__init__(context=ssl.create_default_context())
        self._resolver = resolver

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        def conexao(host: str, **kwargs: Any) -> _ConexaoHTTPS:
            return _ConexaoHTTPS(host, resolver=self._resolver, **kwargs)

        return self.do_open(conexao, req)


class _Redirecionamento(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamento só para http e https, e poucas vezes.

    O destino de cada salto passa pela mesma validação de endereço, porque a
    nova requisição volta para os manipuladores acima.
    """

    max_redirections = MAXIMO_DE_REDIRECIONAMENTOS

    def redirect_request(  # noqa: PLR0913, PLR0917 (assinatura da biblioteca padrão)
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not newurl.lower().startswith(("http://", "https://")):
            raise DestinoProibido(f"redirecionamento para esquema não permitido: {newurl!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def abridor(resolver: Resolvedor = resolver_pelo_sistema) -> urllib.request.OpenerDirector:
    """Um `urllib` que só conversa com endereço público.

    Montado com `OpenerDirector` vazio, e não com `build_opener`, para que o
    manipulador HTTP padrão, que não valida nada, não entre por tabela.
    """
    director = urllib.request.OpenerDirector()
    for manipulador in (
        _ManipuladorHTTP(resolver),
        _ManipuladorHTTPS(resolver),
        _Redirecionamento(),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.HTTPDefaultErrorHandler(),
    ):
        director.add_handler(manipulador)
    return director


__all__ = [
    "MAXIMO_DE_REDIRECIONAMENTOS",
    "DestinoProibido",
    "abridor",
    "destino_seguro",
    "endereco_publico",
    "resolver_pelo_sistema",
]
