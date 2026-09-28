"""A prova de que o trecho citado está na página, palavra por palavra.

Todo fato da base de conhecimento culinário traz um `trecho` copiado da página
de onde ele saiu, com o endereço e a data da conferência. Este módulo é quem
confere: baixa a página, tira o texto que uma pessoa lê nela (sem roteiro, sem
estilo, sem marcação) e procura o trecho ali, literal.

A comparação só perdoa o que não muda o texto que ela leria: espaços repetidos,
quebras de linha, o espaço que não quebra e o hífen invisível de separação de
sílabas. Caixa, acento, pontuação e aspas continuam valendo. Um trecho que
precisou de outra tolerância para casar não é citação, é paráfrase, e paráfrase
não prova nada.

Uma planilha publicada como fonte (a pesquisa semanal de preços da ANP sai em
`.xlsx`) é lida como texto também: cada linha de cada aba, com as células que
têm valor separadas por " | ", do jeito que o `openpyxl` as lê.

A mesma função serve ao `scripts/conferir_conhecimento.py` (que busca as páginas
de verdade) e aos testes (que usam as páginas gravadas), para os dois nunca
discordarem sobre o que é "o trecho está lá".
"""

from __future__ import annotations

import html
import io
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

#: O que não é texto de ler: o conteúdo destas marcas nunca entra.
_INVISIVEIS: Final = frozenset({"script", "style", "noscript", "template", "svg", "head"})

#: Marcas que separam blocos: viram espaço, para duas células não virarem uma palavra.
_BLOCOS: Final = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "td",
        "th",
        "table",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "blockquote",
        "dd",
        "dt",
        "dl",
        "figcaption",
        "caption",
        "hr",
        "main",
        "nav",
        "aside",
        "form",
        "option",
        "pre",
    }
)

