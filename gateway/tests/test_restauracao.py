"""Restaurar os dados da planilha: a cópia antes, o recomeço dentro dos mesmos arquivos, e o que fica.

Ela mexe em tudo pela tela (a despensa, a cozinha, o gosto, as estrelas, o preço
de um ingrediente, a decisão, a compra com os R$ 80,00, a resposta sobre uma
receita, uma receita ditada, uma conversa). "Restaurar os dados da planilha"
guarda a cópia e volta tudo ao começo: 37 ingredientes, R$ 663,39, os R$ 80,00
inteiros, a cozinha sem resposta dela. As receitas das páginas lidas ficam,
como a página veio, e as fotos também. O agente, que é outro processo com o
mesmo dossiê aberto, vê o recomeço na leitura seguinte.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.catalogo import OrigemNoCatalogo
from mise.mcp_server import Sessao, abrir_sessao
from retrieval.extrator import extrair
from test_rotas_dados import _com_um_pouco_de_tudo

from gateway.http import criar_app

RAIZ = Path(__file__).resolve().parents[2]
CONTRATO = RAIZ / "contratos" / "web" / "restauracao.json"

URL_SEM_RENDIMENTO = "https://www.receitasteste.com.br/farofa-de-bacon"
PAGINA_SEM_RENDIMENTO = (
    '<script type="application/ld+json">'
    + json.dumps(
        {
            "@type": "Recipe",
            "name": "Farofa de bacon",
            "publisher": {"@type": "Organization", "name": "Receitas Teste"},
            "recipeIngredient": ["200 g de bacon", "2 xícaras de farinha de mandioca"],
            "recipeInstructions": [
                "Frite o bacon na frigideira por 10 minutos.",
                "Junte a farinha.",
            ],
        }
    )
    + "</script>"
)


@pytest.fixture
def estado(tmp_path: Path) -> Path:
    pasta = tmp_path / "estado"
    pasta.mkdir()
    return pasta


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, estado: Path) -> TestClient:
    banco = estado / "dossie.db"
    trilha = estado / "auditoria.jsonl"
    trilha.write_text('{"momento": 1, "ferramenta": "consultar_despensa"}\n', encoding="utf-8")
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.setenv("MISE_AUDITORIA", str(trilha))
    monkeypatch.delenv("MISE_CONVERSAS", raising=False)
    sessao_de_teste.preparar_dossie(banco)
    app = criar_app()
    sessao = app.state.sessao
    sessao_de_teste.guardar_receitas(sessao)
    sessao.catalogar(extrair(PAGINA_SEM_RENDIMENTO, URL_SEM_RENDIMENTO), OrigemNoCatalogo.CONVERSA)
    return TestClient(app)


def _ok(resposta: Any) -> Any:
    corpo = resposta.json()
    assert resposta.status_code in (200, 201), corpo
    assert corpo["ok"], corpo
    return corpo["dados"]


def _slug(cliente: TestClient, nome: str) -> str:
    sessao: Sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    guardada = sessao.catalogo.por_nome(nome)
    assert guardada is not None, nome
    return guardada.slug


def _mexer_em_tudo(cliente: TestClient) -> None:
    """Uma mudança de cada coisa, pela tela, e uma conversa."""
    _com_um_pouco_de_tudo(cliente)
    _ok(
        cliente.post(
            "/api/despensa/itens",
            json={
                "nome": "Farinha de rosca",
                "estoque": 0.5,
                "unidade": "kg",
                "origem": "ja_tinha",
            },
        )
    )
    _ok(cliente.delete("/api/despensa/itens/sal"))
    _ok(cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json={"valor": 2}))
    bolo = _slug(cliente, "Bolo de fubá")
    _ok(cliente.put(f"/api/receitas/{bolo}/avaliacao", json={"estrelas": {"sabor": 5}}))
    _ok(cliente.put(f"/api/receitas/{bolo}/notas", json={"texto": "Sai bem no sábado."}))
    farofa = _slug(cliente, "Farofa de bacon")
    _ok(
        cliente.post(
            f"/api/receitas/{farofa}/resposta",
            json={"campo": "rendimento_porcoes", "resposta": "6"},
        )
    )
    _ok(cliente.post("/api/conversas", json={}))


def _restaurar(cliente: TestClient, chave: str | None = None) -> dict[str, Any]:
    cabecalhos = {"Idempotency-Key": chave} if chave else {}
    dados: dict[str, Any] = _ok(
        cliente.post("/api/dados/restaurar", json={"confirmar": True}, headers=cabecalhos)
    )
    return dados


def _copias(estado: Path) -> list[Path]:
    pasta = estado / "copias"
    return sorted(pasta.iterdir()) if pasta.is_dir() else []


def _contar(banco: Path, tabela: str) -> int:
    with closing(sqlite3.connect(banco)) as conexao:
        return int(conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])


def test_restaurar_volta_tudo_a_planilha_e_diz_com_o_que_ela_recomeca(
    cliente: TestClient, estado: Path
) -> None:
    _mexer_em_tudo(cliente)
    antes = _ok(cliente.get("/api/despensa"))
    assert antes["total_itens"] != 37 or antes["orcamento"]["compras"]

    dados = _restaurar(cliente, "clique-1")

    assert dados["texto"] == (
        "Pronto, tudo voltou a ser como na planilha: 37 ingredientes, R$ 663,39 pagos, e os "
        "complementos têm R$ 80,00. As 2 receitas que eu já li continuam na grade."
    )
    assert dados["mudou"] is True
    conciliacao = dados["conciliacao"]
    assert conciliacao["ingredientes"] == 37
    assert conciliacao["total_pago"] == {"valor": 663.39, "texto": "R$ 663,39"}
    assert conciliacao["orcamento_restante"] == {"valor": 80.0, "texto": "R$ 80,00"}
    assert conciliacao["texto"] == "37 ingredientes, R$ 663,39 pagos, restam R$ 80,00"
    assert conciliacao["cozinha_texto"].startswith("0 respondidos pela senhora")
    assert set(dados["recursos"]) >= {
        "despensa",
        "orcamento",
        "receitas",
        "perfil",
        "cardapio",
        "atividades",
        "conversas",
        "visao-geral",
    }
    assert dados["mantido"]["receitas"] == 2
    assert dados["apagado"]["conversas"] == 1
    assert dados["apagado"]["receitas ditas"] == 1
    assert dados["apagado"]["respostas sobre as receitas"] == 1

    despensa = _ok(cliente.get("/api/despensa"))
    assert despensa["total_itens"] == 37
    assert despensa["total_investido"] == {"valor": 663.39, "texto": "R$ 663,39"}
    assert despensa["orcamento"]["restante"]["texto"] == "R$ 80,00"
    assert despensa["orcamento"]["compras"] == []
    assert "Sal" in {item["nome"] for item in despensa["itens"]}
    assert "Farinha de rosca" not in {item["nome"] for item in despensa["itens"]}
    assert despensa["pendencias"] == []

    cozinha = _ok(cliente.get("/api/perfil"))
    assert cozinha["respondidos"] == 0
    assert all(r["valor"] is None for r in cozinha["restricoes"].values())
    cardapio = _ok(cliente.get("/api/cardapio"))
    assert (cardapio["pratos"], cardapio["historico"], cardapio["nao_quer"]) == ([], [], [])
    tudo = json.loads(cliente.get("/api/exportacao").content.decode("utf-8"))
    for lista in (
        "despensa_eventos",
        "cozinha_eventos",
        "compras",
        "decisoes",
        "gostos",
        "precos_de_mercado",
        "receitas_em_avaliacao",
    ):
        assert tudo[lista] == [], lista
    assert _ok(cliente.get("/api/conversas"))["conversas"] == []
    assert (estado / "auditoria.jsonl").read_text(encoding="utf-8") == ""


def test_o_catalogo_fica_como_a_pagina_veio_e_a_receita_ditada_sai(cliente: TestClient) -> None:
    _mexer_em_tudo(cliente)
    farofa = _slug(cliente, "Farofa de bacon")
    sessao: Sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    completada = sessao.catalogo.obter(farofa)
    assert completada is not None
    assert completada.receita.rendimento_porcoes == 6
    assert len(completada.respostas) == 1
    arroz = _slug(cliente, "Arroz com frango")

    _restaurar(cliente)

    voltou = sessao.catalogo.obter(farofa)
    assert voltou is not None
    assert voltou.respostas == ()
    # Como a página veio: sem o rendimento que ela disse.
    assert voltou.receita.rendimento_informado is False
    assert voltou.receita.rendimento_porcoes != 6
    assert sessao.catalogo.por_nome("Bolo de fubá") is not None
    assert cliente.get(f"/api/receitas/{arroz}").status_code == 404
    bolo = _ok(cliente.get(f"/api/receitas/{_slug(cliente, 'Bolo de fubá')}"))
    assert bolo["nome"] == "Bolo de fubá"


def test_a_copia_vem_antes_e_guarda_tudo_o_que_havia(cliente: TestClient, estado: Path) -> None:
    _mexer_em_tudo(cliente)
    fotos = estado / "imagens"
    fotos.mkdir()
    (fotos / "0123456789abcdef0123456789abcdef.jpg").write_bytes(b"foto")

    dados = _restaurar(cliente)

    (copia,) = _copias(estado)
    assert copia.name == dados["copia"]
    assert _contar(copia / "dossie.db", "decisoes") == 1
    assert _contar(copia / "dossie.db", "despensa_eventos") >= 2
    assert _contar(copia / "conversas.db", "conversas") == 1
    assert "consultar_despensa" in (copia / "auditoria.jsonl").read_text(encoding="utf-8")
    # O arquivo do dossiê continua o mesmo, no mesmo lugar; as fotos ficam.
    assert (estado / "dossie.db").is_file()
    assert _contar(estado / "dossie.db", "decisoes") == 0
    assert (fotos / "0123456789abcdef0123456789abcdef.jpg").read_bytes() == b"foto"


def test_o_mesmo_clique_nao_restaura_duas_vezes_e_restaurar_de_novo_nao_muda_nada(
    cliente: TestClient, estado: Path
) -> None:
    _mexer_em_tudo(cliente)
    primeira = _restaurar(cliente, "clique-1")
    repetida = _restaurar(cliente, "clique-1")
    assert repetida["repetida"] is True
    assert repetida["copia"] == primeira["copia"]
    assert len(_copias(estado)) == 1

    de_novo = _restaurar(cliente, "clique-2")
    assert de_novo["mudou"] is False
    assert de_novo["texto"].startswith("Já estava tudo como na planilha: 37 ingredientes")
    assert de_novo["conciliacao"] == primeira["conciliacao"]
    assert len(_copias(estado)) == 2


def test_sem_confirmar_nada_muda(cliente: TestClient, estado: Path) -> None:
    _mexer_em_tudo(cliente)
    corpo = cliente.post("/api/dados/restaurar", json={}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")
    assert "confirmar" in corpo["erro"]
    assert _copias(estado) == []
    assert _ok(cliente.get("/api/cardapio"))["pratos"]


def test_a_consultora_ve_o_recomeco_na_leitura_seguinte(cliente: TestClient, estado: Path) -> None:
    """O servidor MCP é outro processo, com a própria conexão e a despensa em cache."""
    _mexer_em_tudo(cliente)
    consultora = abrir_sessao(sessao_de_teste.PLANILHA, estado / "dossie.db")
    try:
        assert "Farinha de rosca" in consultora.despensa.itens
        assert consultora.dossie.cardapio == ("Arroz com frango",)
        assert consultora.perfil.restricoes.tempo_max_por_fornada_min == 120

        _restaurar(cliente)

        despensa = consultora.despensa
        assert len(despensa.itens) == 37
        assert "Farinha de rosca" not in despensa.itens
        assert despensa.total_investido.valor == Decimal("663.39")
        assert consultora.dossie.orcamento().restante.valor == Decimal(80)
        assert consultora.dossie.cardapio == ()
        assert consultora.candidatas == {}
        assert consultora.dossie.gostos() == ()
        assert consultora.perfil.restricoes.tempo_max_por_fornada_min is None
        assert consultora.catalogo.por_nome("Arroz com frango") is None
        assert consultora.catalogo.por_nome("Bolo de fubá") is not None
    finally:
        consultora.dossie.fechar()


def test_a_forma_do_contrato(cliente: TestClient) -> None:
    _mexer_em_tudo(cliente)
    dados = _restaurar(cliente)
    exemplo = json.loads(CONTRATO.read_text(encoding="utf-8"))
    assert set(dados) == set(exemplo)
    assert set(dados["conciliacao"]) == set(exemplo["conciliacao"])
    assert set(dados["mantido"]) == set(exemplo["mantido"])
