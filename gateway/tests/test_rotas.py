"""Os roteadores da API: sessão compartilhada, envelope único e `ausente` com 404."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from mise.erros import (
    Ausente,
    ErroDeDados,
    ErroDeRegra,
    ErroDeUso,
    MassaDesconhecida,
    OrcamentoExcedido,
)

from gateway import rotas
from gateway.http import criar_app
from gateway.rotas._comum import (
    RespostaPadrao,
    SessaoDaApp,
    categoria_de,
    envelope_de_erro,
    responder,
)

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)


def roteador_de_teste() -> APIRouter:
    """Um roteador como os das áreas: sessão por dependência, envelope comum."""
    roteador = APIRouter()

    @roteador.get("/api/teste/itens/{item_id}", response_model=RespostaPadrao)
    def item(item_id: str, sessao: SessaoDaApp) -> RespostaPadrao:
        def montar() -> dict[str, object]:
            if item_id != "alcaparras":
                raise Ausente("não encontrei esse ingrediente na despensa", id=item_id)
            return {"itens": len(sessao.despensa), "canal": sessao.canal}

        return responder(montar)

    @roteador.get("/api/teste/pergunta", response_model=RespostaPadrao)
    def pergunta() -> RespostaPadrao:
        def montar() -> None:
            raise MassaDesconhecida("Cobertura de chocolate", 79.90, "1 un")

        return responder(montar)

    @roteador.get("/api/escopos", response_model=RespostaPadrao)
    def escopos_novos() -> RespostaPadrao:
        return responder(lambda: {"versao": "nova"})

    return roteador


@pytest.fixture
def com_roteador(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(rotas, "ROTEADORES", (roteador_de_teste(),))
    return TestClient(criar_app())


# --------------------------------------------------------------------------- #
# Roteadores
# --------------------------------------------------------------------------- #


def test_as_rotas_antigas_continuam_ao_lado_dos_roteadores() -> None:
    assert all(isinstance(r, APIRouter) for r in rotas.ROTEADORES)
    assert rotas.despensa.roteador in rotas.ROTEADORES
    assert rotas.perfil.roteador in rotas.ROTEADORES
    corpo = TestClient(criar_app()).get("/api/escopos").json()
    assert corpo["ok"] is True
    assert "registrar_decisao" in corpo["dados"]["escrita"]


@pytest.mark.parametrize(
    "modulo", ["imagens", "estimativa", "visao_geral", "cardapio", "atividades"]
)
def test_o_modulo_de_cada_area_esta_registrado(modulo: str) -> None:
    """Rota nova entra no módulo da área: o registro em `ROTEADORES` já está feito."""
    import importlib

    area = importlib.import_module(f"gateway.rotas.{modulo}")
    assert area.roteador in rotas.ROTEADORES
    assert area.__doc__ is not None
    if not area.roteador.routes:
        assert "Vai servir" in area.__doc__, "o módulo vazio diz o que vai servir"


def test_as_receitas_ja_servem_as_rotas_delas() -> None:
    """A grade, o detalhe, o custo, a avaliação e as notas estão na API."""
    caminhos = set(criar_app().openapi()["paths"])
    assert {
        "/api/receitas",
        "/api/receitas/{slug}",
        "/api/receitas/{slug}/custo",
        "/api/receitas/{slug}/avaliacao",
        "/api/receitas/{slug}/notas",
    } <= caminhos
    assert rotas.receitas.roteador in rotas.ROTEADORES


def test_cada_roteador_entra_uma_vez_e_a_exportacao_esta_na_api() -> None:
    assert len(rotas.ROTEADORES) == len({id(r) for r in rotas.ROTEADORES})
    assert rotas.dados.roteador in rotas.ROTEADORES
    assert "/api/exportacao" in set(criar_app().openapi()["paths"])


def test_o_roteador_da_conversa_esta_registrado() -> None:
    from gateway.rotas.conversa import roteador as conversa

    assert conversa in rotas.ROTEADORES
    caminhos = set(criar_app().openapi()["paths"])
    assert "/api/conversas/{conversa_id}/turnos" in caminhos
    assert "/api/chat/estado" in caminhos


def test_roteador_recebe_a_sessao_do_app(com_roteador: TestClient) -> None:
    corpo = com_roteador.get("/api/teste/itens/alcaparras").json()
    assert corpo == {
        "ok": True,
        "dados": {"itens": 37, "canal": "tela"},
        "erro": None,
        "categoria": None,
        "pergunta": None,
    }


def test_o_que_nao_existe_sai_com_404_e_o_mesmo_envelope(com_roteador: TestClient) -> None:
    resposta = com_roteador.get("/api/teste/itens/caviar")
    assert resposta.status_code == 404
    assert resposta.json() == {
        "ok": False,
        "dados": None,
        "erro": "não encontrei esse ingrediente na despensa",
        "categoria": "ausente",
        "pergunta": None,
    }


def test_pergunta_do_motor_continua_200_com_a_pergunta(com_roteador: TestClient) -> None:
    resposta = com_roteador.get("/api/teste/pergunta")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "dado")
    assert "quanto vem na embalagem" in corpo["pergunta"]


def test_a_rota_do_roteador_vale_mais_que_a_antiga(com_roteador: TestClient) -> None:
    """A versão nova de uma rota substitui a antiga assim que o roteador entra."""
    assert com_roteador.get("/api/escopos").json()["dados"] == {"versao": "nova"}


# --------------------------------------------------------------------------- #
# Sessão, CORS e categorias
# --------------------------------------------------------------------------- #


def test_a_sessao_do_app_e_a_das_rotas_antigas() -> None:
    from mise.dossie import Decisao

    app = criar_app()
    app.state.sessao.dossie.registrar_decisao("Bolo", Decisao.ADIADO)
    historico = TestClient(app).get("/api/cardapio").json()["dados"]["historico"]
    assert [(h["prato"], h["tipo"]) for h in historico] == [("Bolo", "adiado")]
    assert app.state.sessao.canal == "tela"


@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "DELETE"])
def test_cors_deixa_a_tela_editar_e_apagar(metodo: str) -> None:
    resposta = TestClient(criar_app()).options(
        "/api/despensa",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": metodo,
            "Access-Control-Request-Headers": "Idempotency-Key",
        },
    )
    assert resposta.status_code == 200
    assert metodo in resposta.headers["access-control-allow-methods"]
    assert resposta.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_continua_fechado_para_outra_origem() -> None:
    resposta = TestClient(criar_app()).options(
        "/api/despensa",
        headers={"Origin": "https://outro.site", "Access-Control-Request-Method": "DELETE"},
    )
    assert resposta.status_code == 400
    assert "access-control-allow-origin" not in resposta.headers


@pytest.mark.parametrize(
    ("erro", "categoria"),
    [
        (Ausente("não existe"), "ausente"),
        (MassaDesconhecida("Cobertura de chocolate", 79.90, "1 un"), "dado"),
        (ErroDeDados("sem dado"), "dado"),
        (OrcamentoExcedido(90.0, 80.0), "regra"),
        (ErroDeRegra("regra"), "regra"),
        (ErroDeUso("uso"), "uso"),
    ],
)
def test_cada_erro_do_motor_tem_a_sua_categoria(erro: ErroDeUso, categoria: str) -> None:
    assert categoria_de(erro) == categoria
    envelope = envelope_de_erro(erro)
    assert (envelope.ok, envelope.categoria, envelope.erro) == (False, categoria, erro.mensagem)


def test_so_o_erro_de_dado_leva_pergunta() -> None:
    assert envelope_de_erro(MassaDesconhecida("Cobertura", 79.90, "1 un")).pergunta
    assert envelope_de_erro(ErroDeDados("sem pergunta")).pergunta is None
    assert envelope_de_erro(ErroDeUso("uso")).pergunta is None