#: Caracteres que a tela mostra como espaço (ou como nada) e que não mudam a leitura.
_COMO_ESPACO: Final = re.compile(r"[\s\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
_INVISIVEL: Final = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")

#: O `charset` declarado no cabeçalho ou na própria página.
_CHARSET: Final = re.compile(rb"""charset\s*=\s*["']?([A-Za-z0-9_\-:.]+)""", re.IGNORECASE)

#: Quanto do começo da página se olha atrás do `charset` declarado.
_CABECA: Final = 4096

#: A página mais longa que a conferência aceita baixar.
TAMANHO_MAXIMO: Final = 8 * 1024 * 1024

#: Tempo máximo esperando uma página, em segundos.
TEMPO_LIMITE: Final = 20.0

#: Como a conferência se apresenta ao site.
AGENTE: Final = "Mozilla/5.0 (compatible; SaborDaMaria-conferencia/1.0)"


class _Leitor(HTMLParser):
    """Junta o texto visível da página, na ordem em que aparece."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pedacos: list[str] = []
        self._escondido = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in _INVISIVEIS:
            self._escondido += 1
        elif tag in _BLOCOS:
            self.pedacos.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in _BLOCOS:
            self.pedacos.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _INVISIVEIS:
            self._escondido = max(0, self._escondido - 1)
        elif tag in _BLOCOS:
            self.pedacos.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._escondido:
            self.pedacos.append(data)


def normalizar(texto: str) -> str:
    """O texto como ela leria: NFC, sem hífen invisível, espaços juntos num só."""
    composto = unicodedata.normalize("NFC", html.unescape(texto))
    return _COMO_ESPACO.sub(" ", _INVISIVEL.sub("", composto)).strip()


def texto_visivel(pagina: str) -> str:
    """O texto que uma pessoa lê na página, normalizado.

    Texto puro (sem nenhuma marca) passa só pela normalização: é assim que a
    conferência lê um arquivo `.txt` publicado como página.
    """
    if "<" not in pagina:
        return normalizar(pagina)
    leitor = _Leitor()
    leitor.feed(pagina)
    leitor.close()
    return normalizar("".join(leitor.pedacos))


def contem_trecho(texto_da_pagina: str, trecho: str) -> bool:
    """O trecho está na página, literal (só os espaços são perdoados)?"""
    procurado = normalizar(trecho)
    return bool(procurado) and procurado in normalizar(texto_da_pagina)


def decodificar(bruto: bytes, declarado: str | None = None) -> str:
    """Os bytes da página como texto, na codificação que ela declara.

    A ordem: o `charset` do cabeçalho HTTP, o da própria página, UTF-8 estrito e,
    se nada disso servir, Windows-1252, que é o que as páginas antigas do governo
    usam sem dizer.
    """
    candidatos: list[str] = []
    if declarado:
        candidatos.append(declarado)
    if achado := _CHARSET.search(bruto[:_CABECA]):
        candidatos.append(achado.group(1).decode("ascii", errors="ignore"))
    candidatos.append("utf-8")
    for codificacao in candidatos:
        try:
            return bruto.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue
    return bruto.decode("cp1252", errors="replace")


#: O começo de todo arquivo ZIP, e portanto de toda planilha `.xlsx`.
_ZIP: Final = b"PK\x03\x04"


@dataclass(frozen=True, slots=True)
class Documento:
    """O que a página devolveu: os bytes, o tipo e a codificação que ela declara."""

    url: str
    bruto: bytes
    tipo: str = ""
    codificacao: str | None = None

    @property
    def planilha(self) -> bool:
        return "spreadsheet" in self.tipo or self.bruto.startswith(_ZIP)

    def texto(self) -> str:
        """O texto que se lê no documento, normalizado."""
        if self.planilha:
            return texto_da_planilha(self.bruto)
        return texto_visivel(decodificar(self.bruto, self.codificacao))


def texto_da_planilha(bruto: bytes) -> str:
    """Cada linha de cada aba, com as células que têm valor separadas por " | "."""
    import openpyxl  # noqa: PLC0415 (só a conferência de planilha precisa dele)

    livro = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True, data_only=True)
    try:
        linhas = [
            " | ".join(str(valor) for valor in linha if valor is not None)
            for aba in livro.worksheets
            for linha in aba.iter_rows(values_only=True)
        ]
    finally:
        livro.close()
    return normalizar("\n".join(linha for linha in linhas if linha))


def baixar(url: str, abrir: urllib.request.OpenerDirector | None = None) -> Documento:
    """O documento, pelo abridor seguro (só endereço público).

    Levanta `urllib.error.URLError` quando a página não vem: a conferência
    registra a falha e diz qual fato ficou sem prova, em vez de dar por provado.
    """
    from retrieval.rede import abridor  # noqa: PLC0415

    requisicao = urllib.request.Request(
        url,
        headers={"User-Agent": AGENTE, "Accept": "text/html,application/xhtml+xml,text/plain,*/*"},
    )
    with (abrir or abridor()).open(requisicao, timeout=TEMPO_LIMITE) as resposta:
        bruto: bytes = resposta.read(TAMANHO_MAXIMO + 1)
        tipo = resposta.headers.get_content_type() or ""
        declarado = resposta.headers.get_content_charset()
    if len(bruto) > TAMANHO_MAXIMO:
        raise urllib.error.URLError(f"página grande demais: {url}")
    return Documento(url, bruto, tipo, declarado)


def baixar_pagina(url: str, abrir: urllib.request.OpenerDirector | None = None) -> str:
    """O HTML (ou o texto) da página, já decodificado."""
    documento = baixar(url, abrir)
    return decodificar(documento.bruto, documento.codificacao)


__all__ = [
    "AGENTE",
    "TAMANHO_MAXIMO",
    "TEMPO_LIMITE",
    "Documento",
    "baixar",
    "baixar_pagina",
    "contem_trecho",
    "decodificar",
    "normalizar",
    "texto_da_planilha",
    "texto_visivel",
]
