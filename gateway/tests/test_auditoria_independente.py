"""A segunda opinião sobre o preço, pelo protocolo A2A ou em processo."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.auditoria_independente import (
    auditor_a2a,
    auditor_do_ambiente,
    auditor_em_processo,
)

PRATO_CERTO: dict[str, Any] = {
    "prato": "Arroz com frango",
    "linhas": [
        {"ingrediente": "Frango", "custo": "1.75"},
        {"ingrediente": "Arroz", "custo": "1.25"},
    ],
    "cmv": "3.00",
    "preco": "12.00",
    "lucro": "7.80",
}


def postar_no_auditor_real() -> Any:
    """Entrega o corpo ao servidor A2A de verdade do auditor, sem rede."""
    from auditor.servidor import criar_app

    cliente = TestClient(criar_app())

    def postar(url: str, corpo: bytes) -> bytes:
        assert url == "http://auditor.local/a2a"
        return cliente.post(
            "/a2a", content=corpo, headers={"Content-Type": "application/json"}
        ).content

    return postar


def test_em_processo_confere_a_conta_certa() -> None:
    parecer = auditor_em_processo(PRATO_CERTO)
    assert parecer["confere"] is True
    assert "em processo" in parecer["por"]


def test_em_processo_avisa_o_prejuizo_sem_recusar() -> None:
    """Aceitar abaixo do mínimo é escolha dela; com o auditor ligado, era sempre recusado."""
    parecer = auditor_em_processo({**PRATO_CERTO, "preco": "3.00", "lucro": "-0.30"})
    assert parecer["confere"] is True
    assert parecer["da_prejuizo"] is True
    assert "R$ 3,34" in parecer["aviso"]
    assert auditor_em_processo(PRATO_CERTO)["da_prejuizo"] is False


def test_em_processo_pega_lucro_errado() -> None:
    parecer = auditor_em_processo({**PRATO_CERTO, "lucro": "9.99"})
    assert parecer["confere"] is False
    assert parecer["divergencias"]


def test_a2a_de_ponta_a_ponta_com_o_servidor_do_auditor() -> None:
    auditar = auditor_a2a("http://auditor.local/a2a", postar_no_auditor_real())
    certo = auditar(PRATO_CERTO)
    assert certo["confere"] is True
    assert certo["por"] == "http://auditor.local/a2a"

    # Abaixo do mínimo com a conta certa: confere, com o aviso do prejuízo.
    abaixo = auditar({**PRATO_CERTO, "preco": "3.00", "lucro": "-0.30"})
    assert abaixo["confere"] is True
    assert abaixo["da_prejuizo"] is True
    assert "mínimo" in abaixo["aviso"]

    errado = auditar({**PRATO_CERTO, "lucro": "9.99"})
    assert errado["confere"] is False
    assert errado["divergencias"][0]["campo"] == "lucro"


def test_a2a_manda_o_envelope_do_protocolo() -> None:
    enviados: list[dict[str, Any]] = []

    def postar(_url: str, corpo: bytes) -> bytes:
        enviados.append(json.loads(corpo))
        return json.dumps(
            {"result": {"parts": [{"kind": "data", "data": {"confere": True}}]}}
        ).encode()

    auditor_a2a("http://a", postar)(PRATO_CERTO)
    (envelope,) = enviados
    assert envelope["jsonrpc"] == "2.0"
    assert envelope["method"] == "message/send"
    assert envelope["params"]["message"]["parts"][0]["data"] == PRATO_CERTO


@pytest.mark.parametrize(
    "falha",
    [
        urllib.error.URLError("recusado"),
        TimeoutError("lento"),
        ValueError("não é json"),
    ],
)
def test_auditor_fora_do_ar_nao_para_nada(falha: Exception) -> None:
    def postar(_url: str, _corpo: bytes) -> bytes:
        raise falha

    parecer = auditor_a2a("http://fora", postar)(PRATO_CERTO)
    assert parecer["confere"] is None
    assert "indisponível" in parecer["observacao"]


def test_resposta_sem_parecer_e_nao_conferido() -> None:
    def postar(_url: str, _corpo: bytes) -> bytes:
        return json.dumps({"error": {"message": "método desconhecido"}}).encode()

    parecer = auditor_a2a("http://a", postar)(PRATO_CERTO)
    assert parecer["confere"] is None
    assert "método desconhecido" in parecer["observacao"]


def test_ambiente_escolhe_a2a_ou_em_processo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISE_AUDITOR_URL", raising=False)
    assert auditor_do_ambiente() is auditor_em_processo
    monkeypatch.setenv("MISE_AUDITOR_URL", "http://auditor:8899/")
    assert auditor_do_ambiente() is not auditor_em_processo


def test_a_api_http_confere_o_preco_antes_de_devolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A porta da tela também passa pelo auditor: o parecer vem junto do aceite."""
    from mise.dossie import Dossie
    from mise.perfil import Gosto, PerfilCozinha, Posse

    from gateway.http import criar_app

    banco = tmp_path / "dossie.db"
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    planilha = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"
    monkeypatch.setenv("MISE_PLANILHA", str(planilha))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITOR_URL", raising=False)
    cliente = TestClient(criar_app())
    receita = {
        "nome": "Arroz com frango",
        "rendimento_porcoes": 4,
        "modo_preparo": ["Cozinhe tudo na panela por 20 minutos."],
        "ingredientes": [
            {
                "texto": "500 g de frango",
                "nome": "peito de frango",
                "quantidade": 500,
                "medida": "g",
            },
            {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        ],
    }
    assert cliente.post("/api/avaliar", json=receita).json()["dados"]["pode_precificar"]

    d = cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 12}
    ).json()["dados"]
    assert d["auditoria_independente"]["confere"] is True


