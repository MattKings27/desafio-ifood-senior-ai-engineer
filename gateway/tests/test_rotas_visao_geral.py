"""A tela inicial: a forma do contrato, os indicadores, as perguntas, o próximo passo e o parado."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.despensa import Pendencia, TipoDePendencia
from mise.dinheiro import Dinheiro
from test_rotas_despensa import conferir_contrato, contrato

from gateway.http import criar_app
from gateway.visao_geral import RASCUNHO_DE_RECEITAS, proximo_passo

#: A receita que pede forno: com a cozinha em aberto, ela espera a resposta do forno.
FRANGO_ASSADO: dict[str, Any] = {
    "nome": "Frango assado",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 50,
    "modo_preparo": ["Tempere o frango.", "Leve ao forno e asse por 40 minutos."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


def _cliente(monkeypatch: pytest.MonkeyPatch, banco: Path, *, aprovada: bool) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    sessao_de_teste.preparar_dossie(banco, aprovada=aprovada)
    app = criar_app()
    sessao_de_teste.guardar_receitas(app.state.sessao)
    return TestClient(app)


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """A cozinha confirmada: o arroz com frango dá pra fazer."""
    return _cliente(monkeypatch, tmp_path / "dossie.db", aprovada=True)


@pytest.fixture
def em_aberto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """A cozinha sem resposta nenhuma, e uma receita que vai ao forno."""
    cliente = _cliente(monkeypatch, tmp_path / "dossie.db", aprovada=False)
    assert cliente.post("/api/avaliar", json=FRANGO_ASSADO).json()["ok"]
    return cliente


def visao(cliente: TestClient) -> dict[str, Any]:
    corpo = cliente.get("/api/visao-geral").json()
    assert corpo["ok"], corpo.get("erro")
    resultado: dict[str, Any] = corpo["dados"]
    return resultado


def test_a_tela_inicial_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    cliente.put("/api/receitas/arroz-com-frango/avaliacao", json={"estrelas": {"sabor": 5}})
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    conferir_contrato(contrato("visao-geral.json"), visao(cliente))


def test_os_indicadores_trazem_o_texto_e_a_rota(cliente: TestClient) -> None:
    kpis = visao(cliente)["kpis"]
    assert kpis["despensa"] == {
        "total": {"valor": 663.39, "texto": "R$ 663,39"},
        "itens": 37,
        "texto": "37 ingredientes",
        "rota": "/despensa",
    }
    assert kpis["orcamento"]["texto"] == "nada gasto ainda"
    assert kpis["orcamento"]["rota"] == "/despensa#orcamento"
    # O bolo sai comprando o coco ralado pelo preço de referência.
    assert kpis["receitas"]["texto"] == "2 de 2 dão pra fazer"
    assert kpis["cardapio"] == {"pratos": 0, "texto": "nenhum prato ainda", "rota": "/cardapio"}
    # A cozinha toda respondida por ela: o que toda cozinha tem, inclusive.
    assert kpis["cozinha"]["texto"] == "63 de 63 respondidos pela senhora"
    assert kpis["cozinha"]["rota"] == "/cozinha"


def test_os_indicadores_acompanham_o_que_ela_fez(cliente: TestClient) -> None:
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    # "Não sei" do freezer: deixa de contar como respondido.
    cliente.put("/api/perfil/equipamentos/freezer", json={"estado": "nao_sei"})
    creme = {"nome": "Creme de leite", "estoque": 1, "unidade": "un 200g", "quantidade_comprada": 1}
    cliente.post("/api/despensa/itens", json={**creme, "preco_pago": 4.5, "origem": "orcamento"})
    kpis = visao(cliente)["kpis"]
    assert kpis["cardapio"]["texto"] == "1 prato no cardápio"
    assert kpis["cozinha"]["texto"] == "62 de 63 respondidos pela senhora"
    assert kpis["orcamento"]["texto"] == "R$ 4,50 já gastos"
    assert kpis["orcamento"]["restante"]["texto"] == "R$ 75,50"
    assert kpis["despensa"]["texto"] == "38 ingredientes"


def test_a_despensa_nao_pergunta_nada_na_tela_inicial(cliente: TestClient) -> None:
    """O peso da cobertura vem estimado, com a fonte: o Início não tem pergunta da despensa."""
    dados = visao(cliente)
    assert dados["pendencias"] == []
    assert "cobertura de chocolate" not in dados["proximo_passo"]["texto"]


def test_a_pergunta_da_cozinha_junta_as_receitas_que_ela_segura(em_aberto: TestClient) -> None:
    em_aberto.patch(
        "/api/despensa/itens/cobertura-de-chocolate", json={"conteudo_da_embalagem": "1 kg"}
    )
    dados = visao(em_aberto)
    perguntas = dados["perguntas_da_cozinha"]
    assert perguntas, "a receita do forno espera uma resposta da cozinha"
    primeira = perguntas[0]
    assert primeira["id"] == f"{primeira['pergunta']['tipo']}:{primeira['pergunta']['campo']}"
    assert primeira["pergunta"]["tipo"] in {"equipamento", "tecnica", "operacional"}
    assert primeira["pergunta"]["motivo"].startswith("Isso segura ")
    assert primeira["rascunho_chat"].startswith("Sobre a pergunta “")
    assert primeira["rota"] == "/receitas?aba=falta_resposta"
    assert primeira["receita"] == primeira["receitas"][0]
    assert dados["proximo_passo"]["texto"].startswith("Responda o que falta saber da sua cozinha")


def test_o_dinheiro_parado_vem_inteiro_e_em_ordem(cliente: TestClient) -> None:
    parado = visao(cliente)["dinheiro_parado"]
    itens = parado["itens"]
    assert parado["total_itens"] == len(itens) == 37
    valores = [i["pago"]["valor"] for i in itens]
    assert valores == sorted(valores, reverse=True)
    assert [i["id"] for i in itens[:2]] == ["alcaparras", "cobertura-de-chocolate"]
    assert itens[0]["fracao_texto"] == "12%"
    assert itens[0]["rota"] == "/despensa/alcaparras"
    assert parado["dois_maiores"]["texto"] == (
        "Alcaparras e Cobertura de chocolate somam 24% de tudo o que a senhora pagou"
    )
    usados = {i["id"] for i in itens if not i["sem_receita"]}
    assert "arroz-branco" in usados or any("arroz" in i for i in usados)
    assert all(i["sem_receita"] for i in itens if i["id"] == "alcaparras")
    pequenos = [i["fracao_texto"] for i in itens if i["fracao"] < 0.005]
    assert all(t == "menos de 1%" for t in pequenos)


def test_despensa_com_um_item_so(cliente: TestClient) -> None:
    for item in cliente.get("/api/despensa").json()["dados"]["itens"][1:]:
        cliente.delete(f"/api/despensa/itens/{item['id']}")
    dois = visao(cliente)["dinheiro_parado"]["dois_maiores"]
    assert dois["texto"] == "Alcaparras é tudo o que a senhora pagou"


def test_as_receitas_recomendadas_e_a_previa_do_cardapio(cliente: TestClient) -> None:
    antes = visao(cliente)
    assert antes["receitas_recomendadas"][0]["slug"] == "arroz-com-frango"
    assert len(antes["receitas_recomendadas"]) == 2
    assert antes["cardapio_previa"] == []
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    cliente.patch(
        "/api/despensa/itens/cobertura-de-chocolate", json={"conteudo_da_embalagem": "1 kg"}
    )
    depois = visao(cliente)
    assert [p["prato"] for p in depois["cardapio_previa"]] == ["Arroz com frango"]
    assert depois["cardapio_previa"][0]["lucro_porcao"]["texto"] == "R$ 13,20"
    assert depois["proximo_passo"]["acao"] == {"tipo": "link", "rota": "/cardapio"}


def test_o_card_da_conversa_recebe_a_tela_inicial(cliente: TestClient) -> None:
    """O card `despensa_resumo` lê esta rota: o que ele usa está aqui."""
    dados = visao(cliente)
    assert dados["kpis"]["despensa"]["rota"] == "/despensa"
    assert dados["dinheiro_parado"]["itens"][0]["pago"]["texto"] == "R$ 82,00"
    assert dados["pendencias"] == []


# --------------------------------------------------------------------------- #
# O próximo passo, caso a caso
# --------------------------------------------------------------------------- #


def _despensa(*pendencias: Pendencia) -> Any:
    return SimpleNamespace(pendencias=list(pendencias))


def _passo(despensa: Any = None, perguntas: Any = (), **numeros: int) -> dict[str, Any]:
    contas = {"no_catalogo": 3, "da_pra_fazer": 0, "pratos": 0, **numeros}
    return proximo_passo(despensa or _despensa(), perguntas, **contas)


def test_o_preco_que_falta_vem_antes_de_tudo() -> None:
    pendencia = Pendencia(
        "Tahine", "sem preço", "Quanto pagou?", Dinheiro.zero(), TipoDePendencia.PRECO
    )
    passo = _passo(_despensa(pendencia))
    assert passo["texto"] == (
        "Responda a pergunta sobre tahine: sem o preço, as receitas com ele ficam sem custo."
    )


@pytest.mark.parametrize(
    ("numeros", "texto", "acao"),
    [
        (
            {"no_catalogo": 0},
            "Peça receitas para o agente",
            {"tipo": "perguntar", "rascunho": RASCUNHO_DE_RECEITAS},
        ),
        (
            {"da_pra_fazer": 1},
            "Veja a receita que já dá pra fazer",
            {"tipo": "link", "rota": "/receitas"},
        ),
        (
            {"da_pra_fazer": 4},
            "Veja as 4 receitas que já dão pra fazer",
            {"tipo": "link", "rota": "/receitas"},
        ),
        (
            {},
            "Nenhuma receita dá pra fazer ainda",
            {"tipo": "perguntar", "rascunho": RASCUNHO_DE_RECEITAS},
        ),
        ({"pratos": 2}, "O seu cardápio tem 2 pratos", {"tipo": "link", "rota": "/cardapio"}),
    ],
)
def test_o_proximo_passo_de_cada_momento(
    numeros: dict[str, int], texto: str, acao: dict[str, str]
) -> None:
    passo = _passo(**numeros)
    assert passo["texto"].startswith(texto)
    assert passo["acao"] == acao


def test_a_pergunta_da_cozinha_libera_receitas() -> None:
    perguntas = [{"receitas": [{}, {}]}, {"receitas": [{}]}]
    passo = _passo(perguntas=perguntas)
    assert passo["texto"] == "Responda o que falta saber da sua cozinha: isso libera 3 receitas."
    # Responde conversando, em tela cheia: o agente conduz.
    assert passo["acao"]["rota"] == "/conversa?comecar=cozinha"


def test_a_lista_de_receitas_resume_depois_de_duas() -> None:
    from gateway.visao_geral import _lista

    assert _lista(["a"]) == "a"
    assert _lista(["a", "b"]) == "a e b"
    assert _lista(["a", "b", "c", "d"]) == "a, b e mais 2"
