"""O que a tela de preço manda, do jeito que ela manda.

Os outros testes da API montam o corpo à mão, com `quantidade` e `medida`
preenchidas, e por isso passavam enquanto a tela real recebia CMV de R$ 0,00.
Este usa o arquivo que o teste da interface também usa
(`contratos/precificar-exemplo-da-tela.json`, gerado por `montarReceita` com o
exemplo que aparece no campo): se um lado mudar o formato, um dos dois quebra.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.http import ReceitaBody, criar_app

RAIZ = Path(__file__).resolve().parents[2]
PLANILHA = RAIZ / "dados" / "despensa_dona_maria.xlsx"
CONTRATO = RAIZ / "contratos" / "precificar-exemplo-da-tela.json"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


@pytest.fixture
def receita_da_tela() -> dict[str, Any]:
    dados: dict[str, Any] = json.loads(CONTRATO.read_text(encoding="utf-8"))
    return dados


def _depois_de_dizer_que_gosta(cliente: TestClient, receita: dict[str, Any]) -> dict[str, Any]:
    """O caminho da tela: ela responde o gosto e volta para avaliar."""
    gosto = cliente.post("/api/gosto", json={"prato": receita["nome"], "gosta": True})
    assert gosto.json()["ok"]
    avaliacao: dict[str, Any] = cliente.post("/api/avaliar", json=receita).json()["dados"]
    return avaliacao


def test_o_corpo_da_tela_e_aceito_pela_api(receita_da_tela: dict[str, Any]) -> None:
    """O formato em si. Falhar aqui é contrato quebrado, não bug de conta."""
    ReceitaBody.model_validate(receita_da_tela)


def test_a_tela_crua_e_segurada_com_as_perguntas_certas(
    cliente: TestClient, receita_da_tela: dict[str, Any]
) -> None:
    """Sem preparo e sem gosto, o portão pergunta as duas coisas e não libera preço."""
    avaliacao = cliente.post("/api/avaliar", json=receita_da_tela).json()["dados"]
    assert not avaliacao["pode_precificar"]
    assert {p["campo"] for p in avaliacao["perguntas"]} >= {"gosto", "modo_preparo"}


def test_bolo_sem_preparo_nao_e_aprovado_as_cegas(
    cliente: TestClient, receita_da_tela: dict[str, Any]
) -> None:
    """Sem preparo não há como saber o equipamento. Antes, isto saía APTO."""
    avaliacao = _depois_de_dizer_que_gosta(cliente, receita_da_tela)
    assert avaliacao["veredito"] != "APTO"
    assert any(p["campo"] == "modo_preparo" for p in avaliacao["perguntas"])


@pytest.fixture
def cozinha_confirmada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    from mise.dossie import Dossie
    from mise.perfil import Gosto, PerfilCozinha, Posse

    banco = tmp_path / "dossie.db"
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Bolo de cenoura", Gosto.GOSTA)
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


def test_com_o_preparo_respondido_o_custo_sai_das_linhas_da_tela(
    cozinha_confirmada: TestClient, receita_da_tela: dict[str, Any]
) -> None:
    """O mesmo corpo da tela, com o preparo que ela respondeu: custo de verdade.

    A tela não manda quantidade; manda a linha. Antes, tudo virava "a gosto", o
    custo saía R$ 0,00 e o preço respondia 422.
    """
    receita = {**receita_da_tela, "modo_preparo": ["Misture tudo e asse no forno por 40 minutos."]}
    avaliacao = cozinha_confirmada.post("/api/avaliar", json=receita).json()["dados"]
    assert avaliacao["pode_precificar"], avaliacao["perguntas"]

    cmv = cozinha_confirmada.post("/api/cmv", json=receita).json()
    assert cmv["ok"], cmv["erro"]
    linhas = {linha["ingrediente"]: linha for linha in cmv["dados"]["linhas"]}
    assert set(linhas) == {"Farinha de trigo", "Ovos", "Óleo de soja"}
    total = cmv["dados"]["total"]["valor"]
    assert total == pytest.approx(sum(linha["custo"]["valor"] for linha in linhas.values()))
    assert total > 0

    precos = cozinha_confirmada.get("/api/precos", params={"prato": receita["nome"]})
    assert precos.status_code == 200, precos.text
    assert precos.json()["ok"]
