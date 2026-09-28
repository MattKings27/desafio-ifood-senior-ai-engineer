#!/usr/bin/env python3
"""Higiene do texto versionado: o que nenhum linter confere e qualquer leitor nota.

Três regras, em todo arquivo de texto que o git versiona:

1. **Travessão não separa ideias.** Um travessão com espaço dos dois lados vira
   vírgula, dois-pontos, ponto ou parênteses. O modelo imita a pontuação que lê,
   a Dona Maria lê vírgula e ponto, e o texto do repositório segue a mesma regra.
   O travessão sozinho, como símbolo (o valor ausente na tela), continua valendo.
2. **Nenhum caminho da máquina de quem escreveu**: a pasta pessoal do Linux, um
   disco do Windows montado no WSL, um disco do Windows. O que só existe numa
   máquina não serve a mais ninguém.
3. **Nenhum plural com "(s)" nos textos da interface.** "1 receita(s)" é a tela
   admitindo que não contou; quem conta escreve a palavra certa. Vale para as
   strings e o texto JSX de `webapp/src`, fora os testes.

Ficam de fora as gravações, que guardam o texto como ele veio: as conversas
reais em `docs/transcricoes/`, as páginas de terceiros em `scripts/tests/fixtures/` e
as receitas do catálogo inicial (`dados/catalogo_inicial.json`), com os passos
iguais aos do site de onde vieram.

    python scripts/higiene.py              # confere o repositório
    python scripts/higiene.py a.py b.tsx   # confere só estes arquivos

Saída: 0 limpo; 1 com achados, um por linha (`arquivo:linha: regra: trecho`).
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RAIZ: Final = Path(__file__).resolve().parents[1]

#: Gravações: o texto fica como veio, com a pontuação de quem escreveu.
GRAVACOES: Final = (
    "docs/transcricoes/",
    "scripts/tests/fixtures/",
    "dados/catalogo_inicial.json",
)

#: Travessão (ou meia-risca) entre espaços, ou no começo e no fim da linha.
_TRAVESSAO: Final = re.compile(r"(?:^|\s)[—–](?:\s|$)", re.MULTILINE)

#: Pasta pessoal, disco do Windows montado no WSL, disco do Windows.
_CAMINHO_LOCAL: Final = re.compile(
    r"(?<![\w.])(?:/home/[A-Za-z0-9._-]+|/mnt/[a-z]/[A-Za-z0-9._-]+)"
    r"|(?<![\w?])[A-Z]:\\{1,2}[A-Za-z0-9._-]"
)

#: "receita(s)", "valor(es)", "porção(ões)".
_PLURAL: Final = re.compile(r"[A-Za-zÀ-ÿ]\((?:s|es|ões)\)")

#: O que a tela mostra: o miolo de uma string e o texto entre duas tags JSX.
_TEXTO_DA_TELA: Final = re.compile(
    r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`|>([^<>{}\n]+)<"
)

_INTERFACE: Final = "webapp/src/"
_EXTENSOES_DA_INTERFACE: Final = (".ts", ".tsx")
_TESTES: Final = re.compile(r"\.(?:test|spec)\.tsx?$|(?:^|/)(?:teste|e2e)/")


@dataclass(frozen=True, slots=True)
class Achado:
    """Uma linha que quebra uma regra."""

    caminho: str
    linha: int
    regra: str
    trecho: str

    def __str__(self) -> str:
        return f"{self.caminho}:{self.linha}: {self.regra}: {self.trecho}"


def _linha(texto: str, posicao: int) -> int:
    return texto.count("\n", 0, posicao) + 1


def _trecho(texto: str, inicio: int, fim: int) -> str:
    return texto[max(0, inicio - 30) : fim + 30].replace("\n", " ").strip()


def _e_da_interface(caminho: str) -> bool:
    return (
        caminho.startswith(_INTERFACE)
        and caminho.endswith(_EXTENSOES_DA_INTERFACE)
        and not _TESTES.search(caminho)
    )


def achados_no_texto(caminho: str, texto: str) -> list[Achado]:
    """As três regras aplicadas a um arquivo, pelo caminho relativo à raiz."""
    if caminho.startswith(GRAVACOES):
        return []
    achados = [
        Achado(
            caminho, _linha(texto, m.start()), regra, _trecho(texto, m.start(), m.end())
        )
        for regra, padrao in (
            ("travessão separando ideias", _TRAVESSAO),
            ("caminho de uma máquina", _CAMINHO_LOCAL),
        )
        for m in padrao.finditer(texto)
    ]
    if _e_da_interface(caminho):
        for m in _TEXTO_DA_TELA.finditer(texto):
            miolo = next(g for g in m.groups() if g is not None)
            inicio = m.start() + 1
            achados.extend(
                Achado(
                    caminho,
                    _linha(texto, inicio + p.start()),
                    "plural com (s)",
                    miolo.strip(),
                )
                for p in _PLURAL.finditer(miolo)
            )
    return sorted(achados, key=lambda a: (a.caminho, a.linha))


def arquivos_versionados(raiz: Path = RAIZ) -> list[str]:
    """Os caminhos que o git versiona, relativos à raiz."""
    saida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=raiz, capture_output=True, check=True
    ).stdout
    return [c for c in saida.decode("utf-8").split("\0") if c]


def ler_texto(arquivo: Path) -> str | None:
    """O conteúdo, se for texto em UTF-8; `None` para binário ou arquivo que sumiu."""
    try:
        bruto = arquivo.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return None
    if b"\0" in bruto:
        return None
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return None


def conferir(caminhos: list[str], raiz: Path = RAIZ) -> list[Achado]:
    """Os achados de todos os arquivos de texto da lista."""
    achados: list[Achado] = []
    for caminho in caminhos:
        texto = ler_texto(raiz / caminho)
        if texto is not None:
            achados.extend(achados_no_texto(caminho, texto))
    return achados


def main(argv: list[str] | None = None, raiz: Path = RAIZ) -> int:
    pedidos = sys.argv[1:] if argv is None else argv
    caminhos = (
        [Path(p).resolve().relative_to(raiz.resolve()).as_posix() for p in pedidos]
        if pedidos
        else arquivos_versionados(raiz)
    )
    achados = conferir(caminhos, raiz)
    for achado in achados:
        print(achado)
    if achados:
        quantos = "1 achado" if len(achados) == 1 else f"{len(achados)} achados"
        print(f"\n{quantos} de higiene. Reescreva a frase; não troque só o sinal.")
        return 1
    print(f"higiene: {len(caminhos)} arquivos conferidos, nada a corrigir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
