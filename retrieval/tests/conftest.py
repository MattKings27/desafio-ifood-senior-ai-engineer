from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def html():
    """Carrega uma página salva. Os testes não tocam a rede."""

    def carregar(nome: str) -> str:
        return (FIXTURES / nome).read_text(encoding="utf-8")

    return carregar
