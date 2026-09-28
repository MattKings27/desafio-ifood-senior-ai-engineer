"""A cozinha na tela: ler, mudar item a item, e o que isso muda nas receitas.

A forma de cada resposta é conferida contra os contratos que o front também lê
(`contratos/web/perfil.json`, `perfil-escrita.json` e `receita.json`): toda
chave do exemplo tem de estar na resposta de verdade.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.dossie import Canal
from mise.mcp_server import abrir_sessao

from gateway.cartoes import cartao_para
from gateway.http import criar_app

RAIZ = Path(__file__).resolve().parents[2]
PLANILHA = RAIZ / "dados" / "despensa_dona_maria.xlsx"
CONTRATOS = RAIZ / "contratos" / "web"

FRANGO_ASSADO: dict[str, Any] = {
    "nome": "Frango assado",
    "rendimento_porcoes": 4,
    "modo_preparo": ["Tempere o frango.", "Leve ao forno a 200 °C por 40 minutos."],
    "ingredientes": [
        {
            "texto": "500 g de peito de frango",
            "nome": "peito de frango",
            "quantidade": 500,
            "medida": "g",
        },
    ],
}

QUANDO = re.compile(r"^hoje, \d{2}:\d{2}$")


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "dossie.db"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, banco: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


def contrato(nome: str) -> Any:
    return json.loads((CONTRATOS / nome).read_text(encoding="utf-8"))


def dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"], corpo.get("erro")
    return corpo["dados"]


def item(perfil: dict[str, Any], lista: str, id_: str) -> dict[str, Any]:
    achado: dict[str, Any] = next(i for i in perfil[lista] if i["id"] == id_)
    return achado


def _com_o_frango_em_avaliacao(cliente: TestClient) -> None:
    """O frango em avaliação, só esperando o forno: ela gosta, e os 40 min cabem na hora dela."""
    assert cliente.post("/api/gosto", json={"prato": "Frango assado", "gosta": True}).json()["ok"]
    # A tela manda o tempo por cozinhada em horas.
    uma_hora = {"valor": 1}
    assert cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json=uma_hora).json()[
        "ok"
    ]
    assert cliente.post("/api/avaliar", json=FRANGO_ASSADO).json()["ok"]


# --------------------------------------------------------------------------- #
# GET /api/perfil
# --------------------------------------------------------------------------- #


def test_perfil_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    exemplo = contrato("perfil.json")
    d = dados(cliente.get("/api/perfil"))
    assert set(exemplo) <= set(d)
    assert set(exemplo["equipamentos"][0]) <= set(d["equipamentos"][0])
    assert set(exemplo["tecnicas"][0]) <= set(d["tecnicas"][0])
    for campo, restricao in exemplo["restricoes"].items():
        assert set(restricao) <= set(d["restricoes"][campo]), campo
    assert d["respondidos"] + d["supostos"] + d["em_aberto"] == len(d["equipamentos"]) + len(
        d["tecnicas"]
    )


def test_perfil_de_partida(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/perfil"))
    assert d["resumo"] == (
        f"0 respondidos pela senhora · {d['supostos']} supostos · {d['em_aberto']} ainda não perguntei"
    )
    total = len(d["equipamentos"]) + len(d["tecnicas"])
    assert d["progresso_texto"] == f"0 de {total} respondidos pela senhora"
    fogao = item(d, "equipamentos", "fogao")
    assert (fogao["estado"], fogao["suposto"], fogao["atualizado_por"], fogao["nao_sei"]) == (
        "tem",
        True,
        None,
        False,
    )
    assert fogao["atualizado_texto"] is None
    assert (fogao["receitas_afetadas"], fogao["receitas_afetadas_texto"]) == (0, "0 receitas")
    assert d["restricoes"]["bocas_fogao"] == {
        "valor": None,
        "tipo": "inteiro",
        "unidade": "bocas",
        "min": 1,
        "max": 8,
        "pergunta": "Seu fogão tem quantas bocas? Isso limita quantas panelas andam juntas.",
        "atualizado_por": None,
        "atualizado_texto": None,
        "nao_sei": False,
    }
    gas = d["restricoes"]["tem_gas_sobrando"]
    assert gas["tipo"] == "sim_nao"
    assert "unidade" not in gas
    assert 0 < d["completude"] < 1


def test_receitas_afetadas_conta_as_receitas_em_avaliacao(cliente: TestClient) -> None:
    _com_o_frango_em_avaliacao(cliente)
    d = dados(cliente.get("/api/perfil"))
    forno = item(d, "equipamentos", "forno")
    assert (forno["receitas_afetadas"], forno["receitas_afetadas_texto"]) == (1, "1 receita")
    assert item(d, "equipamentos", "batedeira")["receitas_afetadas"] == 0
    segunda = {**FRANGO_ASSADO, "nome": "Coxa assada"}
    assert cliente.post("/api/avaliar", json=segunda).json()["ok"]
    forno = item(dados(cliente.get("/api/perfil")), "equipamentos", "forno")
    assert forno["receitas_afetadas_texto"] == "2 receitas"


def test_o_que_a_conversa_mudou_aparece_na_tela(cliente: TestClient, banco: Path) -> None:
    """O selo "atualizado pela conversa": o processo do agente grava no mesmo dossiê."""
    conversa = abrir_sessao(planilha=PLANILHA, banco=banco)
    assert conversa.canal is Canal.CONVERSA
    conversa.responder("equipamento", "forno", "não tenho")

    forno = item(dados(cliente.get("/api/perfil")), "equipamentos", "forno")
    assert (forno["estado"], forno["atualizado_por"]) == ("nao_tem", "conversa")
    assert QUANDO.match(forno["atualizado_texto"])

    dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    forno = item(dados(cliente.get("/api/perfil")), "equipamentos", "forno")
    assert (forno["estado"], forno["atualizado_por"]) == ("tem", "tela")


# --------------------------------------------------------------------------- #
# PUT de equipamento e técnica
# --------------------------------------------------------------------------- #


def test_resposta_do_put_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    exemplo = contrato("perfil-escrita.json")
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json=exemplo["pedido_item"]))
    assert set(exemplo["resposta"]) <= set(d)
    assert set(exemplo["resposta"]["item"]) <= set(d["item"])
    assert set(exemplo["resposta"]["impacto"]) <= set(d["impacto"])
    assert set(exemplo["resposta"]["perfil"]) <= set(d["perfil"])


def test_nao_tenho_forno_pela_tela(cliente: TestClient) -> None:
    _com_o_frango_em_avaliacao(cliente)
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_tem"}))
    assert (d["item"]["id"], d["item"]["estado"], d["item"]["suposto"]) == (
        "forno",
        "nao_tem",
        False,
    )
    assert d["item"]["atualizado_por"] == "tela"
    assert d["impacto"] == {
        "liberadas": [],
        "bloqueadas": [],
        "pendentes": ["Frango assado"],
        "texto": "Sem forno, Frango assado fica dependendo de uma resposta da senhora.",
    }
    depois = dados(cliente.get("/api/perfil"))
    assert d["perfil"] == {
        "respondidos": 1,
        "supostos": depois["supostos"],
        "em_aberto": depois["em_aberto"],
        "fracao_respondida": 0.0159,
        "resumo": depois["resumo"],
        "progresso_texto": depois["progresso_texto"],
    }
    assert d["perfil"]["resumo"].startswith("1 respondido pela senhora · ")
    assert d["perfil"]["progresso_texto"].startswith("1 de ")
    avaliacao = dados(cliente.post("/api/avaliar", json=FRANGO_ASSADO))
    assert any("air fryer" in p["texto"] for p in avaliacao["perguntas"])


def test_sem_forno_nem_substituto_o_frango_deixa_de_dar(cliente: TestClient) -> None:
    _com_o_frango_em_avaliacao(cliente)
    for id_ in ("air_fryer", "forno_eletrico"):
        dados(cliente.put(f"/api/perfil/equipamentos/{id_}", json={"estado": "nao_tem"}))
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_tem"}))
    assert d["impacto"]["bloqueadas"] == ["Frango assado"]
    assert d["impacto"]["texto"] == "Sem forno, Frango assado deixa de dar."


def test_ter_forno_libera_o_frango(cliente: TestClient) -> None:
    _com_o_frango_em_avaliacao(cliente)
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    assert d["impacto"]["liberadas"] == ["Frango assado"]
    assert d["impacto"]["texto"] == "Com forno, Frango assado passa a dar."
    assert dados(cliente.post("/api/avaliar", json=FRANGO_ASSADO))["veredito"] == "APTO"


def test_nao_sei_pela_tela_faz_o_portao_perguntar_de_novo(cliente: TestClient) -> None:
    _com_o_frango_em_avaliacao(cliente)
    dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_sei"}))
    assert (d["item"]["estado"], d["item"]["nao_sei"]) == ("desconhecido", True)
    assert d["impacto"]["pendentes"] == ["Frango assado"]
    assert d["perfil"]["respondidos"] == 0
    avaliacao = dados(cliente.post("/api/avaliar", json=FRANGO_ASSADO))
    assert avaliacao["veredito"] == "FALTA INFO"
    assert "forno" in {p["campo"] for p in avaliacao["perguntas"]}


ARROZ_DE_FOGAO: dict[str, Any] = {
    "nome": "Arroz refogado",
    "rendimento_porcoes": 2,
    "modo_preparo": ["Refogue o arroz e cozinhe em fogo baixo por 20 minutos."],
    "ingredientes": [
        {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
    ],
}


def _com_o_arroz_em_avaliacao(cliente: TestClient) -> None:
    """O arroz de fogão, que dá com a cozinha de partida: ela gosta, e os 20 min cabem."""
    assert cliente.post("/api/gosto", json={"prato": "Arroz refogado", "gosta": True}).json()["ok"]
    # A tela manda o tempo por cozinhada em horas.
    uma_hora = {"valor": 1}
    assert cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json=uma_hora).json()[
        "ok"
    ]
    assert dados(cliente.post("/api/avaliar", json=ARROZ_DE_FOGAO))["veredito"] == "APTO"


def test_nao_sei_conta_a_parte_e_nunca_como_ainda_nao_perguntei(cliente: TestClient) -> None:
    antes = dados(cliente.get("/api/perfil"))
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_sei"}))
    em_aberto = antes["em_aberto"]
    assert d["perfil"]["em_aberto"] == em_aberto
    assert d["perfil"]["resumo"] == (
        f"0 respondidos pela senhora · {antes['supostos']} supostos · "
        f"1 que a senhora não sabe · {em_aberto - 1} ainda não perguntei"
    )
    assert dados(cliente.get("/api/perfil"))["resumo"] == d["perfil"]["resumo"]
    # A restrição em "não sei" não entra na conta dos equipamentos e técnicas.
    dados(cliente.put("/api/perfil/restricoes/bocas_fogao", json={"valor": None}))
    assert "1 que a senhora não sabe" in dados(cliente.get("/api/perfil"))["resumo"]
    # Respondeu de novo: sai do "não sabe".
    dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    assert "não sabe" not in dados(cliente.get("/api/perfil"))["resumo"]
    tecnica = dados(cliente.put("/api/perfil/tecnicas/bechamel", json={"estado": "nao_sei"}))
    assert "1 que a senhora não sabe" in tecnica["perfil"]["resumo"]


def test_nao_tenho_fogao_pela_tela_bloqueia_o_arroz(cliente: TestClient) -> None:
    """O fogão é suposto, mas o "não tenho" dela vale: a receita de fogão deixa de dar."""
    _com_o_arroz_em_avaliacao(cliente)
    d = dados(cliente.put("/api/perfil/equipamentos/fogao", json={"estado": "nao_tem"}))
    assert (d["item"]["estado"], d["item"]["suposto"]) == ("nao_tem", False)
    assert d["impacto"] == {
        "liberadas": [],
        "bloqueadas": ["Arroz refogado"],
        "pendentes": [],
        "texto": "Sem fogão, Arroz refogado deixa de dar.",
    }
    avaliacao = dados(cliente.post("/api/avaliar", json=ARROZ_DE_FOGAO))
    assert avaliacao["veredito"] == "BLOQUEADO"
    assert avaliacao["impedimentos"][0]["motivo"] == (
        "a receita precisa de fogão e a senhora não tem"
    )


def test_nao_sei_do_fogao_pela_tela_faz_o_portao_perguntar(cliente: TestClient) -> None:
    _com_o_arroz_em_avaliacao(cliente)
    d = dados(cliente.put("/api/perfil/equipamentos/fogao", json={"estado": "nao_sei"}))
    assert (d["item"]["estado"], d["item"]["suposto"], d["item"]["nao_sei"]) == (
        "desconhecido",
        False,
        True,
    )
    assert d["impacto"]["pendentes"] == ["Arroz refogado"]
    assert d["impacto"]["texto"] == "Arroz refogado fica dependendo de uma resposta da senhora."
    avaliacao = dados(cliente.post("/api/avaliar", json=ARROZ_DE_FOGAO))
    assert avaliacao["veredito"] == "FALTA INFO"
    assert "fogao" in {p["campo"] for p in avaliacao["perguntas"]}
    fogao = item(dados(cliente.get("/api/perfil")), "equipamentos", "fogao")
    assert (fogao["estado"], fogao["suposto"], fogao["nao_sei"]) == ("desconhecido", False, True)
    assert fogao["receitas_afetadas_texto"] == "1 receita"


def test_repetir_o_clique_nao_muda_nada(cliente: TestClient) -> None:
    dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    d = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    assert d["impacto"]["texto"] == "Isso já estava anotado assim; nada muda nas receitas."
    assert d["perfil"]["respondidos"] == 1


def test_tecnica_pela_tela(cliente: TestClient) -> None:
    d = dados(cliente.put("/api/perfil/tecnicas/bechamel", json={"estado": "tem"}))
    assert (d["item"]["id"], d["item"]["estado"], d["item"]["dificuldade"]) == (
        "bechamel",
        "tem",
        3,
    )
    assert (
        d["impacto"]["texto"]
        == "Anotado. Ainda não há receita em avaliação para conferir com isso."
    )
    # "Não sei" do que toda cozinha faz: fica em aberto, e fica registrado que ela não sabe.
    fritar = dados(cliente.put("/api/perfil/tecnicas/fritar", json={"estado": "nao_sei"}))
    assert (fritar["item"]["estado"], fritar["item"]["suposto"]) == ("desconhecido", False)
    assert (fritar["item"]["nao_sei"], fritar["item"]["atualizado_por"]) == (True, "tela")
    de_novo = dados(cliente.put("/api/perfil/tecnicas/fritar", json={"estado": "nao_sei"}))
    assert de_novo["impacto"]["texto"] == "Isso já estava anotado assim; nada muda nas receitas."


@pytest.mark.parametrize(
    "caminho",
    ["/api/perfil/equipamentos/teletransportador", "/api/perfil/tecnicas/alquimia"],
)
def test_item_que_nao_existe_sai_com_404(cliente: TestClient, caminho: str) -> None:
    resposta = cliente.put(caminho, json={"estado": "tem"})
    assert resposta.status_code == 404
    corpo = resposta.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "ausente")
    assert "não está na lista da cozinha" in corpo["erro"]


def test_equipamento_no_caminho_de_tecnica_sai_com_404(cliente: TestClient) -> None:
    assert cliente.put("/api/perfil/tecnicas/forno", json={"estado": "tem"}).status_code == 404


@pytest.mark.parametrize("corpo", [{"estado": "talvez"}, {"estado": "sim"}, {}, {"estado": None}])
def test_estado_fora_do_combinado_e_recusado(cliente: TestClient, corpo: dict[str, Any]) -> None:
    assert cliente.put("/api/perfil/equipamentos/forno", json=corpo).status_code == 422


# --------------------------------------------------------------------------- #
# PUT de restrição
# --------------------------------------------------------------------------- #


def test_restricao_numero_sim_e_nao_sei(cliente: TestClient) -> None:
    d = dados(cliente.put("/api/perfil/restricoes/bocas_fogao", json={"valor": 4}))
    assert d["item"] == {
        "id": "bocas_fogao",
        "valor": 4,
        "tipo": "inteiro",
        "unidade": "bocas",
        "min": 1,
        "max": 8,
        "pergunta": "Seu fogão tem quantas bocas? Isso limita quantas panelas andam juntas.",
        "atualizado_por": "tela",
        "atualizado_texto": d["item"]["atualizado_texto"],
        "nao_sei": False,
    }
    assert QUANDO.match(d["item"]["atualizado_texto"])

    gas = dados(cliente.put("/api/perfil/restricoes/tem_gas_sobrando", json={"valor": False}))
    assert (gas["item"]["valor"], gas["item"]["tipo"]) == (False, "sim_nao")

    nao_sei = dados(cliente.put("/api/perfil/restricoes/bocas_fogao", json={"valor": None}))
    assert (nao_sei["item"]["valor"], nao_sei["item"]["nao_sei"]) == (None, True)
    perfil = dados(cliente.get("/api/perfil"))
    assert perfil["restricoes"]["bocas_fogao"]["valor"] is None
    assert perfil["restricoes"]["tem_gas_sobrando"]["valor"] is False


def test_numero_inteiro_com_ponto_vale(cliente: TestClient) -> None:
    d = dados(cliente.put("/api/perfil/restricoes/espaco_geladeira_litros", json={"valor": 0.0}))
    assert d["item"]["valor"] == 0


def test_tempo_curto_bloqueia_a_receita_longa(cliente: TestClient) -> None:
    receita = {**FRANGO_ASSADO, "tempo_cozimento_min": 50}
    assert cliente.post("/api/avaliar", json=receita).json()["ok"]
    # Meia hora por cozinhada, como a tela manda (em horas).
    d = dados(cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json={"valor": 0.5}))
    assert d["impacto"]["bloqueadas"] == ["Frango assado"]
    assert d["impacto"]["texto"] == "Frango assado deixa de dar."


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("bocas_fogao", 80, "entre 1 e 8 bocas"),
        ("bocas_fogao", 2.5, "número inteiro"),
        ("bocas_fogao", True, "número inteiro"),
        ("tem_gas_sobrando", 1, "sim ou não"),
    ],
)
def test_valor_fora_da_faixa_ou_do_tipo_volta_com_a_mensagem(
    cliente: TestClient, campo: str, valor: object, trecho: str
) -> None:
    resposta = cliente.put(f"/api/perfil/restricoes/{campo}", json={"valor": valor})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")
    assert trecho in corpo["erro"]
    assert dados(cliente.get("/api/perfil"))["restricoes"][campo]["valor"] is None


def test_resposta_antiga_da_tela_tambem_confere_a_faixa(cliente: TestClient) -> None:
    """`POST /api/resposta` e o `PUT` gravam no mesmo perfil: a faixa vale para os dois."""
    corpo = cliente.post(
        "/api/resposta", json={"tipo": "operacional", "campo": "bocas_fogao", "resposta": "80"}
    ).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")
    assert "entre 1 e 8 bocas" in corpo["erro"]
    assert dados(cliente.get("/api/perfil"))["restricoes"]["bocas_fogao"]["valor"] is None
    ok = dados(
        cliente.post(
            "/api/resposta", json={"tipo": "operacional", "campo": "bocas_fogao", "resposta": "4"}
        )
    )
    assert ok["registrado"] is True


@pytest.mark.parametrize("corpo", [{"valor": "4"}, {}, {"valor": [4]}])
def test_valor_que_nao_e_numero_nem_sim_e_recusado(
    cliente: TestClient, corpo: dict[str, Any]
) -> None:
    assert cliente.put("/api/perfil/restricoes/bocas_fogao", json=corpo).status_code == 422


def test_restricao_que_nao_existe_sai_com_404(cliente: TestClient) -> None:
    resposta = cliente.put("/api/perfil/restricoes/fogao_industrial", json={"valor": 1})
    assert resposta.status_code == 404
    assert resposta.json()["categoria"] == "ausente"


# --------------------------------------------------------------------------- #
# /api/avaliar e o card da conversa
# --------------------------------------------------------------------------- #


def test_avaliar_traz_exige_e_por_passo_na_forma_do_contrato(cliente: TestClient) -> None:
    exemplo = contrato("receita.json")
    d = dados(cliente.post("/api/avaliar", json=FRANGO_ASSADO))
    assert d["exige"] == {"equipamentos": ["Forno"], "tecnicas": []}
    um, dois = d["por_passo"]["passos"]
    assert set(exemplo["passos"][0]) <= set(um)
    (forno,) = dois["requisitos"]
    assert set(exemplo["passos"][0]["requisitos"][0]) <= set(forno)
    assert (forno["id"], forno["estado"], forno["evidencia"], forno["trecho"]) == (
        "forno",
        "desconhecido",
        "leve ao forno a 200 °c por 40 minutos....",  # a evidência é do passo, não da receita
        "forno",
    )
    assert all(set(exemplo["passos"][2]["limites"][0]) <= set(lim) for lim in dois["limites"])
    assert [lim["texto"] for lim in dois["limites"]] == ["forno a 200 °C", "40 min no forno"]
    assert all(set(exemplo["perguntas"][0]) <= set(p) for p in d["perguntas"])
    assert d["por_passo"]["requisitos_da_receita"] == []


def test_o_card_da_cozinha_aponta_para_uma_rota_que_existe(cliente: TestClient) -> None:
    cartao = cartao_para("registrar_resposta", {"tipo": "equipamento", "campo": "forno"})
    assert cartao is not None
    assert cartao["tipo_cartao"] == "cozinha_atualizada"
    rota = cartao["ref"]["rota"]
    assert rota == "/api/perfil"
    forno = item(dados(cliente.get(rota)), "equipamentos", cartao["ref"]["parametros"]["campo"])
    assert forno["id"] == "forno"


# --------------------------------------------------------------------------- #
# O impacto conta também as receitas do catálogo que mudam de aba              #
# --------------------------------------------------------------------------- #

_ASSADO_DA_WEB = (
    '<script type="application/ld+json">'
    + json.dumps(
        {
            "@type": "Recipe",
            "name": "Frango assado da internet",
            "recipeYield": "4 porções",
            "recipeIngredient": ["500 g de peito de frango"],
            "recipeInstructions": ["Tempere o frango.", "Leve ao forno a 200 °C por 40 minutos."],
            "publisher": {"@type": "Organization", "name": "TudoGostoso"},
        }
    )
    + "</script>"
)


def test_o_impacto_conta_a_receita_do_catalogo_que_muda_de_aba(cliente: TestClient) -> None:
    from mise.catalogo import OrigemNoCatalogo
    from mise.perfil import PerfilCozinha, Posse
    from retrieval.extrator import extrair

    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    url = "https://www.tudogostoso.com.br/receita/9-frango-assado.html"
    sessao.catalogar(extrair(_ASSADO_DA_WEB, url), OrigemNoCatalogo.DESCOBERTA)
    # A cozinha inteira dita; do forno ninguém sabe, e nada faz o papel dele.
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    for campo, valor in (
        ("bocas_fogao", 4),
        ("tempo_max_por_fornada_min", 240),
        ("porcoes_por_fornada", 20),
        ("tem_gas_sobrando", True),
        ("espaco_geladeira_litros", 30),
        ("energia_aparelhos_simultaneos", 3),
    ):
        perfil = perfil.com_restricao(campo, valor)
    perfil = (
        perfil.com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
        .sem_resposta("forno")
    )
    sessao.dossie.salvar_perfil(perfil)
    sem_forno = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_tem"}))
    assert sem_forno["impacto"]["bloqueadas"] == ["Frango assado da internet"]
    assert sem_forno["impacto"]["texto"] == "Sem forno, Frango assado da internet deixa de dar."
    com_forno = dados(cliente.put("/api/perfil/equipamentos/forno", json={"estado": "tem"}))
    assert com_forno["impacto"]["liberadas"] == ["Frango assado da internet"]
    assert com_forno["impacto"]["texto"] == "Com forno, Frango assado da internet passa a dar."


# --------------------------------------------------------------------------- #
# O que toda cozinha tem: o bloco da tela e a confirmação
# --------------------------------------------------------------------------- #

#: Quantos itens a taxonomia supõe de toda cozinha (equipamentos e técnicas).
SUPOSTOS_DE_PARTIDA = 17


def test_o_bloco_do_que_toda_cozinha_tem(cliente: TestClient) -> None:
    exemplo = contrato("perfil.json")["toda_cozinha"]
    bloco = dados(cliente.get("/api/perfil"))["toda_cozinha"]
    assert set(bloco) == set(exemplo)
    assert set(bloco["itens"][0]) == set(exemplo["itens"][0])
    assert (bloco["a_confirmar"], bloco["tudo_confirmado"]) == (SUPOSTOS_DE_PARTIDA, False)
    assert bloco["a_confirmar_texto"] == "17 para confirmar"
    fogao = bloco["itens"][0]
    assert (fogao["id"], fogao["status"], fogao["status_texto"]) == (
        "fogao",
        "suposto",
        "suposto: confirme",
    )
    assert fogao["imagem"]["url"].startswith("/motor/imagens/")
    # O que ela respondeu aparece com a resposta dela.
    dados(cliente.put("/api/perfil/equipamentos/peneira", json={"estado": "nao_tem"}))
    dados(cliente.put("/api/perfil/equipamentos/faca", json={"estado": "nao_sei"}))
    dados(cliente.put("/api/perfil/tecnicas/fritar", json={"estado": "tem"}))
    dados(cliente.put("/api/perfil/equipamentos/geladeira", json={"estado": "tem"}))
    itens = {i["id"]: i for i in dados(cliente.get("/api/perfil"))["toda_cozinha"]["itens"]}
    assert (itens["peneira"]["status"], itens["peneira"]["status_texto"]) == (
        "nao_da",
        "a senhora não tem",
    )
    assert (itens["faca"]["status"], itens["faca"]["status_texto"]) == (
        "falta_saber",
        "a senhora não sabe",
    )
    assert itens["fritar"]["status_texto"] == "a senhora faz"
    assert itens["geladeira"]["status_texto"] == "a senhora tem"


def test_tenho_tudo_isso_confirma_o_suposto_pela_tela(cliente: TestClient) -> None:
    dados(cliente.put("/api/perfil/equipamentos/peneira", json={"estado": "nao_tem"}))
    feita = dados(cliente.post("/api/perfil/supostos/confirmar", json={}))
    exemplo = contrato("perfil-supostos.json")["resposta"]
    assert set(feita) == set(exemplo)
    assert len(feita["confirmados"]) == SUPOSTOS_DE_PARTIDA - 1, "a peneira ela disse que não tem"
    assert feita["texto"].startswith("Anotei: a senhora tem fogão, frigideira, panela funda")
    assert feita["toda_cozinha"]["tudo_confirmado"] is True
    assert feita["toda_cozinha"]["texto"] == "A senhora já me disse de tudo isso."
    assert feita["perfil"]["supostos"] == 0
    fogao = item(dados(cliente.get("/api/perfil")), "equipamentos", "fogao")
    assert (fogao["suposto"], fogao["atualizado_por"]) == (False, "tela")
    de_novo = dados(cliente.post("/api/perfil/supostos/confirmar", json={}))
    assert de_novo["confirmados"] == []
    assert de_novo["texto"].startswith("Não havia nada para confirmar")


def test_confirmar_o_que_uma_receita_usa_e_item_por_item(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    sessao_de_teste.guardar_receitas(sessao)
    da_receita = dados(
        cliente.post("/api/perfil/supostos/confirmar", json={"receita": "arroz-com-frango"})
    )
    assert [i["id"] for i in da_receita["confirmados"]] == ["fogao", "refogar"]
    assert da_receita["texto"] == "Anotei: a senhora tem fogão e sabe refogar."
    um = dados(
        cliente.post(
            "/api/perfil/supostos/confirmar",
            json={"itens": [{"tipo": "equipamento", "id": "faca"}]},
        )
    )
    assert um["confirmados"] == [{"tipo": "equipamento", "id": "faca", "nome": "Faca"}]
    assert um["toda_cozinha"]["a_confirmar"] == SUPOSTOS_DE_PARTIDA - 3


def test_confirmar_o_que_nao_existe(cliente: TestClient) -> None:
    sem_receita = cliente.post("/api/perfil/supostos/confirmar", json={"receita": "lasanha"})
    assert (sem_receita.status_code, sem_receita.json()["categoria"]) == (404, "ausente")
    sem_item = cliente.post(
        "/api/perfil/supostos/confirmar", json={"itens": [{"tipo": "tecnica", "id": "levitar"}]}
    )
    assert (sem_item.status_code, sem_item.json()["categoria"]) == (404, "ausente")
    os_dois = cliente.post(
        "/api/perfil/supostos/confirmar",
        json={"receita": "arroz-com-frango", "itens": [{"tipo": "tecnica", "id": "refogar"}]},
    ).json()
    assert (os_dois["ok"], os_dois["categoria"]) == (False, "uso")
    tipo_errado = cliente.post(
        "/api/perfil/supostos/confirmar", json={"itens": [{"tipo": "gosto", "id": "x"}]}
    )
    assert tipo_errado.status_code == 422


def test_o_aceite_pela_tela_espera_a_cozinha_confirmada(cliente: TestClient) -> None:
    """A mesma recusa da conversa: a pergunta, uma só, e depois dela o aceite passa."""
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    sessao_de_teste.guardar_receitas(sessao)
    dados(cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json={"valor": 2}))
    dados(cliente.post("/api/gosto", json={"prato": "Arroz com frango", "gosta": True}))
    detalhe = dados(cliente.get("/api/receitas/arroz-com-frango"))
    checklist = detalhe["checklist"]
    assert checklist["pode_aceitar"] is False
    pergunta = checklist["confirmar_a_cozinha"]["pergunta"]
    assert pergunta == "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?"
    grade = dados(cliente.get("/api/receitas"))["itens"]
    assert next(i for i in grade if i["slug"] == "arroz-com-frango")["nota_da_cozinha"] == (
        "Confirme a cozinha"
    )

    pedido = {"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    recusa = cliente.post("/api/decisao", json=pedido).json()
    assert (recusa["ok"], recusa["categoria"], recusa["pergunta"]) == (False, "regra", pergunta)
    dados(cliente.post("/api/perfil/supostos/confirmar", json={"receita": "arroz-com-frango"}))
    assert dados(cliente.get("/api/receitas/arroz-com-frango"))["checklist"]["pode_aceitar"]
    grade = dados(cliente.get("/api/receitas"))["itens"]
    assert next(i for i in grade if i["slug"] == "arroz-com-frango")["nota_da_cozinha"] is None
    aceite = dados(cliente.post("/api/decisao", json=pedido))
    assert aceite["cardapio"] == ["Arroz com frango"]
