"""As fotos das receitas e dos ingredientes, servidas pelo próprio servidor.

- `GET /api/imagens/{chave}`: a foto, em binário, com cache longo. A chave são
  os 32 primeiros caracteres hexadecimais do sha256 do endereço original
  (`mise.catalogo.chave_da_imagem`). A tela carrega por `/motor/imagens/<chave>`
  e nunca de outro endereço.
- `GET /api/imagens/{chave}/credito`: `{credito, licenca, fonte_url}`.

**Só se serve foto registrada.** Antes de baixar qualquer coisa, a chave tem
que estar num dos dois registros de `mise.fotos`: as fotos do Commons dos itens
da planilha, ou a foto que a página de uma receita declarou quando o servidor a
leu. Chave desconhecida é 404, e não vira download: ninguém faz o servidor
buscar um endereço escolhido por quem chama.

**O download tem as travas da página de receita** (`retrieval.imagens`):
endereço público com o IP fixado na conexão, cada redirecionamento conferido
de novo, no máximo 5 MB, e o tipo decidido pelos bytes (JPEG, PNG, WebP, AVIF
ou GIF; SVG nunca).

**A foto genérica do site não passa.** A foto de uma receita que chega pequena
demais para ser a do prato (`retrieval.imagens.parece_generica`, menos de
15 KB: o chapéu de cozinheiro cinza que o site põe quando a receita não tem
foto) é recusada, e o catálogo esquece a foto daquela receita
(`Catalogo.esquecer_foto`): a tela passa a mostrar o gradiente com o ícone.

**O cache fica em disco**, em `imagens/` ao lado do dossiê (`.estado/imagens/`),
um arquivo por chave. A foto que não veio (site fora do ar, arquivo que não é
foto) fica alguns minutos sem nova tentativa, para a grade não martelar o site
a cada visita.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from gateway.rotas._comum import RespostaDeErro, RespostaPadrao, SessaoDaApp

if TYPE_CHECKING:
    from mise.fotos import Foto
    from mise.mcp_server import Sessao
    from retrieval.imagens import ImagemBaixada

roteador = APIRouter()

#: A chave de uma foto: 32 caracteres hexadecimais minúsculos, e nada mais.
_CHAVE: Final = re.compile(r"^[0-9a-f]{32}$")

#: A foto de uma chave não muda: o navegador guarda por um ano.
CACHE_LONGO: Final = "public, max-age=31536000, immutable"

#: Por quanto tempo a foto que não veio fica sem nova tentativa.
DESCANSO_DA_FALHA_S: Final = 600.0

#: A pasta do cache, ao lado do dossiê.
PASTA_DO_CACHE: Final = "imagens"

_TIPOS_GUARDADOS: Final[dict[str, str]] = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
}

_CABECALHOS: Final[dict[str, str]] = {
    "Cache-Control": CACHE_LONGO,
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
}

SEM_FOTO: Final = "Não encontrei essa foto."
FOTO_RECUSADA: Final = "Essa foto não pode ser mostrada."
FOTO_NAO_VEIO: Final = "A foto não chegou agora. A tela mostra a receita sem ela."
FOTO_GENERICA: Final = "Essa receita não tem foto: o site mostra uma imagem genérica."


class AcervoDeImagens:
    """As fotos já baixadas, em disco, e o download das que faltam.

    `baixar` é injetável: os testes passam um que não usa a rede.
    """

    def __init__(
        self,
        pasta: Path,
        baixar: Callable[[str], ImagemBaixada] | None = None,
        *,
        relogio: Callable[[], float] = time.monotonic,
        descanso_s: float = DESCANSO_DA_FALHA_S,
    ) -> None:
        self.pasta = pasta
        self._baixar = baixar
        self._relogio = relogio
        self._descanso_s = descanso_s
        self._falhas: dict[str, tuple[float, int, str]] = {}
        self._trava = threading.Lock()

    def guardada(self, chave: str) -> tuple[bytes, str] | None:
        """Os bytes e o tipo da foto já baixada, ou `None`."""
        for extensao, tipo in _TIPOS_GUARDADOS.items():
            caminho = self.pasta / f"{chave}.{extensao}"
            if caminho.is_file():
                return caminho.read_bytes(), tipo
        return None

    def baixar(
        self, foto: Foto, *, esquecer: Callable[[str], object] | None = None
    ) -> tuple[bytes, str]:
        """Baixa, guarda e devolve a foto. Falha recente volta a falhar sem tentar de novo.

        A foto de receita que chega pequena demais é a genérica do site: é
        recusada, e `esquecer` (o `Catalogo.esquecer_foto`) tira a foto da receita.
        """
        from retrieval.imagens import (  # noqa: PLC0415
            ImagemIndisponivel,
            ImagemRecusada,
            baixar_imagem,
            parece_generica,
        )

        chave = foto.chave
        with self._trava:
            falha = self._falhas.get(chave)
        if falha is not None and self._relogio() - falha[0] < self._descanso_s:
            raise RespostaDeErro(_erro(falha[2], falha[1]), falha[1])
        try:
            imagem = (self._baixar or baixar_imagem)(foto.url)
        except ImagemRecusada as erro:
            self._lembrar(chave, 404, FOTO_RECUSADA)
            raise RespostaDeErro(_erro(FOTO_RECUSADA, 404), 404) from erro
        except ImagemIndisponivel as erro:
            self._lembrar(chave, 502, FOTO_NAO_VEIO)
            raise RespostaDeErro(_erro(FOTO_NAO_VEIO, 502), 502) from erro
        if foto.da_receita and parece_generica(imagem):
            self._lembrar(chave, 404, FOTO_GENERICA)
            if esquecer is not None:
                esquecer(foto.url)
            raise RespostaDeErro(_erro(FOTO_GENERICA, 404), 404)
        self._gravar(chave, imagem)
        return imagem.conteudo, imagem.tipo

    def _lembrar(self, chave: str, status: int, mensagem: str) -> None:
        with self._trava:
            self._falhas[chave] = (self._relogio(), status, mensagem)

    def _gravar(self, chave: str, imagem: ImagemBaixada) -> None:
        """Grava de uma vez só: quem lê ao mesmo tempo vê o arquivo inteiro ou nenhum."""
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / f"{chave}.{imagem.extensao}"
        provisorio = self.pasta / f".{chave}.{threading.get_ident()}.parcial"
        provisorio.write_bytes(imagem.conteudo)
        provisorio.replace(destino)


def _erro(mensagem: str, status: int) -> RespostaPadrao:
    categoria = "ausente" if status == 404 else "rede"  # noqa: PLR2004
    return RespostaPadrao(ok=False, erro=mensagem, categoria=categoria)


def acervo_do_app(requisicao: Request, sessao: Sessao) -> AcervoDeImagens:
    """O acervo do app, criado na primeira foto, em `imagens/` ao lado do dossiê."""
    acervo: AcervoDeImagens | None = getattr(requisicao.app.state, "imagens", None)
    if acervo is None:
        acervo = AcervoDeImagens(Path(sessao.dossie.caminho).parent / PASTA_DO_CACHE)
        requisicao.app.state.imagens = acervo
    return acervo


def _registrada(sessao: Sessao, chave: str) -> Foto:
    from mise.fotos import foto_pela_chave  # noqa: PLC0415

    foto = foto_pela_chave(sessao, chave) if _CHAVE.match(chave) else None
    if foto is None:
        raise RespostaDeErro(_erro(SEM_FOTO, 404), 404)
    return foto


@roteador.get("/api/imagens/{chave}")
def imagem(chave: str, requisicao: Request, sessao: SessaoDaApp) -> Response:
    """A foto registrada com esta chave, do cache ou baixada agora; 404 se não é registrada."""
    if not _CHAVE.match(chave):
        raise RespostaDeErro(_erro(SEM_FOTO, 404), 404)
    acervo = acervo_do_app(requisicao, sessao)
    guardada = acervo.guardada(chave)
    if guardada is None:
        guardada = acervo.baixar(_registrada(sessao, chave), esquecer=sessao.catalogo.esquecer_foto)
    conteudo, tipo = guardada
    return Response(content=conteudo, media_type=tipo, headers=_CABECALHOS)


@roteador.get("/api/imagens/{chave}/credito", response_model=RespostaPadrao)
def credito(chave: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """`{credito, licenca, fonte_url}` da foto registrada com esta chave."""
    return RespostaPadrao(dados=_registrada(sessao, chave).credito_json())


__all__ = [
    "CACHE_LONGO",
    "DESCANSO_DA_FALHA_S",
    "AcervoDeImagens",
    "acervo_do_app",
    "roteador",
]
