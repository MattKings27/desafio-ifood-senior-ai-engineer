"""O cardápio: a forma do contrato, a conta de agora, as decisões em frases e o desfazer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.dinheiro import Dinheiro
from mise.dossie import Decisao, Dossie
from mise.perfil import Gosto
from test_rotas_despensa import conferir_contrato, contrato

from gateway.cardapio import (
    Passo,
    controle_do_preco,
    dinheiro_do_texto,
    do_prato,
    o_prato,
    texto_da_decisao,
)
from gateway.http import criar_app

PRATO = "Arroz com frango"


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


def dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"], corpo.get("erro")
    return corpo["dados"]


def decidir(cliente: TestClient, decisao: str, **extra: Any) -> dict[str, Any]:
    resultado: dict[str, Any] = dados(
        cliente.post("/api/decisao", json={"prato": PRATO, "decisao": decisao, **extra})
    )
    return resultado


def cardapio(cliente: TestClient) -> dict[str, Any]:
    resultado: dict[str, Any] = dados(cliente.get("/api/cardapio"))
    return resultado


# --------------------------------------------------------------------------- #
# A forma e a conta
# --------------------------------------------------------------------------- #


def test_o_cardapio_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    conferir_contrato(contrato("cardapio.json"), cardapio(cliente))


def test_sem_decisao_o_cardapio_diz_que_nao_ha_prato(cliente: TestClient) -> None:
    vazio = cardapio(cliente)
    assert (vazio["pratos"], vazio["historico"], vazio["nao_quer"]) == ([], [], [])
    resumo = vazio["resumo"]
    assert resumo["texto"] == "nenhum prato no cardápio ainda"
    assert resumo["preco_medio"] is None
    assert resumo["margem_media_texto"] == "sem prato com a conta pronta ainda"
    assert resumo["orcamento_texto"] == "Nada gasto dos R$ 80,00 dos complementos ainda."
    assert resumo["orcamento_rota"] == "/despensa#orcamento"


def test_o_prato_aceito_traz_o_que_chega_e_o_lucro_com_a_conta(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    (prato,) = cardapio(cliente)["pratos"]
    assert prato["prato"] == PRATO
    assert prato["slug"] == "arroz-com-frango"
    assert prato["rota"] == "/receitas/arroz-com-frango"
    textos = {c: prato[c]["texto"] for c in ("preco", "recebe", "custo_porcao", "lucro_porcao")}
    assert textos == {
        "preco": "R$ 18,00",
        "recebe": "R$ 16,20",
        "custo_porcao": "R$ 3,00",
        "lucro_porcao": "R$ 13,20",
    }
    assert "chegam R$ 16,20" in prato["derivacao"]
    assert (prato["da_prejuizo"], prato["aviso"]) == (False, None)
    assert prato["decidido_texto"].startswith("hoje, ")


def test_o_resumo_soma_no_servidor(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    resumo = cardapio(cliente)["resumo"]
    assert resumo["texto"] == "1 prato no cardápio"
    assert resumo["preco_medio"]["texto"] == "R$ 18,00"
    assert resumo["margem_media_texto"] == "73% de sobra depois da taxa e do ingrediente"


def test_o_lucro_acompanha_a_despensa_de_agora(cliente: TestClient) -> None:
    """O preço é o dela; o custo vem da despensa de hoje, e o aviso diz o que mudou."""
    decidir(cliente, "aceito", preco=18)
    frango = next(i for i in dados(cliente.get("/api/despensa"))["itens"] if "rango" in i["nome"])
    dados(cliente.patch(f"/api/despensa/itens/{frango['id']}", json={"preco_pago": 60}))
    (prato,) = cardapio(cliente)["pratos"]
    assert prato["preco"]["texto"] == "R$ 18,00"
    assert prato["custo_porcao"]["texto"] != "R$ 3,00"
    assert prato["aviso"].startswith(
        "O custo da porção mudou desde que a senhora aceitou: era R$ 3,00"
    )


def test_preco_abaixo_do_minimo_avisa_o_prejuizo(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=3)
    (prato,) = cardapio(cliente)["pratos"]
    assert prato["da_prejuizo"] is True
    assert prato["aviso"] == (
        "A R$ 3,00, a senhora perde R$ 0,30 em cada porção. O mínimo sem prejuízo é R$ 3,34."
    )


def test_prato_sem_receita_guardada_usa_a_conta_do_aceite(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_decisao(
            "Pastel", Decisao.ACEITO, detalhes={"preco": "R$ 10,00", "cmv_por_porcao": "R$ 2,00"}
        )
        dossie.registrar_decisao("Coxinha", Decisao.ACEITO, detalhes={})
    pratos = {p["prato"]: p for p in cardapio(cliente)["pratos"]}
    pastel, coxinha = pratos["Pastel"], pratos["Coxinha"]
    assert (pastel["slug"], pastel["rota"], pastel["imagem"]) == ("pastel", "/cardapio", None)
    assert pastel["lucro_porcao"]["texto"] == "R$ 7,00"
    assert pastel["aviso"].startswith("Não consegui refazer a conta com a despensa de agora")
    assert (coxinha["preco"], coxinha["lucro_porcao"], coxinha["derivacao"]) == (None, None, "")
    assert coxinha["aviso"] is None


# --------------------------------------------------------------------------- #
# As decisões em frases
# --------------------------------------------------------------------------- #


def test_cada_decisao_vira_uma_frase_dela(cliente: TestClient) -> None:
    assert decidir(cliente, "aceito", preco=18)["texto"] == (
        "A senhora aceitou o arroz com frango a R$ 18,00."
    )
    assert decidir(cliente, "aceito", preco=20)["texto"] == (
        "A senhora mudou o preço do arroz com frango de R$ 18,00 para R$ 20,00."
    )
    assert decidir(cliente, "recusado", motivo="muito trabalho.")["texto"] == (
        "A senhora tirou o arroz com frango do cardápio. O motivo: muito trabalho."
    )
    historico = cardapio(cliente)["historico"]
    assert [(h["tipo"], h["tipo_rotulo"]) for h in historico] == [
        ("retirado", "Tirou do cardápio"),
        ("preco", "Mudou o preço"),
        ("aceito", "Aceitou"),
    ]
    assert [h["pode_desfazer"] for h in historico] == [True, False, False]
    assert {h["canal"] for h in historico} == {"tela"}
    assert {h["rota"] for h in historico} == {"/receitas/arroz-com-frango"}


def test_recusar_e_adiar_sem_ter_aceitado(cliente: TestClient) -> None:
    assert decidir(cliente, "adiado")["texto"] == (
        "A senhora deixou o arroz com frango para decidir depois."
    )
    assert decidir(cliente, "recusado")["texto"] == (
        "A senhora disse que não quer o arroz com frango no cardápio."
    )


def test_a_chave_da_tela_vale_como_id_cliente(cliente: TestClient) -> None:
    for _ in range(2):
        decidir(cliente, "adiado", id_cliente="clique-1")
    assert len(cardapio(cliente)["historico"]) == 1


def test_os_que_ela_nao_quer(cliente: TestClient, banco: Path) -> None:
    decidir(cliente, "aceito", preco=18)
    decidir(cliente, "recusado")
    with Dossie(banco) as dossie:
        dossie.registrar_gosto("Bolo de fubá", Gosto.NAO_GOSTA, "suja muito o forno")
        dossie.registrar_gosto("Pudim", Gosto.NAO_GOSTA)
        dossie.registrar_gosto("Quindim", Gosto.GOSTA)
        dossie.registrar_decisao("Pastel", Decisao.RECUSADO, "não tenho fritadeira")
    nao_quer = {n["prato"]: n for n in cardapio(cliente)["nao_quer"]}
    assert {p: n["motivo_texto"] for p, n in nao_quer.items()} == {
        "Arroz com frango": "tirou do cardápio",
        "Bolo de fubá": "suja muito o forno",
        "Pudim": "não gosta de fazer",
        "Pastel": "não tenho fritadeira",
    }
    assert nao_quer["Bolo de fubá"]["rota"].startswith("/receitas/")
    assert nao_quer["Pudim"]["rota"] == "/cardapio"
    assert all(n["decidido_texto"] for n in nao_quer.values())


def test_prato_recusado_de_primeira_nao_quer_no_cardapio(cliente: TestClient) -> None:
    decidir(cliente, "recusado")
    (entrada,) = cardapio(cliente)["nao_quer"]
    assert entrada["motivo_texto"] == "não quer no cardápio"


# --------------------------------------------------------------------------- #
# Desfazer
# --------------------------------------------------------------------------- #


def test_desfazer_a_retirada_volta_o_prato_com_o_preco(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    decidir(cliente, "recusado")
    feito = dados(cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer"))
    assert feito["texto"] == (
        "A senhora voltou atrás: o arroz com frango está de novo no cardápio, a R$ 18,00."
    )
    assert [p["preco"]["texto"] for p in feito["pratos"]] == ["R$ 18,00"]
    ultimo = feito["historico"][0]
    assert (ultimo["tipo"], ultimo["tipo_rotulo"], ultimo["pode_desfazer"]) == (
        "desfeito",
        "Voltou atrás",
        False,
    )


def test_desfazer_a_mudanca_de_preco_volta_o_preco_de_antes(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    decidir(cliente, "aceito", preco=20)
    feito = dados(cliente.post("/api/cardapio/arroz-com-frango/desfazer"))
    assert [p["preco"]["texto"] for p in feito["pratos"]] == ["R$ 18,00"]


def test_desfazer_o_unico_aceite_deixa_para_decidir_depois(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    feito = dados(cliente.post("/api/cardapio/ARROZ%20COM%20FRANGO/desfazer"))
    assert feito["pratos"] == []
    assert feito["texto"] == "A senhora voltou atrás: o arroz com frango fica para decidir depois."


def test_desfazer_a_recusa_volta_a_recusa_anterior(cliente: TestClient) -> None:
    decidir(cliente, "recusado", motivo="caro")
    decidir(cliente, "adiado")
    feito = dados(cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer"))
    assert feito["texto"] == (
        "A senhora voltou atrás: o arroz com frango fica fora do cardápio. O motivo: caro."
    )


def test_nao_se_desfaz_o_que_ja_foi_desfeito_nem_o_adiado_sozinho(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    dados(cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer"))
    de_novo = cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer").json()
    assert (de_novo["ok"], de_novo["categoria"]) == (False, "uso")
    assert "Não há o que desfazer" in de_novo["erro"]


def test_desfazer_prato_sem_decisao_e_404(cliente: TestClient) -> None:
    resposta = cliente.post("/api/cardapio/lasanha/desfazer")
    assert resposta.status_code == 404
    assert resposta.json()["categoria"] == "ausente"


def test_desfazer_com_a_mesma_chave_nao_grava_duas_vezes(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    decidir(cliente, "recusado")
    clique = {"Idempotency-Key": "desfazer-1"}
    dados(cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer", headers=clique))
    segunda = cliente.post("/api/cardapio/Arroz%20com%20frango/desfazer", headers=clique).json()
    assert segunda["ok"] is False
    assert len(cardapio(cliente)["historico"]) == 3


# --------------------------------------------------------------------------- #
# As notas
# --------------------------------------------------------------------------- #


def test_as_notas_do_prato_sao_as_da_receita(cliente: TestClient) -> None:
    decidir(cliente, "aceito", preco=18)
    feito = dados(
        cliente.put(
            "/api/cardapio/Arroz%20com%20frango/notas", json={"texto": " Sai bem no almoço "}
        )
    )
    assert feito["texto"] == "Anotei."
    assert feito["pratos"][0]["notas"] == "Sai bem no almoço"
    receita = dados(cliente.get("/api/receitas/arroz-com-frango"))
    assert receita["avaliacao"]["notas"] == "Sai bem no almoço"
    apagado = dados(cliente.put("/api/cardapio/arroz-com-frango/notas", json={"texto": ""}))
    assert (apagado["texto"], apagado["pratos"][0]["notas"]) == ("Apaguei as notas.", None)


def test_notas_de_prato_sem_receita_sao_404(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_decisao("Pastel", Decisao.ADIADO)
    resposta = cliente.put("/api/cardapio/Pastel/notas", json={"texto": "x"})
    assert resposta.status_code == 404
    assert resposta.json()["erro"] == "O prato pastel não tem receita guardada para anotar."


# --------------------------------------------------------------------------- #
# O controle de preço e as peças
# --------------------------------------------------------------------------- #


def test_os_limites_do_controle_vem_da_api(cliente: TestClient) -> None:
    precos = dados(cliente.get("/api/precos", params={"prato": PRATO}))
    assert precos["controle"] == {
        "min": {"valor": 3.34, "texto": "R$ 3,34"},
        "max": {"valor": 18.0, "texto": "R$ 18,00"},
        "passo": 0.5,
    }


def test_o_controle_de_um_prato_baratinho() -> None:
    controle = controle_do_preco(Dinheiro.de("0.05"), Dinheiro.de("0.06"))
    assert (controle["min"]["texto"], controle["max"]["texto"]) == ("R$ 0,50", "R$ 1,50")


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("R$ 18,00", Dinheiro.de("18.00")),
        ("R$ 1.234,56", Dinheiro.de("1234.56")),
        ("-R$ 0,03", Dinheiro.de("-0.03")),
        ("18", None),
        (None, None),
    ],
)
def test_o_valor_gravado_volta_a_ser_dinheiro(texto: object, valor: Dinheiro | None) -> None:
    assert dinheiro_do_texto(texto) == valor


def test_nome_sem_genero_conhecido_leva_o_prato() -> None:
    assert (o_prato("Arroz com frango"), do_prato("Arroz com frango")) == (
        "o arroz com frango",
        "do arroz com frango",
    )
    assert (o_prato("Xis"), do_prato("Xis")) == ("o prato xis", "do prato xis")


def test_a_frase_sem_o_preco_gravado(banco: Path) -> None:
    with Dossie(banco) as dossie:
        aceite = dossie.registrar_decisao("Xis", Decisao.ACEITO, detalhes={})
        outro = dossie.registrar_decisao("Xis", Decisao.ACEITO, detalhes={"preco": "R$ 9,00"})
        desfeito = dossie.registrar_decisao("Xis", Decisao.ACEITO, detalhes={}, desfaz=outro.id)
    assert texto_da_decisao(aceite, ()) == "A senhora aceitou o prato xis."
    assert Passo(outro, aceite).texto() == "A senhora mudou o preço do prato xis para R$ 9,00."
    assert Passo(aceite, outro).texto() == "A senhora mudou o preço do prato xis de R$ 9,00."
    assert Passo(desfeito, outro).texto() == (
        "A senhora voltou atrás: o prato xis está de novo no cardápio."
    )
