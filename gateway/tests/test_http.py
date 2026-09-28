"""A API HTTP: a mesma sessão do motor que o MCP usa, e não uma segunda verdade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.http import ReceitaBody, criar_app

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"

RECEITA_FORNO: dict[str, Any] = {
    "nome": "Frango assado",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 50,
    "modo_preparo": ["Leve ao forno e asse por 40 minutos."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "dossie.db"))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    return TestClient(criar_app())


def dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert corpo["ok"], corpo.get("erro")
    return corpo["dados"]


# --------------------------------------------------------------------------- #
# Saúde: liveness e readiness são coisas diferentes
# --------------------------------------------------------------------------- #


def test_liveness(cliente: TestClient) -> None:
    assert cliente.get("/saude/vivo").json() == {"estado": "vivo"}


def test_readiness_confere_a_despensa(cliente: TestClient) -> None:
    """Processo vivo com planilha ilegível não deve receber tráfego."""
    corpo = cliente.get("/saude/pronto").json()
    assert corpo["estado"] == "pronto"
    assert corpo["itens"] == 37
    # A embalagem sem peso vem estimada, com a fonte: nenhuma pergunta à espera dela.
    assert corpo["pendencias"] == 0


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #


def test_despensa_traz_derivacao_de_cada_item(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/despensa"))
    assert d["total_investido"]["texto"] == "R$ 663,39"
    assert len(d["itens"]) == 37
    assert all(i["derivacao"] for i in d["itens"])
    assert d["itens"][0]["nome"] == "Alcaparras", "ordenado por capital"


def test_despensa_nao_pergunta_o_peso_da_embalagem(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/despensa"))
    assert d["pendencias"] == []
    cobertura = next(i for i in d["itens"] if i["nome"] == "Cobertura de chocolate")
    assert cobertura["custo_unitario"]["texto"] == "R$ 79,90/kg"
    assert "estimativa" in cobertura["derivacao"]


def test_a_despensa_marca_as_seis_contas_que_a_divisao_crua_erraria(cliente: TestClient) -> None:
    itens = dados(cliente.get("/api/despensa"))["itens"]
    armadilhas = [i for i in itens if i["normalizacao_importou"]]
    assert len(armadilhas) == 6
    alcaparras = next(i for i in armadilhas if i["nome"] == "Alcaparras")
    assert alcaparras["custo_ingenuo"]["texto"] == "R$ 82,00"
    assert alcaparras["custo_texto"] == "R$ 41,00/kg"


def test_perfil_traz_a_pergunta_de_cada_item(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/perfil"))
    assert len(d["equipamentos"]) == 31
    assert len(d["tecnicas"]) == 32
    forno = next(e for e in d["equipamentos"] if e["id"] == "forno")
    assert forno["estado"] == "desconhecido"
    assert "?" in forno["pergunta"]


def test_a_tela_inicial_traz_a_soma_dos_dois_maiores_pronta(cliente: TestClient) -> None:
    """A tela mostrava a soma calculada no navegador; conta é do motor."""
    d = dados(cliente.get("/api/visao-geral"))["dinheiro_parado"]["dois_maiores"]
    assert d["nomes"] == ["Alcaparras", "Cobertura de chocolate"]
    assert d["soma"]["texto"] == "R$ 161,90"
    assert round(d["fracao"], 3) == 0.244


def test_perfil_nao_pinta_suposicao_como_resposta_dela(cliente: TestClient) -> None:
    """Com o dossiê zerado, "fogão: tem" é suposição; a tela não pode dizer que ela disse."""
    d = dados(cliente.get("/api/perfil"))
    fogao = next(e for e in d["equipamentos"] if e["id"] == "fogao")
    assert (fogao["estado"], fogao["suposto"]) == ("tem", True)
    forno = next(e for e in d["equipamentos"] if e["id"] == "forno")
    assert forno["suposto"] is False
    assert d["respondidos"] == 0
    assert d["fracao_respondida"] == 0
    assert d["supostos"] > 0

    cliente.post("/api/resposta", json={"tipo": "equipamento", "campo": "fogao", "resposta": "sim"})
    depois = dados(cliente.get("/api/perfil"))
    fogao = next(e for e in depois["equipamentos"] if e["id"] == "fogao")
    assert (fogao["estado"], fogao["suposto"]) == ("tem", False)
    assert depois["respondidos"] == 1


def test_orcamento_comeca_intacto(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/orcamento"))
    assert d["restante"]["texto"] == "R$ 80,00"
    assert d["compras"] == []


def test_cardapio_vazio(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/cardapio"))
    assert d["pratos"] == []
    assert d["historico"] == []


def test_escopos_espelham_a_politica_do_mcp(cliente: TestClient) -> None:
    """Se a API divergir da política do MCP, há duas verdades de acesso."""
    from gateway.politica import ESCOPOS, Escopo

    d = dados(cliente.get("/api/escopos"))
    assert set(d["leitura"]) == {n for n, e in ESCOPOS.items() if e is Escopo.LEITURA}
    assert set(d["escrita"]) == {n for n, e in ESCOPOS.items() if e is Escopo.ESCRITA}


def test_auditoria_sem_arquivo_configurado(cliente: TestClient) -> None:
    d = dados(cliente.get("/api/auditoria"))
    assert d["eventos"] == []
    assert d["arquivo"] is None


# --------------------------------------------------------------------------- #
# O portão, pela porta HTTP
# --------------------------------------------------------------------------- #


def test_avaliar_devolve_veredito_e_perguntas(cliente: TestClient) -> None:
    d = dados(cliente.post("/api/avaliar", json=RECEITA_FORNO))
    assert d["veredito"] == "FALTA INFO"
    assert not d["pode_precificar"]
    assert any(p["campo"] == "forno" for p in d["perguntas"])


def test_cmv_recusa_sem_viabilidade(cliente: TestClient) -> None:
    """A mesma garantia do MCP tem de valer aqui. Senão a web app é um bypass."""
    assert dados(cliente.post("/api/avaliar", json=RECEITA_FORNO))["veredito"] == "FALTA INFO"
    corpo = cliente.post("/api/cmv", json=RECEITA_FORNO).json()
    assert corpo["ok"] is False
    assert corpo["categoria"] == "regra"
    assert corpo["dados"] is None


def test_avaliar_le_o_tempo_de_cozimento_da_tela(cliente: TestClient) -> None:
    """A tela manda os três tempos separados; sem tempo nos passos, vale o de cozimento."""
    # A tela manda o tempo por cozinhada em horas.
    uma_hora = {"valor": 1}
    assert dados(cliente.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json=uma_hora))
    sem_tempo_nos_passos = {
        **RECEITA_FORNO,
        "modo_preparo": ["Leve ao forno até dourar."],
        "tempo_preparo_min": 20,
        "tempo_cozimento_min": 90,
        "tempo_total_min": 110,
    }
    d = dados(cliente.post("/api/avaliar", json=sem_tempo_nos_passos))
    assert d["veredito"] == "BLOQUEADO"
    assert d["impedimentos"][0]["motivo"] == (
        "a receita diz que o cozimento leva 90 minutos; a senhora tem 60 por cozinhada"
    )
    assert d["avisos"] == []
    guardada = dados(cliente.get("/api/receita", params={"prato": "Frango assado"}))
    assert (
        guardada["tempo_preparo_min"],
        guardada["tempo_cozimento_min"],
        guardada["tempo_total_min"],
    ) == (20, 90, 110)


def test_rendimento_invalido_e_rejeitado_no_schema(cliente: TestClient) -> None:
    ruim = {**RECEITA_FORNO, "rendimento_porcoes": 0}
    assert cliente.post("/api/avaliar", json=ruim).status_code == 422


def test_receita_body_tem_defaults_uteis() -> None:
    r = ReceitaBody(nome="X", ingredientes=[])
    # Sem rendimento informado o motor pergunta; 1 como padrão inflava o preço.
    assert r.rendimento_porcoes is None
    assert r.modo_preparo == []


# --------------------------------------------------------------------------- #
# Preço
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("params", [{"cmv": 0}, {"cmv": -1}])
def test_cmv_invalido_no_query(cliente: TestClient, params: dict[str, Any]) -> None:
    assert cliente.get("/api/precos", params=params).status_code == 422


# --------------------------------------------------------------------------- #
# Formatação
# --------------------------------------------------------------------------- #


def test_cors_permite_o_front_local(cliente: TestClient) -> None:
    resposta = cliente.get("/api/orcamento", headers={"Origin": "http://localhost:3000"})
    assert resposta.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --------------------------------------------------------------------------- #
# Bordas
# --------------------------------------------------------------------------- #


def test_auditoria_le_a_trilha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    trilha = tmp_path / "auditoria.jsonl"
    trilha.write_text(
        '{"ferramenta": "custo_unitario", "resultado": "ok"}\n'
        "isto nao e json e nao pode derrubar a leitura\n"
        '{"ferramenta": "calcular_cmv", "resultado": "negado"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    monkeypatch.setenv("MISE_AUDITORIA", str(trilha))

    d = dados(TestClient(criar_app()).get("/api/auditoria"))
    assert len(d["eventos"]) == 2, "linha corrompida é pulada, não fatal"
    assert d["eventos"][0]["ferramenta"] == "custo_unitario"


def test_auditoria_com_arquivo_inexistente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A trilha só nasce na primeira chamada do agente: antes disso é lista vazia.

    A tela mostrava "motor respondeu 503" para quem ainda não tinha conversado.
    """
    caminho = str(tmp_path / "nao-existe.jsonl")
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    monkeypatch.setenv("MISE_AUDITORIA", caminho)
    resposta = TestClient(criar_app()).get("/api/auditoria")
    assert resposta.status_code == 200
    d = dados(resposta)
    assert d["eventos"] == []
    assert d["arquivo"] == caminho


