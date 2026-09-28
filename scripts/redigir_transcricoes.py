"""Redige as transcrições gravadas antes de publicá-las.

As conversas em `docs/transcricoes/` foram gravadas numa máquina de
desenvolvimento, e o que o agente viu nas ferramentas veio junto: caminhos
absolutos da pasta pessoal e do disco, e o nome de um canal de mensagens que
saiu do escopo. Este script troca cada um por um marcador fixo:

- caminho dentro de uma cópia do repositório (o clone ou uma worktree) vira
  `<repo>`, e o resto do caminho fica, porque diz qual arquivo o agente leu;
- a pasta pessoal vira `<home>`; dentro dela, só o perfil do Hermes
  (`<home>/.hermes/...`) fica legível, e qualquer outro caminho vira `<home>/…`;
- outro caminho num disco montado vira `<home>`;
- o nome do canal de mensagens vira `[canal]`.

Nada mais muda. O JSON é lido e regravado no mesmo formato em que foi gravado
(recuo de 2, acentos sem escape, uma linha por evento no JSONL), então o arquivo
continua válido, o diff mostra só os trechos trocados e o teste do guard-rail,
que relê essas conversas, confere os mesmos números. Rodar de novo não muda
nada.

    python scripts/redigir_transcricoes.py               # redige docs/transcricoes
    python scripts/redigir_transcricoes.py --conferir    # só confere; sai com 1 se sobrou algo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

RAIZ: Final = Path(__file__).resolve().parents[1]
PASTA: Final = RAIZ / "docs" / "transcricoes"

#: O que pode compor um segmento de caminho no texto gravado. Aspas, barra
#: invertida (escape de JSON aninhado) e espaço encerram o caminho.
_SEG: Final = r"[^/\s\"'`\\<>|,;()\[\]{}]"

#: Uma cópia do repositório num disco montado: o clone ou uma worktree.
_COPIA: Final = re.compile(
    rf"/mnt/[a-z](?:/{_SEG}+)*?"
    rf"/(?:desafio-ifood-senior-ai-engineer[\w-]*|sabor-da-maria|worktrees/{_SEG}+)"
    rf"(?!{_SEG})"
)
#: A pasta pessoal, com o que vier depois dela no mesmo caminho.
_PESSOAL: Final = re.compile(rf"/home/{_SEG}+((?:/{_SEG}*)*)")
#: Qualquer outro caminho num disco montado: o disco e a primeira pasta.
_DISCO: Final = re.compile(rf"/mnt/[a-z](?:/{_SEG}+)?(?!{_SEG})")
#: O canal de mensagens que saiu do escopo, em qualquer grafia.
_CANAL: Final = re.compile(r"whats\s?app", re.IGNORECASE)

#: O que não pode sobrar depois da redação.
_SOBRA: Final = re.compile(r"/home/|/mnt/[a-z]/|whats\s?app", re.IGNORECASE)


def _pessoal(achado: re.Match[str]) -> str:
    resto = achado.group(1)
    if not resto:
        return "<home>"
    if resto.startswith("/.hermes"):
        return "<home>" + resto
    return "<home>/…"


def redigir_texto(texto: str) -> str:
    """Aplica as trocas, na ordem: cópia do repositório, pasta pessoal, disco, canal."""
    texto = _COPIA.sub("<repo>", texto)
    texto = _PESSOAL.sub(_pessoal, texto)
    texto = _DISCO.sub("<home>", texto)
    return _CANAL.sub("[canal]", texto)


def _redigir(valor: Any) -> Any:
    if isinstance(valor, str):
        return redigir_texto(valor)
    if isinstance(valor, list):
        return [_redigir(v) for v in valor]
    if isinstance(valor, dict):
        return {redigir_texto(k): _redigir(v) for k, v in valor.items()}
    return valor


def _strings(valor: Any) -> Iterator[str]:
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, list):
        for v in valor:
            yield from _strings(v)
    elif isinstance(valor, dict):
        for k, v in valor.items():
            yield k
            yield from _strings(v)


#: Os formatos em que as transcrições foram gravadas. Um arquivo que não volta
#: idêntico por nenhum deles é recusado: regravá-lo mudaria mais do que a redação.
_FORMATOS: Final[tuple[Callable[[Any], str], ...]] = (
    lambda d: json.dumps(d, ensure_ascii=False, indent=2) + "\n",
    lambda d: json.dumps(d, ensure_ascii=False, indent=2),
    lambda d: json.dumps(d, ensure_ascii=True, indent=2) + "\n",
    lambda d: json.dumps(d, ensure_ascii=False) + "\n",
    lambda d: json.dumps(d, ensure_ascii=False),
    lambda d: json.dumps(d, ensure_ascii=True),
)


def _formato_de(bruto: str, dados: Any, arquivo: Path) -> Callable[[Any], str]:
    for formato in _FORMATOS:
        if formato(dados) == bruto:
            return formato
    raise ValueError(f"{arquivo}: formato de JSON desconhecido, nada foi regravado")


def _redigir_json(bruto: str, arquivo: Path) -> str:
    dados = json.loads(bruto)
    formato = _formato_de(bruto, dados, arquivo)
    return formato(_redigir(dados))


def _redigir_jsonl(bruto: str, arquivo: Path) -> str:
    linhas = bruto.split("\n")
    saida = []
    for linha in linhas:
        if not linha.strip():
            saida.append(linha)
            continue
        dados = json.loads(linha)
        saida.append(_formato_de(linha, dados, arquivo)(_redigir(dados)))
    return "\n".join(saida)


def redigir_arquivo(arquivo: Path) -> str:
    """O conteúdo redigido do arquivo, sem gravar."""
    bruto = arquivo.read_text(encoding="utf-8")
    if arquivo.suffix == ".json":
        return _redigir_json(bruto, arquivo)
    if arquivo.suffix == ".jsonl":
        return _redigir_jsonl(bruto, arquivo)
    return redigir_texto(bruto)


def sobras(arquivo: Path) -> list[str]:
    """Os trechos que a redação deveria ter trocado e ainda estão no arquivo.

    No JSON, confere cada string já decodificada, para não deixar passar um
    caminho gravado com escape.
    """
    bruto = arquivo.read_text(encoding="utf-8")
    if arquivo.suffix == ".json":
        textos = list(_strings(json.loads(bruto)))
    elif arquivo.suffix == ".jsonl":
        textos = [
            s
            for linha in bruto.splitlines()
            if linha.strip()
            for s in _strings(json.loads(linha))
        ]
    else:
        textos = [bruto]
    return [achado.group(0) for texto in textos for achado in _SOBRA.finditer(texto)]


@dataclass(frozen=True)
class Resultado:
    arquivos: int
    alterados: list[Path]
    trocas: int


def _arquivos(pasta: Path) -> list[Path]:
    return sorted(
        p
        for p in pasta.rglob("*")
        if p.is_file() and p.suffix in {".json", ".jsonl", ".md"}
    )


def _trocas(antes: str, depois: str) -> int:
    marcadores = ("<repo>", "<home>", "[canal]")
    return sum(depois.count(m) - antes.count(m) for m in marcadores)


def redigir_pasta(pasta: Path, *, gravar: bool) -> Resultado:
    alterados: list[Path] = []
    trocas = 0
    arquivos = _arquivos(pasta)
    for arquivo in arquivos:
        antes = arquivo.read_text(encoding="utf-8")
        depois = redigir_arquivo(arquivo)
        if depois == antes:
            continue
        alterados.append(arquivo)
        trocas += _trocas(antes, depois)
        if gravar:
            if arquivo.suffix == ".json":
                json.loads(depois)
            arquivo.write_text(depois, encoding="utf-8")
    return Resultado(len(arquivos), alterados, trocas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pasta", nargs="?", type=Path, default=PASTA)
    parser.add_argument(
        "--conferir", action="store_true", help="só confere, sem gravar"
    )
    args = parser.parse_args(argv)

    resultado = redigir_pasta(args.pasta, gravar=not args.conferir)
    restos = {p: sobras(p) for p in _arquivos(args.pasta)}
    restos = {p: r for p, r in restos.items() if r}
    if args.conferir:
        pendentes = sorted(set(resultado.alterados) | set(restos))
        for arquivo in pendentes:
            print(f"falta redigir: {arquivo.relative_to(args.pasta)}")
        print(
            f"{resultado.arquivos} arquivos conferidos, {len(pendentes)} com o que redigir"
        )
        return 1 if pendentes else 0
    print(
        f"{resultado.arquivos} arquivos lidos, {len(resultado.alterados)} redigidos, "
        f"{resultado.trocas} trechos trocados"
    )
    for arquivo, resto in restos.items():
        print(f"sobrou em {arquivo.relative_to(args.pasta)}: {sorted(set(resto))}")
    return 1 if restos else 0


if __name__ == "__main__":
    sys.exit(main())
