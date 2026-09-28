"""Exporta o catálogo de um dossiê para a semente `dados/catalogo_inicial.json`.

Só as receitas lidas de uma página (com endereço), cada uma como a página veio
(`receita_lida`), sem nenhuma resposta dela: a semente é o ponto de partida de
um clone novo, não o estado de quem testou.

    mise/.venv/bin/python scripts/exportar_catalogo.py .estado/dossie.db
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dados" / "catalogo_inicial.json"


def exportar(banco: Path, destino: Path = DESTINO) -> int:
    """Grava a semente e devolve quantas receitas foram."""
    conexao = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    conexao.row_factory = sqlite3.Row
    linhas = conexao.execute(
        "SELECT * FROM catalogo WHERE url_canonica IS NOT NULL AND origem != 'dita' "
        "ORDER BY criada_em, slug"
    ).fetchall()
    conexao.close()
    semente = []
    for linha in linhas:
        receita = dict(linha)
        receita["receita"] = receita.get("receita_lida") or receita["receita"]
        receita["respostas"] = "[]"
        semente.append(receita)
    destino.write_text(
        json.dumps(semente, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return len(semente)


if __name__ == "__main__":
    print(f"{exportar(Path(sys.argv[1]))} receitas em {DESTINO.relative_to(RAIZ)}")
