"""A composição raiz: onde motor e política se encontram, e em lugar nenhum mais."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from gateway import principal

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    for chave in ("MISE_TOKEN_LEITURA", "MISE_TOKEN_ESCRITA", "MISE_AUDITORIA", "MISE_TOKEN"):
        monkeypatch.delenv(chave, raising=False)


def test_log_vai_para_stderr() -> None:
    """stdout é do JSON-RPC. Um `print` perdido ali corrompe o protocolo."""
    principal.configurar_log()
    handlers = logging.getLogger().handlers
    assert handlers
    assert all(getattr(h, "stream", None) is not None for h in handlers if hasattr(h, "stream"))


def test_main_monta_servidor_com_a_pilha_completa(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main` compõe motor + política e entrega ao transporte stdio."""
    capturado: dict[str, Any] = {}

    class ServidorFalso:
        def run(self, transport: str = "stdio", **_: Any) -> None:
            capturado["transport"] = transport

    def construir_falso(sessao: Any, middleware: list[Any] | None = None) -> ServidorFalso:
        capturado["sessao"] = sessao
        capturado["middleware"] = middleware or []
        return ServidorFalso()

    import mise.mcp_server as mcp

    monkeypatch.setattr(mcp, "construir_servidor", construir_falso)
    principal.main()

    assert capturado["transport"] == "stdio"
    assert len(capturado["sessao"].despensa) == 37
    assert capturado["sessao"].canal == "conversa", "o que chega por aqui é o agente"
    assert [type(m).__name__ for m in capturado["middleware"]] == [
        "Autenticacao",
        "Auditoria",
        "Autorizacao",
        "RateLimit",
        "Quota",
        "CircuitBreaker",
    ]


def test_avisa_quando_roda_sem_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Modo aberto é aceitável em desenvolvimento, mas não pode passar em silêncio."""

    class ServidorFalso:
        def run(self, **_: Any) -> None:
            return None

    import mise.mcp_server as mcp

    monkeypatch.setattr(mcp, "construir_servidor", lambda *a, **k: ServidorFalso())
    with caplog.at_level(logging.WARNING):
        principal.main()

    avisos = " ".join(r.message for r in caplog.records)
    assert "modo aberto" in avisos
    assert "auditoria" in avisos


def test_nao_avisa_quando_configurado(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    monkeypatch.setenv("MISE_TOKEN_LEITURA", "r")
    monkeypatch.setenv("MISE_TOKEN_ESCRITA", "w")
    monkeypatch.setenv("MISE_AUDITORIA", str(tmp_path / "a.jsonl"))

    class ServidorFalso:
        def run(self, **_: Any) -> None:
            return None

    import mise.mcp_server as mcp

    monkeypatch.setattr(mcp, "construir_servidor", lambda *a, **k: ServidorFalso())
    with caplog.at_level(logging.WARNING):
        principal.main()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_motor_nao_importa_gateway() -> None:
    """A dependência é de mão única: o gateway conhece o motor, nunca o contrário.

    Inverter isso amarraria a regra de negócio à política de acesso, e as duas
    mudam por motivos completamente diferentes.
    """
    fonte = Path(__file__).resolve().parents[2] / "mise" / "src" / "mise"
    for arquivo in fonte.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "import gateway" not in texto, f"{arquivo.name} importa o gateway"
        assert "from gateway" not in texto, f"{arquivo.name} importa o gateway"
