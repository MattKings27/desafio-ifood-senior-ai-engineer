"""As rotas das receitas: a grade só com o que ela consegue fazer, o detalhe, o custo e a avaliação."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.catalogo import OrigemNoCatalogo
from mise.perfil import Gosto

from gateway.conversa import resolver_contexto
from gateway.http import criar_app

CONTRATOS = Path(__file__).resolve().parents[2] / "contratos" / "web"
BOLO_URL = sessao_de_teste.BOLO_DA_WEB["url"]


def _contrato(nome: str) -> Any:
    return json.loads((CONTRATOS / nome).read_text(encoding="utf-8"))


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


def _dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert corpo["ok"], corpo
    return corpo["dados"]


def _do(itens: list[dict[str, Any]], nome: str) -> dict[str, Any]:
    """O card da grade com este nome."""
    return next(i for i in itens if i["nome"] == nome)


def _chaves_iguais(dados: dict[str, Any], contrato: dict[str, Any]) -> None:
    assert set(dados) == set(contrato)


def _bolo(cliente: TestClient) -> str:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    guardada = sessao.catalogo.por_url(BOLO_URL)
    assert guardada is not None
    slug: str = guardada.slug
    return slug


# --------------------------------------------------------------------------- #
# A grade                                                                      #
# --------------------------------------------------------------------------- #


def test_a_grade_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    lista = _dados(cliente.get("/api/receitas"))
    _chaves_iguais(lista, _contrato("receitas.json"))
    assert lista["aba"] == "pode_fazer"
    arroz = _do(lista["itens"], "Arroz com frango")
    _chaves_iguais(arroz, _contrato("receitas.json")["itens"][0])
    # O bolo sai comprando o coco ralado pelo preço de referência: nada espera resposta.
    assert lista["contagens"] == {"pode_fazer": 2, "falta_resposta": 0, "ranking": 0, "nao_quer": 0}
    assert lista["sem_preco_na_internet"] is None
    assert lista["descoberta"]["estado"] == "parada"


def test_o_que_falta_comprar_sai_pelo_preco_de_referencia_sem_pergunta(
    cliente: TestClient,
) -> None:
    """O coco ralado: a xícara pela tabela do USDA, e o preço pela página do supermercado."""
    assert _dados(cliente.get("/api/receitas", params={"aba": "falta_resposta"}))["itens"] == []
    bolo = _do(_dados(cliente.get("/api/receitas"))["itens"], "Bolo de fubá")
    assert bolo["selo"]["codigo"] == "comprando"
    assert bolo["pergunta"] is None
    assert [r["ingrediente"] for r in bolo["referencias"]] == ["coco ralado"]
    assert bolo["gosta"] is None


def test_o_card_da_grade_diz_se_ela_gosta(cliente: TestClient) -> None:
    arroz = _do(_dados(cliente.get("/api/receitas"))["itens"], "Arroz com frango")
    assert arroz["gosta"] is True
    cliente.put("/api/receitas/arroz-com-frango/avaliacao", json={"gosta": False})
    (arroz,) = _dados(cliente.get("/api/receitas", params={"aba": "nao_quer"}))["itens"]
    assert arroz["gosta"] is False


def test_mudei_de_ideia_tira_o_impedimento(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA, "não tenho panela grande")
    (arroz,) = _dados(cliente.get("/api/receitas", params={"aba": "nao_quer"}))["itens"]
    assert arroz["gosta"] is True, "gosta, mas viu um impedimento"
    resposta = _dados(cliente.put("/api/receitas/arroz-com-frango/avaliacao", json={"gosta": True}))
    assert (
        "O impedimento que a senhora tinha apontado (não tenho panela grande) não segura"
        in (resposta["texto"])
    )
    assert _dados(cliente.get("/api/receitas", params={"aba": "nao_quer"}))["itens"] == []
    arroz = _do(_dados(cliente.get("/api/receitas"))["itens"], "Arroz com frango")
    assert arroz["nome"] == "Arroz com frango"


def test_os_filtros_vao_pela_consulta(cliente: TestClient) -> None:
    def nomes(**consulta: Any) -> list[str]:
        return [i["nome"] for i in _dados(cliente.get("/api/receitas", params=consulta))["itens"]]

    assert nomes(q="FRANGO") == ["Arroz com frango"]
    assert nomes(q="bolo") == ["Bolo de fubá"]
    assert nomes(usa="peito-de-frango") == ["Arroz com frango"]
    assert nomes(tempo_max=30) == []
    assert nomes(tempo_max=40, so_com_o_que_tenho="true", ordem="tempo") == ["Arroz com frango"]
    assert nomes(nota_min=10) == []


@pytest.mark.parametrize("consulta", [{"aba": "todas"}, {"ordem": "preco"}])
def test_aba_ou_ordem_que_nao_existe_e_422(cliente: TestClient, consulta: dict[str, str]) -> None:
    resposta = cliente.get("/api/receitas", params=consulta)
    assert resposta.status_code == 422
    corpo = resposta.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")


# --------------------------------------------------------------------------- #
# O detalhe, a receita trazida e a resposta sobre a receita                    #
# --------------------------------------------------------------------------- #


def test_o_detalhe_tem_a_forma_do_contrato(cliente: TestClient) -> None:
    detalhe = _dados(cliente.get(f"/api/receitas/{_bolo(cliente)}"))
    _chaves_iguais(detalhe, _contrato("receita.json"))
    assert detalhe["fonte"]["site"] == "TudoGostoso"
    assert detalhe["origem"] == "conversa"
    linhas = {i["nome"]: i["situacao"] for i in detalhe["ingredientes"]}
    assert linhas == {"Polenta (fubá)": "tem", "coco ralado": "falta"}
    ausente = cliente.get("/api/receitas/lasanha")
    assert ausente.status_code == 404 and ausente.json()["categoria"] == "ausente"


def test_trazer_uma_receita_pelo_endereco(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from retrieval import busca

    pagina = sessao_de_teste.pagina_do_bolo().replace("Bolo de fub", "Bolo de milho de fub")
    monkeypatch.setattr(busca, "baixar", lambda *_a, **_c: pagina)
    endereco = "https://www.tudogostoso.com.br/receita/99-bolo-de-milho"
    nova = cliente.post("/api/receitas", json={"url": endereco})
    assert nova.status_code == 201
    detalhe = nova.json()["dados"]
    assert (detalhe["origem"], detalhe["fonte"]["url"]) == ("url_dela", endereco)
    de_novo = cliente.post("/api/receitas", json={"url": endereco + "/?utm=x"})
    assert de_novo.status_code == 200 and de_novo.json()["dados"]["slug"] == detalhe["slug"]
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    guardada = sessao.catalogo.obter(detalhe["slug"])
    assert guardada is not None and guardada.origem is OrigemNoCatalogo.URL_DELA
    assert detalhe["nome"] not in sessao.candidatas, "trazer não põe em avaliação"


def test_endereco_invalido_na_receita_trazida(cliente: TestClient) -> None:
    corpo = cliente.post("/api/receitas", json={"url": "file:///etc/passwd"}).json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "uso")


def test_resposta_sobre_a_receita_volta_com_o_detalhe(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    pure = sessao_de_teste.guardar_da_pagina(
        sessao,
        sessao_de_teste.pagina_do_bolo().replace('"8"', '""'),
        "https://www.tudogostoso.com.br/receita/77-bolo-sem-rendimento",
    )
    slug = sessao.catalogo.por_nome(pure.nome).slug
    detalhe = _dados(
        cliente.post(
            f"/api/receitas/{slug}/resposta", json={"campo": "rendimento_porcoes", "resposta": "8"}
        )
    )
    assert detalhe["rendimento_texto"] == "8 porções"
    assert detalhe["respostas"][0]["texto"] == "A senhora disse que rende 8 porções."
    recusada = cliente.post(
        f"/api/receitas/{slug}/resposta", json={"campo": "rendimento_porcoes", "resposta": "9"}
    ).json()
    assert (recusada["ok"], recusada["categoria"]) == (False, "uso")


# --------------------------------------------------------------------------- #
# O peso de uma linha cuja medida não se converte                              #
# --------------------------------------------------------------------------- #

PEITO = "1 peito cortado em 4 filés"
ALCAPARRAS = "2 colheres de sopa de alcaparras"


def _frango_com_alcaparras(cliente: TestClient) -> str:
    """A receita da verificação real: um peito sem peso e a colher de alcaparras."""
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    objeto = {
        "@type": "Recipe",
        "name": "Frango com alcaparras",
        "recipeYield": "2 porções",
        "recipeIngredient": [PEITO, ALCAPARRAS, "sal a gosto"],
        "recipeInstructions": [
            "Grelhe os filés na frigideira por 10 minutos e junte as alcaparras."
        ],
    }
    receita = sessao_de_teste.guardar_da_pagina(
        sessao,
        f'<script type="application/ld+json">{json.dumps(objeto)}</script>',
        "https://www.tudogostoso.com.br/receita/33527-frango-com-alcaparras.html",
    )
    sessao.dossie.registrar_gosto(receita.nome, Gosto.GOSTA)
    slug: str = sessao.catalogo.por_nome(receita.nome).slug
    return slug


def test_o_peso_de_uma_linha_pela_tela_destrava_o_custo(cliente: TestClient) -> None:
    slug = _frango_com_alcaparras(cliente)
    antes = _dados(cliente.get(f"/api/receitas/{slug}"))
    # Nenhum peso é pergunta: o peito pela tabela do IBGE, a colher de alcaparras pela do USDA.
    assert not [p for p in antes["perguntas"] if p["assunto"] == "medida"]
    referencias = {
        i["nome"]: i["medida_de_referencia"]
        for i in antes["ingredientes"]
        if i["medida_de_referencia"] is not None
    }
    assert referencias["Peito de frango"]["pergunta"]["campo"] == PEITO
    assert referencias["Alcaparras"]["pergunta"]["entrada"] == {
        "tipo": "peso",
        "unidade": "g",
        "peso_de": {"cada": "1 colher de sopa", "tudo": "2 colheres de sopa"},
    }

    rota = f"/api/receitas/{slug}/resposta"
    cliente.post(rota, json={"campo": PEITO, "resposta": "300", "por_unidade": True})
    depois = _dados(
        cliente.post(rota, json={"campo": ALCAPARRAS, "resposta": "20 g", "por_unidade": False})
    )
    assert [r["texto"] for r in depois["respostas"]] == [
        "A senhora disse que um peito de frango pesa 300 g.",
        f"A senhora disse que “{ALCAPARRAS}” pesam 20 g.",
    ]
    assert [p for p in depois["perguntas"] if p["assunto"] == "medida"] == []
    assert depois["pode_precificar"] is True
    custo = _dados(cliente.get(f"/api/receitas/{slug}/custo"))
    assert custo["total"]["texto"] == "R$ 2,51"

    recusada = cliente.post(
        rota, json={"campo": "sal a gosto", "resposta": "5 g", "por_unidade": True}
    ).json()
    assert (recusada["ok"], recusada["categoria"]) == (False, "uso")
    assert "não pede peso" in recusada["erro"]


async def test_o_peso_de_uma_linha_pela_conversa_vale_para_a_tela(cliente: TestClient) -> None:
    """O agente responde pelo `avaliar_receita` com o `receita_id`, e a tela já custeia."""
    from mise.mcp_server import construir_servidor

    slug = _frango_com_alcaparras(cliente)
    servidor = construir_servidor(cliente.app.state.sessao)  # type: ignore[attr-defined]
    resultado = await servidor.call_tool(
        "avaliar_receita",
        {
            "receita_id": slug,
            "receita": {
                "nome": "Frango com alcaparras",
                "ingredientes": [
                    {"texto": PEITO, "nome": "peito", "peso": "300 g", "por_unidade": True},
                    {"texto": ALCAPARRAS, "nome": "alcaparras", "peso": "20 g as duas"},
                ],
            },
        },
    )
    resposta = json.loads(resultado.content[0].text)
    assert "erro" not in resposta, resposta
    assert resposta["veredito"] == "APTO"
    assert "peso: um peito de frango pesa 300 g" in resposta["recado"]
    custo = _dados(cliente.get(f"/api/receitas/{slug}/custo"))
    assert custo["total"]["texto"] == "R$ 2,51"


# --------------------------------------------------------------------------- #
# O custo, a avaliação e as notas                                              #
# --------------------------------------------------------------------------- #


def test_custo_so_do_que_a_conferencia_libera(cliente: TestClient) -> None:
    custo = _dados(cliente.get("/api/receitas/arroz-com-frango/custo"))
    esperado = _contrato("custo.json")
    esperado.pop("ingrediente_que_falta_exemplo")
    esperado.pop("ingrediente_com_preco_de_referencia_exemplo")
    _chaves_iguais(custo, esperado)
    assert custo["total"] == {"valor": 3.0, "texto": "R$ 3,00"}
    recusa = cliente.get(f"/api/receitas/{_bolo(cliente)}/custo")
    assert recusa.status_code == 409
    corpo = recusa.json()
    assert (corpo["ok"], corpo["categoria"]) == (False, "regra")
    assert corpo["erro"].startswith("Ainda não calculo o custo de bolo de fubá")


def test_avaliacao_e_notas(cliente: TestClient) -> None:
    antes = _dados(cliente.get("/api/receitas/arroz-com-frango/avaliacao"))
    assert antes["texto"] == "Quando a senhora der as estrelas, arroz com frango entra no ranking."
    assert antes["atualizado_texto"].startswith("hoje, "), "o gosto que ela disse conta"
    feita = _dados(
        cliente.put(
            "/api/receitas/arroz-com-frango/avaliacao",
            json={"estrelas": {"sabor": 5, "apelo": 4}},
        )
    )
    _chaves_iguais(feita, _contrato("avaliacao-escrita.json")["resposta"])
    assert feita["avaliacao"]["gosta"] is True, "sem mandar o gosto, ele continua"
    assert feita["posicao_no_ranking"] == 1
    sem_gosto = _dados(
        cliente.put("/api/receitas/arroz-com-frango/avaliacao", json={"gosta": None})
    )
    assert sem_gosto["avaliacao"]["gosta"] is None
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    opiniao = sessao.dossie.gosto_por("Arroz com frango")
    assert opiniao is not None and opiniao.gosto is Gosto.DESCONHECIDO
    errada = cliente.put(
        "/api/receitas/arroz-com-frango/avaliacao", json={"estrelas": {"sabor": 7}}
    ).json()
    assert (errada["ok"], errada["categoria"]) == (False, "uso")
    notas = _dados(
        cliente.put("/api/receitas/arroz-com-frango/notas", json={"texto": "Com farofa."})
    )
    _chaves_iguais(notas, _contrato("notas-escrita.json")["resposta"])
    assert notas["texto"] == "Guardei a anotação."
    assert cliente.put("/api/receitas/lasanha/notas", json={"texto": "x"}).status_code == 404


def test_o_contexto_da_grade_acha_a_receita_do_catalogo(cliente: TestClient) -> None:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    with sessao.dossie.cursor() as cur:
        cur.execute("DELETE FROM candidatas")
    contexto = resolver_contexto(sessao, {"tipo": "receita", "id": _bolo(cliente)})
    assert contexto is not None and contexto["rotulo"] == "Bolo de fubá"
    pelo_nome = resolver_contexto(sessao, {"tipo": "receita", "id": "bolo de fubá"})
    assert pelo_nome is not None and pelo_nome["rotulo"] == "Bolo de fubá"
