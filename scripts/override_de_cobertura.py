#!/usr/bin/env python3
"""A válvula de escape do portão de cobertura do diff.

Existe porque portão sem saída legítima é portão que alguém desliga. Mas a saída
custa alguma coisa: a label sozinha não vale, é preciso escrever por quê.

O detalhe que faz diferença: label presente **sem** justificativa não é "override
não se aplica": é erro. Se a ausência fosse silenciosa, a exigência viraria
decorativa no dia em que alguém pusesse a label e seguisse em frente.

Saída: 0 override válido, 1 label presente e justificativa ausente ou curta,
3 sem label (o portão normal decide).
"""

from __future__ import annotations

import argparse
import json
import re
import sys

LABEL = "coverage-override"
TITULO = re.compile(
    r"^#{1,6}\s*coverage override justification\s*$", re.IGNORECASE | re.MULTILINE
)
MINIMO = 20


def justificativa(corpo: str) -> str:
    """O texto sob o título, até o próximo título ou o fim."""
    casou = TITULO.search(corpo or "")
    if not casou:
        return ""
    resto = corpo[casou.end() :]
    proximo = re.search(r"^#{1,6}\s+\S", resto, re.MULTILINE)
    trecho = resto[: proximo.start()] if proximo else resto
    # Comentário HTML é instrução do template, não justificativa de ninguém.
    return re.sub(r"<!--.*?-->", "", trecho, flags=re.DOTALL).strip()


def main() -> int:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--evento", required=True, help="JSON do evento do GitHub")
    args = analise.parse_args()

    try:
        with open(args.evento, encoding="utf-8") as arquivo:
            pr = json.load(arquivo).get("pull_request") or {}
    except (OSError, json.JSONDecodeError) as erro:
        print(f"::error::não consegui ler o evento: {erro}", file=sys.stderr)
        return 1

    rotulos = {(r.get("name") or "").strip().lower() for r in pr.get("labels") or []}
    if LABEL not in rotulos:
        print(f"sem a label '{LABEL}': o portão de cobertura decide normalmente")
        return 3

    texto = justificativa(pr.get("body") or "")
    if len(texto) < MINIMO:
        print(
            f"::error::a label '{LABEL}' está no PR, mas falta a seção "
            f"'## Coverage override justification' com ao menos {MINIMO} caracteres. "
            "A label sozinha não dispensa a cobertura.",
            file=sys.stderr,
        )
        return 1

    print(f"override aceito, justificado em {len(texto)} caracteres:\n\n{texto}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
