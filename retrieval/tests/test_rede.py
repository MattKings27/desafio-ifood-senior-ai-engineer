"""A busca não conversa com a rede de dentro, nem por redirecionamento."""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from retrieval import rede
from retrieval.busca import UrlRecusada, _baixar, validar
from retrieval.rede import DestinoProibido, abridor, destino_seguro, endereco_publico


@pytest.mark.parametrize(
    ("ip", "publico"),
    [
        ("127.0.0.1", False),
        ("10.0.0.1", False),
        ("172.16.5.4", False),
        ("192.168.0.10", False),
        ("169.254.169.254", False),  # metadados da nuvem
        ("100.64.0.1", False),  # rede da operadora
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fc00::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:127.0.0.1", False),  # IPv4 de loopback dentro de IPv6
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
    ],
)
def test_so_endereco_publico_passa(ip: str, publico: bool) -> None:
    assert endereco_publico(ip) is publico


def test_nome_que_mistura_publico_e_privado_e_recusado() -> None:
    with pytest.raises(DestinoProibido, match=r"10\.0\.0\.9"):
        destino_seguro("truque.test", 80, lambda _h, _p: ["8.8.8.8", "10.0.0.9"])


def test_nome_publico_devolve_onde_conectar() -> None:
    assert destino_seguro("site.test", 443, lambda _h, _p: ["8.8.8.8"]) == "8.8.8.8"


def test_nome_que_nao_resolve_e_recusado() -> None:
    def falha(_h: str, _p: int) -> list[str]:
        raise socket.gaierror("sem nome")

    with pytest.raises(DestinoProibido, match="não consegui resolver"):
        destino_seguro("nada.test", 80, falha)
    with pytest.raises(DestinoProibido, match="endereço nenhum"):
        destino_seguro("vazio.test", 80, lambda _h, _p: [])


def test_url_com_usuario_embutido_e_recusada() -> None:
    with pytest.raises(UrlRecusada, match="usuário ou senha"):
        validar("http://tudogostoso.com.br@10.0.0.1/receita")


def test_o_abridor_nao_traz_o_manipulador_padrao() -> None:
    """O HTTPHandler padrão não valida nada; se entrasse, contornaria tudo."""
    tipos = {type(m) for m in abridor().handlers}
    assert urllib.request.HTTPHandler not in tipos
    assert urllib.request.HTTPSHandler not in tipos


# --------------------------------------------------------------------------- #
# De ponta a ponta, com servidor de verdade
# --------------------------------------------------------------------------- #


class _Servidor(http.server.BaseHTTPRequestHandler):
    recebidas: list[str] = []  # noqa: RUF012
    destino: str = ""

    def do_GET(self) -> None:
        _Servidor.recebidas.append(self.path)
        if _Servidor.destino:
            self.send_response(302)
            self.send_header("Location", _Servidor.destino)
        else:
            self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<html>segredo interno</html>")

    def log_message(self, *_: object) -> None:
        return None


@pytest.fixture
def servidor_local() -> Iterator[int]:
    _Servidor.recebidas = []
    _Servidor.destino = ""
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Servidor)
    fio = threading.Thread(target=httpd.serve_forever, daemon=True)
    fio.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_servidor_na_maquina_e_recusado_sem_receber_requisicao(servidor_local: int) -> None:
    """A API do próprio motor roda em localhost; a busca não pode chegar nela."""
    with pytest.raises(UrlRecusada, match="não é público"):
        _baixar(f"http://127.0.0.1:{servidor_local}/api/despensa")
    assert _Servidor.recebidas == [], "a recusa tem que vir antes de conectar"


def test_redirecionamento_para_dentro_e_recusado(
    servidor_local: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma página "pública" manda a busca para a rede interna."""
    # Só neste teste, o servidor em 127.0.0.1 faz o papel de site público.
    verdadeiro = rede.endereco_publico
    monkeypatch.setattr(rede, "endereco_publico", lambda ip: ip == "127.0.0.1" or verdadeiro(ip))
    _Servidor.destino = "http://interno.test/admin"
    nomes = {"publico.test": ["127.0.0.1"], "interno.test": ["10.0.0.5"]}
    abrir = abridor(lambda host, _p: nomes[host])

    with pytest.raises((DestinoProibido, urllib.error.URLError)) as capturado:
        abrir.open(f"http://publico.test:{servidor_local}/receita", timeout=5)
    assert "10.0.0.5" in str(capturado.value)
    assert _Servidor.recebidas == ["/receita"], "o primeiro salto foi; o segundo, não"


def test_redirecionamento_para_outro_esquema_e_recusado(
    servidor_local: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdadeiro = rede.endereco_publico
    monkeypatch.setattr(rede, "endereco_publico", lambda ip: ip == "127.0.0.1" or verdadeiro(ip))
    _Servidor.destino = "file:///etc/passwd"
    abrir = abridor(lambda _h, _p: ["127.0.0.1"])
    # A biblioteca padrão já recusa esse salto; a checagem daqui é a segunda camada.
    with pytest.raises((DestinoProibido, urllib.error.HTTPError), match=r"esquema|not allowed"):
        abrir.open(f"http://publico.test:{servidor_local}/", timeout=5)


def test_segunda_camada_recusa_esquema_estranho() -> None:
    manipulador = rede._Redirecionamento()
    requisicao = urllib.request.Request("http://publico.test/")
    with pytest.raises(DestinoProibido, match="esquema"):
        manipulador.redirect_request(requisicao, None, 302, "Found", {}, "gopher://interno/")


def test_https_passa_pela_mesma_checagem() -> None:
    abrir = abridor(lambda _h, _p: ["169.254.169.254"])
    with pytest.raises((DestinoProibido, urllib.error.URLError)) as capturado:
        abrir.open("https://metadados.test/latest/meta-data/", timeout=5)
    assert "169.254.169.254" in str(capturado.value)
