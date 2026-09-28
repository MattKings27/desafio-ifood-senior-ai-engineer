from __future__ import annotations

import os

# A busca da plataforma usa o modelo semântico quando ele está baixado; os testes
# usam sempre os n-gramas, que dão o mesmo resultado em qualquer máquina.
os.environ.setdefault("SABOR_VETORIZADOR", "ngramas")

from pathlib import Path

import pytest

from mise.despensa import Despensa, carregar_despensa

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"


@pytest.fixture(scope="session")
def caminho_planilha() -> Path:
    if not PLANILHA.is_file():
        pytest.fail(f"planilha de entrada não encontrada em {PLANILHA}")
    return PLANILHA


@pytest.fixture(scope="session")
def despensa(caminho_planilha: Path) -> Despensa:
    """A despensa real da Dona Maria, carregada uma vez por sessão."""
    return carregar_despensa(caminho_planilha)


@pytest.fixture
def sem_precos_de_referencia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sessão sem os preços de referência: o que falta e ela não cotou vira pergunta.

    Os preços de referência (`dados/precos_de_referencia.json`) valem para toda
    sessão da planilha real. Os testes que conferem o caminho sem fonte
    nenhuma (o ingrediente fora da lista) apontam para um arquivo que não existe.
    """
    monkeypatch.setenv("MISE_PRECOS_DE_REFERENCIA", str(tmp_path / "sem-precos.json"))
