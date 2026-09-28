"""A porta da API: só esta máquina, e escrita só a pedido da tela."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway import seguranca
from gateway.http import criar_app
from gateway.seguranca import (
    HOSTS_PADRAO,
    ORIGENS_PADRAO,
    LimiteDeTaxa,
    hosts_permitidos,
    origens_permitidas,
)

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"


def _app_minima(ambiente: dict[str, str]) -> FastAPI:
    app = FastAPI()

    @app.get("/api/ler")
    def ler() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/escrever")
    def escrever() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/saude/vivo")
    def vivo() -> dict[str, str]:
        return {"estado": "vivo"}

    seguranca.configurar(app, ambiente)
    return app


@pytest.fixture
def local() -> TestClient:
    return TestClient(_app_minima({}), base_url="http://127.0.0.1:8777")


# --------------------------------------------------------------------------- #
# Host                                                                         #
# --------------------------------------------------------------------------- #


def test_so_localhost_por_padrao() -> None:
    assert hosts_permitidos({}) == list(HOSTS_PADRAO)
    assert hosts_permitidos({"MISE_HOSTS": " motor , localhost,"}) == [
        "localhost",
        "127.0.0.1",
        "motor",
    ]


@pytest.mark.parametrize("base", ["http://127.0.0.1:8777", "http://localhost:8777"])
def test_localhost_e_atendido(base: str) -> None:
    cliente = TestClient(_app_minima({}), base_url=base)
    assert cliente.get("/api/ler").json() == {"ok": True}


def test_dns_rebinding_leva_400() -> None:
    """Um site que aponta o próprio domínio para 127.0.0.1 chega com o nome dele."""
    cliente = TestClient(_app_minima({}), base_url="http://site-do-atacante.com:8777")
    assert cliente.get("/api/ler").status_code == 400


def test_sondas_de_saude_passam_por_qualquer_host() -> None:
    """O Kubernetes chama pelo IP do pod; a sonda só lê."""
    cliente = TestClient(_app_minima({}), base_url="http://10.1.2.3:8777")
    assert cliente.get("/saude/vivo").json() == {"estado": "vivo"}
    assert cliente.get("/api/ler").status_code == 400


def test_host_extra_pela_variavel() -> None:
    cliente = TestClient(_app_minima({"MISE_HOSTS": "motor"}), base_url="http://motor")
    assert cliente.get("/api/ler").status_code == 200


# --------------------------------------------------------------------------- #
# Origem                                                                       #
# --------------------------------------------------------------------------- #


def test_origens_sao_as_do_cors() -> None:
    assert origens_permitidas({}) == list(ORIGENS_PADRAO)
    assert origens_permitidas({"MISE_CORS": "http://x:1, http://y:2"}) == [
        "http://x:1",
        "http://y:2",
    ]


@pytest.mark.parametrize("origem", ORIGENS_PADRAO)
def test_a_tela_escreve(local: TestClient, origem: str) -> None:
    assert local.post("/api/escrever", headers={"Origin": origem}).status_code == 200


def test_sem_origem_nao_e_navegador_e_passa(local: TestClient) -> None:
    """O servidor do Next, o curl e os testes não mandam Origin."""
    assert local.post("/api/escrever").status_code == 200


@pytest.mark.parametrize(
    "origem", ["https://site-do-atacante.com", "null", "http://localhost:3001"]
)
def test_escrita_de_outra_origem_leva_403(local: TestClient, origem: str) -> None:
    resposta = local.post("/api/escrever", headers={"Origin": origem})
    assert resposta.status_code == 403
    corpo = resposta.json()
    assert corpo["ok"] is False and corpo["categoria"] == "regra"
    assert "tela" in corpo["erro"]


def test_leitura_de_outra_origem_nao_e_barrada_aqui(local: TestClient) -> None:
    """Ler não muda nada; quem impede o site de ler a resposta é o CORS."""
    assert local.get("/api/ler", headers={"Origin": "https://outro.com"}).status_code == 200


def test_corpo_grande_demais_leva_413(local: TestClient) -> None:
    grande = b"x" * (seguranca.TAMANHO_DO_CORPO + 1)
    resposta = local.post(
        "/api/escrever", content=grande, headers={"Content-Type": "application/octet-stream"}
    )
    assert resposta.status_code == 413
    assert resposta.json()["ok"] is False


# --------------------------------------------------------------------------- #
# Na API de verdade                                                            #
# --------------------------------------------------------------------------- #


def test_a_api_do_motor_liga_as_duas_defesas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    monkeypatch.setenv("MISE_HOSTS", "")
    app = criar_app()
    fora = TestClient(app, base_url="http://site-do-atacante.com")
    assert fora.get("/api/orcamento").status_code == 400
    dentro = TestClient(app, base_url="http://127.0.0.1:8777")
    assert dentro.get("/api/orcamento").json()["ok"] is True
    recusada = dentro.post(
        "/api/gosto",
        json={"prato": "Arroz", "gosta": True},
        headers={"Origin": "https://site-do-atacante.com"},
    )
    assert recusada.status_code == 403
    aceita = dentro.post(
        "/api/gosto",
        json={"prato": "Arroz", "gosta": True},
        headers={"Origin": "http://localhost:3000"},
    )
    assert aceita.json()["ok"] is True


# --------------------------------------------------------------------------- #
# Limite de mensagens                                                          #
# --------------------------------------------------------------------------- #


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def test_limite_por_chave_em_janela_movel() -> None:
    relogio = Relogio()
    limite = LimiteDeTaxa(maximo=3, janela_s=60, relogio=relogio)
    assert [limite.espera("cv-1") for _ in range(3)] == [None, None, None]
    relogio.agora += 10
    assert limite.espera("cv-1") == pytest.approx(50.0)
    assert limite.espera("cv-2") is None, "cada conversa tem a sua conta"
    relogio.agora += 50
    assert limite.espera("cv-1") is None, "a primeira saiu da janela"
    limite.esquecer("cv-1")
    assert [limite.espera("cv-1") for _ in range(3)] == [None, None, None]


def test_pedido_recusado_nao_conta() -> None:
    relogio = Relogio()
    limite = LimiteDeTaxa(maximo=1, janela_s=60, relogio=relogio)
    assert limite.espera("c") is None
    for _ in range(5):
        assert limite.espera("c") is not None
    relogio.agora += 60
    assert limite.espera("c") is None