def test_a_api_http_aceita_abaixo_do_minimo_com_o_auditor_de_verdade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A docstring e o teste diziam que a escolha é dela; com o auditor ligado, era recusa."""
    from mise.dossie import Dossie
    from mise.perfil import Gosto, PerfilCozinha, Posse

    from gateway.http import criar_app

    banco = tmp_path / "dossie.db"
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    planilha = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"
    monkeypatch.setenv("MISE_PLANILHA", str(planilha))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITOR_URL", raising=False)
    cliente = TestClient(criar_app())
    receita = {
        "nome": "Arroz com frango",
        "rendimento_porcoes": 4,
        "modo_preparo": ["Cozinhe tudo na panela por 20 minutos."],
        "ingredientes": [
            {
                "texto": "500 g de frango",
                "nome": "peito de frango",
                "quantidade": 500,
                "medida": "g",
            },
            {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        ],
    }
    assert cliente.post("/api/avaliar", json=receita).json()["dados"]["pode_precificar"]

    corpo = cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 3}
    ).json()
    assert corpo["ok"], corpo["erro"]
    d = corpo["dados"]
    assert d["da_prejuizo"] is True
    assert "o mínimo é R$ 3,34" in d["aviso"]
    assert d["auditoria_independente"]["confere"] is True
    assert d["auditoria_independente"]["da_prejuizo"] is True
    pratos = cliente.get("/api/cardapio").json()["dados"]["pratos"]
    assert [p["prato"] for p in pratos] == ["Arroz com frango"]


def test_postar_de_verdade_por_http() -> None:
    """O transporte real, contra um servidor HTTP local que responde como o auditor."""
    import http.server
    import threading

    from gateway.auditoria_independente import _postar_http

    class Responde(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            tamanho = int(self.headers["Content-Length"])
            recebido = json.loads(self.rfile.read(tamanho))
            corpo = json.dumps({"eco": recebido["method"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_: object) -> None:
            return None

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Responde)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        porta = servidor.server_address[1]
        bruto = _postar_http(f"http://127.0.0.1:{porta}/a2a", b'{"method": "message/send"}')
        assert json.loads(bruto) == {"eco": "message/send"}
    finally:
        servidor.shutdown()
        servidor.server_close()


def _cmv_em_faixa() -> Any:
    """Um custo com medida caseira: incerteza de 20%, apresentado como faixa."""
    from decimal import Decimal

    from mise.cmv import CMV, LinhaCMV
    from mise.dinheiro import Dinheiro

    linhas = (
        LinhaCMV("queijo parmesão", "1 xícara", Dinheiro.de("3.4567"), "1 xícara", Decimal("0.2")),
        LinhaCMV(
            "farinha de trigo", "2 xícaras", Dinheiro.de("0.6667"), "2 xícaras", Decimal("0.2")
        ),
    )
    cmv = CMV("Pão de queijo", linhas, Dinheiro.de("4.1234"), Decimal("0.20"))
    assert cmv.e_faixa
    return cmv


def test_custo_em_faixa_confere_as_linhas_com_o_total_delas() -> None:
    """Numa faixa, o preço sai do topo, e as linhas somam o total do meio.

    O auditor recebia as linhas (R$ 4,13) e o topo (R$ 4,95) como se fossem a
    mesma conta, e segurava um preço certo por uma diferença que não é erro.
    """
    from mise.preco import montar_cenarios
    from mise.serializacao import prato_para_auditoria

    cmv = _cmv_em_faixa()
    assert auditor_em_processo(prato_para_auditoria(cmv))["confere"] is True

    for cenario in montar_cenarios(cmv.para_precificar):
        parecer = auditor_em_processo(prato_para_auditoria(cmv, cenario.preco, cenario.lucro))
        assert parecer["confere"] is True, parecer
