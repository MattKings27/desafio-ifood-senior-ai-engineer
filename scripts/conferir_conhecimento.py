"""Prova que cada trecho citado continua na página de onde saiu.

Confere duas coisas que o agente cita com fonte:

- os fatos da base de cozinha (`retrieval/src/retrieval/conhecimento/*.yaml`);
- os valores padrão das premissas do preço preliminar (`mise.parametros`): o
  salário mínimo por hora, o botijão, o kWh e as potências dos aparelhos.

Para cada endereço, busca a página uma vez (pelo abridor seguro, só endereço
público), tira o texto que se lê nela e procura cada trecho ali, letra por
letra (`retrieval.corpus.conferencia`). Trecho que não está mais na página, ou
página que não vem, reprova: o fato fica sem prova, e sem prova ele sai.

    python scripts/conferir_conhecimento.py              # busca as páginas agora
    python scripts/conferir_conhecimento.py --gravar     # e grava o trecho de cada página
    python scripts/conferir_conhecimento.py --gravadas   # confere com o que foi gravado

O que `--gravar` guarda (`scripts/tests/fixtures/conhecimento_paginas.json`) é o
pedaço de cada página em volta de cada trecho, com a data. É com ele que os
testes refazem a prova sem rede: se alguém mudar um trecho no YAML, ele deixa
de estar no pedaço gravado da página, e o teste reprova.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

RAIZ: Final = Path(__file__).resolve().parents[1]
GRAVADAS: Final = RAIZ / "scripts" / "tests" / "fixtures" / "conhecimento_paginas.json"

#: Quanto do texto da página, antes e depois de cada trecho, a gravação guarda.
MARGEM: Final = 300


@dataclass(frozen=True, slots=True)
class Citacao:
    """Um trecho que alguém cita, e a página que deve contê-lo."""

    id: str
    url: str
    trecho: str


def citacoes() -> list[Citacao]:
    """Os fatos da base de cozinha e as fontes dos padrões do preço preliminar."""
    from mise.parametros import PARAMETROS
    from retrieval.corpus.conhecimento import carregar_fatos

    todas = [
        Citacao(f"conhecimento:{f.id}", f.fonte_url, f.trecho) for f in carregar_fatos()
    ]
    todas += [
        Citacao(f"parametro:{p.nome}", p.fonte.url, p.fonte.trecho)
        for p in PARAMETROS
        if p.fonte is not None
    ]
    return todas


#: Lê o texto de uma página pelo endereço.
Leitor = Callable[[str], str]


def ler_da_rede(url: str) -> str:
    """O texto da página, buscado agora."""
    from retrieval.corpus.conferencia import baixar

    return baixar(url).texto()


def conferir(
    lista: Sequence[Citacao], ler: Leitor
) -> tuple[list[tuple[Citacao, str]], dict[str, str]]:
    """Cada citação com o resultado ("" quando está lá) e o texto de cada página lida."""
    from retrieval.corpus.conferencia import contem_trecho

    paginas: dict[str, str] = {}
    falhas: dict[str, str] = {}
    for url in dict.fromkeys(c.url for c in lista):
        try:
            paginas[url] = ler(url)
        except (urllib.error.URLError, OSError, ValueError) as erro:
            falhas[url] = f"a página não veio ({erro})"
    resultado: list[tuple[Citacao, str]] = []
    for citacao in lista:
        if citacao.url in falhas:
            resultado.append((citacao, falhas[citacao.url]))
        elif not contem_trecho(paginas[citacao.url], citacao.trecho):
            resultado.append((citacao, "o trecho não está mais na página"))
        else:
            resultado.append((citacao, ""))
    return resultado, paginas


def janelas(texto: str, trechos: Iterable[str]) -> list[str]:
    """O pedaço da página em volta de cada trecho, para a prova sem rede."""
    from retrieval.corpus.conferencia import normalizar

    pagina = normalizar(texto)
    pedacos: list[str] = []
    for trecho in trechos:
        inicio = pagina.find(normalizar(trecho))
        if inicio < 0:
            continue
        fim = inicio + len(normalizar(trecho))
        pedacos.append(pagina[max(0, inicio - MARGEM) : fim + MARGEM])
    return pedacos


def gravar(
    lista: Sequence[Citacao], paginas: dict[str, str], destino: Path, hoje: dt.date
) -> None:
    """Guarda o pedaço de cada página em volta dos trechos dela."""
    por_url: dict[str, list[str]] = {}
    for citacao in lista:
        por_url.setdefault(citacao.url, []).append(citacao.trecho)
    gravado: dict[str, Any] = {
        "gravado_em": hoje.isoformat(),
        "paginas": {
            url: {"janelas": janelas(paginas[url], trechos)}
            for url, trechos in sorted(por_url.items())
            if url in paginas
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(gravado, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )


def ler_gravadas(origem: Path = GRAVADAS) -> Leitor:
    """Um leitor que devolve os pedaços gravados de cada página, sem rede."""
    gravado = json.loads(origem.read_text("utf-8"))
    paginas: dict[str, Any] = gravado["paginas"]

    def ler(url: str) -> str:
        if url not in paginas:
            raise ValueError("a página não foi gravada")
        return "\n".join(paginas[url]["janelas"])

    return ler


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--gravar", action="store_true", help="grava o pedaço de cada página"
    )
    modo.add_argument(
        "--gravadas", action="store_true", help="confere com as páginas gravadas"
    )
    parser.add_argument(
        "--arquivo", type=Path, default=GRAVADAS, help="onde gravar ou ler"
    )
    opcoes = parser.parse_args(argumentos)

    lista = citacoes()
    ler = ler_gravadas(opcoes.arquivo) if opcoes.gravadas else ler_da_rede
    resultado, paginas = conferir(lista, ler)
    for citacao, problema in resultado:
        marca = "ok   " if not problema else "FALTA"
        detalhe = f"  ({problema})" if problema else ""
        print(f"{marca} {citacao.id}{detalhe}")
    falhas = [c for c, problema in resultado if problema]
    origem = "páginas gravadas" if opcoes.gravadas else "páginas buscadas agora"
    print(
        f"\n{len(resultado) - len(falhas)} de {len(resultado)} trechos conferidos "
        f"em {len(paginas)} {origem}"
    )
    if opcoes.gravar:
        if falhas:
            print("nada foi gravado: há trecho sem prova")
            return 1
        gravar(lista, paginas, opcoes.arquivo, dt.datetime.now(tz=dt.UTC).date())
        print(f"gravado em {opcoes.arquivo}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