def test_auditoria_ilegivel_continua_503(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Um diretório no lugar do arquivo é defeito de instalação, não trilha vazia."""
    pasta = tmp_path / "auditoria.jsonl"
    pasta.mkdir()
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    monkeypatch.setenv("MISE_AUDITORIA", str(pasta))
    assert TestClient(criar_app()).get("/api/auditoria").status_code == 503


def test_auditoria_expande_o_til_como_quem_escreve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Quem grava expande `~`; quem lê tem de ler o mesmo arquivo."""
    (tmp_path / "trilha.jsonl").write_text('{"ferramenta": "custo_unitario"}\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    monkeypatch.setenv("MISE_AUDITORIA", "~/trilha.jsonl")
    d = dados(TestClient(criar_app()).get("/api/auditoria"))
    assert d["eventos"] == [{"ferramenta": "custo_unitario"}]


def test_auditoria_respeita_o_limite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    trilha = tmp_path / "a.jsonl"
    trilha.write_text("".join(f'{{"i": {i}}}\n' for i in range(100)), encoding="utf-8")
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    monkeypatch.setenv("MISE_AUDITORIA", str(trilha))

    d = dados(TestClient(criar_app()).get("/api/auditoria", params={"limite": 5}))
    assert [e["i"] for e in d["eventos"]] == [95, 96, 97, 98, 99]


def test_readiness_falha_com_despensa_vazia(cliente: TestClient) -> None:
    """Processo vivo com despensa vazia não deve receber tráfego."""
    from gateway import http

    app = criar_app()
    for rota in app.routes:
        if getattr(rota, "path", "") == "/saude/pronto":
            break

    # Esvazia a despensa da sessão em voo, simulando planilha que sumiu.
    import mise.mcp_server as mcp

    sessao = mcp.abrir_sessao()
    sessao.despensa.itens.clear()
    original = mcp.abrir_sessao
    mcp.abrir_sessao = lambda *a, **k: sessao  # type: ignore[assignment]
    try:
        assert TestClient(http.criar_app()).get("/saude/pronto").status_code == 503
    finally:
        mcp.abrir_sessao = original  # type: ignore[assignment]
        sessao.dossie.fechar()


def test_erro_de_dado_traz_a_pergunta(cliente: TestClient) -> None:
    """Pedir massa de embalagem opaca vira pergunta, não estimativa."""
    receita = {
        "nome": "Bolo",
        "ingredientes": [
            {
                "texto": "200 g de cobertura",
                "nome": "Cobertura de chocolate",
                "quantidade": 200,
                "medida": "g",
            }
        ],
    }
    d = dados(cliente.post("/api/avaliar", json=receita))
    # O peso da embalagem vem estimado: nada de pergunta sobre ele.
    assert not any("embalagem" in p["texto"] for p in d["perguntas"])
    assert all(p["tipo"] != "ingrediente" for p in d["perguntas"])


def test_cmv_de_receita_apta_traz_fracao_por_linha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A interface desenha o waterfall a partir de `fracao`, sem calcular nada."""
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "d.db"))
    c = TestClient(criar_app())

    receita = {
        "nome": "Arroz simples",
        "rendimento_porcoes": 2,
        "ingredientes": [
            {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
            {"texto": "sal a gosto", "nome": "sal"},
        ],
        "modo_preparo": ["Cozinhe o arroz na panela por 20 minutos."],
    }
    # A quinta checagem do portão: sem ela dizer que gosta, nada é apto.
    assert dados(c.post("/api/gosto", json={"prato": "Arroz simples", "gosta": True}))
    # E os 20 min de fogo só cabem sabendo quanto tempo ela tem por cozinhada.
    # A tela manda o tempo por cozinhada em horas.
    uma_hora = {"valor": 1}
    assert dados(c.put("/api/perfil/restricoes/tempo_max_por_fornada_min", json=uma_hora))
    assert dados(c.post("/api/avaliar", json=receita))["pode_precificar"]

    d = dados(c.post("/api/cmv", json=receita))
    assert d["rendimento_original"] == 2
    assert d["total"]["texto"] == "R$ 2,49"
    assert d["itens_a_gosto"] == ["sal"]
    assert sum(linha["fracao"] for linha in d["linhas"]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Gosto e preço de mercado
# --------------------------------------------------------------------------- #


def test_gosto_bloqueia_o_prato(cliente: TestClient) -> None:
    d = dados(cliente.post("/api/gosto", json={"prato": "Camarão", "gosta": False}))
    assert d["bloqueia"] is True
    assert d["gosto"] == "nao_gosta"


def test_impedimento_dela_bloqueia_mesmo_gostando(cliente: TestClient) -> None:
    """Gostar de fazer e conseguir fazer não são a mesma coisa (§2.1)."""
    d = dados(
        cliente.post(
            "/api/gosto",
            json={"prato": "Bolo", "gosta": True, "impedimento": "meu forno não fecha direito"},
        )
    )
    assert d["bloqueia"] is True
    assert "forno não fecha" in d["texto"]


def test_gostar_sem_impedimento_nao_bloqueia(cliente: TestClient) -> None:
    d = dados(cliente.post("/api/gosto", json={"prato": "Bolo", "gosta": True}))
    assert d["bloqueia"] is False


def test_gosto_exige_nome_de_prato(cliente: TestClient) -> None:
    assert cliente.post("/api/gosto", json={"prato": "", "gosta": True}).status_code == 422


def test_listar_gostos(cliente: TestClient) -> None:
    cliente.post("/api/gosto", json={"prato": "Bolo", "gosta": True})
    cliente.post("/api/gosto", json={"prato": "Camarão", "gosta": False})

    lista = dados(cliente.get("/api/gostos"))["gostos"]
    assert [g["prato"] for g in lista] == ["Bolo", "Camarão"]


def test_preco_de_mercado_devolve_orcamento(cliente: TestClient) -> None:
    d = dados(cliente.post("/api/preco-mercado", json={"ingrediente": "trufa", "valor": 18.5}))
    assert d["valor"]["texto"] == "R$ 18,50"
    assert d["orcamento_restante"]["texto"] == "R$ 80,00"
    assert d["origem"] == "informado_por_ela"


def test_preco_de_mercado_recusa_origem_inventada(cliente: TestClient) -> None:
    corpo = cliente.post(
        "/api/preco-mercado",
        json={"ingrediente": "trufa", "valor": 1.0, "origem": "chutei"},
    ).json()
    assert corpo["ok"] is False
    assert corpo["categoria"] == "uso"


def test_preco_de_mercado_recusa_valor_negativo(cliente: TestClient) -> None:
    resposta = cliente.post("/api/preco-mercado", json={"ingrediente": "trufa", "valor": -1.0})
    assert resposta.status_code == 422


def test_listar_precos_de_mercado(cliente: TestClient) -> None:
    cliente.post("/api/preco-mercado", json={"ingrediente": "trufa", "valor": 18.5})
    lista = dados(cliente.get("/api/precos-mercado"))["precos"]
    assert lista[0]["ingrediente"] == "trufa"
    assert lista[0]["valor"]["valor"] == 18.5


# --------------------------------------------------------------------------- #
# Decisão dela                                                                 #
# --------------------------------------------------------------------------- #


def test_decisao_carrega_o_motivo(cliente: TestClient) -> None:
    d = dados(
        cliente.post(
            "/api/decisao",
            json={"prato": "Camarão", "decisao": "adiado", "motivo": "quero pensar no preço"},
        )
    )
    assert d["motivo"] == "quero pensar no preço"
    assert "quero pensar" in d["texto"]


def test_decisao_pela_tela_grava_o_canal(cliente: TestClient, tmp_path: Path) -> None:
    """O histórico diz "pela tela" ou "pela conversa": a API é a tela."""
    from mise.dossie import Dossie

    dados(cliente.post("/api/decisao", json={"prato": "Camarão", "decisao": "adiado"}))
    with Dossie(tmp_path / "dossie.db") as dossie:
        assert [r.canal for r in dossie.historico()] == ["tela"]


def test_decisao_inventada_e_recusada(cliente: TestClient) -> None:
    corpo = cliente.post("/api/decisao", json={"prato": "Bolo", "decisao": "talvez"}).json()
    assert corpo["ok"] is False
    assert corpo["categoria"] == "uso"


def test_decisao_exige_nome_de_prato(cliente: TestClient) -> None:
    assert cliente.post("/api/decisao", json={"prato": "", "decisao": "aceito"}).status_code == 422


# --------------------------------------------------------------------------- #
# Observabilidade                                                              #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _metricas_limpas():
    """Cada teste de observabilidade começa do zero.

    `REGISTRO` é global de processo, como métrica deve ser. Sem zerar entre
    testes, a taxa de erro de um teste mede o tráfego bem-sucedido dos outros,
    o que aconteceu de verdade e fez `test_resposta_de_erro_conta_como_erro`
    medir 0,2 em vez de 1,0.
    """
    from telemetria.metricas import REGISTRO

    REGISTRO.limpar()
    yield
    REGISTRO.limpar()


def test_metricas_medem_trafego_real(cliente: TestClient) -> None:
    """A primeira versão disto media zero: a instrumentação estava só no MCP.

    São **dois** pontos de entrada: o MCP, por onde o agente chama, e o HTTP,
    por onde a interface chama. Instrumentar um só deixa metade do sistema
    invisível.
    """
    for _ in range(3):
        cliente.get("/api/despensa")

    d = dados(cliente.get("/observabilidade"))
    por_rota = {s["ferramenta"]: s for s in d["series"]}

    assert "GET /api/despensa" in por_rota
    assert por_rota["GET /api/despensa"]["chamadas"] >= 3
    assert por_rota["GET /api/despensa"]["p95_ms"] >= 0


def test_resposta_de_erro_conta_como_erro(cliente: TestClient) -> None:
    cliente.post("/api/decisao", json={"prato": "", "decisao": "aceito"})  # 422

    por_rota = {s["ferramenta"]: s for s in dados(cliente.get("/observabilidade"))["series"]}
    assert por_rota["POST /api/decisao"]["taxa_de_erro"] == 1.0


def test_probe_nao_polui_a_amostra(cliente: TestClient) -> None:
    """Probe a cada dez segundos dominaria a amostra e esconderia o que importa."""
    for _ in range(5):
        cliente.get("/saude/vivo")
        cliente.get("/saude/pronto")

    nomes = {s["ferramenta"] for s in dados(cliente.get("/observabilidade"))["series"]}
    assert not any(n.endswith(("/saude/vivo", "/saude/pronto")) for n in nomes)
    assert not any("/metricas" in n or "/observabilidade" in n for n in nomes)


def test_mais_lentas_vem_ordenado(cliente: TestClient) -> None:
    cliente.get("/api/despensa")
    cliente.get("/api/visao-geral")

    d = dados(cliente.get("/observabilidade"))
    assert d["mais_lentas"]
    assert len(d["mais_lentas"]) <= 3


def test_metricas_em_formato_prometheus(cliente: TestClient) -> None:
    cliente.get("/api/despensa")

    resposta = cliente.get("/metricas")
    assert resposta.status_code == 200
    assert "text/plain" in resposta.headers["content-type"]
    assert "# TYPE sabor_ferramenta_duracao_ms summary" in resposta.text
    assert 'quantile="0.99"' in resposta.text


def test_sem_otel_nao_ha_cabecalho_de_trace(cliente: TestClient) -> None:
    """A instrumentação é no-op sem SDK, e é esse o comportamento pretendido."""
    resposta = cliente.get("/api/despensa")
    assert "X-Trace-Id" not in resposta.headers
    assert dados(cliente.get("/observabilidade"))["rastro_ativo"] is False


# --------------------------------------------------------------------------- #
# Preço e decisão só para prato aprovado
# --------------------------------------------------------------------------- #

ARROZ_COM_FRANGO: dict[str, Any] = {
    "nome": "Arroz com frango",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 40,
    "modo_preparo": ["Refogue a cebola.", "Junte o frango e o arroz e cozinhe na panela."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


@pytest.fixture
def aprovado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """Cozinha confirmada, gosto confirmado e o prato avaliado: o portão libera.

    0,5 kg de frango a R$ 14,00 + 1 kg de arroz a R$ 4,98 = R$ 11,98 ÷ 4 porções
    = R$ 2,995, que sobe para R$ 3,00 no preço.
    """
    from mise.dossie import Dossie
    from mise.perfil import Gosto, PerfilCozinha, Posse

    banco = tmp_path / "dossie.db"
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    cliente = TestClient(criar_app())
    assert dados(cliente.post("/api/avaliar", json=ARROZ_COM_FRANGO))["pode_precificar"]
    return cliente


def test_cenarios_de_preco(aprovado: TestClient) -> None:
    d = dados(aprovado.get("/api/precos", params={"prato": "Arroz com frango"}))
    assert d["cmv"]["texto"] == "R$ 3,00"
    assert d["preco_minimo"]["texto"] == "R$ 3,34"
    assert [c["preco"]["texto"] for c in d["cenarios"]] == ["R$ 7,50", "R$ 8,57", "R$ 10,00"]
    assert "÷ 0,90" in d["explicacao_da_taxa"]
    assert d["sensibilidade"]["ainda_lucrativo"] is True


def test_preco_de_prato_nao_aprovado_e_recusado(cliente: TestClient) -> None:
    corpo = cliente.get("/api/precos", params={"prato": "Lasanha"}).json()
    assert not corpo["ok"]
    assert "ainda não foi avaliado" in corpo["erro"]


def test_custo_da_tela_que_nao_bate_e_recusado(aprovado: TestClient) -> None:
    corpo = aprovado.get("/api/precos", params={"prato": "Arroz com frango", "cmv": 0.5}).json()
    assert not corpo["ok"]
    assert "não é o que a conta dá" in corpo["erro"]


def test_preco_em_alimenta_o_slider(aprovado: TestClient) -> None:
    """A interface não calcula: pergunta ao motor a cada passo do slider."""
    d = dados(aprovado.get("/api/preco-em", params={"prato": "Arroz com frango", "preco": 8.57}))
    assert d["recebe"]["texto"] == "R$ 7,71"
    assert d["lucro"]["texto"] == "R$ 4,71"
    assert d["da_prejuizo"] is False


def test_preco_abaixo_do_minimo_marca_prejuizo(aprovado: TestClient) -> None:
    d = dados(aprovado.get("/api/preco-em", params={"prato": "Arroz com frango", "preco": 3.30}))
    assert d["da_prejuizo"] is True
    assert d["lucro"]["texto"] == "-R$ 0,03"  # 0,90 × 3,30 − 3,00


def test_todo_valor_vem_com_numero_e_texto(aprovado: TestClient) -> None:
    """A interface nunca formata moeda: formatar em dois lugares é como
    pt-BR e en-US aparecem na mesma tela."""
    d = dados(aprovado.get("/api/precos", params={"prato": "Arroz com frango"}))
    for cenario in d["cenarios"]:
        for campo in ("preco", "taxa", "recebe", "lucro"):
            assert set(cenario[campo]) == {"valor", "texto"}
            assert cenario[campo]["texto"].startswith(("R$", "-R$"))


def test_aceitar_um_prato_entra_no_cardapio(aprovado: TestClient) -> None:
    d = dados(
        aprovado.post(
            "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 8.57}
        )
    )
    assert d["cardapio"] == ["Arroz com frango"]
    assert d["preco"] == "R$ 8,57"
    assert d["lucro_por_porcao"] == "R$ 4,71"


def test_aceitar_sem_preco_ou_sem_portao_e_recusado(cliente: TestClient) -> None:
    sem_portao = cliente.post(
        "/api/decisao", json={"prato": "Bolo", "decisao": "aceito", "preco": 10}
    ).json()
    assert not sem_portao["ok"]
    sem_preco = cliente.post("/api/decisao", json={"prato": "Bolo", "decisao": "aceito"}).json()
    assert "informe o preço" in sem_preco["erro"]


def test_recusar_depois_nao_apaga_o_aceite(aprovado: TestClient) -> None:
    """O log é append-only: é o que permite responder "por que entrou?" depois."""
    aprovado.post(
        "/api/decisao", json={"prato": "Arroz com frango", "decisao": "aceito", "preco": 8.57}
    )
    aprovado.post(
        "/api/decisao",
        json={"prato": "Arroz com frango", "decisao": "recusado", "motivo": "muito caro"},
    )
    d = dados(aprovado.get("/api/cardapio"))
    assert d["pratos"] == []
    assert [h["tipo"] for h in d["historico"]] == ["retirado", "aceito"]
    assert d["historico"][1]["texto_humano"] == "A senhora aceitou o arroz com frango a R$ 8,57."


def test_aceitar_recusar_e_aceitar_de_novo_pela_tela(aprovado: TestClient) -> None:
    """No terceiro passo o prato voltava a sumir do cardápio."""
    for corpo in (
        {"decisao": "aceito", "preco": 8.57},
        {"decisao": "recusado", "motivo": "muito caro"},
        {"decisao": "aceito", "preco": 8.57},
    ):
        dados(aprovado.post("/api/decisao", json={"prato": "Arroz com frango", **corpo}))
    d = dados(aprovado.get("/api/cardapio"))
    assert [p["prato"] for p in d["pratos"]] == ["Arroz com frango"]
    assert [h["tipo"] for h in d["historico"]] == ["aceito", "retirado", "aceito"]


def test_reenvio_do_mesmo_clique_nao_grava_duas_vezes(aprovado: TestClient) -> None:
    """O reenvio que chega atrasado não desfaz o que ela decidiu depois."""
    aceite = {"prato": "Arroz com frango", "decisao": "aceito", "preco": 8.57}
    clique = {"Idempotency-Key": "clique-7"}
    dados(aprovado.post("/api/decisao", json=aceite, headers=clique))
    recusa = {"prato": "Arroz com frango", "decisao": "recusado", "chave": "clique-8"}
    dados(aprovado.post("/api/decisao", json=recusa))
    dados(aprovado.post("/api/decisao", json=aceite, headers=clique))
    d = dados(aprovado.get("/api/cardapio"))
    assert d["pratos"] == []
    assert len(d["historico"]) == 2


def test_chave_de_idempotencia_grande_demais_e_recusada(aprovado: TestClient) -> None:
    corpo = {"prato": "Arroz com frango", "decisao": "adiado"}
    comprida = "x" * 201
    resposta = aprovado.post("/api/decisao", json=corpo, headers={"Idempotency-Key": comprida})
    assert resposta.status_code == 422
    assert aprovado.post("/api/decisao", json={**corpo, "chave": comprida}).status_code == 422


COM_MILHO: dict[str, Any] = {
    **ARROZ_COM_FRANGO,
    "nome": "Frango com milho",
    "ingredientes": [
        *ARROZ_COM_FRANGO["ingredientes"],
        {"texto": "1 lata de milho", "nome": "milho verde", "quantidade": 1, "medida": "lata"},
    ],
}

COMPRA_DO_MILHO: dict[str, Any] = {
    "prato": "Frango com milho",
    "ingrediente": "milho verde",
    "quantidade": 1,
    "unidade": "lata",
    "valor": 6,
}


@pytest.fixture
def falta_o_milho(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """Cozinha e gosto confirmados; o prato só precisa comprar a lata de milho."""
    from mise.dossie import Dossie
    from mise.perfil import Gosto, PerfilCozinha, Posse

    banco = tmp_path / "dossie.db"
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Frango com milho", Gosto.GOSTA)
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    cliente = TestClient(criar_app())
    assert dados(cliente.post("/api/avaliar", json=COM_MILHO))["falta_comprar"]
    return cliente


def test_reenvio_da_compra_com_a_mesma_chave_nao_desconta_duas_vezes(
    falta_o_milho: TestClient, tmp_path: Path
) -> None:
    """A rede repete o clique; a lata já deixou de faltar, e o reenvio não vira erro."""
    from mise.dossie import Dossie

    clique = {"Idempotency-Key": "clique-1"}
    primeira = dados(falta_o_milho.post("/api/compra", json=COMPRA_DO_MILHO, headers=clique))
    reenvio = dados(falta_o_milho.post("/api/compra", json=COMPRA_DO_MILHO, headers=clique))
    assert reenvio == primeira
    assert primeira["orcamento_restante"]["texto"] == "R$ 74,00"
    assert dados(falta_o_milho.get("/api/orcamento"))["gasto"]["texto"] == "R$ 6,00"
    with Dossie(tmp_path / "dossie.db") as dossie, dossie.cursor() as cur:
        assert [linha["canal"] for linha in cur.execute("SELECT canal FROM gastos")] == ["tela"]


def test_chave_da_compra_tambem_vale_no_corpo(falta_o_milho: TestClient) -> None:
    compra = {**COMPRA_DO_MILHO, "chave": "clique-9"}
    dados(falta_o_milho.post("/api/compra", json=compra))
    dados(falta_o_milho.post("/api/compra", json=compra))
    assert dados(falta_o_milho.get("/api/orcamento"))["gasto"]["texto"] == "R$ 6,00"


def test_compra_repetida_sem_chave_nao_desconta_de_novo(falta_o_milho: TestClient) -> None:
    """Sem chave, a segunda compra do que já não falta é recusada, e nada é descontado."""
    dados(falta_o_milho.post("/api/compra", json=COMPRA_DO_MILHO))
    repetida = falta_o_milho.post("/api/compra", json=COMPRA_DO_MILHO).json()
    assert not repetida["ok"], "o milho já não falta: o portão recusa a segunda"
    assert dados(falta_o_milho.get("/api/orcamento"))["gasto"]["texto"] == "R$ 6,00"


# --------------------------------------------------------------------------- #
# O que a tela precisa para responder o portão e comparar receitas
# --------------------------------------------------------------------------- #


def test_resposta_do_portao_pela_tela(cliente: TestClient) -> None:
    def forno() -> dict[str, Any]:
        equipamentos = dados(cliente.get("/api/perfil"))["equipamentos"]
        item: dict[str, Any] = next(e for e in equipamentos if e["id"] == "forno")
        return item

    d = dados(
        cliente.post(
            "/api/resposta", json={"tipo": "equipamento", "campo": "forno", "resposta": "não"}
        )
    )
    assert d["registrado"] is True
    assert forno()["estado"] == "nao_tem"

    # "Não sei" é resposta: apaga o "não tenho" e o forno volta a ser perguntado.
    nao_sei = dados(
        cliente.post(
            "/api/resposta", json={"tipo": "equipamento", "campo": "forno", "resposta": "não sei"}
        )
    )
    assert nao_sei["nao_sei"] is True
    assert (forno()["estado"], forno()["nao_sei"], forno()["atualizado_por"]) == (
        "desconhecido",
        True,
        "tela",
    )

    recusada = cliente.post(
        "/api/resposta", json={"tipo": "equipamento", "campo": "forno", "resposta": "talvez"}
    ).json()
    assert not recusada["ok"]
    assert recusada["categoria"] == "uso"


def test_candidatas_lado_a_lado(aprovado: TestClient) -> None:
    d = dados(aprovado.get("/api/candidatas"))
    (candidata,) = d["candidatas"]
    assert candidata["prato"] == "Arroz com frango"
    assert candidata["usa_do_estoque_dela"]["texto"] == "R$ 11,98"
    assert candidata["falta_comprar"] == []


def test_receita_da_web_recusa_endereco_interno(cliente: TestClient) -> None:
    corpo = cliente.post(
        "/api/receita-da-web", json={"url": "http://127.0.0.1:8777/api/despensa"}
    ).json()
    assert not corpo["ok"]
    assert "não busco esse endereço" in corpo["erro"]


def test_receita_da_web_traz_e_guarda_a_candidata(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from retrieval import busca

    pagina = (
        '<script type="application/ld+json">{"@type":"Recipe","name":"Arroz da web",'
        '"recipeYield":"4","recipeIngredient":["1 kg de arroz"],'
        '"recipeInstructions":["Cozinhe na panela."]}</script>'
    )
    monkeypatch.setattr(busca, "baixar", lambda url, *_a, **_k: pagina)
    d = dados(
        cliente.post(
            "/api/receita-da-web",
            json={"url": "https://www.exemplo.com.br/arroz", "fonte": "Exemplo"},
        )
    )
    assert d["receita"]["nome"] == "Arroz da web"
    # A fonte é a que a página diz de si (aqui, o domínio), não a que veio no pedido.
    assert d["procedencia"]["fonte"] == "exemplo.com.br"
    assert d["receita"]["origem"] == "web"
    assert "Arroz da web" in cliente.app.state.sessao.candidatas
    catalogo = dados(cliente.get(f"/api/receitas/{d['receita_id']}"))
    assert (catalogo["origem"], catalogo["fonte"]["site"]) == ("url_dela", "exemplo.com.br")


def test_receita_guardada_abre_a_tela_preenchida(aprovado: TestClient) -> None:
    d = dados(aprovado.get("/api/receita", params={"prato": "arroz com FRANGO"}))
    assert d["nome"] == "Arroz com frango"
    assert [i["texto"] for i in d["ingredientes"]][:1] == ["500 g de frango"]
    ausente = aprovado.get("/api/receita", params={"prato": "Lasanha"}).json()
    assert not ausente["ok"]
