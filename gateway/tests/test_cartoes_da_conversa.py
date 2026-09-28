"""Os cards e os botões da conversa: dados do motor, rota concreta, e só o que existe."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from mise.mcp_server import Sessao
from mise.perfil import Gosto

from gateway.acoes_da_conversa import (
    EXECUTORES,
    AcaoInvalida,
    ResultadoDaAcao,
    executar,
    sem_dinheiro,
)
from gateway.cartoes import Cartao, cartao_para
from gateway.cartoes_da_conversa import (
    MontadorDeCartoes,
    RefResolvida,
    dados_iguais,
    gerado_texto,
    id_do_ingrediente,
    opcoes_da_pergunta,
    slug,
    slug_da_receita,
    sugestoes_para,
    url_canonica,
)

AGORA = datetime(2026, 9, 25, 17, 30, tzinfo=UTC)
BOLO_DA_WEB = sessao_de_teste.BOLO_DA_WEB


def _sessao(tmp_path: Path, *, aprovada: bool = True) -> Sessao:
    return sessao_de_teste.sessao_com_receitas(tmp_path, aprovada=aprovada)


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    return _sessao(tmp_path)


Respostas = dict[str, tuple[int, Any]]


def _buscar(respostas: Respostas, pedidos: list[str]) -> Callable[[str], Any]:
    async def buscar(rota: str) -> tuple[int, Any]:
        pedidos.append(rota)
        return respostas.get(rota, (404, {"detail": "Not Found"}))

    return buscar


def _montador(
    sessao: Sessao, respostas: Respostas | None = None
) -> tuple[MontadorDeCartoes, list[str]]:
    pedidos: list[str] = []
    buscar = _buscar(respostas, pedidos) if respostas is not None else None
    return MontadorDeCartoes(sessao, buscar, lambda: AGORA), pedidos


def _cartao(ferramenta: str, args: dict[str, Any] | None = None) -> Cartao:
    cartao = cartao_para(ferramenta, args or {})
    assert cartao is not None, ferramenta
    return cartao


# --------------------------------------------------------------------------- #
# Ids do contrato                                                              #
# --------------------------------------------------------------------------- #


def test_slug_como_o_contrato() -> None:
    assert slug("Óleo de soja") == "oleo-de-soja"
    assert slug("Arroz branco tipo 1") == "arroz-branco-tipo-1"
    assert slug("  Pão   francês! ") == "pao-frances"


def test_url_canonica_e_slug_da_receita(sessao: Sessao) -> None:
    assert url_canonica("https://WWW.TudoGostoso.com.br/receita/1-a/?utm=1#x") == (
        "tudogostoso.com.br/receita/1-a"
    )
    bolo = sessao.dossie.candidata("Bolo de fubá")
    arroz = sessao.dossie.candidata("Arroz com frango")
    assert bolo is not None and arroz is not None
    esperado = hashlib.sha256(b"tudogostoso.com.br/receita/123-bolo-de-fuba").hexdigest()[:16]
    assert slug_da_receita(bolo) == esperado
    assert slug_da_receita(arroz) == "arroz-com-frango"


def test_id_do_ingrediente_usa_o_id_da_despensa_quando_houver(sessao: Sessao) -> None:
    item = sessao.despensa.get("Alcaparras")
    assert item is not None
    assert id_do_ingrediente(item) == "alcaparras"

    class ComId:
        id = "item-1a2b3c4d"
        nome = "Coentro"

    assert id_do_ingrediente(ComId()) == "item-1a2b3c4d"  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# A rota concreta                                                              #
# --------------------------------------------------------------------------- #


def test_receita_pelo_nome_vira_a_rota_do_slug(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    ref = montador.resolver(_cartao("avaliar_receita", {"receita": {"nome": "arroz com FRANGO"}}))
    assert ref == RefResolvida(
        "viabilidade",
        "/api/receitas/arroz-com-frango",
        {"slug": "arroz-com-frango", "prato": "Arroz com frango"},
        receita="Arroz com frango",
    )
    assert ref.chave == "viabilidade /api/receitas/arroz-com-frango"


def test_receita_pelo_endereco(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    ref = montador.resolver(
        _cartao(
            "buscar_receita_na_web", {"url": "http://tudogostoso.com.br/receita/123-bolo-de-fuba"}
        )
    )
    assert ref is not None and ref.receita == "Bolo de fubá"
    assert ref.rota == f"/api/receitas/{ref.parametros['slug']}"


def test_receita_que_nao_existe_nao_vira_card(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    assert montador.resolver(_cartao("avaliar_receita", {"receita": {"nome": "Lasanha"}})) is None
    assert montador.resolver(_cartao("buscar_receita_na_web", {"url": "https://x.com/y"})) is None
    assert montador.resolver(_cartao("avaliar_receita", {"receita_id": "lasanha"})) is None
    assert montador.resolver(_cartao("cenarios_preco", {"receita_id": "lasanha"})) is None
    id_que_nao_e_texto: Cartao = {
        "tipo_cartao": "viabilidade",
        "ref": {"rota": "/api/receitas/{slug}", "parametros": {"receita_id": 7.0}},
    }
    assert montador.resolver(id_que_nao_e_texto) is None


def test_receita_pelo_id_que_as_ferramentas_devolvem(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    bolo = sessao.dossie.candidata("Bolo de fubá")
    assert bolo is not None
    ref = montador.resolver(_cartao("calcular_cmv", {"receita_id": slug_da_receita(bolo)}))
    assert ref is not None and ref.receita == "Bolo de fubá"
    assert ref.rota == f"/api/receitas/{slug_da_receita(bolo)}/custo"
    avaliacao = montador.resolver(
        _cartao("registrar_avaliacao_da_receita", {"receita_id": "arroz-com-frango"})
    )
    assert avaliacao == RefResolvida(
        "avaliacao_da_receita",
        "/api/receitas/arroz-com-frango/avaliacao",
        {"slug": "arroz-com-frango", "prato": "Arroz com frango"},
        receita="Arroz com frango",
    )


def test_nas_rotas_de_preco_o_id_vira_o_nome_e_vale_mais_que_ele(sessao: Sessao) -> None:
    """As rotas de preço de hoje recebem o prato; o id vale mais que o nome, como na ferramenta."""
    montador, _ = _montador(sessao)
    ref = montador.resolver(
        _cartao(
            "testar_sensibilidade",
            {"receita_id": "arroz-com-frango", "prato": "Bolo de fubá", "preco": 18},
        )
    )
    assert ref is not None
    assert ref.rota == "/api/preco-em?prato=Arroz%20com%20frango&preco=18.0"
    assert ref.parametros == {"prato": "Arroz com frango", "preco": 18.0}
    assert ref.receita == "Arroz com frango"
    avaliar = montador.resolver(
        _cartao("avaliar_receita", {"receita_id": "outra", "receita": {"nome": "Bolo de fubá"}})
    )
    assert avaliar is not None and avaliar.receita == "Bolo de fubá", "a receita inteira vale mais"


def test_as_fontes_do_conhecimento_viram_chips_com_a_tela(sessao: Sessao) -> None:
    montador, pedidos = _montador(sessao, {})
    cartao = _cartao("consultar_conhecimento", {"pergunta": "quanto paguei nas alcaparras?"})
    ref = montador.resolver(cartao)
    assert ref == RefResolvida("fontes", None, {"pergunta": "quanto paguei nas alcaparras?"})
    dados = montador.dados_minimos(ref)
    assert dados is not None
    assert dados["texto"] == "De onde eu tirei isso"
    assert dados["chips"][0] == {
        "rotulo": "Alcaparras, na sua despensa",
        "rota": "/despensa/alcaparras",
    }
    assert len({(c["rotulo"], c["rota"]) for c in dados["chips"]}) == len(dados["chips"])
    assert pedidos == []


async def test_o_card_de_fontes_sai_pronto_e_o_nao_sei_nao_tem_card(sessao: Sessao) -> None:
    montador, _ = _montador(sessao, {})
    pronto = await montador.montar(
        _cartao("consultar_conhecimento", {"pergunta": "quanto paguei nas alcaparras?"}),
        cartao_id="k-1",
    )
    assert pronto is not None and pronto["tipo_cartao"] == "fontes"
    assert pronto["ref"] == {
        "rota": None,
        "parametros": {"pergunta": "quanto paguei nas alcaparras?"},
    }
    nao_sei = await montador.montar(
        _cartao("consultar_conhecimento", {"pergunta": "qual a capital da França?"}),
        cartao_id="k-2",
    )
    assert nao_sei is None
    vazia = RefResolvida("fontes", None, {"pergunta": " "})
    assert montador.dados_minimos(vazia) is None


def test_ingrediente_pelo_nome_do_casamento(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    ref = montador.resolver(_cartao("custo_unitario", {"ingrediente": "alcaparra"}))
    assert ref is not None
    assert ref.rota == "/api/despensa/itens/alcaparras"
    assert ref.parametros == {"id": "alcaparras", "ingrediente": "Alcaparras"}
    assert montador.resolver(_cartao("custo_unitario", {"ingrediente": "caviar beluga"})) is None
    pelo_id = montador.resolver(
        _cartao("atualizar_despensa", {"ingrediente": "carne-moida-patinho"})
    )
    assert pelo_id is not None and pelo_id.rota == "/api/despensa/itens/carne-moida-patinho"
    vazio: Cartao = {
        "tipo_cartao": "ingrediente",
        "ref": {"rota": "/api/despensa/itens/{id}", "parametros": {}},
    }
    assert montador.resolver(vazio) is None


def test_rota_sem_marcador_leva_os_parametros_na_consulta(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    ref = montador.resolver(
        _cartao("testar_sensibilidade", {"prato": "arroz com frango", "preco": 18})
    )
    assert ref is not None
    assert ref.rota == "/api/preco-em?prato=Arroz%20com%20frango&preco=18.0"
    assert ref.receita == "Arroz com frango"
    sem_receita = montador.resolver(_cartao("registrar_decisao", {"prato": "Pastel"}))
    assert sem_receita is not None and sem_receita.rota == "/api/cardapio?prato=Pastel"
    assert montador.resolver(_cartao("consultar_orcamento")) == RefResolvida(
        "orcamento", "/api/orcamento", {}
    )


def test_pergunta_nao_tem_rota(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    ref = montador.resolver(_cartao("proxima_pergunta"))
    assert ref == RefResolvida("pergunta", None, {})
    assert ref.chave == "pergunta"


# --------------------------------------------------------------------------- #
# Os dados                                                                     #
# --------------------------------------------------------------------------- #


async def test_rota_que_existe_da_os_dados(sessao: Sessao) -> None:
    orcamento = {"inicial": {"texto": "R$ 80,00"}}
    montador, pedidos = _montador(
        sessao, {"/api/orcamento": (200, {"ok": True, "dados": orcamento})}
    )
    pronto = await montador.montar(_cartao("consultar_orcamento"), cartao_id="k-1")
    assert pronto == {
        "cartao_id": "k-1",
        "tipo_cartao": "orcamento",
        "ref": {"rota": "/api/orcamento", "parametros": {}},
        "dados": orcamento,
        "gerado": AGORA.isoformat(),
    }
    assert pedidos == ["/api/orcamento"]


@pytest.mark.parametrize(
    "resposta",
    [
        (200, {"ok": False, "erro": "o portão não liberou"}),
        (404, {"ok": False, "categoria": "ausente"}),
        (500, None),
    ],
)
async def test_rota_que_recusa_nao_vira_card(sessao: Sessao, resposta: tuple[int, Any]) -> None:
    montador, _ = _montador(sessao, {"/api/orcamento": resposta})
    assert await montador.montar(_cartao("consultar_orcamento"), cartao_id="k-1") is None


async def test_rota_que_ainda_nao_existe_da_dados_minimos(sessao: Sessao) -> None:
    montador, pedidos = _montador(sessao, {})
    pronto = await montador.montar(_cartao("diagnostico_despensa"), cartao_id="k-2")
    assert pronto is not None
    assert pedidos == ["/api/visao-geral"]
    dados = pronto["dados"]
    assert dados["kpis"]["despensa"]["total"] == {"valor": 663.39, "texto": "R$ 663,39"}
    assert dados["kpis"]["despensa"]["texto"] == "37 ingredientes"
    maiores = dados["dinheiro_parado"]["itens"]
    assert [i["id"] for i in maiores] == [
        "alcaparras",
        "cobertura-de-chocolate",
        "carne-moida-patinho",
    ]
    assert maiores[0]["fracao_texto"] == "12%"
    assert maiores[0]["rota"] == "/despensa/alcaparras"
    # O peso da cobertura vem estimado, com a fonte: nenhuma pergunta da despensa.
    assert dados["pendencias"] == []


async def test_card_do_ingrediente_vem_da_rota_do_item(sessao: Sessao) -> None:
    """A rota do item existe (despensa editável): o card tem a forma dela, e sem ela não há card."""
    item = {"id": "alcaparras", "nome": "Alcaparras", "pago": None, "custo_unitario": None}
    montador, pedidos = _montador(
        sessao, {"/api/despensa/itens/alcaparras": (200, {"ok": True, "dados": item})}
    )
    cartao = _cartao("custo_unitario", {"ingrediente": "Alcaparras"})
    pronto = await montador.montar(cartao, cartao_id="k")
    assert pronto is not None and pronto["dados"] == item
    assert pedidos == ["/api/despensa/itens/alcaparras"]
    sem_rota, _ = _montador(sessao)
    assert await sem_rota.montar(cartao, cartao_id="k") is None


async def test_dados_minimos_da_receita_e_da_viabilidade(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    bolo = await montador.montar(
        _cartao("buscar_receita_na_web", {"url": BOLO_DA_WEB["url"]}), cartao_id="k"
    )
    assert bolo is not None
    assert bolo["dados"]["nome"] == "Bolo de fubá"
    assert bolo["dados"]["fonte"] == {
        "site": "TudoGostoso",
        "url": BOLO_DA_WEB["url"],
        "autor": None,
    }
    assert bolo["dados"]["origem"] == "conversa"
    assert bolo["dados"]["rendimento_texto"] == "8 porções"
    assert bolo["dados"]["tempo_texto"] is None
    assert set(bolo["dados"]) == set(_contrato("receita.json"))
    arroz = await montador.montar(
        _cartao("avaliar_receita", {"receita": {"nome": "Arroz com frango"}}), cartao_id="k"
    )
    assert arroz is not None
    dados = arroz["dados"]
    assert (dados["veredito"], dados["veredito_rotulo"], dados["pode_precificar"]) == (
        "APTO",
        "Dá pra fazer",
        True,
    )
    assert dados["resumo"] == "Arroz com frango: dá pra fazer hoje, com o que a senhora tem"
    assert dados["falta_comprar"] == {
        "itens": [],
        "custo": {"valor": 0.0, "texto": "R$ 0,00"},
        "cabe_no_orcamento": True,
        "texto": "nada a comprar",
    }
    assert dados["veredito_da_cozinha"]["codigo"] == "com_o_que_tem"
    assert dados["rota"] == "/receitas/arroz-com-frango"


def test_card_da_receita_mostra_o_tempo_que_a_receita_declara(sessao: Sessao) -> None:
    """O tempo do cartão é o que a receita diz levar: aqui, os 40 min de cozimento."""
    montador, _ = _montador(sessao)
    ref = RefResolvida("receita", "/api/receitas/x", {}, receita="Arroz com frango")
    dados = montador.dados_minimos(ref)
    assert dados is not None
    assert dados["tempo_texto"] == "40 min"


def test_viabilidade_traz_os_avisos(tmp_path: Path) -> None:
    """Com uma boca só, a receita de duas panelas continua dando, e o card diz o porquê do tempo."""
    from mise.dossie import Dossie
    from mise.mcp_server import ReceitaEntrada

    sessao = _sessao(tmp_path)
    with Dossie(tmp_path / "dossie.db") as dossie:
        dossie.salvar_perfil(dossie.carregar_perfil().com_restricao("bocas_fogao", 1))
        dossie.registrar_gosto("Arroz e feijão", Gosto.GOSTA)
    sessao.guardar(
        ReceitaEntrada(
            nome="Arroz e feijão",
            rendimento_porcoes=2,
            modo_preparo=[
                "Cozinhe o feijão na panela por 20 minutos.",
                "Em outra panela, refogue o arroz por 15 minutos.",
            ],
            ingredientes=[
                {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"}
            ],
        ).para_dominio()
    )
    montador, _ = _montador(sessao)
    ref = RefResolvida("viabilidade", "/api/receitas/x", {}, receita="Arroz e feijão")
    dados = montador.dados_minimos(ref)
    assert dados is not None
    assert dados["veredito"] == "APTO"
    assert dados["avisos"] == [
        {
            "tipo": "bocas",
            "texto": "O passo 2 pede outra panela no fogo ao mesmo tempo. Com uma boca, a "
            "senhora faz uma parte depois da outra e leva mais tempo.",
        }
    ]
    arroz = montador.dados_minimos(
        RefResolvida("viabilidade", "/api/receitas/x", {}, receita="Arroz com frango")
    )
    assert arroz is not None
    assert arroz["avisos"] == []


async def test_viabilidade_com_o_que_falta_comprar(tmp_path: Path) -> None:
    montador, _ = _montador(_sessao(tmp_path, aprovada=False))
    bolo = await montador.montar(
        _cartao("avaliar_receita", {"receita": {"nome": "Bolo de fubá"}}), cartao_id="k"
    )
    assert bolo is not None
    dados = bolo["dados"]
    assert dados["veredito"] in {"FALTA INFO", "BLOQUEADO", "APTO COM COMPRA"}
    assert dados["perguntas"], "sem a cozinha confirmada, há o que perguntar"
    assert "coco" in dados["falta_comprar"]["itens"][0]["nome"].lower()


async def test_comparacao_so_mostra_o_que_ela_consegue_fazer(sessao: Sessao) -> None:
    """A aba `pode_fazer` da grade: o bolo sai comprando o coco pelo preço de referência."""
    montador, _ = _montador(sessao)
    comparacao = await montador.montar(_cartao("comparar_candidatas"), cartao_id="k")
    assert comparacao is not None
    assert comparacao["ref"]["rota"] == "/api/receitas?aba=pode_fazer"
    itens = comparacao["dados"]["itens"]
    assert {i["nome"] for i in itens} == {"Arroz com frango", "Bolo de fubá"}
    arroz = next(i for i in itens if i["nome"] == "Arroz com frango")
    assert comparacao["dados"]["aba"] == "pode_fazer"
    assert (arroz["nome"], arroz["selo"], arroz["site"]) == (
        "Arroz com frango",
        {"codigo": "com_o_que_tem", "texto": "Com o que a senhora tem"},
        None,
    )
    assert (arroz["usa_texto"], arroz["falta_texto"], arroz["tempo_texto"]) == (
        "usa 2 de 2 ingredientes que a senhora tem",
        "nada a comprar",
        "40 min",
    )
    assert arroz["rota"] == "/receitas/arroz-com-frango"


async def test_comparacao_com_o_que_falta_comprar(sessao: Sessao) -> None:
    sessao.dossie.registrar_gosto("Bolo de fubá", Gosto.GOSTA)
    sessao.cotar("coco ralado", 5.5, 100, "g")
    montador, _ = _montador(sessao)
    comparacao = await montador.montar(_cartao("comparar_candidatas"), cartao_id="k")
    assert comparacao is not None
    arroz, bolo = comparacao["dados"]["itens"]
    assert arroz["nome"] == "Arroz com frango", "menos compra primeiro"
    assert (bolo["nome"], bolo["site"]) == ("Bolo de fubá", "TudoGostoso")
    assert bolo["selo"]["codigo"] == "comprando"
    assert bolo["selo"]["texto"].startswith("Comprando R$ ")
    assert bolo["selo"]["texto"].endswith("cabe nos R$ 80,00")
    assert bolo["falta_texto"] == "falta comprar coco ralado"


async def test_custo_da_porcao(sessao: Sessao) -> None:
    montador, _ = _montador(sessao)
    custo = await montador.montar(
        _cartao("calcular_cmv", {"receita": {"nome": "Arroz com frango"}}), cartao_id="k"
    )
    assert custo is not None
    assert custo["dados"]["total"] == {"valor": 3.0, "texto": "R$ 3,00"}
    assert custo["dados"]["itens_a_gosto"] == ["sal"]
    assert len(custo["dados"]["linhas"]) == 2


async def test_custo_de_prato_que_o_portao_nao_liberou_nao_vira_card(tmp_path: Path) -> None:
    montador, _ = _montador(_sessao(tmp_path, aprovada=False))
    custo = await montador.montar(
        _cartao("calcular_cmv", {"receita": {"nome": "Bolo de fubá"}}), cartao_id="k"
    )
    assert custo is None


async def test_card_de_prato_sem_receita_em_avaliacao(sessao: Sessao) -> None:
    montador, _ = _montador(sessao, {})
    ref = RefResolvida("custo_porcao", "/api/receitas/pastel/custo", {"prato": "Pastel"})
    assert await montador.montar_resolvido(ref, cartao_id="k") is None
    ref = RefResolvida("viabilidade", "/api/receitas/x", {"prato": "Pastel"}, receita="Pastel")
    assert await montador.montar_resolvido(ref, cartao_id="k") is None
    ref = RefResolvida("receita", "/api/receitas/x", {}, receita="Pastel")
    assert await montador.montar_resolvido(ref, cartao_id="k") is None
    ref = RefResolvida("ingrediente", "/api/despensa/itens/x", {}, ingrediente="Caviar")
    assert await montador.montar_resolvido(ref, cartao_id="k") is None


async def test_tipo_sem_dados_minimos_nao_vira_card(sessao: Sessao) -> None:
    montador, _ = _montador(sessao, {})
    ref = RefResolvida("cenarios", "/api/precos?prato=X", {"prato": "X"})
    assert await montador.montar_resolvido(ref, cartao_id="k") is None


async def test_erro_ao_montar_dados_nao_derruba_o_turno(
    sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    montador, _ = _montador(sessao)

    def quebra(*_: Any) -> Any:
        raise RuntimeError("banco sumiu")

    monkeypatch.setattr(type(sessao.dossie), "orcamento", quebra)
    assert montador.dados_minimos(RefResolvida("comparacao", None, {})) is None


async def test_pergunta_da_vez_com_as_opcoes(tmp_path: Path) -> None:
    montador, _ = _montador(_sessao(tmp_path, aprovada=False))
    pronto = await montador.montar(_cartao("proxima_pergunta"), cartao_id="k")
    assert pronto is not None
    dados = pronto["dados"]
    assert dados["ha_pergunta"] is True and dados["pergunta"]
    assert dados["opcoes"] == opcoes_da_pergunta(dados["tipo"], dados["campo"])
    assert pronto["ref"] == {"rota": None, "parametros": {}}


async def test_sem_pergunta_nao_ha_card(sessao: Sessao, monkeypatch: pytest.MonkeyPatch) -> None:
    from mise import elicitacao

    montador, _ = _montador(sessao)
    monkeypatch.setattr(elicitacao, "montar_plano", lambda *_, **__: elicitacao.PlanoDeElicitacao())
    assert await montador.montar(_cartao("proxima_pergunta"), cartao_id="k") is None


def test_gerado_texto_e_dados_iguais() -> None:
    assert gerado_texto("orcamento", "hoje, 14:32") == "conta de hoje, 14:32"
    assert gerado_texto("receita", "hoje, 14:32") == "hoje, 14:32"
    assert dados_iguais({"a": 1, "b": [1]}, {"b": [1], "a": 1})
    assert not dados_iguais({"a": 1}, {"a": 2})


# --------------------------------------------------------------------------- #
# Opções e sugestões                                                           #
# --------------------------------------------------------------------------- #


def test_opcoes_de_equipamento_tecnica_gas_e_gosto() -> None:
    forno = opcoes_da_pergunta("equipamento", "forno")
    assert [o["rotulo"] for o in forno] == ["Tenho", "Não tenho", "Não sei"]
    assert forno[0]["texto"] == "Tenho forno."
    assert forno[0]["acao"] == {
        "tipo": "responder",
        "tipo_pergunta": "equipamento",
        "campo": "forno",
        "resposta": "sim",
    }
    assert "acao" not in forno[2], "não sei não se grava como não tem"
    tecnica = opcoes_da_pergunta("tecnica", "bechamel")
    assert tecnica[0]["rotulo"] == "Sei fazer" and tecnica[1]["acao"]["resposta"] == "nao"
    gas = opcoes_da_pergunta("operacional", "tem_gas_sobrando")
    assert [o["rotulo"] for o in gas] == ["Sim", "Não", "Não sei"]
    gosto = opcoes_da_pergunta("gosto", "Arroz com frango")
    assert gosto[0]["texto"] == "Gosto de fazer arroz com frango."
    assert gosto[1]["acao"]["resposta"] == "nao_gosta"
    assert opcoes_da_pergunta("operacional", "bocas_fogao") == [], "número: a tela pede o número"
    assert opcoes_da_pergunta("equipamento", "teletransporte") == []
    assert opcoes_da_pergunta("ingrediente", "Coentro") == []


def _com(tipo: str, dados: dict[str, Any] | None = None, **parametros: Any) -> dict[str, Any]:
    return {
        "tipo_cartao": tipo,
        "dados": dados or {},
        "ref": {"rota": None, "parametros": parametros},
    }


def test_sugestoes_depois_de_cada_card() -> None:
    assert sugestoes_para(None) == []
    assert sugestoes_para(_com("pergunta", {"opcoes": [{"rotulo": "Tenho"}, "lixo"]})) == [
        {"rotulo": "Tenho"}
    ]
    ponto = sugestoes_para(_com("ponto_de_preco", prato="Arroz com frango", preco=18.0))
    assert ponto[0]["acao"] == {
        "tipo": "decidir",
        "prato": "Arroz com frango",
        "decisao": "aceito",
        "preco": 18.0,
    }
    assert [s["rotulo"] for s in sugestoes_para(_com("ponto_de_preco"))] == ["Quero outro preço"]
    assert sugestoes_para(_com("viabilidade", {"pode_precificar": True}))[0]["rotulo"] == (
        "Quanto cobrar?"
    )
    assert sugestoes_para(_com("viabilidade", {"pode_precificar": False})) == []
    assert sugestoes_para(_com("ingrediente", {"nome": "Alcaparras"}))[0]["texto"] == (
        "Que receitas usam alcaparras?"
    )
    assert [s["rotulo"] for s in sugestoes_para(_com("cenarios"))] == [
        "Quero outro preço",
        "Vou pensar",
    ]
    assert sugestoes_para(_com("cozinha_atualizada")) == []
    fixas = sugestoes_para(_com("decisao"))
    fixas[0]["rotulo"] = "mudado"
    assert sugestoes_para(_com("decisao"))[0]["rotulo"] == "Ver o cardápio", "cópia, não a original"
    assert sugestoes_para({"tipo_cartao": "orcamento", "dados": None, "ref": None})


# --------------------------------------------------------------------------- #
# Os botões                                                                    #
# --------------------------------------------------------------------------- #


def test_responder_a_pergunta_da_propria_receita_grava_na_receita(sessao: Sessao) -> None:
    """ "A receita pede canela. É a sua canela em pó?" respondida pelo card da conversa."""
    import json

    from mise.catalogo import OrigemNoCatalogo
    from retrieval.extrator import extrair

    pagina = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "Recipe",
                "name": "Arroz doce com canela",
                "recipeYield": "4 porções",
                "recipeIngredient": ["1 kg de arroz", "1 colher de sopa de canela"],
                "recipeInstructions": ["Cozinhe o arroz na panela por 20 minutos."],
            }
        )
        + "</script>"
    )
    url = "https://www.tudogostoso.com.br/receita/1-arroz-doce.html"
    receita = sessao.catalogar(extrair(pagina, url), OrigemNoCatalogo.DESCOBERTA)
    acao = {
        "tipo": "responder",
        "tipo_pergunta": "ingrediente",
        "campo": "1 colher de sopa de canela",
        "resposta": "sim",
        "receita_id": receita.slug,
    }
    feito = executar(sessao, acao, "u-r")
    assert feito.ok, feito.texto
    assert feito.texto == (
        "Anotei a resposta da senhora sobre “1 colher de sopa de canela”, na receita "
        "Arroz doce com canela."
    )
    assert feito.cartao is not None
    assert feito.cartao["tipo_cartao"] == "viabilidade"
    assert feito.cartao["ref"]["parametros"] == {"receita_id": receita.slug}
    assert "não registre de novo" in feito.nota
    guardada = sessao.catalogo.obter(receita.slug)
    assert guardada is not None
    assert [i.item_da_despensa for i in guardada.receita.ingredientes] == [None, "Canela em pó"]
    de_novo = executar(sessao, acao, "u-r2")
    assert not de_novo.ok, "a mesma resposta não muda a receita, e nada é gravado de novo"
    incompleta = executar(sessao, {**acao, "receita_id": "  "}, "u-r3")
    assert not incompleta.ok


def test_responder_equipamento_tecnica_rotina_e_gosto(sessao: Sessao) -> None:
    feito = executar(
        sessao,
        {"tipo": "responder", "tipo_pergunta": "tecnica", "campo": "bechamel", "resposta": "nao"},
        "u-1",
    )
    assert feito.ok and feito.texto.startswith("Anotei: a senhora não sabe fazer")
    assert feito.cartao is not None and feito.cartao["tipo_cartao"] == "cozinha_atualizada"
    rotina = executar(
        sessao,
        {
            "tipo": "responder",
            "tipo_pergunta": "operacional",
            "campo": "bocas_fogao",
            "resposta": "6",
        },
        "u-2",
    )
    assert rotina.texto == "Anotei a resposta da senhora sobre bocas fogao: 6."
    gosto = executar(
        sessao,
        {
            "tipo": "responder",
            "tipo_pergunta": "gosto",
            "campo": "Bolo de fubá",
            "resposta": "gosta",
        },
        "u-3",
    )
    assert gosto.texto == "Anotei que a senhora gosta de fazer Bolo de fubá."
    assert gosto.cartao is None and gosto.recursos == ("receitas", "atividades")
    opiniao = sessao.dossie.gosto_por("Bolo de fubá")
    assert opiniao is not None and opiniao.gosto is Gosto.GOSTA


def test_decidir_aceitar_com_preco_e_prejuizo(sessao: Sessao) -> None:
    aceito = executar(
        sessao,
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 18},
        "u-aceite",
    )
    assert aceito.ok
    assert aceito.texto == "Anotado: Arroz com frango entra no cardápio a R$ 18,00."
    assert "R$" not in aceito.nota and "18" not in aceito.nota
    barato = executar(
        sessao,
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 2},
        "u-barato",
    )
    assert barato.ok and "A decisão é da senhora." in barato.texto
    adiado = executar(
        sessao, {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "adiado"}, "u-adiar"
    )
    assert adiado.texto == "Anotado: a senhora vai pensar mais sobre Arroz com frango."
    # A mesma chave de novo devolve o mesmo registro: nada novo na trilha.
    antes = len(sessao.dossie.historico("Arroz com frango"))
    executar(
        sessao,
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 18},
        "u-aceite",
    )
    assert len(sessao.dossie.historico("Arroz com frango")) == antes


def test_vou_cobrar_da_conversa_com_a_cozinha_suposta_vira_a_pergunta(sessao: Sessao) -> None:
    """O botão do card não contorna a confirmação: ela lê a pergunta, e o agente sabe gravar."""
    # O fogão e o refogar voltam a suposto: "tem", sem ela ter dito.
    perfil = sessao.perfil
    sessao.dossie.salvar_perfil(
        replace(perfil, confirmados=perfil.confirmados - {"fogao", "refogar"})
    )
    recusa = executar(
        sessao,
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 18},
        "u-sem-cozinha",
    )
    assert recusa.ok is False
    assert recusa.texto == "Antes de aceitar, a senhora confirma que tem fogão e que sabe refogar?"
    assert "registrar_resposta(tipo='cozinha', campo='arroz-com-frango'" in recusa.nota
    assert "R$" not in recusa.nota
    assert sessao.dossie.cardapio == ()


@pytest.mark.parametrize(
    "acao",
    [
        {"tipo": "decidir", "decisao": "aceito"},
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": "18"},
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": True},
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 10**7},
        {"tipo": "responder", "tipo_pergunta": "equipamento", "campo": "forno", "resposta": ""},
        {"tipo": "responder", "tipo_pergunta": "x" * 300, "campo": "forno", "resposta": "sim"},
    ],
)
def test_acao_incompleta_nao_grava(sessao: Sessao, acao: dict[str, Any]) -> None:
    resultado = executar(sessao, acao, "u-x")
    assert resultado.ok is False
    assert resultado.texto.endswith(": o botão veio incompleto.")
    assert "nada foi gravado" in resultado.nota


def test_mensagem_do_motor_sem_jargao_chega_a_ela(sessao: Sessao) -> None:
    resultado = executar(
        sessao,
        {
            "tipo": "responder",
            "tipo_pergunta": "equipamento",
            "campo": "forno",
            "resposta": "talvez",
        },
        "u-x",
    )
    assert resultado.ok is False
    assert resultado.texto == "Não consegui registrar a resposta da senhora agora."
    decisao = executar(
        sessao, {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "talvez"}, "u-y"
    )
    assert decisao.texto == "Não consegui registrar a decisão da senhora agora."
    assert "decisao deve ser" in decisao.nota, "o agente recebe o motivo e explica"


def test_auditor_que_discorda_segura_o_aceite(sessao: Sessao) -> None:
    sessao.auditor = lambda _prato: {"confere": False, "divergencias": ["conta diferente"]}
    resultado = executar(
        sessao,
        {"tipo": "decidir", "prato": "Arroz com frango", "decisao": "aceito", "preco": 18},
        "u-auditor",
    )
    assert resultado.ok is False
    assert resultado.texto.startswith("A conta não bateu na conferência")
    assert "conferência independente recusou" in resultado.nota
    assert sessao.dossie.cardapio == ()


def test_acao_desconhecida_e_avaliar(sessao: Sessao) -> None:
    desconhecida = executar(sessao, {"tipo": "teleportar"}, "u")
    assert desconhecida.ok is False and "Não reconheci" in desconhecida.texto
    sem_id = executar(sessao, {"tipo": "avaliar", "receita": "x", "sabor": 5}, "u")
    assert sem_id.ok is False
    assert sem_id.texto == "Não consegui registrar a avaliação da receita: o botão veio incompleto."


def test_botao_de_avaliar_grava_o_gosto_e_as_estrelas(sessao: Sessao) -> None:
    acao = {
        "tipo": "avaliar",
        "receita_id": "arroz-com-frango",
        "gosta": True,
        "estrelas": {"sabor": 4, "apelo": None},
        "notas": "Servir com farofa.",
    }
    feito = executar(sessao, acao, "u")
    assert feito.ok is True
    assert feito.texto == "Anotei. Arroz com frango está em primeiro lugar no ranking da senhora."
    assert "gosta de fazer; estrelas sabor 4, apelo apagada; anotação guardada" in feito.nota
    assert feito.cartao == {
        "tipo_cartao": "avaliacao_da_receita",
        "ref": {
            "rota": "/api/receitas/{slug}/avaliacao",
            "parametros": {"receita_id": "arroz-com-frango"},
        },
    }
    assert feito.recursos == ("receitas", "avaliacoes", "atividades")
    assert sessao.avaliacoes.obter("arroz-com-frango").estrelas["sabor"] == 4
    so_o_gosto = executar(
        sessao, {"tipo": "avaliar", "receita_id": "arroz-com-frango", "gosta": None}, "u"
    )
    assert "ainda não disse se gosta" in so_o_gosto.nota
    montador, _ = _montador(sessao)
    ref = montador.resolver(feito.cartao) if feito.cartao else None
    assert ref is not None and ref.rota == "/api/receitas/arroz-com-frango/avaliacao"


@pytest.mark.parametrize(
    "acao",
    [
        {"tipo": "avaliar", "receita_id": "arroz-com-frango", "gosta": "sim"},
        {"tipo": "avaliar", "receita_id": "arroz-com-frango", "estrelas": [5]},
        {"tipo": "avaliar", "receita_id": "arroz-com-frango", "notas": 3},
    ],
)
def test_botao_de_avaliar_com_valor_errado_nao_grava(sessao: Sessao, acao: dict[str, Any]) -> None:
    feito = executar(sessao, acao, "u")
    assert feito.ok is False
    assert sessao.dossie.gosto_por("Arroz com frango") is not None  # o do dossiê de teste
    assert not sessao.avaliacoes.obter("arroz-com-frango").avaliada


def test_avaliar_entra_quando_o_executor_existir(
    sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    def avaliar(_sessao: Sessao, acao: Any, _chave: str) -> ResultadoDaAcao:
        if "sabor" not in acao:
            raise AcaoInvalida("faltou a nota de sabor")
        return ResultadoDaAcao(ok=True, texto="Anotei as estrelas.", nota="[ok]")

    monkeypatch.setitem(EXECUTORES, "avaliar", avaliar)
    assert executar(sessao, {"tipo": "avaliar", "sabor": 5}, "u").texto == "Anotei as estrelas."
    falhou = executar(sessao, {"tipo": "avaliar"}, "u")
    assert falhou.texto == "Não consegui registrar a avaliação da receita: o botão veio incompleto."
    assert "faltou a nota de sabor" in falhou.nota


def test_sem_dinheiro() -> None:
    assert sem_dinheiro("paguei R$ 12,50, US$ 3 e 6 reais") == "paguei …, … e …"


# --------------------------------------------------------------------------- #
# Os dados mínimos têm os nomes do contrato                                    #
# --------------------------------------------------------------------------- #

CONTRATOS = Path(__file__).resolve().parents[2] / "contratos" / "web"


def _contrato(arquivo: str) -> Any:
    import json

    return json.loads((CONTRATOS / arquivo).read_text(encoding="utf-8"))


def _nomes_do_contrato(nosso: Any, do_contrato: Any, onde: str) -> None:
    """Todo campo que o card manda existe no contrato, com o mesmo tipo de valor."""
    if nosso is None or do_contrato is None:
        return
    if isinstance(nosso, dict):
        assert isinstance(do_contrato, dict), onde
        for chave, valor in nosso.items():
            assert chave in do_contrato, f"{onde}.{chave} não está no contrato"
            _nomes_do_contrato(valor, do_contrato[chave], f"{onde}.{chave}")
    elif isinstance(nosso, list):
        assert isinstance(do_contrato, list), onde
        if nosso and do_contrato:
            _nomes_do_contrato(nosso[0], do_contrato[0], f"{onde}[0]")
    elif isinstance(nosso, bool) or isinstance(do_contrato, bool):
        assert isinstance(nosso, bool) and isinstance(do_contrato, bool), onde
    elif isinstance(nosso, int | float):
        assert isinstance(do_contrato, int | float), onde
    else:
        assert isinstance(do_contrato, type(nosso)), onde


async def test_dados_minimos_tem_os_nomes_do_contrato(tmp_path: Path) -> None:
    aprovada, _ = _montador(_sessao(tmp_path / "a"))
    aberta, _ = _montador(_sessao(tmp_path / "b", aprovada=False))
    receita = _contrato("receita.json")
    receita["falta_comprar"]["itens"] = [_contrato("custo.json")["ingrediente_que_falta_exemplo"]]
    casos = [
        (aprovada, _cartao("diagnostico_despensa"), _contrato("visao-geral.json")),
        (aprovada, _cartao("buscar_receita_na_web", {"url": BOLO_DA_WEB["url"]}), receita),
        (aberta, _cartao("avaliar_receita", {"receita": {"nome": "Bolo de fubá"}}), receita),
        (aprovada, _cartao("comparar_candidatas"), _contrato("receitas.json")),
        (
            aprovada,
            _cartao("calcular_cmv", {"receita": {"nome": "Arroz com frango"}}),
            _contrato("custo.json"),
        ),
    ]
    for montador, cartao, contrato in casos:
        ref = montador.resolver(cartao)
        assert ref is not None
        dados = montador.dados_minimos(ref)
        assert dados is not None, cartao["tipo_cartao"]
        _nomes_do_contrato(dados, contrato, cartao["tipo_cartao"])
