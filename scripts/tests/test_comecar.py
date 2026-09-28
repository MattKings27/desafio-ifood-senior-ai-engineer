"""O `make comecar`, simulado, numa casa de mentira.

Roda o script de verdade (`scripts/comecar.sh`) com `SIMULAR=1`, que só mostra
os passos, e `HOME` num diretório temporário: nada é instalado, e o
`~/.hermes` de quem roda os testes não é tocado. O que importa provar é a
ordem dos passos e que a chave da Anthropic nunca aparece na tela.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "comecar.sh"
CHAVE = "sk-ant-teste-que-nunca-aparece"


def _rodar(casa: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    ambiente = {"PATH": os.environ["PATH"], "HOME": str(casa), "SIMULAR": "1", **extra}
    return subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=ambiente, check=True
    )


def test_os_seis_passos_saem_em_ordem_e_terminam_no_site(tmp_path: Path) -> None:
    saida = _rodar(tmp_path).stdout
    # O passo 4 diz "npm ci" ou que as dependências já estão lá, conforme a pasta.
    marcos = [
        "1/6",
        "make instalar-hermes",
        "hermes setup model",
        "make bootstrap",
        "4/6",
        "make verificar",
        "make demo",
    ]
    posicoes = [saida.index(m) for m in marcos]
    assert posicoes == sorted(posicoes)
    assert "http://localhost:3000" in saida


def test_a_chave_do_ambiente_nunca_aparece_na_tela(tmp_path: Path) -> None:
    saida = _rodar(tmp_path, ANTHROPIC_API_KEY=CHAVE)
    assert CHAVE not in saida.stdout + saida.stderr
    assert "gravaria a chave" in saida.stdout
    assert "hermes setup model" not in saida.stdout


def test_chave_que_ja_existe_nao_e_pedida_de_novo(tmp_path: Path) -> None:
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes" / ".env").write_text(
        f"ANTHROPIC_API_KEY={CHAVE}\n", encoding="utf-8"
    )
    saida = _rodar(tmp_path)
    assert "já está no" in saida.stdout
    assert CHAVE not in saida.stdout + saida.stderr
    assert "hermes setup model" not in saida.stdout
