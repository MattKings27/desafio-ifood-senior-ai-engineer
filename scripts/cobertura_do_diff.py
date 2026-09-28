#!/usr/bin/env python3
"""Cobertura das linhas que este PR mudou.

O piso global (`fail_under = 95`) responde "o projeto está coberto?". Não responde
"o que você acabou de escrever está coberto?": num repositório com 98% de base,
dá para acrescentar um arquivo inteiro sem teste e continuar acima do piso.

Este portão olha só as linhas que o diff acrescentou ou alterou. É o que impede a
cobertura de descer devagar, um PR de cada vez.

Saída: 0 aprovado, 1 reprovado, 2 não consegui decidir (que também é vermelho:
um portão sem veredito não é um portão verde).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PISO_PADRAO = 80.0

# `@@ -a,b +c,d @@`: só o lado novo interessa, porque linha removida não precisa de teste.
CABECALHO_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class NaoDecidiu(Exception):
    """Faltou insumo para dar veredito. Nunca vira 'passou'."""


def linhas_alteradas(base: str, alvo: str) -> dict[str, set[int]]:
    """Linhas acrescentadas por arquivo, do ponto de bifurcação até `alvo`.

    `--unified=0` remove o contexto: linha que só mudou de indentação não entra e
    não passa a exigir teste. `...` usa o merge-base, para não cobrar deste PR o
    que entrou em `main` depois que ele foi criado.
    """
    try:
        bruto = subprocess.run(
            ["git", "diff", "--unified=0", "--diff-filter=AM", f"{base}...{alvo}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as erro:
        detalhe = (erro.stderr or "").strip()
        raise NaoDecidiu(
            f"git diff falhou entre {base} e {alvo}: {detalhe}\n"
            "Em CI isso costuma ser clone raso: use fetch-depth: 0."
        ) from erro

    por_arquivo: dict[str, set[int]] = {}
    arquivo: str | None = None
    for linha in bruto.splitlines():
        if linha.startswith("+++ b/"):
            arquivo = linha[6:]
            continue
        if linha.startswith("+++ "):
            arquivo = None
            continue
        casou = CABECALHO_HUNK.match(linha)
        if casou and arquivo:
            inicio = int(casou.group(1))
            quantas = int(casou.group(2)) if casou.group(2) is not None else 1
            if quantas:
                por_arquivo.setdefault(arquivo, set()).update(
                    range(inicio, inicio + quantas)
                )
    return por_arquivo


def linhas_medidas(relatorios: list[Path]) -> dict[str, dict[int, bool]]:
    """Mapa arquivo -> {linha: foi executada}, lido dos XML do Cobertura.

    Só linhas que o coverage considera executáveis aparecem. Comentário, import
    e linha em branco ficam de fora e não entram na conta, que é o certo.
    """
    medidas: dict[str, dict[int, bool]] = {}
    for relatorio in relatorios:
        if not relatorio.exists():
            raise NaoDecidiu(f"relatório de cobertura ausente: {relatorio}")
        try:
            raiz = ET.parse(relatorio).getroot()
        except ET.ParseError as erro:
            raise NaoDecidiu(f"{relatorio} não é XML válido: {erro}") from erro

        # <sources><source>/caminho/da/raiz</source></sources>
        origens = [
            (s.text or "").strip()
            for s in raiz.findall("./sources/source")
            if (s.text or "").strip()
        ]
        for classe in raiz.iter("class"):
            nome = classe.get("filename")
            if not nome:
                continue
            for candidato in _caminhos_possiveis(nome, origens):
                alvo = medidas.setdefault(candidato, {})
                for linha in classe.iter("line"):
                    numero = linha.get("number")
                    if numero is None:
                        continue
                    coberta = (linha.get("hits") or "0") != "0"
                    # Mesma linha medida em dois relatórios: basta um cobrir.
                    alvo[int(numero)] = alvo.get(int(numero), False) or coberta
    return medidas


def _caminhos_possiveis(nome: str, origens: list[str]) -> list[str]:
    """O XML guarda o caminho relativo à `source`; o git, relativo à raiz do repo.

    Em vez de adivinhar qual prefixo o coverage usou, registro todas as combinações
    plausíveis e deixo o casamento com o diff decidir.
    """
    raiz = Path.cwd()
    candidatos = [nome]
    for origem in origens:
        try:
            absoluto = (Path(origem) / nome).resolve()
            candidatos.append(str(absoluto.relative_to(raiz)))
        except (ValueError, OSError):
            continue
    return list(dict.fromkeys(candidatos))


def main() -> int:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--base", default="origin/main")
    analise.add_argument("--alvo", default="HEAD")
    analise.add_argument("--piso", type=float, default=PISO_PADRAO)
    analise.add_argument("relatorios", nargs="+", type=Path)
    args = analise.parse_args()

    try:
        alteradas = linhas_alteradas(args.base, args.alvo)
        medidas = linhas_medidas(args.relatorios)
    except NaoDecidiu as erro:
        print(f"::error::sem veredito de cobertura do diff: {erro}", file=sys.stderr)
        return 2

    total = cobertas = 0
    descobertas: dict[str, list[int]] = {}

    for arquivo, linhas in sorted(alteradas.items()):
        do_arquivo = medidas.get(arquivo)
        if do_arquivo is None:
            continue  # não é código medido (markdown, yaml, config)
        for numero in sorted(linhas):
            if numero not in do_arquivo:
                continue  # linha não executável
            total += 1
            if do_arquivo[numero]:
                cobertas += 1
            else:
                descobertas.setdefault(arquivo, []).append(numero)

    if total == 0:
        print("cobertura do diff: nenhuma linha executável alterada, nada a exigir")
        return 0

    pct = 100.0 * cobertas / total
    print(
        f"cobertura do diff: {cobertas}/{total} linhas = {pct:.1f}% (piso {args.piso:.0f}%)"
    )

    if descobertas:
        print("\nlinhas alteradas e sem teste:")
        for arquivo, numeros in descobertas.items():
            print(f"  {arquivo}: {_faixas(numeros)}")

    if pct + 1e-9 < args.piso:
        print(
            f"\n::error::cobertura do diff {pct:.1f}% abaixo do piso de {args.piso:.0f}%.",
            file=sys.stderr,
        )
        return 1
    return 0


def _faixas(numeros: list[int]) -> str:
    """[3,4,5,9] -> '3-5, 9'. Lista longa de linha solta ninguém lê."""
    if not numeros:
        return ""
    faixas: list[str] = []
    inicio = anterior = numeros[0]
    for numero in numeros[1:]:
        if numero == anterior + 1:
            anterior = numero
            continue
        faixas.append(str(inicio) if inicio == anterior else f"{inicio}-{anterior}")
        inicio = anterior = numero
    faixas.append(str(inicio) if inicio == anterior else f"{inicio}-{anterior}")
    return ", ".join(faixas)


if __name__ == "__main__":
    sys.exit(main())
