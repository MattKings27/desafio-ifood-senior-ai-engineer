"""Do pôr preço ao cardápio, pela API de verdade, do jeito que a tela faz.

A tela de pôr preço manda a receita escrita por ela a cada conferência, sem o
`receita_id`: os ingredientes são o texto de cada linha e um palpite de nome.
A conferência pergunta o que falta (o tempo por cozinhada, em horas; o tempo no
fogo; o peso de "2 peitos de frango"; se ela gosta de fazer) e a tela responde
cada uma pela rota dela. O peso que ela disse tem de continuar valendo quando a
receita escrita volta na conferência seguinte: antes, a receita escrita de novo
apagava o peso, a pergunta voltava para sempre e o preço nunca liberava.

Antes do "Vou cobrar", ela confirma num toque o que toda cozinha tem e a
receita usa (a frigideira, o fogão): sem isso, o aceite é recusado com a
pergunta. Depois, o "Vou cobrar" grava a decisão, e o cardápio tem o prato com
os mesmos números que o ponto de preço mostrou: o preço dela, o que chega, o
custo, o lucro e a conta escrita.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient

from gateway.http import criar_app

PRATO = "Frango grelhado da vizinha"
LINHAS = ("2 peitos de frango", "1 cebola", "sal a gosto")


def _nome(linha: str) -> str:
    """O palpite de nome que a tela manda junto do texto (`nomeDaLinha`)."""
    sem_numero = linha.lstrip("0123456789 ,./")
    depois_do_de = sem_numero.split(" de ", 1)
    return depois_do_de[1] if len(depois_do_de) > 1 else sem_numero


def _receita_escrita(**extra: Any) -> dict[str, Any]:
    return {
        "nome": PRATO,
        "ingredientes": [{"texto": linha, "nome": _nome(linha)} for linha in LINHAS],
        "rendimento_porcoes": 4,
        "modo_preparo": ["Tempere o frango com sal.", "Grelhe na frigideira com a cebola."],
        **extra,
    }


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """Um dossiê novo: a cozinha sem nenhuma resposta dela, como depois de restaurar."""
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


def _ok(resposta: Any) -> Any:
    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"], corpo
    return corpo["dados"]


def _conferir_ate_liberar(cliente: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    """Responde cada pergunta pela rota que a tela usa, até o preço liberar."""
    receita = _receita_escrita()
    perguntadas: list[str] = []
    for _ in range(12):
        avaliacao: dict[str, Any] = _ok(cliente.post("/api/avaliar", json=receita))
        if avaliacao["pode_precificar"]:
            return receita, avaliacao
        if not avaliacao["perguntas"]:
            # O tempo que a receita não diz nunca é pergunta: com o limite dela, a receita
            # fica de fora, e ela diz o tempo na receita (o `editar` do checklist).
            assert [i["id"] for i in avaliacao["impedimentos"]] == ["tempo_max_por_fornada_min"]
            assert "tempo_cozimento_min" not in receita
            receita = {**receita, "tempo_cozimento_min": 25}
            continue
        pergunta = avaliacao["perguntas"][0]
        campo, assunto = pergunta["campo"], pergunta["assunto"]
        assert campo not in perguntadas, f"a pergunta {campo!r} voltou depois de respondida"
        perguntadas.append(campo)
        if assunto == "gosto":
            _ok(cliente.post("/api/gosto", json={"prato": avaliacao["prato"], "gosta": True}))
        elif campo == "tempo_max_por_fornada_min":
            # A tela pergunta em horas.
            assert pergunta["entrada"]["tipo"] == "horas"
            _ok(cliente.put(f"/api/perfil/restricoes/{campo}", json={"valor": 2}))
        elif campo == "tempo_cozimento_min":
            receita = {**receita, "tempo_cozimento_min": 25}
        elif assunto == "medida":
            corpo = {"campo": campo, "resposta": "300 g", "por_unidade": True}
            _ok(cliente.post(f"/api/receitas/{avaliacao['receita_id']}/resposta", json=corpo))
        elif pergunta["tipo"] in ("equipamento", "tecnica"):
            _ok(cliente.put(f"/api/perfil/{pergunta['tipo']}s/{campo}", json={"estado": "tem"}))
        else:  # pragma: no cover (uma pergunta que a tela não saberia responder)
            pytest.fail(f"pergunta sem resposta pela tela: {pergunta}")
    pytest.fail("o preço não liberou")  # pragma: no cover


def test_o_peso_dito_na_tela_continua_valendo_quando_a_receita_volta(cliente: TestClient) -> None:
    """O peso do peito sai da tabela do IBGE; o que ela diz na tela vale mais, e continua."""
    primeira = _ok(cliente.post("/api/avaliar", json=_receita_escrita()))
    assert "medida" not in {p["assunto"] for p in primeira["perguntas"]}
    corpo = {"campo": "2 peitos de frango", "resposta": "300 g", "por_unidade": True}
    _ok(cliente.post(f"/api/receitas/{primeira['receita_id']}/resposta", json=corpo))
    de_novo = _ok(cliente.post("/api/avaliar", json=_receita_escrita()))
    assert "medida" not in {p["assunto"] for p in de_novo["perguntas"]}
    (peito,) = [
        u for u in de_novo["ingredientes_na_despensa"] if u["ingrediente"] == "Peito de frango"
    ]
    assert "a senhora disse" in peito["derivacao"]


def test_vou_cobrar_grava_e_o_cardapio_mostra_os_mesmos_numeros(cliente: TestClient) -> None:
    receita, avaliacao = _conferir_ate_liberar(cliente)
    custo = _ok(cliente.post("/api/cmv", json=receita))
    tabela = _ok(
        cliente.get("/api/precos", params={"prato": custo["prato"], "cmv": custo["total"]["valor"]})
    )
    preco = round(tabela["controle"]["min"]["valor"] + 1.5, 2)
    ponto = _ok(cliente.get("/api/preco-em", params={"prato": tabela["prato"], "preco": preco}))

    # O aceite pede a cozinha confirmada: a recusa traz a pergunta, uma só, e ela confirma.
    confirmar = avaliacao["confirmar_a_cozinha"]
    assert not avaliacao["pode_aceitar"]
    assert confirmar["pergunta"].startswith("Antes de aceitar, a senhora confirma que tem ")
    pedido = {"prato": tabela["prato"], "decisao": "aceito", "preco": ponto["preco"]["valor"]}
    recusa = cliente.post("/api/decisao", json=pedido).json()
    assert (recusa["ok"], recusa["categoria"], recusa["pergunta"]) == (
        False,
        "regra",
        confirmar["pergunta"],
    )
    # Como a tela faz: a receita escrita pelo `receita_id` que a conferência devolveu.
    confirmados = _ok(
        cliente.post("/api/perfil/supostos/confirmar", json={"receita": avaliacao["receita_id"]})
    )
    assert [i["id"] for i in confirmados["confirmados"]] == [i["id"] for i in confirmar["itens"]]
    de_novo = _ok(cliente.post("/api/avaliar", json=receita))
    assert (de_novo["pode_aceitar"], de_novo["confirmar_a_cozinha"]) == (True, None)

    decisao = _ok(
        cliente.post(
            "/api/decisao",
            json={
                "prato": tabela["prato"],
                "decisao": "aceito",
                "preco": ponto["preco"]["valor"],
                "motivo": "",
                "id_cliente": "vou-cobrar-1",
            },
        )
    )
    assert (
        decisao["texto"]
        == f"A senhora aceitou o frango grelhado da vizinha a {ponto['preco']['texto']}."
    )
    assert decisao["cardapio"] == [PRATO]

    cardapio = _ok(cliente.get("/api/cardapio"))
    (prato,) = cardapio["pratos"]
    assert prato["prato"] == PRATO
    assert prato["preco"] == ponto["preco"]
    assert prato["recebe"] == ponto["recebe"]
    assert prato["custo_porcao"] == custo["total"] == tabela["cmv"]
    assert prato["lucro_porcao"] == ponto["lucro"]
    assert prato["derivacao"] == ponto["explicacao"]
    assert (prato["da_prejuizo"], prato["aviso"]) == (False, None)
    assert prato["rota"] == f"/receitas/{avaliacao['receita_id']}"
    assert cardapio["resumo"]["texto"] == "1 prato no cardápio"
    (passo,) = cardapio["historico"]
    assert (passo["tipo"], passo["canal"]) == ("aceito", "tela")

    # O mesmo clique reenviado não grava duas vezes.
    _ok(
        cliente.post(
            "/api/decisao",
            json={
                "prato": tabela["prato"],
                "decisao": "aceito",
                "preco": ponto["preco"]["valor"],
                "id_cliente": "vou-cobrar-1",
            },
        )
    )
    assert len(_ok(cliente.get("/api/cardapio"))["historico"]) == 1
