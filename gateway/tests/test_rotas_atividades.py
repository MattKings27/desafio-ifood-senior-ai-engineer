"""O histórico: uma linha do tempo em frases, com busca, filtros, dias e página.

Cada fonte tem o seu teste (as decisões, a despensa, as compras, a cozinha, o
gosto, as estrelas, as receitas, os preços e o que o agente consultou), e
todos conferem a regra que vale para a tela inteira: nada de nome de
ferramenta, identidade, milissegundos nem caminho de arquivo.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.catalogo import OrigemNoCatalogo
from mise.dinheiro import Dinheiro
from mise.dossie import Decisao, Dossie, OrigemPreco
from mise.perfil import Gosto
from retrieval.extrator import extrair
from test_rotas_despensa import conferir_contrato, contrato

from gateway.atividades import (
    DIAS_NO_FILTRO,
    Filtros,
    da_consultora,
    ler_trilha,
    pagina,
    rotulo_do_dia,
)
from gateway.http import criar_app


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "dossie.db"


@pytest.fixture
def trilha(tmp_path: Path) -> Path:
    return tmp_path / "trilha.jsonl"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, banco: Path, trilha: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.setenv("MISE_AUDITORIA", str(trilha))
    sessao_de_teste.preparar_dossie(banco)
    app = criar_app()
    sessao_de_teste.guardar_receitas(app.state.sessao)
    return TestClient(app)


def historico(cliente: TestClient, **filtros: Any) -> dict[str, Any]:
    corpo = cliente.get("/api/atividades", params=filtros).json()
    assert corpo["ok"], corpo.get("erro")
    resultado: dict[str, Any] = corpo["dados"]
    return resultado


def itens(pagina_: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for grupo in pagina_["grupos"] for item in grupo["itens"]]


def textos(cliente: TestClient, **filtros: Any) -> list[str]:
    return [item["texto"] for item in itens(historico(cliente, **filtros))]


def escrever_trilha(trilha: Path, *eventos: dict[str, Any], lixo: bool = False) -> None:
    with trilha.open("a", encoding="utf-8") as arquivo:
        for evento in eventos:
            arquivo.write(json.dumps(evento) + "\n")
        if lixo:
            arquivo.write("isto não é json\n[1, 2]\n")


def chamada(ferramenta: str, momento: float, resultado: str = "ok") -> dict[str, Any]:
    return {
        "momento": momento,
        "ferramenta": ferramenta,
        "identidade": "agente-hermes",
        "resultado": resultado,
        "duracao_ms": 12.34,
    }


#: O que nunca pode aparecer num texto do histórico.
PROIBIDO = re.compile(r"\b[a-z]+_[a-z_]+\b|\bms\b|/mnt/|\.jsonl|agente-hermes|12,34|12\.34")


# --------------------------------------------------------------------------- #
# A forma e a regra da tela
# --------------------------------------------------------------------------- #


def test_o_historico_tem_a_forma_do_contrato(cliente: TestClient, trilha: Path) -> None:
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    escrever_trilha(trilha, chamada("diagnostico_despensa", datetime.now(UTC).timestamp()))
    conferir_contrato(contrato("atividades.json"), historico(cliente, limite=1))


def test_nenhum_texto_tem_ferramenta_identidade_ou_caminho(
    cliente: TestClient, trilha: Path
) -> None:
    agora = datetime.now(UTC).timestamp()
    escrever_trilha(
        trilha,
        *(chamada(nome, agora - i) for i, nome in enumerate(("calcular_cmv", "consultar_perfil"))),
    )
    cliente.post("/api/decisao", json={"prato": "Arroz com frango", "decisao": "adiado"})
    todos = itens(historico(cliente))
    assert todos
    for item in todos:
        assert not PROIBIDO.search(item["texto"]), item["texto"]
        assert item["quem_rotulo"] in {"A senhora", "O agente", "A tela"}
        assert item["categoria_rotulo"]
        assert item["link"].startswith("/")


# --------------------------------------------------------------------------- #
# Cada fonte, em frases
# --------------------------------------------------------------------------- #


def test_as_decisoes_com_a_frase_do_cardapio(cliente: TestClient) -> None:
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    (decisao,) = itens(historico(cliente, categoria="cardapio"))
    assert decisao["texto"] == "A senhora aceitou o arroz com frango a R$ 18,00."
    assert (decisao["quem"], decisao["canal_texto"]) == ("senhora", "pela tela")
    assert decisao["link"] == "/receitas/arroz-com-frango"


def test_decisao_de_prato_sem_receita_leva_ao_cardapio(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_decisao("Pastel", Decisao.RECUSADO)
    (decisao,) = itens(historico(cliente, categoria="cardapio"))
    assert (decisao["link"], decisao["canal_texto"]) == ("/cardapio", "pela conversa")


def test_as_mudancas_da_despensa_com_o_nome_do_item(cliente: TestClient) -> None:
    creme = {
        "nome": "Creme de leite",
        "estoque": 2,
        "unidade": "un 200g",
        "quantidade_comprada": 2,
        "preco_pago": 9.0,
        "origem": "orcamento",
    }
    novo = cliente.post("/api/despensa/itens", json=creme).json()["dados"]["item"]
    cliente.post(
        "/api/despensa/itens",
        json={"nome": "Tahine", "estoque": 1, "unidade": "kg", "origem": "ja_tinha"},
    )
    cliente.patch(
        "/api/despensa/itens/cobertura-de-chocolate", json={"conteudo_da_embalagem": "1 kg"}
    )
    cliente.patch("/api/despensa/itens/acucar", json={"estoque": 0, "motivo": "acabou"})
    cliente.patch("/api/despensa/itens/alcaparras", json={"estoque": 0.5})
    cliente.delete(f"/api/despensa/itens/{novo['id']}")
    ultimo = cliente.get("/api/despensa/eventos").json()["dados"]["eventos"][0]
    cliente.post(f"/api/despensa/eventos/{ultimo['id']}/desfazer")
    frases = textos(cliente, categoria="despensa")
    assert (
        "A senhora comprou o creme de leite com os complementos: 2 embalagens de 200 g por R$ 9,00."
        in frases
    )
    assert any(f.startswith("A senhora acrescentou tahine à despensa: 1 kg") for f in frases)
    assert "A senhora informou que a embalagem da cobertura de chocolate tem 1 kg." in frases
    assert any(f.startswith("A senhora corrigiu as alcaparras: estoque de ") for f in frases)
    assert (
        "A senhora tirou o creme de leite da despensa. R$ 9,00 voltaram para os complementos."
        in frases
    )
    assert any(f.startswith("O creme de leite voltou para a despensa.") for f in frases)
    links = {item["link"] for item in itens(historico(cliente, categoria="despensa"))}
    assert f"/despensa/{novo['id']}" in links
    assert "/despensa/cobertura-de-chocolate" in links


def test_acabou_e_estorno_pela_despensa(cliente: TestClient) -> None:
    creme = {
        "nome": "Creme de leite",
        "estoque": 1,
        "unidade": "un 200g",
        "quantidade_comprada": 1,
        "preco_pago": 4.5,
        "origem": "orcamento",
    }
    novo = cliente.post("/api/despensa/itens", json=creme).json()["dados"]["item"]
    compra = cliente.get(f"/api/despensa/itens/{novo['id']}").json()["dados"]["compras"][0]
    cliente.post(f"/api/compras/{compra['id']}/estorno")
    cliente.patch("/api/despensa/itens/leite-integral", json={"estoque": 0})
    frases = textos(cliente, categoria="despensa")
    assert any(
        f.startswith("A compra do creme de leite voltou para os complementos (R$ 4,50)")
        for f in frases
    )
    removido = next(
        i for i in itens(historico(cliente)) if "voltou para os complementos" in i["texto"]
    )
    assert removido["link"] == "/despensa"


def test_as_compras_para_um_prato_e_a_devolucao(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_compra("milho verde", Decimal(1), "lata", Dinheiro.de("6"))
        compra = dossie.extrato()[-1]
        dossie.estornar(compra.id)
    frases = textos(cliente, categoria="despensa")
    assert "A senhora comprou o milho verde com os complementos: R$ 6,00." in frases
    assert "A compra do milho verde voltou para os complementos (R$ 6,00)." in frases


def test_as_respostas_sobre_a_cozinha(cliente: TestClient) -> None:
    cliente.put("/api/perfil/equipamentos/forno", json={"estado": "nao_tem"})
    (resposta,) = itens(historico(cliente, categoria="cozinha"))
    assert resposta["texto"] == "A senhora disse que não tem forno."
    assert (resposta["link"], resposta["canal_texto"]) == ("/cozinha", "pela tela")


def test_o_gosto_e_o_impedimento(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_gosto("Bolo de fubá", Gosto.NAO_GOSTA, "suja o forno.")
        dossie.registrar_gosto("Pudim", Gosto.DESCONHECIDO, "falta forma")
        dossie.registrar_gosto("Quindim", Gosto.DESCONHECIDO)
    frases = textos(cliente, categoria="receitas")
    assert "A senhora disse que gosta de fazer o arroz com frango." in frases
    assert (
        "A senhora disse que não gosta de fazer o bolo de fubá. O impedimento: suja o forno."
        in frases
    )
    assert any(
        f.startswith("A senhora apontou um impedimento para") and "falta forma" in f for f in frases
    )
    assert not any("Quindim" in f or "quindim" in f for f in frases)


def test_as_estrelas_e_as_notas(cliente: TestClient) -> None:
    cliente.put("/api/receitas/arroz-com-frango/avaliacao", json={"estrelas": {"sabor": 5}})
    frases = textos(cliente, categoria="receitas")
    assert any(
        f.startswith("A senhora deu estrelas para o arroz com frango: pontuação ") for f in frases
    )


def test_so_as_notas_tambem_contam(cliente: TestClient) -> None:
    cliente.put("/api/receitas/arroz-com-frango/notas", json={"texto": "Sai bem no almoço"})
    frases = textos(cliente, categoria="receitas")
    assert "A senhora anotou sobre o arroz com frango." in frases


def test_as_receitas_que_entraram_na_grade(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao
    pagina_do_bolo = sessao_de_teste.pagina_do_bolo()
    for url, origem in (
        ("https://www.tudogostoso.com.br/receita/9-bolo-de-milho", OrigemNoCatalogo.DESCOBERTA),
        ("https://www.tudogostoso.com.br/receita/8-bolo-de-coco", OrigemNoCatalogo.URL_DELA),
    ):
        sessao.catalogar(extrair(pagina_do_bolo, url), origem)
    por_quem = {(i["quem"], i["texto"]) for i in itens(historico(cliente, categoria="receitas"))}
    assert ("senhora", "A senhora ditou a receita Arroz com frango.") in por_quem
    assert ("consultora", "Trouxe a receita Bolo de fubá, do TudoGostoso.") in por_quem
    assert any(q == "tela" and t.startswith("Receita nova na grade: ") for q, t in por_quem)
    assert any(q == "senhora" and t.startswith("A senhora trouxe a receita ") for q, t in por_quem)


def test_a_resposta_dela_sobre_a_receita(cliente: TestClient) -> None:
    bolo = next(r for r in cliente.app.state.sessao.catalogo.listar() if r.nome.startswith("Bolo"))
    resposta = cliente.post(
        f"/api/receitas/{bolo.slug}/resposta",
        json={"campo": "tempo_cozimento_min", "resposta": "40"},
    ).json()
    assert resposta["ok"], resposta
    frases = textos(cliente, categoria="receitas")
    assert any(
        f.startswith("A senhora disse que fica 40") and "(Bolo de fubá)" in f for f in frases
    )


def test_os_precos_de_quem_disse(cliente: TestClient, banco: Path) -> None:
    with Dossie(banco) as dossie:
        dossie.registrar_preco(
            "milho verde", Dinheiro.de("6"), OrigemPreco.INFORMADO_POR_ELA, Decimal(1), "lata"
        )
        dossie.registrar_preco("coco ralado", Dinheiro.de("4.5"), OrigemPreco.PESQUISADO_NA_WEB)
        dossie.registrar_preco("fermento", Dinheiro.de("3"), OrigemPreco.ESTIMADO)
    por_quem = {(i["quem"], i["texto"]) for i in itens(historico(cliente, categoria="preco"))}
    assert por_quem == {
        ("senhora", "A senhora informou o preço do milho verde: R$ 6,00 por 1 lata."),
        ("consultora", "Achei o preço do coco ralado na internet: R$ 4,50."),
        ("consultora", "Estimei o preço do fermento: R$ 3,00."),
    }


def test_o_que_a_consultora_consultou(cliente: TestClient, trilha: Path) -> None:
    agora = datetime.now(UTC).timestamp()
    escrever_trilha(
        trilha,
        chamada("diagnostico_despensa", agora - 300),
        chamada("diagnostico_despensa", agora - 200),
        chamada("registrar_decisao", agora - 150),
        chamada("buscar_receita_na_web", agora - 140),
        chamada("ferramenta_inventada", agora - 130),
        chamada("calcular_cmv", agora - 100, resultado="erro"),
        {"ferramenta": "consultar_perfil"},
        lixo=True,
    )
    da_consultora_ = [
        i for i in itens(historico(cliente, quem="consultora")) if i["id"].startswith("consulta-")
    ]
    assert [i["texto"] for i in da_consultora_] == [
        "Calculei o custo por porção, mas não deu certo.",
        "Olhei sua despensa.",
    ]
    assert da_consultora_[0]["resultado"] == "erro"
    assert da_consultora_[0]["link"] == "/precificar"
    assert da_consultora_[1]["canal_texto"] == "pela conversa"


def test_consulta_com_frase_generica(cliente: TestClient, trilha: Path) -> None:
    escrever_trilha(trilha, chamada("custo_unitario", datetime.now(UTC).timestamp()))
    (consulta,) = [i for i in itens(historico(cliente)) if i["id"].startswith("consulta-")]
    assert consulta["categoria"] == "despensa"
    assert consulta["texto"][0].isupper() and consulta["texto"].endswith(".")


def test_sem_trilha_nao_ha_consulta(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert ler_trilha(None) == []
    assert ler_trilha(str(tmp_path / "nao-existe.jsonl")) == []
    pasta = tmp_path / "uma-pasta.jsonl"
    pasta.mkdir()
    assert ler_trilha(str(pasta)) == []
    repetida = [chamada("consultar_cardapio", 1000.0), chamada("consultar_cardapio", 5000.0)]
    assert [a.texto for a in da_consultora(repetida)] == ["Olhei o cardápio.", "Olhei o cardápio."]


# --------------------------------------------------------------------------- #
# Busca, filtros, dias e página
# --------------------------------------------------------------------------- #


def test_busca_sem_acento_e_filtros_combinados(cliente: TestClient) -> None:
    cliente.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 18}
    )
    cliente.put("/api/perfil/equipamentos/freezer", json={"estado": "nao_tem"})
    assert textos(cliente, q="CARDAPIO") == []
    assert textos(cliente, q="aceitou") == ["A senhora aceitou o arroz com frango a R$ 18,00."]
    assert textos(cliente, q="freezer", categoria="cozinha") == [
        "A senhora disse que não tem freezer."
    ]
    assert textos(cliente, quem="tela") == []
    assert all(i["quem"] == "senhora" for i in itens(historico(cliente, quem="senhora")))


@pytest.mark.parametrize(("filtro", "valor"), [("categoria", "compras"), ("quem", "vizinha")])
def test_filtro_que_nao_existe_e_recusado(cliente: TestClient, filtro: str, valor: str) -> None:
    corpo = cliente.get("/api/atividades", params={filtro: valor}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")


def test_dia_mal_escrito_e_422(cliente: TestClient) -> None:
    assert cliente.get("/api/atividades", params={"dia": "ontem"}).status_code == 422


def test_agrupado_por_dia_com_o_filtro_de_dia(cliente: TestClient, banco: Path) -> None:
    ontem = datetime.now(UTC) - timedelta(days=1)
    with Dossie(banco, relogio=lambda: ontem) as dossie:
        dossie.registrar_decisao("Pastel", Decisao.ADIADO)
    pagina_ = historico(cliente)
    assert [g["rotulo"] for g in pagina_["grupos"]] == ["Hoje", "Ontem"]
    assert [d["rotulo"] for d in pagina_["dias"]] == ["Hoje", "Ontem"]
    dia_de_ontem = pagina_["dias"][1]["id"]
    so_ontem = historico(cliente, dia=dia_de_ontem)
    assert [g["dia"] for g in so_ontem["grupos"]] == [dia_de_ontem]
    assert so_ontem["texto"] == "1 registro"
    assert len(so_ontem["dias"]) == 2, "os dias do filtro não somem ao escolher um"


def test_pagina_por_cursor(cliente: TestClient, trilha: Path) -> None:
    agora = datetime.now(UTC).timestamp()
    nomes = ("consultar_cardapio", "consultar_perfil", "consultar_orcamento", "comparar_candidatas")
    escrever_trilha(trilha, *(chamada(n, agora - 60 * i) for i, n in enumerate(nomes)))
    primeira = historico(cliente, quem="consultora", limite=2)
    assert len(itens(primeira)) == 2
    assert primeira["texto"].endswith("registros")
    segunda = historico(cliente, quem="consultora", limite=2, cursor=primeira["proximo_cursor"])
    ids = [i["id"] for i in itens(primeira) + itens(segunda)]
    assert len(ids) == len(set(ids))
    ultima = historico(cliente, quem="consultora", limite=200)
    assert ultima["proximo_cursor"] is None
    corpo = cliente.get("/api/atividades", params={"cursor": "consulta-0-0"}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")


def test_historico_vazio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "vazio.db"))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    vazio = historico(TestClient(criar_app()))
    assert (vazio["grupos"], vazio["total"], vazio["texto"]) == ([], 0, "nada por aqui ainda")
    assert [c["id"] for c in vazio["categorias"]] == [
        "despensa",
        "receitas",
        "cozinha",
        "preco",
        "cardapio",
    ]
    assert [q["rotulo"] for q in vazio["quem"]] == ["A senhora", "O agente", "A tela"]


def test_os_dias_do_filtro_tem_limite(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao
    agora = datetime.now(UTC).timestamp()
    eventos = [chamada("consultar_cardapio", agora - 86400 * dias) for dias in range(20)]
    dados = pagina(sessao, Filtros(), trilha=eventos)
    assert len(dados["dias"]) == DIAS_NO_FILTRO


def test_o_rotulo_de_cada_dia() -> None:
    agora = datetime(2026, 9, 26, 15, 0, tzinfo=UTC)
    assert rotulo_do_dia("2026-09-26", agora) == "Hoje"
    assert rotulo_do_dia("2026-09-25", agora) == "Ontem"
    assert rotulo_do_dia("2026-09-02", agora) == "2 de setembro"
    assert rotulo_do_dia("2025-12-31", agora) == "31 de dezembro de 2025"


def test_desfazer_na_despensa_tambem_vira_frase(cliente: TestClient) -> None:
    tahine = {"nome": "Tahine", "estoque": 1, "unidade": "kg", "origem": "ja_tinha"}
    cliente.post("/api/despensa/itens", json=tahine)
    cliente.patch("/api/despensa/itens/alcaparras", json={"estoque": 0.5})
    for evento in cliente.get("/api/despensa/eventos").json()["dados"]["eventos"]:
        cliente.post(f"/api/despensa/eventos/{evento['id']}/desfazer")
    frases = textos(cliente, categoria="despensa")
    assert "Desfeito: tahine saiu da despensa." in frases
    assert any(f.startswith("Desfeita a correção das alcaparras: estoque de ") for f in frases)


def test_o_nome_do_item_de_um_evento_sem_item() -> None:
    from types import SimpleNamespace

    from gateway.atividades import _nome_do_evento

    evento = SimpleNamespace(item_id="sumiu", dados={"linha": {"nome": "Trufa"}})
    estado = SimpleNamespace(item=lambda _id: None)
    assert _nome_do_evento(evento, estado) == ("Trufa", "")  # type: ignore[arg-type]


def test_estrela_apagada_sem_notas_nao_conta(cliente: TestClient) -> None:
    avaliacao = "/api/receitas/arroz-com-frango/avaliacao"
    cliente.put(avaliacao, json={"estrelas": {"sabor": 5}})
    cliente.put(avaliacao, json={"estrelas": {"sabor": None}})
    assert not any("estrelas" in f for f in textos(cliente, categoria="receitas"))


def test_duas_decisoes_do_mesmo_prato_levam_a_mesma_receita(cliente: TestClient) -> None:
    for decisao in ("adiado", "recusado"):
        cliente.post("/api/decisao", json={"prato": "Arroz com frango", "decisao": decisao})
    links = {i["link"] for i in itens(historico(cliente, categoria="cardapio"))}
    assert links == {"/receitas/arroz-com-frango"}
