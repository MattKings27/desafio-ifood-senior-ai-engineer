"""Baixar uma foto da internet com as mesmas travas da página de receita.

A foto de uma receita é um endereço que a página declarou, e a página é de
terceiros: pode apontar para dentro da rede, para um arquivo enorme, ou para um
SVG com script. Por isso a foto passa pelo mesmo `urllib` que só conversa com
endereço público (`retrieval.rede`: IP validado e fixado na conexão, cada
redirecionamento conferido de novo) e por mais três travas:

1. **Tamanho.** No máximo 5 MB, contados nos bytes que chegaram (o
   `Content-Length` declarado só serve para desistir antes).
2. **Tipo pelos bytes.** O que decide se é foto são os primeiros bytes do
   arquivo (JPEG, PNG, WebP, AVIF ou GIF), e não o `Content-Type` que o
   servidor diz. SVG nunca passa: é texto, e pode carregar script.
3. **Só http e https**, sem usuário e senha no endereço.
"""

from __future__ import annotations

import functools
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from retrieval.rede import DestinoProibido, abridor

#: O maior arquivo de foto que se aceita.
TAMANHO_MAXIMO_DA_IMAGEM: Final = 5 * 1024 * 1024

#: Quanto se espera por uma foto.
TIMEOUT_DA_IMAGEM: Final = 10.0

#: Abaixo disto, a "foto" que a página de uma receita declara é a imagem
#: genérica do site, e não a do prato: o chapéu de cozinheiro cinza do
#: TudoGostoso tem uns 3 KB, e a foto de um prato, dezenas ou centenas.
TAMANHO_MINIMO_DA_FOTO_DE_RECEITA: Final = 15 * 1024

AGENTE: Final = "SaborDaMaria/1.0 (fotos das receitas e dos ingredientes)"

#: Os tipos aceitos e a extensão com que cada um fica guardado.
EXTENSOES: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
}

_MARCAS_AVIF: Final = frozenset({b"avif", b"avis"})
#: O cabeçalho do WebP e da caixa `ftyp` do AVIF: tamanho, tipo e a marca principal.
_CABECALHO: Final = 12
#: Onde começam as marcas compatíveis da caixa `ftyp`, depois da versão.
_MARCAS_COMPATIVEIS: Final = 16


class ImagemRecusada(Exception):  # noqa: N818
    """O endereço ou o arquivo não é uma foto que se possa servir."""


class ImagemIndisponivel(Exception):  # noqa: N818
    """A foto não chegou: o site não respondeu, ou respondeu com erro."""


@dataclass(frozen=True, slots=True)
class ImagemBaixada:
    """Os bytes da foto e o tipo que os próprios bytes dizem."""

    conteudo: bytes
    tipo: str

    @property
    def extensao(self) -> str:
        return EXTENSOES[self.tipo]


def parece_generica(imagem: ImagemBaixada) -> bool:
    """A foto de uma receita pequena demais para ser a do prato: é a genérica do site.

    Vale só para foto de receita: a do item da planilha é uma miniatura do
    Commons, pequena de propósito.
    """
    return len(imagem.conteudo) < TAMANHO_MINIMO_DA_FOTO_DE_RECEITA


def tipo_pelos_bytes(bruto: bytes) -> str | None:
    """O tipo da foto pelos primeiros bytes, ou `None` se não é foto aceita.

    SVG, HTML e o resto não têm assinatura aqui, e ficam de fora.
    """
    if bruto.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if bruto.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if bruto.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(bruto) >= _CABECALHO and bruto[:4] == b"RIFF" and bruto[8:12] == b"WEBP":
        return "image/webp"
    if len(bruto) >= _CABECALHO and bruto[4:8] == b"ftyp":
        tamanho = int.from_bytes(bruto[:4], "big")
        marcas = {bruto[8:12]}
        # As marcas compatíveis vêm depois da versão, de 4 em 4 bytes, até o fim da caixa.
        fim = min(tamanho, len(bruto))
        marcas.update(bruto[i : i + 4] for i in range(_MARCAS_COMPATIVEIS, fim - 3, 4))
        if marcas & _MARCAS_AVIF:
            return "image/avif"
    return None


def validar_endereco(url: str) -> str:
    """O endereço, se é http ou https com um host e sem credencial embutida."""
    partes = urlsplit(url.strip())
    if partes.scheme not in {"http", "https"}:
        raise ImagemRecusada(f"só baixo foto por http e https, não {partes.scheme or 'nada'!r}")
    if not partes.hostname:
        raise ImagemRecusada("endereço de foto sem domínio")
    if "@" in partes.netloc:
        raise ImagemRecusada("endereço de foto com usuário ou senha embutidos")
    return url.strip()


@functools.cache
def _abridor_padrao() -> urllib.request.OpenerDirector:
    """O `urllib` de endereço público, um por processo, montado na primeira foto."""
    return abridor()


def baixar_imagem(
    url: str,
    abrir: urllib.request.OpenerDirector | None = None,
    *,
    limite: int = TAMANHO_MAXIMO_DA_IMAGEM,
) -> ImagemBaixada:
    """Baixa a foto por endereço público e confere tamanho e tipo pelos bytes.

    `abrir` é injetável para o teste não usar a rede; sem ele, é o `urllib` de
    `retrieval.rede`, que recusa endereço que não é público em cada conexão.
    """
    endereco = validar_endereco(url)
    requisicao = urllib.request.Request(
        endereco,
        headers={
            "User-Agent": AGENTE,
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif;q=0.9",
        },
    )
    try:
        with (abrir or _abridor_padrao()).open(requisicao, timeout=TIMEOUT_DA_IMAGEM) as resposta:
            declarado = resposta.headers.get("Content-Length", "").strip()
            if declarado.isdigit() and int(declarado) > limite:
                raise ImagemRecusada("a foto passa de 5 MB")
            bruto: bytes = resposta.read(limite + 1)
    except DestinoProibido as erro:
        raise ImagemRecusada(str(erro)) from erro
    except urllib.error.HTTPError as erro:
        raise ImagemIndisponivel(f"o site respondeu HTTP {erro.code}") from erro
    except urllib.error.URLError as erro:
        if isinstance(erro.reason, DestinoProibido):
            raise ImagemRecusada(str(erro.reason)) from erro
        raise ImagemIndisponivel(f"não consegui falar com o site: {erro.reason}") from erro
    except (TimeoutError, OSError) as erro:
        raise ImagemIndisponivel(f"não consegui falar com o site: {erro}") from erro
    if len(bruto) > limite:
        raise ImagemRecusada("a foto passa de 5 MB")
    tipo = tipo_pelos_bytes(bruto)
    if tipo is None:
        raise ImagemRecusada("o arquivo não é uma foto em JPEG, PNG, WebP, AVIF ou GIF")
    return ImagemBaixada(bruto, tipo)


__all__ = [
    "EXTENSOES",
    "TAMANHO_MAXIMO_DA_IMAGEM",
    "TAMANHO_MINIMO_DA_FOTO_DE_RECEITA",
    "TIMEOUT_DA_IMAGEM",
    "ImagemBaixada",
    "ImagemIndisponivel",
    "ImagemRecusada",
    "baixar_imagem",
    "parece_generica",
    "tipo_pelos_bytes",
    "validar_endereco",
]
