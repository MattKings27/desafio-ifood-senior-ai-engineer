"""Os exemplos de `contratos/web/` fecham a conta e têm a forma das rotas que eles imitam.

Um exemplo de contrato é o que a tela e os testes copiam. Um número que não fecha ali
vira um número que não fecha na tela, e um card com a forma errada vira um card
que quebra na conversa.
"""

from __future__ import annotations

import json
import re
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.mcp_server import abrir_sessao

from gateway.cartoes import TIPOS_DE_CARTAO
from gateway.cartoes_da_conversa import RefResolvida, fontes_do_conhecimento
from gateway.http import criar_app

CONTRATOS = Path(__file__).resolve().parents[2] / "contratos" / "web"
CENTAVO = Decimal("0.01")


def contrato(nome: str) -> Any:
    return json.loads((CONTRATOS / nome).read_text(encoding="utf-8"))


def _valor(dinheiro: dict[str, Any]) -> Decimal:
    return Decimal(str(dinheiro["valor"]))


def _redondo(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# As contas dos exemplos                                                       #
# --------------------------------------------------------------------------- #


def test_o_preco_preliminar_de_exemplo_fecha_a_conta() -> None:
    estimativa = contrato("estimativa.json")
    linhas = {linha["id"]: linha["valor"] for linha in estimativa["linhas"]}
    ingrediente = _valor(linhas["ingredientes"])
    producao = sum((_valor(v) for v in linhas.values() if v is not None), Decimal(0))
    assert _valor(estimativa["custo_producao"]) == producao
    piso = (producao / Decimal("0.9")).quantize(CENTAVO, rounding=ROUND_CEILING)
    assert _valor(estimativa["piso"]) == piso
    minimo = (ingrediente / Decimal("0.9")).quantize(CENTAVO, rounding=ROUND_CEILING)
    assert _valor(estimativa["minimo_so_ingrediente"]) == minimo
    for ponto, fracao in zip(estimativa["pontos"], ("0.40", "0.35", "0.30"), strict=True):
        preco = max(piso, _redondo(ingrediente / Decimal(fracao)))
        assert _valor(ponto["preco"]) == preco, ponto["nome"]
        assert _valor(ponto["taxa"]) == _redondo(preco * Decimal("0.10"))
        assert _valor(ponto["recebe"]) == _redondo(preco * Decimal("0.90"))
        assert _valor(ponto["lucro"]) == _redondo(preco * Decimal("0.90") - ingrediente)
        assert _valor(ponto["sobra_real"]) == _redondo(preco * Decimal("0.90") - producao)
    assert estimativa["preliminar"] is True
    assert estimativa["referencias_de_mercado"] == []
    assert "conferido" in estimativa["referencias_texto"]
    nomes = {p["nome"] for p in estimativa["premissas"]}
    assert {n for linha in estimativa["linhas"] for n in linha["premissas"]} <= nomes


@pytest.mark.parametrize("avaliacao", ["receita.json", "avaliacao-escrita.json"])
def test_a_pontuacao_de_exemplo_segue_a_formula(avaliacao: str) -> None:
    dados = contrato(avaliacao)
    avaliada = dados["avaliacao"] if "avaliacao" in dados else dados["resposta"]["avaliacao"]
    pesos = {
        "sabor": Decimal("0.30"),
        "apelo": Decimal("0.25"),
        "entrega": Decimal("0.20"),
        "facilidade": Decimal("0.15"),
        "tempo": Decimal("0.10"),
    }
    dadas = {k: Decimal(n) for k, n in avaliada["estrelas"].items() if n is not None}
    nota = sum(pesos[k] * (n - 1) / 4 for k, n in dadas.items()) / sum(pesos[k] for k in dadas)
    gosta = {True: Decimal(1), None: Decimal("0.5"), False: Decimal(0)}[avaliada["gosta"]]
    pontuacao = (100 * (Decimal("0.75") * nota + Decimal("0.25") * gosta)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    assert Decimal(str(avaliada["pontuacao"]["valor"])) == pontuacao
    assert avaliada["pontuacao"]["texto"] == str(pontuacao).replace(".", ",")


def test_a_lista_de_exemplo_conta_o_que_mostra() -> None:
    lista = contrato("receitas.json")
    assert set(lista["contagens"]) == {"pode_fazer", "falta_resposta", "ranking", "nao_quer"}
    assert lista["contagens"][lista["aba"]] == len(lista["itens"])
    assert {i["selo"]["codigo"] for i in lista["itens"]} <= {"com_o_que_tem", "comprando"}
    assert lista["descoberta"]["estado"] in {"parada", "procurando", "erro"}


def test_ids_e_chaves_de_foto_seguem_a_regra() -> None:
    """Receita da internet: 16 hex. Foto: `/motor/imagens/` e 32 hex, em todo exemplo."""
    textos = "".join(p.read_text(encoding="utf-8") for p in CONTRATOS.rglob("*.json*"))
    chaves = re.findall(r"/motor/imagens/([^\"]+)", textos)
    assert chaves
    assert all(re.fullmatch(r"[0-9a-f]{32}", chave) for chave in chaves), chaves
    receita = contrato("receita.json")
    assert re.fullmatch(r"[0-9a-f]{16}", receita["slug"])
    assert receita["fonte"]["url"]


# --------------------------------------------------------------------------- #
# Os cards de exemplo têm a forma da rota                                      #
# --------------------------------------------------------------------------- #

#: O contrato da rota de cada card que tem rota com contrato próprio.
ROTA_DO_CARD: dict[str, Any] = {
    "despensa_resumo": "visao-geral.json",
    "ingrediente": "despensa-item.json",
    "receita": "receita.json",
    "viabilidade": "receita.json",
    "comparacao": "receitas.json",
    "cozinha_atualizada": "perfil.json",
    "custo_porcao": "custo.json",
    "preco_preliminar": "estimativa.json",
    "decisao": "cardapio.json",
}


def _card(tipo: str) -> dict[str, Any]:
    dados: dict[str, Any] = contrato(f"cartoes/{tipo}.json")
    return dados


@pytest.mark.parametrize("tipo", sorted(ROTA_DO_CARD))
def test_o_card_tem_a_forma_do_contrato_da_rota(tipo: str) -> None:
    da_rota = contrato(ROTA_DO_CARD[tipo])
    da_rota.pop("ingrediente_que_falta_exemplo", None)
    da_rota.pop("ingrediente_com_preco_de_referencia_exemplo", None)
    assert set(_card(tipo)["dados"]) == set(da_rota)


def test_o_card_da_avaliacao_tem_a_forma_da_resposta_da_avaliacao() -> None:
    resposta = contrato("avaliacao-escrita.json")["resposta"]
    assert set(_card("avaliacao_da_receita")["dados"]) == set(resposta)


def test_os_cards_sem_rota_tem_a_forma_do_contrato() -> None:
    assert _card("pergunta")["ref"]["rota"] is None
    assert set(_card("pergunta")["dados"]) >= {"ha_pergunta", "pergunta", "tipo", "campo", "opcoes"}
    fontes = _card("fontes")
    assert fontes["ref"]["rota"] is None
    assert set(fontes["dados"]) == {"texto", "chips"}
    assert all(set(chip) == {"rotulo", "rota"} for chip in fontes["dados"]["chips"])


def test_o_card_de_fontes_de_exemplo_e_o_que_o_montador_devolve(tmp_path: Path) -> None:
    """O exemplo sai do montador de verdade, sobre a planilha dela e a base de cozinha de hoje.

    Escrito à mão, ele citava um livro que a base não tem mais, e a tela aprendia
    a mostrar uma fonte que o agente nunca daria.
    """
    exemplo = _card("fontes")
    sessao = abrir_sessao(planilha=sessao_de_teste.PLANILHA, banco=tmp_path / "dossie.db")
    try:
        ref = RefResolvida("fontes", None, exemplo["ref"]["parametros"])
        dados = fontes_do_conhecimento(SimpleNamespace(sessao=sessao), ref)
    finally:
        sessao.dossie.fechar()
    assert dados == exemplo["dados"]


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    banco = tmp_path / "dossie.db"
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    sessao_de_teste.preparar_dossie(banco)
    app = criar_app()
    sessao_de_teste.guardar_receitas(app.state.sessao)
    return TestClient(app)


@pytest.mark.parametrize("tipo", ["orcamento", "cenarios", "ponto_de_preco"])
def test_os_cards_das_rotas_de_hoje_tem_a_forma_delas(cliente: TestClient, tipo: str) -> None:
    """`/api/orcamento`, `/api/precos` e `/api/preco-em` não têm arquivo próprio: o card é o contrato."""
    exemplo = _card(tipo)
    resposta = cliente.get(exemplo["ref"]["rota"]).json()
    assert resposta["ok"], resposta
    assert set(resposta["dados"]) == set(exemplo["dados"])


def test_ha_um_card_de_exemplo_para_cada_tipo() -> None:
    arquivos = {p.stem for p in (CONTRATOS / "cartoes").glob("*.json")}
    assert arquivos == TIPOS_DE_CARTAO
    assert set(ROTA_DO_CARD) | {
        "avaliacao_da_receita",
        "pergunta",
        "fontes",
        "orcamento",
        "cenarios",
        "ponto_de_preco",
    } == set(TIPOS_DE_CARTAO)
