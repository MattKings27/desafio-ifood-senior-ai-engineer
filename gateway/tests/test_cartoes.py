"""Os cards da conversa: o tipo do contrato e a rota que traz os dados do motor."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from gateway.cartoes import CARTOES, PRECO_MAXIMO, TIPOS_DE_CARTAO, cartao_para
from gateway.frases import FRASES_DA_AGENTE
from gateway.politica import ESCOPOS

RAIZ = Path(__file__).resolve().parents[2]
CONTRATOS = RAIZ / "contratos" / "web"
LEIA = (CONTRATOS / "LEIA.md").read_text(encoding="utf-8")

MODELOS = [(nome, modelo) for nome, modelo in CARTOES.items() if modelo is not None]


def _rota_casa(modelo: str, rota: str) -> bool:
    """`/api/receitas/{slug}` casa com `/api/receitas/arroz-com-frango`."""
    padrao = re.sub(r"\\\{\w+\\\}", "[^/?]+", re.escape(modelo))
    return re.fullmatch(padrao, urlsplit(rota).path) is not None


# --------------------------------------------------------------------------- #
# O catálogo
# --------------------------------------------------------------------------- #


def test_toda_ferramenta_do_motor_tem_a_decisao_de_card() -> None:
    """Sem card é uma decisão (`None`), não um esquecimento."""
    assert set(CARTOES) == set(ESCOPOS)


def test_os_tipos_de_card_sao_os_do_contrato() -> None:
    (lista,) = re.findall(r"Cards \(`tipo_cartao`\):(.*?)`dados`", LEIA, re.S)
    assert set(re.findall(r"`(\w+)`", lista)) == TIPOS_DE_CARTAO
    assert {m.tipo_cartao for _, m in MODELOS} <= TIPOS_DE_CARTAO


def test_toda_rota_de_card_e_uma_rota_de_hoje_ou_do_contrato(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from gateway.http import criar_app

    monkeypatch.setenv("MISE_PLANILHA", str(RAIZ / "dados" / "despensa_dona_maria.xlsx"))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    app = TestClient(criar_app()).app
    de_hoje = {getattr(r, "path", "") for r in app.routes}
    do_contrato = set(re.findall(r"(/api/[\w\-{}|/]+)", LEIA))
    exemplos = "".join(p.read_text(encoding="utf-8") for p in CONTRATOS.glob("*.json*"))
    dos_exemplos = {urlsplit(r).path for r in re.findall(r'"rota": "(/api/[^"]+)"', exemplos)}
    conhecidas = de_hoje | do_contrato | dos_exemplos
    for nome, modelo in MODELOS:
        assert modelo.rota is None or modelo.rota in conhecidas, (nome, modelo.rota)


def test_as_ferramentas_do_hermes_nao_geram_card() -> None:
    for nome in FRASES_DA_AGENTE:
        assert cartao_para(nome, {"query": "arroz", "urls": ["https://a.com"]}) is None


# --------------------------------------------------------------------------- #
# O contrato da conversa
# --------------------------------------------------------------------------- #


def test_o_card_do_turno_de_exemplo_sai_do_mesmo_tipo_e_rota() -> None:
    eventos = [
        json.loads(linha)
        for linha in (CONTRATOS / "chat-eventos.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (atividade,) = [e for e in eventos if e["tipo"] == "atividade.iniciada"]
    (evento,) = [e for e in eventos if e["tipo"] == "cartao"]
    cartao = cartao_para(atividade["ferramenta"], {"receita": {"nome": "Arroz com frango"}})
    assert cartao is not None
    assert cartao["tipo_cartao"] == evento["tipo_cartao"]
    assert cartao["ref"]["rota"] is not None
    assert _rota_casa(cartao["ref"]["rota"], evento["ref"]["rota"])


def test_o_card_da_conversa_de_exemplo_aponta_para_a_mesma_conta() -> None:
    conversa = json.loads((CONTRATOS / "conversa.json").read_text(encoding="utf-8"))
    (guardado,) = [
        parte["cartao"]
        for mensagem in conversa["mensagens"]
        for parte in mensagem["partes"]
        if parte["tipo"] == "cartao"
    ]
    cartao = cartao_para("calcular_cmv", {"receita": {"nome": "Arroz com frango"}})
    assert cartao is not None
    assert cartao["tipo_cartao"] == guardado["tipo_cartao"]
    assert cartao["ref"]["rota"] is not None
    assert _rota_casa(cartao["ref"]["rota"], guardado["ref"]["rota"])


def test_os_cards_de_exemplo_sao_um_por_tipo_na_rota_do_modelo() -> None:
    """`contratos/web/cartoes/<tipo>.json`: um exemplo de cada tipo, na rota da ferramenta."""
    exemplos = {
        arquivo.stem: json.loads(arquivo.read_text(encoding="utf-8"))
        for arquivo in sorted((CONTRATOS / "cartoes").glob("*.json"))
    }
    assert set(exemplos) == TIPOS_DE_CARTAO
    modelos = {m.tipo_cartao: m.rota for _, m in MODELOS}
    for tipo, exemplo in exemplos.items():
        assert exemplo["tipo_cartao"] == tipo
        assert set(exemplo) == {"cartao_id", "tipo_cartao", "ref", "gerado_texto", "dados"}, tipo
        assert isinstance(exemplo["dados"], dict) and exemplo["dados"], tipo
        rota = exemplo["ref"]["rota"]
        if tipo in modelos:
            modelo = modelos[tipo]
            assert (rota is None) == (modelo is None), tipo
            assert modelo is None or _rota_casa(modelo, rota), (tipo, modelo, rota)


# --------------------------------------------------------------------------- #
# Cada ferramenta
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ferramenta", "argumentos", "tipo", "rota", "parametros"),
    [
        ("diagnostico_despensa", {}, "despensa_resumo", "/api/visao-geral", {}),
        (
            "custo_unitario",
            {"ingrediente": " Peito de   frango "},
            "ingrediente",
            "/api/despensa/itens/{id}",
            {"ingrediente": "Peito de frango"},
        ),
        (
            "registrar_resposta",
            {"tipo": "Equipamento", "campo": "air_fryer", "resposta": "tem"},
            "cozinha_atualizada",
            "/api/perfil",
            {"tipo": "equipamento", "campo": "air_fryer"},
        ),
        (
            "registrar_resposta",
            {"tipo": "operacional", "campo": "bocas_fogao", "resposta": "4"},
            "cozinha_atualizada",
            "/api/perfil",
            {"tipo": "operacional", "campo": "bocas_fogao"},
        ),
        ("proxima_pergunta", {}, "pergunta", None, {}),
        (
            "avaliar_receita",
            {"receita": {"nome": "Arroz com frango", "url": "https://tudogostoso.com.br/r/1"}},
            "viabilidade",
            "/api/receitas/{slug}",
            {"prato": "Arroz com frango", "url": "https://tudogostoso.com.br/r/1"},
        ),
        (
            "avaliar_receita",
            {"receita": {"nome": "Arroz com frango", "url": "javascript:alert(1)"}},
            "viabilidade",
            "/api/receitas/{slug}",
            {"prato": "Arroz com frango"},
        ),
        (
            "avaliar_receita",
            {"receita_id": " Arroz-com-frango "},
            "viabilidade",
            "/api/receitas/{slug}",
            {"receita_id": "arroz-com-frango"},
        ),
        ("comparar_candidatas", {}, "comparacao", "/api/receitas", {"aba": "pode_fazer"}),
        (
            "calcular_cmv",
            {"receita": {"nome": "Bolo de cenoura"}},
            "custo_porcao",
            "/api/receitas/{slug}/custo",
            {"prato": "Bolo de cenoura"},
        ),
        (
            "calcular_cmv",
            {"receita_id": "3f2a9c0d1b7e4a55"},
            "custo_porcao",
            "/api/receitas/{slug}/custo",
            {"receita_id": "3f2a9c0d1b7e4a55"},
        ),
        ("cenarios_preco", {"prato": "Bolo"}, "cenarios", "/api/precos", {"prato": "Bolo"}),
        (
            "cenarios_preco",
            {"receita_id": "bolo", "prato": "Bolo"},
            "cenarios",
            "/api/precos",
            {"receita_id": "bolo", "prato": "Bolo"},
        ),
        (
            "testar_sensibilidade",
            {"prato": "Bolo", "preco": 12},
            "ponto_de_preco",
            "/api/preco-em",
            {"prato": "Bolo", "preco": 12.0},
        ),
        (
            "testar_sensibilidade",
            {"prato": "Bolo", "preco": "12.5"},
            "ponto_de_preco",
            "/api/preco-em",
            {"prato": "Bolo", "preco": 12.5},
        ),
        (
            "testar_sensibilidade",
            {"receita_id": "bolo", "preco": 12},
            "ponto_de_preco",
            "/api/preco-em",
            {"receita_id": "bolo", "preco": 12.0},
        ),
        (
            "estimar_preco_preliminar",
            {"prato": "Bolo"},
            "preco_preliminar",
            "/api/receitas/{slug}/estimativa",
            {"prato": "Bolo"},
        ),
        (
            "estimar_preco_preliminar",
            {"receita_id": "bolo"},
            "preco_preliminar",
            "/api/receitas/{slug}/estimativa",
            {"receita_id": "bolo"},
        ),
        (
            "registrar_avaliacao_da_receita",
            {"receita_id": "arroz-com-frango", "gosta": True, "estrelas": {"sabor": 5}},
            "avaliacao_da_receita",
            "/api/receitas/{slug}/avaliacao",
            {"receita_id": "arroz-com-frango"},
        ),
        (
            "consultar_conhecimento",
            {"pergunta": "Posso trocar  manteiga\npor óleo?", "k": 3},
            "fontes",
            None,
            {"pergunta": "Posso trocar manteiga por óleo?"},
        ),
        (
            "buscar_receita_na_web",
            {"url": " https://www.tudogostoso.com.br/receita/1 ", "fonte": "TudoGostoso"},
            "receita",
            "/api/receitas/{slug}",
            {"url": "https://www.tudogostoso.com.br/receita/1"},
        ),
        ("consultar_orcamento", {}, "orcamento", "/api/orcamento", {}),
        (
            "registrar_compra",
            {"prato": "Frango com milho", "ingrediente": "milho", "valor": 6},
            "orcamento",
            "/api/orcamento",
            {},
        ),
        ("registrar_preco_mercado", {"valor": 18.5}, "orcamento", "/api/orcamento", {}),
        (
            "registrar_decisao",
            {"prato": "Bolo", "decisao": "aceito", "preco": 12},
            "decisao",
            "/api/cardapio",
            {"prato": "Bolo"},
        ),
    ],
)
def test_card_de_cada_ferramenta(
    ferramenta: str,
    argumentos: dict[str, Any],
    tipo: str,
    rota: str | None,
    parametros: dict[str, object],
) -> None:
    assert cartao_para(ferramenta, argumentos) == {
        "tipo_cartao": tipo,
        "ref": {"rota": rota, "parametros": parametros},
    }


def test_so_o_que_identifica_o_card_vai_para_ele() -> None:
    """O resto dos argumentos (um HTML, as estrelas, as notas) nunca entra no card."""
    cartao = cartao_para(
        "buscar_receita_na_web", {"html": "<script>x</script>", "url": "https://exemplo.com.br/r"}
    )
    assert cartao == {
        "tipo_cartao": "receita",
        "ref": {"rota": "/api/receitas/{slug}", "parametros": {"url": "https://exemplo.com.br/r"}},
    }


def test_a_ordem_dos_parametros_e_a_precedencia_da_ferramenta() -> None:
    """A receita inteira vale mais que o id na avaliação; no preço, o id vale mais que o nome."""
    avaliar = cartao_para(
        "avaliar_receita", {"receita_id": "outra", "receita": {"nome": "Arroz com frango"}}
    )
    assert avaliar is not None
    assert list(avaliar["ref"]["parametros"]) == ["prato", "receita_id"]
    preco = cartao_para("cenarios_preco", {"prato": "Arroz com frango", "receita_id": "arroz"})
    assert preco is not None
    assert list(preco["ref"]["parametros"]) == ["receita_id", "prato"]


@pytest.mark.parametrize(
    "nome",
    [
        "converter_medida_culinaria",
        "consultar_perfil",
        "pauta_de_descoberta",
        "registrar_gosto",
        "consultar_gostos",
        "consultar_precos_de_mercado",
        "consultar_cardapio",
    ],
)
def test_ferramentas_sem_card(nome: str) -> None:
    assert CARTOES[nome] is None
    assert cartao_para(nome, {"prato": "Bolo"}) is None


@pytest.mark.parametrize(
    ("ferramenta", "argumentos"),
    [
        ("registrar_resposta", {"tipo": "gosto", "campo": "Bolo", "resposta": "gosta"}),
        ("registrar_resposta", {"tipo": "equipamento", "campo": "forno; DROP"}),
        ("registrar_resposta", {"tipo": "equipamento"}),
        ("registrar_resposta", {"tipo": 3, "campo": "forno"}),
        ("registrar_resposta", {"tipo": "tecnica", "campo": ["forno"]}),
        ("custo_unitario", {"ingrediente": ""}),
        ("custo_unitario", {"ingrediente": "x" * 201}),
        ("custo_unitario", {"ingrediente": 3}),
        ("avaliar_receita", {"receita": {"url": "https://a.com"}}),
        ("buscar_receita_na_web", {"url": "file:///etc/passwd"}),
        ("buscar_receita_na_web", {"url": "https://"}),
        ("buscar_receita_na_web", {"url": "http://[::1"}),
        ("buscar_receita_na_web", {"url": "https://a.com/" + "x" * 2000}),
        ("buscar_receita_na_web", {}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": True}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": -1}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": 0}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": float("nan")}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": PRECO_MAXIMO + 1}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": "12,50"}),
        ("testar_sensibilidade", {"prato": "Bolo", "preco": [12]}),
        ("testar_sensibilidade", {"preco": 12}),
        ("testar_sensibilidade", {"receita_id": "bolo", "preco": 0}),
        ("cenarios_preco", {"prato": None}),
        ("cenarios_preco", {}),
        ("cenarios_preco", {"receita_id": "não é id!"}),
        ("calcular_cmv", {"receita": {}}),
        ("avaliar_receita", {"receita_id": 42}),
        ("estimar_preco_preliminar", {}),
        ("registrar_avaliacao_da_receita", {"gosta": True}),
        ("registrar_avaliacao_da_receita", {"receita_id": "a" * 121}),
        ("consultar_conhecimento", {}),
    ],
)
def test_sem_o_que_identifica_o_card_nao_ha_card(
    ferramenta: str, argumentos: dict[str, Any]
) -> None:
    assert cartao_para(ferramenta, argumentos) is None


@pytest.mark.parametrize("nome", ["mcp__mise__cenarios_preco", "mcp_mise_cenarios_preco"])
def test_prefixo_do_hermes_e_argumento_em_texto(nome: str) -> None:
    cartao = cartao_para(nome, json.dumps({"prato": "Bolo"}))
    assert cartao is not None
    assert cartao["ref"]["parametros"] == {"prato": "Bolo"}


def test_ferramenta_desconhecida_ou_argumento_estranho() -> None:
    assert cartao_para("apagar_tudo", {}) is None
    assert cartao_para("cenarios_preco", "não é json") is None
    assert cartao_para("cenarios_preco", None) is None
