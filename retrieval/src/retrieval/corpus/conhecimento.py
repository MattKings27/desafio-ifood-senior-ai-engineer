"""A base de conhecimento de cozinha: cada fato com a página e o trecho que o provam.

Os fatos moram em `retrieval/conhecimento/*.yaml`, um arquivo por assunto
(técnica, equipamento, conservação e segurança, entrega, operação, preço).
Cada fato traz:

- `texto`: o que o fato diz, em português dela, sem acrescentar nada que a
  fonte não diga;
- `trecho`: as palavras da página, copiadas letra por letra;
- `fonte_titulo`, `fonte_url` e `verificado_em`: de onde, e quando alguém
  conferiu que o trecho estava lá.

`scripts/conferir_conhecimento.py` busca cada página de novo e prova que o
trecho continua nela (`retrieval.corpus.conferencia`). Fato sem página que o
sustente não entra: conhecimento sem procedência é palpite com formatação
melhor.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import yaml

from retrieval.corpus.modelo import Trecho

#: A pasta dos fatos, dentro do pacote, para viajar com ele.
PASTA: Final = Path(__file__).resolve().parents[1] / "conhecimento"

#: Os assuntos da base, e como cada um é dito para ela.
CATEGORIAS: Final[dict[str, str]] = {
    "tecnica": "técnica de cozinha",
    "equipamento": "equipamento de cozinha",
    "conservacao": "conservação dos alimentos",
    "seguranca": "segurança dos alimentos",
    "delivery": "entrega e embalagem",
    "operacao": "operação da cozinha",
    "preco": "preço e custo",
}

#: Um travessão ou hífen usado como separador de frase: não entra em texto que chega a ela.
SEPARADOR_PROIBIDO: Final = re.compile(r" [\u2014\u2013-] ")

#: Palavras internas que não chegam a ela, nem por citação.
JARGAO: Final = re.compile(
    r"\b(?:cmv|food cost|motor|port[aã]o|veredito|apto|bloqueado|falta info)\b", re.IGNORECASE
)

_ID: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_CAMPOS: Final = (
    "id",
    "titulo",
    "categoria",
    "texto",
    "trecho",
    "fonte_titulo",
    "fonte_url",
    "verificado_em",
)


class FatoInvalido(ValueError):  # noqa: N818 (o nome diz o que aconteceu, como no projeto)
    """Um fato da base que não segue a regra: sem fonte, com jargão, com id repetido."""


@dataclass(frozen=True, slots=True)
class Fato:
    """Um fato de cozinha, com a página e o trecho que o sustentam."""

    id: str
    titulo: str
    categoria: str
    texto: str
    trecho: str
    fonte_titulo: str
    fonte_url: str
    verificado_em: dt.date
    palavras: tuple[str, ...] = ()
    arquivo: str = ""

    @property
    def dominio(self) -> str:
        """O site da fonte, sem o `www.`: "gov.br", "pt.wikipedia.org"."""
        return (urlsplit(self.fonte_url).hostname or "").removeprefix("www.")

    def para_trecho(self) -> Trecho:
        """O fato como trecho do corpus, com a fonte e o trecho literal à vista."""
        data = self.verificado_em.strftime("%d/%m/%Y")
        return Trecho(
            id=f"conhecimento:{self.id}",
            tipo="conhecimento",
            rota=None,
            fonte=self.fonte_titulo,
            cabecalho=f"Conhecimento de cozinha, {CATEGORIAS[self.categoria]}, {self.titulo}:",
            corpo=(f"{self.texto} Na fonte ({self.dominio}, conferida em {data}): “{self.trecho}”"),
            palavras=self.palavras,
        )


def _texto(bruto: object) -> str:
    return " ".join(str(bruto).split()) if bruto is not None else ""


def _fato(bruto: Any, arquivo: str) -> Fato:
    if not isinstance(bruto, dict):
        raise FatoInvalido(f"{arquivo}: cada fato é um mapa com {', '.join(_CAMPOS)}")
    faltam = [c for c in _CAMPOS if not bruto.get(c)]
    if faltam:
        raise FatoInvalido(f"{arquivo}: fato {bruto.get('id')!r} sem {', '.join(faltam)}")
    fato_id = str(bruto["id"])
    if not _ID.fullmatch(fato_id):
        raise FatoInvalido(f"{arquivo}: id {fato_id!r} fora do formato (minúsculas e hífen)")
    categoria = str(bruto["categoria"])
    if categoria not in CATEGORIAS:
        raise FatoInvalido(f"{arquivo}: {fato_id} com categoria desconhecida {categoria!r}")
    url = str(bruto["fonte_url"])
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).hostname:
        raise FatoInvalido(f"{arquivo}: {fato_id} com endereço que não é página: {url!r}")
    verificado = bruto["verificado_em"]
    if isinstance(verificado, str):
        verificado = dt.date.fromisoformat(verificado)
    if not isinstance(verificado, dt.date):
        raise FatoInvalido(f"{arquivo}: {fato_id} sem data de conferência válida")
    texto, trecho = _texto(bruto["texto"]), _texto(bruto["trecho"])
    for nome, valor in (("texto", texto), ("trecho", trecho), ("titulo", _texto(bruto["titulo"]))):
        if SEPARADOR_PROIBIDO.search(valor):
            raise FatoInvalido(f"{arquivo}: {fato_id} com travessão como separador no {nome}")
        if achado := JARGAO.search(valor):
            raise FatoInvalido(f"{arquivo}: {fato_id} com a palavra {achado.group()!r} no {nome}")
    return Fato(
        id=fato_id,
        titulo=_texto(bruto["titulo"]),
        categoria=categoria,
        texto=texto,
        trecho=trecho,
        fonte_titulo=_texto(bruto["fonte_titulo"]),
        fonte_url=url,
        verificado_em=verificado,
        palavras=tuple(_texto(p) for p in bruto.get("palavras") or ()),
        arquivo=arquivo,
    )


def carregar_fatos(pasta: Path = PASTA) -> tuple[Fato, ...]:
    """Todos os fatos da pasta, conferidos na forma, na ordem dos arquivos."""
    fatos: list[Fato] = []
    for caminho in sorted(pasta.glob("*.yaml")):
        bruto = yaml.safe_load(caminho.read_text("utf-8")) or []
        if not isinstance(bruto, list):
            raise FatoInvalido(f"{caminho.name}: o arquivo é uma lista de fatos")
        fatos.extend(_fato(item, caminho.name) for item in bruto)
    ids = [f.id for f in fatos]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise FatoInvalido(f"fatos com o mesmo id: {', '.join(repetidos)}")
    return tuple(fatos)


def trechos_do_conhecimento(fatos: Iterable[Fato] | None = None) -> list[Trecho]:
    """Os fatos como trechos do corpus."""
    return [f.para_trecho() for f in (carregar_fatos() if fatos is None else fatos)]


__all__ = [
    "CATEGORIAS",
    "JARGAO",
    "PASTA",
    "SEPARADOR_PROIBIDO",
    "Fato",
    "FatoInvalido",
    "carregar_fatos",
    "trechos_do_conhecimento",
]
