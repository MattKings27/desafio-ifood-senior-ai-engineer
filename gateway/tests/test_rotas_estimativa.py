"""O preço preliminar e as premissas na tela: a forma do contrato e a conta que fecha.

Toda chave do exemplo (`contratos/web/estimativa.json` e
`contratos/web/parametro-escrita.json`) tem de estar na resposta de verdade, e
os números da resposta fecham entre si como o contrato diz.
"""

from __future__ import annotations

import json
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.dossie import Dossie
from mise.mcp_server import abrir_sessao
from mise.perfil import Gosto

from gateway.http import criar_app

RAIZ = Path(__file__).resolve().parents[2]
CONTRATOS = RAIZ / "contratos" / "web"
CENTAVO = Decimal("0.01")


def contrato(nome: str) -> Any:
    return json.loads((CONTRATOS / nome).read_text(encoding="utf-8"))


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    banco = tmp_path / "dossie.db"
    sessao_de_teste.preparar_dossie(banco)
    sessao = abrir_sessao(sessao_de_teste.PLANILHA, banco)
    sessao_de_teste.guardar_receitas(sessao)
    sessao.dossie.fechar()
    return banco


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, banco: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


def _chaves(exemplo: Any, resposta: Any, caminho: str = "") -> None:
    """Toda chave do exemplo existe na resposta, no mesmo lugar."""
    if isinstance(exemplo, dict):
        assert isinstance(resposta, dict), caminho
        for chave, valor in exemplo.items():
            assert chave in resposta, f"{caminho}.{chave}"
            if valor is not None and resposta[chave] is not None:
                _chaves(valor, resposta[chave], f"{caminho}.{chave}")
    elif isinstance(exemplo, list) and exemplo and resposta:
        for item in resposta:
            _chaves(exemplo[0], item, f"{caminho}[]")


def _valor(dinheiro: dict[str, Any]) -> Decimal:
    return Decimal(str(dinheiro["valor"]))


def test_a_estimativa_tem_a_forma_do_contrato_e_fecha_a_conta(cliente: TestClient) -> None:
    resposta = cliente.get("/api/receitas/arroz-com-frango/estimativa")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    dados = corpo["dados"]
    exemplo = contrato("estimativa.json")
    _chaves({k: v for k, v in exemplo.items() if k != "linhas"}, dados)
    for linha in dados["linhas"]:
        _chaves(exemplo["linhas"][0], linha)
    assert (dados["slug"], dados["prato"], dados["preliminar"]) == (
        "arroz-com-frango",
        "Arroz com frango",
        True,
    )
    assert dados["referencias_de_mercado"] == []

    linhas = {linha["id"]: linha for linha in dados["linhas"]}
    ingrediente = _valor(linhas["ingredientes"]["valor"])
    producao = sum((_valor(ln["valor"]) for ln in linhas.values() if ln["valor"]), Decimal(0))
    assert _valor(dados["custo_producao"]) == producao
    piso = (producao / Decimal("0.9")).quantize(CENTAVO, rounding=ROUND_CEILING)
    assert _valor(dados["piso"]) == piso
    for ponto, fracao in zip(dados["pontos"], ("0.40", "0.35", "0.30"), strict=True):
        pelo_ingrediente = (ingrediente / Decimal(fracao)).quantize(CENTAVO, ROUND_HALF_UP)
        preco = max(piso, pelo_ingrediente)
        assert _valor(ponto["preco"]) == preco
        recebe = (preco * Decimal("0.90")).quantize(CENTAVO, ROUND_HALF_UP)
        assert _valor(ponto["recebe"]) == recebe
        assert _valor(ponto["taxa"]) + _valor(ponto["recebe"]) == preco
        assert _valor(ponto["lucro"]) == recebe - ingrediente
        assert _valor(ponto["sobra_real"]) == recebe - producao


def test_receita_que_nao_existe_e_404(cliente: TestClient) -> None:
    resposta = cliente.get("/api/receitas/pudim/estimativa")
    assert resposta.status_code == 404
    assert resposta.json()["categoria"] == "ausente"


def test_receita_que_ela_nao_consegue_fazer_e_recusada(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_gosto("Arroz com frango", Gosto.NAO_GOSTA)
    corpo = cliente.get("/api/receitas/arroz-com-frango/estimativa").json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "regra")
    assert "não consegue fazer" in corpo["erro"]


def test_ingrediente_sem_preco_dela_sai_pela_referencia_sem_pergunta(cliente: TestClient) -> None:
    from mise.catalogo import id_da_url

    slug = id_da_url(sessao_de_teste.BOLO_DA_WEB["url"])
    dados = cliente.get(f"/api/receitas/{slug}/estimativa").json()["dados"]
    # O coco ralado sai pelo preço de referência: a estimativa tem número, e nada se pergunta.
    assert dados["custo_producao"] is not None
    assert not any("coco ralado" in c for c in dados["sinais"]["falta_confirmar"])


def test_a_premissa_pela_tela(cliente: TestClient) -> None:
    lida = cliente.get("/api/parametros/valor_hora").json()["dados"]
    assert (lida["origem"], lida["valor"]["texto"]) == ("padrao", "R$ 7,37 por hora")

    exemplo = contrato("parametro-escrita.json")
    resposta = cliente.put("/api/parametros/embalagem_por_porcao", json=exemplo["pedido"])
    assert resposta.status_code == 200
    gravada = resposta.json()["dados"]
    _chaves(exemplo["resposta"], gravada)
    assert gravada["valor"] == {"valor": 1.2, "texto": "R$ 1,20 por porção"}
    assert (gravada["origem"], gravada["fonte"]) == ("dela", "informado pela senhora")

    estimativa = cliente.get("/api/receitas/arroz-com-frango/estimativa").json()["dados"]
    embalagem = next(ln for ln in estimativa["linhas"] if ln["id"] == "embalagem")
    assert embalagem["valor"] == {"valor": 1.2, "texto": "R$ 1,20"}
    assert estimativa["sinais"]["faltam_parametros"] == []

    apagada = cliente.put("/api/parametros/embalagem_por_porcao", json={"valor": None})
    assert apagada.json()["dados"]["origem"] == "falta"


@pytest.mark.parametrize("valor", ["1,20", True, -5])
def test_premissa_com_valor_que_nao_serve(cliente: TestClient, valor: object) -> None:
    resposta = cliente.put("/api/parametros/embalagem_por_porcao", json={"valor": valor})
    if isinstance(valor, str | bool):
        assert resposta.status_code == 422
    else:
        assert resposta.json()["categoria"] == "uso"


def test_premissa_que_nao_existe_e_404(cliente: TestClient) -> None:
    assert cliente.get("/api/parametros/salario_do_papa").status_code == 404
    assert cliente.put("/api/parametros/salario_do_papa", json={"valor": 1}).status_code == 404
