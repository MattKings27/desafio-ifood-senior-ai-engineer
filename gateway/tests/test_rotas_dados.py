"""Os dados dela para baixar: tudo o que está gravado, num arquivo só, sem conta nova."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.erros import ErroDeDados

from gateway.http import criar_app
from gateway.rotas import dados as rota_dos_dados

RAIZ = Path(__file__).resolve().parents[2]
CONTRATO = RAIZ / "contratos" / "web" / "exportacao.json"


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "dossie.db"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, banco: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    sessao_de_teste.preparar_dossie(banco)
    app = criar_app()
    sessao_de_teste.guardar_receitas(app.state.sessao)
    return TestClient(app)


def _ok(resposta: Any) -> None:
    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"], corpo


def _com_um_pouco_de_tudo(cliente: TestClient) -> None:
    """Uma mudança de cada coisa que ela pode fazer, pela tela."""
    _ok(cliente.put("/api/perfil/equipamentos/freezer", json={"estado": "nao_tem"}))
    _ok(
        cliente.patch(
            "/api/despensa/itens/cobertura-de-chocolate", json={"conteudo_da_embalagem": "1 kg"}
        )
    )
    _ok(cliente.post("/api/gosto", json={"prato": "Bolo de fubá", "gosta": True}))
    _ok(
        cliente.post(
            "/api/preco-mercado",
            json={"ingrediente": "coco ralado", "valor": 5.5, "quantidade": 100, "unidade": "g"},
        )
    )
    _ok(
        cliente.post(
            "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 12}
        )
    )
    _ok(
        cliente.post(
            "/api/compra",
            json={
                "prato": "Bolo de fubá",
                "ingrediente": "coco ralado",
                "quantidade": 100,
                "unidade": "g",
                "valor": 5.5,
            },
        )
    )


def _exportar(cliente: TestClient) -> dict[str, Any]:
    resposta = cliente.get("/api/exportacao")
    assert resposta.status_code == 200
    assert resposta.headers["content-disposition"] == (
        'attachment; filename="sabor-da-maria-dados.json"'
    )
    assert resposta.headers["content-type"].startswith("application/json")
    dados: dict[str, Any] = json.loads(resposta.content.decode("utf-8"))
    return dados


def test_o_arquivo_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    _com_um_pouco_de_tudo(cliente)
    exemplo = json.loads(CONTRATO.read_text(encoding="utf-8"))
    dados = _exportar(cliente)
    assert list(dados) == list(exemplo)
    for secao in ("despensa", "cozinha", "orcamento"):
        assert set(dados[secao]) == set(exemplo[secao]), secao
    for lista in (
        "despensa_eventos",
        "cozinha_eventos",
        "compras",
        "decisoes",
        "gostos",
        "precos_de_mercado",
        "receitas_em_avaliacao",
    ):
        assert dados[lista], lista
        assert set(dados[lista][0]) == set(exemplo[lista][0]), lista
    assert set(dados["despensa"]["itens"][0]) == set(exemplo["despensa"]["itens"][0])


def test_o_arquivo_leva_o_que_ela_fez(cliente: TestClient) -> None:
    _com_um_pouco_de_tudo(cliente)
    dados = _exportar(cliente)
    assert (dados["arquivo"], dados["versao"]) == ("sabor-da-maria-dados", 1)
    assert dados["despensa"]["total_itens"] == 37
    assert [e["acao"] for e in dados["despensa_eventos"]] == ["informar_embalagem"]
    assert [(e["campo"], e["texto"]) for e in dados["cozinha_eventos"]] == [
        ("freezer", "a senhora disse que não tem freezer")
    ]
    assert dados["cozinha"]["respondidos"] >= 1
    assert dados["orcamento"]["restante"]["texto"] == "R$ 74,50"
    assert [c["ingrediente"] for c in dados["compras"]] == ["coco ralado"]
    assert [(d["prato"], d["decisao"]) for d in dados["decisoes"]] == [
        ("Arroz com frango", "aceito")
    ]
    assert dados["cardapio"] == ["Arroz com frango"]
    assert {g["prato"] for g in dados["gostos"]} == {"Arroz com frango", "Bolo de fubá"}
    (preco,) = dados["precos_de_mercado"]
    assert (preco["ingrediente"], preco["valor"]["texto"], preco["por"]) == (
        "coco ralado",
        "R$ 5,50",
        "0,1 kg",
    )
    receitas = {r["receita_id"]: r["nome"] for r in dados["receitas_em_avaliacao"]}
    assert receitas["arroz-com-frango"] == "Arroz com frango"
    assert "Bolo de fubá" in receitas.values()


def test_baixar_nao_grava_nada(cliente: TestClient, banco: Path) -> None:
    _com_um_pouco_de_tudo(cliente)
    _exportar(cliente)
    with closing(sqlite3.connect(banco)) as monitor:
        antes = monitor.execute("PRAGMA data_version").fetchone()[0]
        _exportar(cliente)
        assert monitor.execute("PRAGMA data_version").fetchone()[0] == antes


def test_sem_nada_feito_o_arquivo_sai_com_as_listas_vazias(
    monkeypatch: pytest.MonkeyPatch, banco: Path
) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    dados = _exportar(TestClient(criar_app()))
    vazias = ("despensa_eventos", "cozinha_eventos", "compras", "decisoes", "gostos")
    assert all(dados[lista] == [] for lista in vazias)
    assert dados["receitas_em_avaliacao"] == []
    assert dados["orcamento"]["restante"]["texto"] == "R$ 80,00"


def test_erro_do_motor_vem_no_envelope(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebra(_sessao: object) -> dict[str, Any]:
        raise ErroDeDados("o dossiê não abriu")

    monkeypatch.setattr(rota_dos_dados, "exportacao", quebra)
    resposta = cliente.get("/api/exportacao")
    assert "content-disposition" not in resposta.headers
    assert resposta.json() == {
        "ok": False,
        "dados": None,
        "erro": "o dossiê não abriu",
        "categoria": "dado",
        "pergunta": None,
    }
