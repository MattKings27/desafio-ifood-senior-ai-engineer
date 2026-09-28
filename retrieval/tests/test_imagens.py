"""A foto chega pelas mesmas travas da página: endereço público, até 5 MB, tipo pelos bytes."""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.request
from collections.abc import Iterator

import pytest

from retrieval import rede
from retrieval.imagens import (
    EXTENSOES,
    TAMANHO_MAXIMO_DA_IMAGEM,
    TAMANHO_MINIMO_DA_FOTO_DE_RECEITA,
    ImagemBaixada,
    ImagemIndisponivel,
    ImagemRecusada,
    baixar_imagem,
    parece_generica,
    tipo_pelos_bytes,
    validar_endereco,
)
from retrieval.rede import abridor

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
AVIF = b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1miaf" + b"\x00" * 64
AVIF_COMPATIVEL = b"\x00\x00\x00\x1cftypmif1\x00\x00\x00\x00mif1avifmiaf" + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = "<!doctype html><html><body>não é foto</body></html>".encode()


@pytest.mark.parametrize(
    ("bruto", "tipo"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (GIF, "image/gif"),
        (WEBP, "image/webp"),
        (AVIF, "image/avif"),
        (AVIF_COMPATIVEL, "image/avif"),
        (HEIC, None),
        (SVG, None),
        (HTML, None),
        (b"", None),
        (b"RIFF", None),
    ],
)
def test_o_tipo_sai_dos_bytes(bruto: bytes, tipo: str | None) -> None:
    assert tipo_pelos_bytes(bruto) == tipo
    if tipo is not None:
        assert tipo in EXTENSOES


@pytest.mark.parametrize(
    ("url", "motivo"),
    [
        ("file:///etc/passwd", "só baixo foto por http e https"),
        ("ftp://site.test/foto.jpg", "só baixo foto por http e https"),
        ("https:///foto.jpg", "sem domínio"),
        ("https://site.test@10.0.0.1/foto.jpg", "usuário ou senha"),
    ],
)
def test_endereco_que_nao_se_busca(url: str, motivo: str) -> None:
    with pytest.raises(ImagemRecusada, match=motivo):
        validar_endereco(url)


# --------------------------------------------------------------------------- #
# Com um servidor de verdade                                                   #
# --------------------------------------------------------------------------- #


class _Fotos(http.server.BaseHTTPRequestHandler):
    recebidas: list[str] = []  # noqa: RUF012
    corpos: dict[str, tuple[int, bytes, dict[str, str]]] = {}  # noqa: RUF012

    def do_GET(self) -> None:
        _Fotos.recebidas.append(self.path)
        status, corpo, cabecalhos = _Fotos.corpos.get(self.path, (404, b"", {}))
        self.send_response(status)
        for nome, valor in cabecalhos.items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_: object) -> None:
        return None


@pytest.fixture
def servidor() -> Iterator[int]:
    _Fotos.recebidas = []
    _Fotos.corpos = {}
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Fotos)
    fio = threading.Thread(target=httpd.serve_forever, daemon=True)
    fio.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def como_publico(monkeypatch: pytest.MonkeyPatch) -> None:
    """Só nestes testes, o servidor em 127.0.0.1 faz o papel de site público."""
    verdadeiro = rede.endereco_publico
    monkeypatch.setattr(rede, "endereco_publico", lambda ip: ip == "127.0.0.1" or verdadeiro(ip))


def _abrir() -> urllib.request.OpenerDirector:
    return abridor(lambda _h, _p: ["127.0.0.1"])


@pytest.mark.usefixtures("como_publico")
def test_foto_publica_chega_com_o_tipo_dos_bytes(servidor: int) -> None:
    # O servidor diz que é texto; o que vale são os bytes.
    _Fotos.corpos["/foto"] = (200, JPEG, {"Content-Type": "text/plain"})
    imagem = baixar_imagem(f"http://fotos.test:{servidor}/foto", _abrir())
    assert (imagem.conteudo, imagem.tipo, imagem.extensao) == (JPEG, "image/jpeg", "jpg")


@pytest.mark.usefixtures("como_publico")
def test_svg_nunca_passa(servidor: int) -> None:
    _Fotos.corpos["/foto.svg"] = (200, SVG, {"Content-Type": "image/svg+xml"})
    with pytest.raises(ImagemRecusada, match="não é uma foto"):
        baixar_imagem(f"http://fotos.test:{servidor}/foto.svg", _abrir())


@pytest.mark.usefixtures("como_publico")
def test_foto_grande_demais_e_recusada(servidor: int) -> None:
    grande = JPEG + b"\x00" * 200
    _Fotos.corpos["/grande"] = (200, grande, {})
    with pytest.raises(ImagemRecusada, match="5 MB"):
        baixar_imagem(
            f"http://fotos.test:{servidor}/grande",
            _abrir(),
            limite=100,
        )
    declarada = str(TAMANHO_MAXIMO_DA_IMAGEM + 1)
    _Fotos.corpos["/declarada"] = (200, JPEG, {"Content-Length": declarada})
    with pytest.raises(ImagemRecusada, match="5 MB"):
        baixar_imagem(f"http://fotos.test:{servidor}/declarada", _abrir())


@pytest.mark.usefixtures("como_publico")
def test_site_que_responde_erro(servidor: int) -> None:
    with pytest.raises(ImagemIndisponivel, match="HTTP 404"):
        baixar_imagem(f"http://fotos.test:{servidor}/sumiu", _abrir())


def test_endereco_de_dentro_e_recusado_sem_conectar(servidor: int) -> None:
    """Sem fingir que é público: 127.0.0.1 é recusado antes de a requisição sair."""
    _Fotos.corpos["/foto"] = (200, JPEG, {})
    with pytest.raises(ImagemRecusada, match="não é público"):
        baixar_imagem(f"http://127.0.0.1:{servidor}/foto")
    with pytest.raises(ImagemRecusada, match="não é público"):
        baixar_imagem(
            "http://metadados.test/foto",
            abridor(lambda _h, _p: ["169.254.169.254"]),
        )
    assert _Fotos.recebidas == []


@pytest.mark.usefixtures("como_publico")
def test_redirecionamento_para_dentro_e_recusado(servidor: int) -> None:
    _Fotos.corpos["/pula"] = (302, b"", {"Location": "http://interno.test/foto"})
    nomes = {"fotos.test": ["127.0.0.1"], "interno.test": ["10.0.0.5"]}
    with pytest.raises(ImagemRecusada, match=r"10\.0\.0\.5"):
        baixar_imagem(f"http://fotos.test:{servidor}/pula", abridor(lambda h, _p: nomes[h]))
    assert _Fotos.recebidas == ["/pula"]


@pytest.mark.usefixtures("como_publico")
def test_servidor_fora_do_ar() -> None:
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
    with pytest.raises(ImagemIndisponivel, match="não consegui falar"):
        baixar_imagem(f"http://fotos.test:{porta}/foto", _abrir())


def test_foto_de_receita_pequena_demais_e_a_generica_do_site() -> None:
    """O chapéu cinza do TudoGostoso tem uns 3 KB; a foto de um prato, muito mais."""
    assert parece_generica(ImagemBaixada(PNG + b"\x00" * 3000, "image/png"))
    no_limite = JPEG + b"\x00" * (TAMANHO_MINIMO_DA_FOTO_DE_RECEITA - len(JPEG))
    assert not parece_generica(ImagemBaixada(no_limite, "image/jpeg"))
