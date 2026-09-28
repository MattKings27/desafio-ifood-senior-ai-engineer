"""A prova do trecho: o texto que se lê na página, a codificação dela e a comparação literal."""

from __future__ import annotations

import io
import urllib.error
from email.message import Message
from typing import Any, Self

import openpyxl
import pytest

from retrieval.corpus.conferencia import (
    TAMANHO_MAXIMO,
    Documento,
    baixar,
    baixar_pagina,
    contem_trecho,
    decodificar,
    normalizar,
    texto_da_planilha,
    texto_visivel,
)

PAGINA = """<!doctype html>
<html><head><title>Título da aba</title><style>p { color: red }</style></head>
<body>
<nav>Menu</nav>
<script>var x = "não é texto";</script>
<h1>Boas práticas</h1>
<p>Os alimentos preparados devem ser conservados&nbsp;sob refrigeração
a temperaturas inferiores a 5&ordm;C.</p><p>Outro parágrafo</p>
<ul><li>um</li><li>dois</li></ul>texto<br>solto<br/>fim<img src="x"/>!
<noscript>habilite o javascript</noscript>
</body></html>"""


def test_texto_visivel_sem_roteiro_estilo_nem_cabeca() -> None:
    texto = texto_visivel(PAGINA)
    assert "Título da aba" not in texto
    assert "var x" not in texto
    assert "color" not in texto
    assert "javascript" not in texto
    assert "Boas práticas" in texto
    assert "conservados sob refrigeração a temperaturas inferiores a 5ºC." in texto
    assert "5ºC. Outro parágrafo" in texto, "blocos viram espaço"
    assert "um dois texto solto fim!" in texto


def test_texto_puro_so_e_normalizado() -> None:
    assert texto_visivel("linha um\n\n  linha   dois") == "linha um linha dois"


def test_normalizar_so_perdoa_espaco() -> None:
    espacos = "a\u00a0b\u2009c  d\u00ad\u00e9"
    assert normalizar(espacos) == "a b c d\u00e9"
    assert normalizar("e\u0301") == "\u00e9"


def test_trecho_literal_so_com_espacos_perdoados() -> None:
    texto = texto_visivel(PAGINA)
    assert contem_trecho(texto, "conservados sob\n refrigeração")
    assert not contem_trecho(texto, "Conservados sob refrigeração"), "caixa conta"
    assert not contem_trecho(texto, "conservados sob refrigeracao"), "acento conta"
    assert not contem_trecho(texto, "   ")


@pytest.mark.parametrize(
    ("bruto", "declarado", "esperado"),
    [
        ("ação".encode("iso-8859-1"), "iso-8859-1", "ação"),
        (b'<meta charset="windows-1252"><p>a\xe7\xe3o</p>', None, "ação"),
        ("ação".encode(), None, "ação"),
        ("ação".encode(), "nao-existe", "ação"),
        ("ação".encode("cp1252"), None, "ação"),
        (b"\x81\x8d", None, "��"),
    ],
)
def test_decodificar_pela_codificacao_declarada(
    bruto: bytes, declarado: str | None, esperado: str
) -> None:
    assert esperado in decodificar(bruto, declarado)


def _planilha() -> bytes:
    livro = openpyxl.Workbook()
    aba = livro.active
    assert aba is not None
    aba.append(["BRASIL", "GLP", 3301, "R$/13kg", 114.8])
    aba.append([None, None])
    aba.append(["BRASIL", "GNV", None, "R$/m³", 4.75])
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def test_planilha_vira_linhas_com_as_celulas_separadas() -> None:
    texto = texto_da_planilha(_planilha())
    assert texto == "BRASIL | GLP | 3301 | R$/13kg | 114.8 BRASIL | GNV | R$/m³ | 4.75"
    documento = Documento("https://x/p.xlsx", _planilha())
    assert documento.planilha
    assert contem_trecho(documento.texto(), "BRASIL | GLP | 3301 | R$/13kg | 114.8")
    html = Documento("https://x/p.html", PAGINA.encode(), "text/html", "utf-8")
    assert not html.planilha
    assert "Boas práticas" in html.texto()


class _Resposta:
    def __init__(self, bruto: bytes, tipo: str) -> None:
        self._bruto = io.BytesIO(bruto)
        self.headers = Message()
        self.headers["Content-Type"] = tipo

    def read(self, limite: int) -> bytes:
        return self._bruto.read(limite)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Abridor:
    def __init__(self, bruto: bytes, tipo: str) -> None:
        self.resposta = _Resposta(bruto, tipo)
        self.pedidos: list[Any] = []

    def open(self, requisicao: Any, timeout: float) -> _Resposta:
        self.pedidos.append((requisicao, timeout))
        return self.resposta


def test_baixar_pelo_abridor_com_o_tipo_e_a_codificacao() -> None:
    abridor = _Abridor("<p>ação</p>".encode("iso-8859-1"), "text/html; charset=ISO-8859-1")
    documento = baixar("https://exemplo.com.br/a", abridor)  # type: ignore[arg-type]
    assert (documento.tipo, documento.codificacao) == ("text/html", "iso-8859-1")
    assert documento.texto() == "ação"
    requisicao, tempo = abridor.pedidos[0]
    assert requisicao.get_header("User-agent").startswith("Mozilla/5.0")
    assert tempo > 0
    pagina = baixar_pagina(
        "https://exemplo.com.br/a",
        _Abridor("<p>ação</p>".encode("iso-8859-1"), "text/html; charset=ISO-8859-1"),  # type: ignore[arg-type]
    )
    assert pagina == "<p>ação</p>"


def test_pagina_grande_demais_nao_e_lida() -> None:
    abridor = _Abridor(b"x" * (TAMANHO_MAXIMO + 1), "text/html")
    with pytest.raises(urllib.error.URLError, match="grande demais"):
        baixar("https://exemplo.com.br/a", abridor)  # type: ignore[arg-type]
