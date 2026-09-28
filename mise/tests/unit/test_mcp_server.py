"""O servidor MCP: a fronteira entre o agente e o motor.

O teste mais importante deste arquivo é o que verifica que `calcular_cmv`
recusa receita não aprovada. Se ele cair, a garantia central do desafio caiu:
o agente conseguiria dizer um preço para um prato que a Dona Maria não
consegue cozinhar.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mise.mcp_server import (
    INSTRUCOES,
    IngredienteEntrada,
    ReceitaEntrada,
    Sessao,
    abrir_sessao,
    construir_servidor,
)
from mise.perfil import Gosto, Posse

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

RECEITA_FORNO: dict[str, Any] = {
    "nome": "Frango à parmegiana",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 50,
    "modo_preparo": ["Empane o frango e frite.", "Leve ao forno e gratine."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "200 g de mussarela", "nome": "mussarela", "quantidade": 200, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    return abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")


@pytest.fixture
def servidor(sessao: Sessao) -> Any:
    return construir_servidor(sessao)


async def chamar(servidor: Any, ferramenta: str, **argumentos: Any) -> dict[str, Any]:
    resultado = await servidor.call_tool(ferramenta, argumentos)
    return json.loads(resultado.content[0].text)


# --------------------------------------------------------------------------- #
# Registro e contrato
# --------------------------------------------------------------------------- #


async def test_ferramentas_registradas(servidor: Any) -> None:
    nomes = {t.name for t in await servidor.list_tools()}
    assert nomes == {
        "diagnostico_despensa",
        "custo_unitario",
        "converter_medida_culinaria",
        "consultar_perfil",
        "consultar_gostos",
        "registrar_gosto",
        "buscar_receita_na_web",
        "buscar_preco_na_web",
        "consultar_conhecimento",
        "consultar_precos_de_mercado",
        "registrar_preco_mercado",
        "registrar_resposta",
        "proxima_pergunta",
        "avaliar_receita",
        "comparar_candidatas",
        "calcular_cmv",
        "cenarios_preco",
        "testar_sensibilidade",
        "registrar_decisao",
        "consultar_orcamento",
        "registrar_compra",
        "consultar_cardapio",
        "consultar_planilha",
        "atualizar_despensa",
        "registrar_avaliacao_da_receita",
        "estimar_preco_preliminar",
        "pauta_de_descoberta",
    }


async def test_toda_ferramenta_tem_descricao_util(servidor: Any) -> None:
    """A descrição é o que o modelo lê para decidir se chama. Vazia = inútil."""
    for t in await servidor.list_tools():
        assert t.description and len(t.description) > 40, t.name


async def test_schema_e_derivado_da_assinatura(servidor: Any) -> None:
    """Regressão: um wrapper sem `functools.wraps` faz o schema virar args/kwargs."""
    tools = {t.name: t for t in await servidor.list_tools()}
    assert tools["diagnostico_despensa"].input_schema.get("properties", {}) == {}
    assert "ingrediente" in tools["custo_unitario"].input_schema["properties"]
    assert "receita" in tools["avaliar_receita"].input_schema["properties"]
    assert "args" not in tools["custo_unitario"].input_schema["properties"]


def test_instrucoes_orientam_o_uso() -> None:
    assert "Nunca calcule" in INSTRUCOES
    assert "avaliar_receita" in INSTRUCOES
    assert "receita_id" in INSTRUCOES


async def test_nenhuma_ferramenta_recebe_o_html_de_quem_chama(servidor: Any) -> None:
    """Receita da internet só entra pela página que o próprio servidor buscou."""
    for t in await servidor.list_tools():
        assert "html" not in t.input_schema.get("properties", {}), t.name


async def test_a_receita_vem_pelo_id_ou_inteira(servidor: Any) -> None:
    """As ferramentas de receita e de preço aceitam o id no lugar da receita ou do nome."""
    tools = {t.name: t for t in await servidor.list_tools()}
    for nome in ("avaliar_receita", "calcular_cmv", "cenarios_preco", "testar_sensibilidade"):
        propriedades = tools[nome].input_schema["properties"]
        assert "receita_id" in propriedades, nome
        assert "receita_id" not in tools[nome].input_schema.get("required", []), nome
    assert "receita" in tools["calcular_cmv"].input_schema["properties"]
    assert "prato" in tools["cenarios_preco"].input_schema["properties"]
    assert tools["testar_sensibilidade"].input_schema["required"] == ["preco"]
    assert set(tools["consultar_conhecimento"].input_schema["properties"]) == {
        "pergunta",
        "tipos",
        "k",
    }
    assert tools["registrar_avaliacao_da_receita"].input_schema["required"] == ["receita_id"]


# --------------------------------------------------------------------------- #
# Despensa
# --------------------------------------------------------------------------- #


async def test_diagnostico_traz_o_essencial(servidor: Any) -> None:
    d = await chamar(servidor, "diagnostico_despensa")
    assert d["itens"] == 37
    assert d["total_investido"]["texto"] == "R$ 663,39"
    assert len(d["itens_com_normalizacao_relevante"]) == 6
    # A embalagem sem peso vem estimada, com a fonte: nada vira pergunta.
    assert d["pendencias"] == []
    assert "R$ 80,00" in d["orcamento"]["estado"]


async def test_custo_unitario_encontrado(servidor: Any) -> None:
    d = await chamar(servidor, "custo_unitario", ingrediente="frango")
    assert d["encontrado"]
    assert d["ingrediente"] == "Peito de frango"
    assert d["custo_unitario"] == "R$ 14,00/kg"
    assert "÷" in d["derivacao"]


async def test_custo_unitario_ausente_orienta_compra(servidor: Any) -> None:
    d = await chamar(servidor, "custo_unitario", ingrediente="caviar")
    assert not d["encontrado"]
    assert "compra complementar" in d["orientacao"]


async def test_conversao_de_medida(servidor: Any) -> None:
    d = await chamar(
        servidor,
        "converter_medida_culinaria",
        quantidade=1,
        medida="xicara",
        ingrediente="farinha de trigo",
    )
    assert d["resultado"] == "0,1272 kg"
    assert d["derivacao"] == "1 xícara = 240 ml × 0,53 g/ml = 127,2 g"


async def test_conversao_sem_densidade_vira_erro_com_pergunta(servidor: Any) -> None:
    d = await chamar(
        servidor,
        "converter_medida_culinaria",
        quantidade=1,
        medida="xicara",
        ingrediente="bacalhau",
    )
    assert d["categoria"] == "dado"
    assert d["tipo"] == "DensidadeDesconhecida"


# --------------------------------------------------------------------------- #
# O portão
# --------------------------------------------------------------------------- #


async def test_portao_pede_informacao_com_perfil_zerado(servidor: Any) -> None:
    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert d["veredito"] == "FALTA INFO"
    assert not d["pode_precificar"]
    assert {p["campo"] for p in d["perguntas"]} >= {"forno", "empanar"}
    assert "NÃO calcule preço" in d["orientacao"]


async def test_portao_diz_com_que_orcamento_comparou_a_compra(servidor: Any) -> None:
    """ "Cabe nos R$ 80,00" só tem origem se o número vier na saída da ferramenta."""
    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert d["orcamento"] == {"inicial": "R$ 80,00", "gasto": "R$ 0,00", "restante": "R$ 80,00"}


async def test_portao_detecta_exigencias_do_modo_de_preparo(servidor: Any) -> None:
    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert "Forno" in d["exige"]["equipamentos"]
    assert "Empanar" in d["exige"]["tecnicas"]


async def test_cmv_recusa_sem_viabilidade(servidor: Any) -> None:
    """A garantia central. Se este teste cair, o sistema perdeu o sentido."""
    await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    d = await chamar(servidor, "calcular_cmv", receita=RECEITA_FORNO)
    assert d["categoria"] == "regra"
    assert d["tipo"] == "ViabilidadeNaoConfirmada"
    assert "não contorne" in d["orientacao"].lower()
    assert "cmv_por_porcao" not in d


async def test_cmv_recusa_quando_bloqueado(servidor: Any) -> None:
    for campo in ("forno", "air_fryer", "forno_eletrico"):
        await chamar(
            servidor, "registrar_resposta", tipo="equipamento", campo=campo, resposta="nao_tem"
        )
    avaliacao = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert avaliacao["veredito"] == "BLOQUEADO"

    cmv = await chamar(servidor, "calcular_cmv", receita=RECEITA_FORNO)
    assert cmv["tipo"] == "ViabilidadeNaoConfirmada"


async def test_substituto_destrava_sem_bloquear(servidor: Any) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="nao_tem"
    )
    await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="air_fryer", resposta="tem"
    )
    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert d["veredito"] != "BLOQUEADO"


# --------------------------------------------------------------------------- #
# Fluxo completo
# --------------------------------------------------------------------------- #


async def _liberar(servidor: Any) -> None:
    """Ela respondeu tudo (equipamento, técnica, tempo) e disse que gosta do prato."""
    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    await chamar(servidor, "registrar_resposta", tipo="tecnica", campo="empanar", resposta="tem")
    await chamar(
        servidor,
        "registrar_resposta",
        tipo="operacional",
        campo="tempo_max_por_fornada_min",
        # Ela responde em horas; o motor guarda em minutos.
        resposta="1,5 hora",
    )
    await chamar(servidor, "registrar_gosto", prato="Frango à parmegiana", gosta=True)


async def test_fluxo_da_despensa_ao_preco(servidor: Any) -> None:
    await _liberar(servidor)

    avaliacao = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert avaliacao["veredito"] == "APTO"

    cmv = await chamar(servidor, "calcular_cmv", receita=RECEITA_FORNO)
    assert cmv["rendimento_original"] == 4
    assert cmv["cmv_por_porcao"]["valor"] == pytest.approx(3.75)
    assert cmv["itens_a_gosto"] == ["sal"]
    assert all("derivacao" in linha for linha in cmv["linhas"])

    preco = await chamar(
        servidor,
        "cenarios_preco",
        cmv_por_porcao=cmv["cmv_por_porcao"]["valor"],
        prato=cmv["prato"],
    )
    assert len(preco["cenarios"]) == 3
    assert preco["preco_minimo_sem_prejuizo"]["valor"] == pytest.approx(4.17)
    assert "escolha é dela" in preco["orientacao"]
    precos = [c["preco"]["valor"] for c in preco["cenarios"]]
    assert precos == sorted(precos)


async def test_proxima_pergunta_comeca_pelo_gosto(servidor: Any) -> None:
    """Antes de qualquer coisa, se ela quer fazer o prato."""
    await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    d = await chamar(servidor, "proxima_pergunta")
    assert d["ha_pergunta"]
    assert d["tipo"] == "gosto"
    # O campo do gosto é o prato: é por ele que registrar_resposta grava.
    assert d["campo"] == "Frango à parmegiana"
    await chamar(servidor, "registrar_resposta", tipo="gosto", campo=d["campo"], resposta="gosta")
    seguinte = await chamar(servidor, "proxima_pergunta")
    assert seguinte["tipo"] != "gosto"


async def test_proxima_pergunta_prioriza(servidor: Any) -> None:
    await chamar(servidor, "registrar_gosto", prato="Frango à parmegiana", gosta=True)
    await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    d = await chamar(servidor, "proxima_pergunta")
    assert d["ha_pergunta"]
    assert d["campo"] == "forno"
    assert d["pratos_afetados"] == ["Frango à parmegiana"]


async def test_nao_gostar_bloqueia_o_prato(servidor: Any) -> None:
    """A quinta checagem bloqueia como as outras quatro."""
    await _liberar(servidor)
    await chamar(servidor, "registrar_gosto", prato="Frango à parmegiana", gosta=False)

    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert d["veredito"] == "BLOQUEADO"
    assert any("não gosta" in i["motivo"] for i in d["impedimentos"])


async def test_impedimento_dela_bloqueia_mesmo_gostando(servidor: Any) -> None:
    """Gostar de fazer e conseguir fazer não são a mesma coisa (§2.1)."""
    await _liberar(servidor)
    await chamar(
        servidor,
        "registrar_gosto",
        prato="Frango à parmegiana",
        gosta=True,
        impedimento="meu filho tem alergia a ovo e eu empano com ovo",
    )

    d = await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    assert d["veredito"] == "BLOQUEADO"
    assert any("alergia a ovo" in i["motivo"] for i in d["impedimentos"])


async def test_consultar_gostos_lista_o_que_ela_disse(servidor: Any) -> None:
    await chamar(servidor, "registrar_gosto", prato="Bolo", gosta=True)
    await chamar(servidor, "registrar_gosto", prato="Camarão", gosta=False)

    gostos = (await chamar(servidor, "consultar_gostos"))["gostos"]
    assert len(gostos) == 2
    assert any("Bolo: gosta" in g for g in gostos)
    assert any("Camarão: nao gosta" in g for g in gostos)


async def test_sem_pergunta_quando_tudo_resolvido(servidor: Any) -> None:
    await _liberar(servidor)
    await chamar(servidor, "avaliar_receita", receita=RECEITA_FORNO)
    d = await chamar(servidor, "proxima_pergunta")
    assert not d["ha_pergunta"]
    assert d["aptas"] == ["Frango à parmegiana"]


# --------------------------------------------------------------------------- #
# Perfil, decisões e orçamento
# --------------------------------------------------------------------------- #


async def test_perfil_evolui(servidor: Any) -> None:
    antes = await chamar(servidor, "consultar_perfil")
    await chamar(servidor, "registrar_resposta", tipo="equipamento", campo="forno", resposta="tem")
    depois = await chamar(servidor, "consultar_perfil")
    assert "Forno" in depois["ela_confirmou"]["tem"]
    assert depois["ainda_em_aberto"] < antes["ainda_em_aberto"]


async def test_perfil_separa_o_que_ela_disse_do_que_e_pressuposto(servidor: Any) -> None:
    """O agente disse "a senhora disse que domina fritar", e ela nunca tinha dito."""
    d = await chamar(servidor, "consultar_perfil")
    assert "Fogão" in d["pressuposto"]["tem"]
    assert "Fritar" in d["pressuposto"]["domina"]
    assert d["ela_confirmou"]["tem"] == []
    assert set(d["restricoes"]) >= {"tem_gas_sobrando", "espaco_geladeira_litros"}

    await chamar(servidor, "registrar_resposta", tipo="tecnica", campo="fritar", resposta="sim")
    d = await chamar(servidor, "consultar_perfil")
    assert "Fritar" in d["ela_confirmou"]["domina"]
    assert "Fritar" not in d["pressuposto"]["domina"]


async def test_resposta_negativa_registra_ausencia(servidor: Any) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="tecnica", campo="temperagem", resposta="nao_tem"
    )
    d = await chamar(servidor, "consultar_perfil")
    assert "Temperagem de chocolate" in d["ela_confirmou"]["nao_domina"]


async def test_restricao_operacional(servidor: Any) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="operacional", campo="bocas_fogao", resposta="4"
    )
    d = await chamar(servidor, "consultar_perfil")
    assert d["restricoes"]["bocas_fogao"] == 4


@pytest.mark.parametrize(
    ("tipo", "campo"),
    [("equipamento", "teletransportador"), ("tecnica", "alquimia"), ("operacional", "inventado")],
)
async def test_vocabulario_invalido_e_recusado(servidor: Any, tipo: str, campo: str) -> None:
    d = await chamar(servidor, "registrar_resposta", tipo=tipo, campo=campo, resposta="tem")
    assert "erro" in d or "registrado" not in d


async def test_tipo_de_resposta_invalido(servidor: Any) -> None:
    d = await chamar(servidor, "registrar_resposta", tipo="magia", campo="x", resposta="y")
    assert d["categoria"] == "uso"


async def test_decisao_invalida(servidor: Any) -> None:
    d = await chamar(servidor, "registrar_decisao", prato="X", decisao="talvez")
    assert d["categoria"] == "uso"


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #


def test_receita_entrada_converte_para_dominio() -> None:
    entrada = ReceitaEntrada(
        nome="X",
        ingredientes=[
            IngredienteEntrada(texto="1 kg de arroz", nome="arroz", quantidade=1, medida="kg")
        ],
        rendimento_porcoes=2,
        modo_preparo=["Leve ao forno."],
        tempo_preparo_min=15,
        tempo_cozimento_min=40,
        tempo_total_min=55,
    )
    dominio = entrada.para_dominio()
    assert dominio.rendimento_porcoes == 2
    assert "forno" in dominio.equipamentos
    assert (dominio.tempo_preparo_min, dominio.tempo_cozimento_min, dominio.tempo_total_min) == (
        15,
        40,
        55,
    )


def test_tempo_negativo_e_recusado_no_schema() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        ReceitaEntrada(
            nome="X",
            ingredientes=[IngredienteEntrada(texto="a", nome="arroz", quantidade=1, medida="kg")],
            tempo_cozimento_min=-1,
        )


def test_linha_lida_no_servidor_vale_mais_que_o_palpite_da_tela() -> None:
    """A tela adivinhava "sopa de óleo" e o prato pedia para comprar sopa de óleo."""
    palpite = IngredienteEntrada(texto="2 colheres de sopa de óleo", nome="sopa de óleo")
    lido = ReceitaEntrada(nome="X", ingredientes=[palpite]).para_dominio().ingredientes[0]
    assert (lido.nome, lido.quantidade, lido.medida) == ("óleo", Decimal(2), "colher de sopa")
    # Sem medida na linha, o nome de quem mandou continua valendo.
    sem_medida = IngredienteEntrada(texto="1 pimentão vermelho", nome="pimentão")
    lido = ReceitaEntrada(nome="X", ingredientes=[sem_medida]).para_dominio().ingredientes[0]
    assert lido.nome == "pimentão"


def test_ingrediente_sem_quantidade_vira_a_gosto() -> None:
    entrada = ReceitaEntrada(
        nome="X", ingredientes=[IngredienteEntrada(texto="sal a gosto", nome="sal")]
    )
    assert entrada.para_dominio().ingredientes[0].a_gosto


def test_rendimento_minimo_e_validado_no_schema() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        ReceitaEntrada(
            nome="X",
            ingredientes=[IngredienteEntrada(texto="a", nome="arroz", quantidade=1, medida="kg")],
            rendimento_porcoes=0,
        )


def test_abrir_sessao_usa_ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "x.db"))
    sessao = abrir_sessao()
    assert len(sessao.despensa) == 37
    sessao.dossie.fechar()


# --------------------------------------------------------------------------- #
# Preço do que falta comprar                                                   #
# --------------------------------------------------------------------------- #


async def test_registrar_preco_mercado_guarda_e_devolve_orcamento(servidor: Any) -> None:
    resposta = await chamar(
        servidor, "registrar_preco_mercado", ingrediente="trufa branca", valor=18.5
    )
    assert "R$ 18,50" in resposta["registrado"]
    assert "informado por ela" in resposta["registrado"]
    assert resposta["orcamento_restante"]["texto"] == "R$ 80,00"


async def test_registrar_preco_mercado_aceita_origem_explicita(servidor: Any) -> None:
    resposta = await chamar(
        servidor,
        "registrar_preco_mercado",
        ingrediente="trufa branca",
        valor=18.5,
        origem="pesquisado_na_web",
    )
    assert "pesquisado na web" in resposta["registrado"]


async def test_registrar_preco_mercado_recusa_origem_inventada(servidor: Any) -> None:
    """Origem desconhecida é erro de quem chamou, e o erro diz quais servem."""
    resposta = await chamar(
        servidor, "registrar_preco_mercado", ingrediente="trufa", valor=1.0, origem="chutei"
    )
    assert resposta["categoria"] == "uso"
    # O erro diz quais origens servem, em vez de só recusar.
    assert "informado_por_ela" in json.dumps(resposta, ensure_ascii=False)


async def test_registrar_preco_mercado_recusa_valor_negativo(servidor: Any) -> None:
    resposta = await chamar(servidor, "registrar_preco_mercado", ingrediente="trufa", valor=-5.0)
    assert resposta["categoria"] == "uso"
    assert "registrado" not in resposta


async def test_consultar_precos_comeca_vazio(servidor: Any) -> None:
    assert (await chamar(servidor, "consultar_precos_de_mercado"))["precos"] == []


async def test_consultar_precos_lista_o_que_foi_registrado(servidor: Any) -> None:
    await chamar(servidor, "registrar_preco_mercado", ingrediente="trufa branca", valor=18.5)
    await chamar(servidor, "registrar_preco_mercado", ingrediente="acafrao", valor=9.0)

    precos = (await chamar(servidor, "consultar_precos_de_mercado"))["precos"]
    assert len(precos) == 2
    # Ordem alfabética, para a lista não dançar entre uma consulta e outra.
    # "acafrao" casou com o item da despensa e foi guardado com o nome dele.
    assert precos[0].startswith("Açafrão em pó")


# --------------------------------------------------------------------------- #
# Receita da web, pela página que o servidor buscou                            #
# --------------------------------------------------------------------------- #

PAGINA_COM_RECEITA = (
    '<script type="application/ld+json">'
    '{"@type":"Recipe","name":"Arroz da web","recipeYield":"4",'
    '"recipeIngredient":["1 xícara de arroz","sal a gosto"],'
    '"recipeInstructions":["Refogue e cozinhe na panela."]}'
    "</script>"
)


def _pagina(monkeypatch: pytest.MonkeyPatch, html: str) -> None:
    """A página que a busca "traz", sem rede."""
    monkeypatch.setattr("retrieval.busca.baixar", lambda *_a, **_c: html)


async def test_receita_da_web_traz_a_procedencia_e_o_id(
    servidor: Any, sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mise.despensa_json import slug_da_receita

    _pagina(monkeypatch, PAGINA_COM_RECEITA)
    d = await chamar(
        servidor, "buscar_receita_na_web", url="https://www.tudogostoso.com.br/receita/9-arroz"
    )

    assert d["receita"]["nome"] == "Arroz da web"
    assert d["receita"]["origem"] == "web"
    assert d["procedencia"]["fonte"] == "tudogostoso.com.br"
    assert "tudogostoso.com.br" in d["procedencia"]["citacao"]
    assert d["ja_conhecida"] is False
    # É o texto original que ela confere quando discorda da nossa leitura.
    assert "1 xícara de arroz" in [i["texto"] for i in d["receita"]["ingredientes"]]
    guardada = sessao.catalogo.obter(d["receita_id"])
    assert guardada is not None and guardada.nome == "Arroz da web"
    assert d["receita_id"] == slug_da_receita(guardada.receita)
    assert len(d["receita_id"]) == 16
    # Trazer não põe em avaliação: só a conversa sobre ela põe.
    assert "Arroz da web" not in sessao.candidatas


async def test_endereco_ja_lido_volta_do_catalogo_sem_buscar_de_novo(
    servidor: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pagina(monkeypatch, PAGINA_COM_RECEITA)
    primeira = await chamar(servidor, "buscar_receita_na_web", url="https://tudogostoso.com.br/r/9")

    def nao_busca(*_a: Any, **_c: Any) -> str:
        raise AssertionError("buscou de novo uma página que já está no catálogo")

    monkeypatch.setattr("retrieval.busca.baixar", nao_busca)
    segunda = await chamar(
        servidor, "buscar_receita_na_web", url="https://www.TudoGostoso.com.br/r/9/?utm=x"
    )
    assert segunda["ja_conhecida"] is True
    assert segunda["receita_id"] == primeira["receita_id"]


async def test_receita_da_web_e_avaliada_pelo_id(
    servidor: Any, sessao: Sessao, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pagina(monkeypatch, PAGINA_COM_RECEITA)
    trazida = await chamar(servidor, "buscar_receita_na_web", url="https://tudogostoso.com.br/r/9")
    d = await chamar(servidor, "avaliar_receita", receita_id=trazida["receita_id"])
    assert d["receita_id"] == trazida["receita_id"]
    assert "Arroz da web" in sessao.candidatas
    linhas = {i["nome"]: i for i in d["ingredientes"]}
    assert linhas["Arroz branco tipo 1"]["situacao"] == "tem"
    assert linhas["Arroz branco tipo 1"]["tem"] == {"texto": "5 kg"}


async def test_pagina_sem_receita_vira_pergunta(
    servidor: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falhar a extração não é erro fatal: é tentar outra página."""
    _pagina(monkeypatch, "<html><body>nada aqui</body></html>")
    d = await chamar(servidor, "buscar_receita_na_web", url="https://exemplo.com.br/nada")
    assert d["categoria"] == "dado"
    assert "Tenta outro?" in json.dumps(d, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# As ferramentas que ainda respondem que não estão prontas                     #
# --------------------------------------------------------------------------- #


async def test_avaliacao_da_receita_guarda_gosto_estrelas_e_notas(
    servidor: Any, sessao: Sessao
) -> None:
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor,
        "registrar_avaliacao_da_receita",
        receita_id="arroz-com-frango",
        gosta=True,
        estrelas={"sabor": 5},
        notas="Testar com açafrão.",
    )
    assert (d["registrado"], d["receita_id"]) == (True, "arroz-com-frango")
    assert d["avaliacao"]["estrelas"]["sabor"] == 5
    assert d["avaliacao"]["notas"] == "Testar com açafrão."
    assert d["avaliacao"]["pontuacao"]["texto"] == "100,0"
    assert "100 × (0,75 × 1 + 0,25 × 1)" in d["avaliacao"]["pontuacao"]["derivacao"]
    (opiniao,) = sessao.dossie.gostos()
    assert (opiniao.prato, opiniao.gosto) == ("Arroz com frango", Gosto.GOSTA)


async def test_avaliacao_de_receita_que_nao_existe_e_recusada(servidor: Any) -> None:
    d = await chamar(
        servidor, "registrar_avaliacao_da_receita", receita_id="lasanha", estrelas={"sabor": 4}
    )
    assert (d["categoria"], d["tipo"]) == ("uso", "Ausente")


async def test_estrela_fora_de_um_a_cinco_nao_grava_nada(servidor: Any, sessao: Sessao) -> None:
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor,
        "registrar_avaliacao_da_receita",
        receita_id="arroz-com-frango",
        gosta=False,
        estrelas={"sabor": 9},
    )
    assert d["categoria"] == "uso"
    assert sessao.dossie.gostos() == ()


async def test_estimativa_preliminar_de_prato_que_nao_existe(servidor: Any) -> None:
    """Sem a receita em avaliação, nenhum número: a recusa diz o que falta."""
    d = await chamar(servidor, "estimar_preco_preliminar", prato="Arroz com frango")
    assert d["categoria"] == "uso"
    assert "não encontrei essa receita" in d["erro"]
    assert "R$" not in json.dumps(d, ensure_ascii=False)


async def test_pauta_de_descoberta_pelo_dinheiro_parado(servidor: Any) -> None:
    """A pauta sai da despensa: os pratos que ela cobre, e o dinheiro parado sem receita."""
    d = await chamar(servidor, "pauta_de_descoberta")
    assert d["disponivel"] is True
    assert d["buscas"][0] == "receita de feijão tropeiro"
    assert d["buscas"][4:6] == ["receita com alcaparras", "receita com cobertura de chocolate"]
    assert 5 <= len(d["buscas"]) <= 8
    assert d["limites"] == {"buscas": 8, "paginas": 20, "paginas_por_busca": 3}
    assert d["urls_conhecidas"] == []
    primeiro = d["itens_para_procurar"][0]
    assert (primeiro["item_id"], primeiro["motivo"]) == ("alcaparras", "sem_receita")
    assert primeiro["pago"]["texto"] == "R$ 82,00"


# --------------------------------------------------------------------------- #
# Conhecimento culinário                                                       #
# --------------------------------------------------------------------------- #


async def test_conhecimento_traz_o_trecho_com_fonte_e_rota(servidor: Any) -> None:
    """A plataforma inteira é o corpus: o item da despensa volta com a tela dele."""
    d = await chamar(servidor, "consultar_conhecimento", pergunta="quanto paguei nas alcaparras?")
    assert set(d) == {"trechos", "nada_relevante", "texto"}
    assert d["nada_relevante"] is False
    primeiro = d["trechos"][0]
    assert set(primeiro) == {"id", "tipo", "rota", "fonte", "texto", "pontuacao"}
    assert (primeiro["id"], primeiro["tipo"], primeiro["rota"]) == (
        "despensa:alcaparras",
        "despensa",
        "/despensa/alcaparras",
    )
    assert "R$ 82,00" in primeiro["texto"]
    assert 0 < primeiro["pontuacao"] <= 1


async def test_pergunta_fora_do_assunto_diz_que_nao_sabe(servidor: Any) -> None:
    """Devolver o "menos pior" com fonte seria pior do que não responder."""
    d = await chamar(servidor, "consultar_conhecimento", pergunta="qual a capital da Mongólia")
    assert (d["trechos"], d["nada_relevante"]) == ([], True)
    assert "Não sei" in d["texto"]
    assert "procurar na internet" in d["texto"]


async def test_k_e_tipos_limitam_a_resposta(servidor: Any) -> None:
    async def trechos(**argumentos: Any) -> list[dict[str, Any]]:
        d = await chamar(servidor, "consultar_conhecimento", pergunta="carne", **argumentos)
        return d["trechos"]

    assert len(await trechos(k=99)) <= 12
    assert len(await trechos(k=0)) == 1
    assert {t["tipo"] for t in await trechos(tipos=["despensa"])} == {"despensa"}
    invalido = await chamar(servidor, "consultar_conhecimento", pergunta="x", tipos=["moveis"])
    assert invalido["categoria"] == "uso"
    vazia = await chamar(servidor, "consultar_conhecimento", pergunta="   ")
    assert vazia["categoria"] == "uso"


async def test_busca_na_web_recusa_endereco_perigoso(servidor: Any) -> None:
    """A URL vem do modelo, que a leu de uma página. Não é dado confiável."""
    d = await chamar(servidor, "buscar_receita_na_web", url="file:///etc/passwd")
    assert d["categoria"] == "uso"


async def test_busca_na_web_falha_dizendo_o_que_fazer(servidor: Any, monkeypatch) -> None:
    """Sem internet a consultoria continua, com ela ditando a receita."""
    from retrieval.busca import BuscaFalhou

    def cair(*_args: Any, **_chaves: Any) -> str:
        raise BuscaFalhou("servidor fora do ar")

    monkeypatch.setattr("retrieval.busca.baixar", cair)
    d = await chamar(servidor, "buscar_receita_na_web", url="https://exemplo.com.br/x")
    assert d["categoria"] == "dado"
    assert "dita a receita" in json.dumps(d, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Dinheiro e decisão passam pelo portão
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

COM_MILHO: dict[str, Any] = {
    **ARROZ_COM_FRANGO,
    "nome": "Frango com milho",
    "ingredientes": [
        *ARROZ_COM_FRANGO["ingredientes"],
        {"texto": "1 lata de milho", "nome": "milho verde", "quantidade": 1, "medida": "lata"},
    ],
}


def confirmar_cozinha(sessao: Sessao, *pratos: str) -> None:
    perfil = sessao.perfil
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    perfil = perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
    sessao.dossie.salvar_perfil(perfil)
    for prato in pratos:
        sessao.dossie.registrar_gosto(prato, Gosto.GOSTA)


async def test_preco_de_prato_nao_avaliado_e_recusado(servidor: Any) -> None:
    d = await chamar(servidor, "cenarios_preco", prato="Lasanha")
    assert d["categoria"] == "uso"
    assert "ainda não foi avaliado" in d["erro"]


async def test_preco_antes_do_portao_e_recusado(servidor: Any) -> None:
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(servidor, "cenarios_preco", prato="Arroz com frango")
    assert d["categoria"] == "regra", "sem gosto confirmado o portão não libera"


async def test_cenarios_usam_o_custo_do_motor(servidor: Any, sessao: Sessao) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)

    d = await chamar(servidor, "cenarios_preco", prato="arroz com FRANGO")
    # 0,5 kg × 14,00 + 1 kg × 4,98 = 11,98 ÷ 4 = 2,995 → 3,00 (para cima)
    assert d["cmv"]["valor"] == pytest.approx(3.00)
    assert len(d["cenarios"]) == 3

    errado = await chamar(servidor, "cenarios_preco", prato="Arroz com frango", cmv_por_porcao=1.0)
    assert errado["categoria"] == "uso"
    assert "não é o que a conta dá" in errado["erro"]


async def test_sensibilidade(servidor: Any, sessao: Sessao) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(servidor, "testar_sensibilidade", prato="Arroz com frango", preco=12.0)
    assert d["se_subir_20_porcento"]["continua_lucrativo"]
    assert "%" in d["aguenta_alta_de"]
    no_preco = d["no_preco"]
    assert no_preco["taxa_ifood"]["texto"] == "R$ 1,20"
    assert no_preco["ela_recebe"]["texto"] == "R$ 10,80"
    assert no_preco["lucro"]["texto"] == "R$ 7,80"
    assert no_preco["da_prejuizo"] is False
    assert no_preco["preco_minimo_sem_prejuizo"]["texto"] == "R$ 3,34"


async def test_o_id_que_a_avaliacao_devolve_serve_no_custo_e_no_preco(
    servidor: Any, sessao: Sessao
) -> None:
    """O modelo não precisa redigitar a receita: o id devolvido vale nas próximas."""
    confirmar_cozinha(sessao, "Arroz com frango")
    avaliada = await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    assert avaliada["receita_id"] == "arroz-com-frango"

    de_novo = await chamar(servidor, "avaliar_receita", receita_id="arroz-com-frango")
    assert (de_novo["receita_id"], de_novo["veredito"]) == ("arroz-com-frango", "APTO")
    pelo_id = await chamar(servidor, "calcular_cmv", receita_id="arroz-com-frango")
    pela_receita = await chamar(servidor, "calcular_cmv", receita=ARROZ_COM_FRANGO)
    assert (
        pelo_id["cmv_por_porcao"]
        == pela_receita["cmv_por_porcao"]
        == {
            "valor": 3.0,
            "texto": "R$ 3,00",
        }
    )
    cenarios = await chamar(servidor, "cenarios_preco", receita_id="arroz-com-frango")
    assert (cenarios["prato"], cenarios["cmv"]["texto"]) == ("Arroz com frango", "R$ 3,00")
    ponto = await chamar(
        servidor, "testar_sensibilidade", receita_id="arroz-com-frango", prato="Lasanha", preco=12
    )
    assert ponto["no_preco"]["lucro"]["texto"] == "R$ 7,80", "o id vale mais que o nome"
    (candidata,) = (await chamar(servidor, "comparar_candidatas"))["candidatas"]
    assert candidata["receita_id"] == "arroz-com-frango"


async def test_a_receita_que_ela_dita_de_novo_e_a_correcao_dela(
    servidor: Any, sessao: Sessao
) -> None:
    """A receita dela volta com o que faltava (o rendimento que ela disse) pelo mesmo id."""
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    corrigida = {**ARROZ_COM_FRANGO, "rendimento_porcoes": 8}
    d = await chamar(servidor, "avaliar_receita", receita_id="arroz-com-frango", receita=corrigida)
    assert d["receita_id"] == "arroz-com-frango"
    assert sessao.candidatas["Arroz com frango"].rendimento_porcoes == 8
    outra = await chamar(
        servidor,
        "avaliar_receita",
        receita_id="arroz-com-frango",
        receita={**ARROZ_COM_FRANGO, "nome": "Lasanha"},
    )
    assert outra["categoria"] == "uso"
    assert "sem o receita_id" in outra["erro"]


async def test_custo_de_receita_redigitada_diferente_e_recusado(
    servidor: Any, sessao: Sessao
) -> None:
    """A quantidade não pode mudar entre a conferência e o custo."""
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    mexida = {
        **ARROZ_COM_FRANGO,
        "ingredientes": [
            {"texto": "50 g de frango", "nome": "peito de frango", "quantidade": 50, "medida": "g"},
            *ARROZ_COM_FRANGO["ingredientes"][1:],
        ],
    }
    d = await chamar(servidor, "calcular_cmv", receita=mexida)
    assert d["categoria"] == "uso"
    assert "receita_id arroz-com-frango" in d["erro"]
    assert sessao.candidatas["Arroz com frango"].ingredientes[0].quantidade == Decimal(500)
    pelo_id = await chamar(servidor, "calcular_cmv", receita_id="arroz-com-frango", receita=mexida)
    assert pelo_id["categoria"] == "uso"


async def test_custo_de_receita_digitada_que_nunca_passou_pela_conferencia(servidor: Any) -> None:
    d = await chamar(servidor, "calcular_cmv", receita=ARROZ_COM_FRANGO)
    assert d["categoria"] == "uso"
    assert "avaliar_receita" in d["erro"]


@pytest.mark.parametrize(
    ("ferramenta", "argumentos"),
    [
        ("avaliar_receita", {}),
        ("calcular_cmv", {"receita_id": "  "}),
        ("cenarios_preco", {}),
        ("testar_sensibilidade", {"preco": 12.0, "prato": " "}),
    ],
)
async def test_sem_receita_nem_id_a_recusa_diz_o_que_mandar(
    servidor: Any, ferramenta: str, argumentos: dict[str, Any]
) -> None:
    d = await chamar(servidor, ferramenta, **argumentos)
    assert d["categoria"] == "uso"
    assert "receita_id" in d["erro"]


async def test_id_que_nao_esta_em_avaliacao_e_recusado(servidor: Any) -> None:
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(servidor, "cenarios_preco", receita_id="lasanha")
    assert (d["categoria"], d["tipo"]) == ("uso", "Ausente")
    assert d["contexto"]["em_avaliacao"] == "Arroz com frango"


async def test_preco_proposto_abaixo_do_minimo_vem_marcado(servidor: Any, sessao: Sessao) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(servidor, "testar_sensibilidade", prato="Arroz com frango", preco=3.0)
    assert d["no_preco"]["da_prejuizo"] is True
    assert d["no_preco"]["lucro"]["texto"] == "-R$ 0,30"


async def test_receita_digitada_com_endereco_nao_vira_da_internet(
    servidor: Any, sessao: Sessao
) -> None:
    """Endereço digitado não é procedência: só a página que o servidor leu é da internet."""
    web = {
        **ARROZ_COM_FRANGO,
        "url": "https://www.tudogostoso.com.br/receita/1",
        "fonte": "TudoGostoso",
    }
    d = await chamar(servidor, "avaliar_receita", receita=web)
    assert d["categoria"] == "uso"
    assert "buscar_receita_na_web" in d["erro"]
    assert sessao.candidatas == {}
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    (candidata,) = (await chamar(servidor, "comparar_candidatas"))["candidatas"]
    assert "como a senhora me passou" in candidata["fonte"]


async def test_aceitar_grava_preco_e_lucro(servidor: Any, sessao: Sessao) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)

    sem_preco = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito"
    )
    assert "informe o preço" in sem_preco["erro"]

    d = await chamar(
        servidor,
        "registrar_decisao",
        prato="Arroz com frango",
        decisao="aceito",
        motivo="gosta de fazer",
        preco=12.0,
    )
    assert d["preco"] == "R$ 12,00"
    assert d["lucro_por_porcao"] == "R$ 7,80"  # 0,90 × 12 − 3,00
    assert d["da_prejuizo"] is False
    cardapio = await chamar(servidor, "consultar_cardapio")
    assert cardapio["cardapio"] == ["Arroz com frango"]
    assert "gosta de fazer" in cardapio["historico"][0]
    (aceito,) = cardapio["aceitos"]
    assert aceito == {
        "prato": "Arroz com frango",
        "preco": "R$ 12,00",
        "cmv_por_porcao": "R$ 3,00",
        "lucro_por_porcao": "R$ 7,80",
        "preco_minimo": "R$ 3,34",
        "da_prejuizo": False,
        "taxa_ifood": "R$ 1,20",
        "ela_recebe": "R$ 10,80",
        # Sem gateway não há auditor injetado; quem injeta é a raiz de composição.
        "auditoria_independente": None,
    }


async def test_aceitar_abaixo_do_minimo_e_dela_mas_diz_quanto_perde(
    servidor: Any, sessao: Sessao
) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=3.0
    )
    assert d["da_prejuizo"] is True
    assert d["preco_minimo"] == "R$ 3,34"


async def test_recusar_nao_precisa_de_portao(servidor: Any) -> None:
    d = await chamar(servidor, "registrar_decisao", prato="Qualquer", decisao="recusado")
    assert "Qualquer" in d["registrado"]


async def test_compra_antes_de_confirmar_a_cozinha_e_recusada(servidor: Any) -> None:
    await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    d = await chamar(
        servidor,
        "registrar_compra",
        prato="Frango com milho",
        ingrediente="milho verde",
        quantidade=1,
        unidade="lata",
        valor=6.0,
    )
    assert d["categoria"] == "uso"
    assert "ainda não está confirmado" in d["erro"]
    assert (await chamar(servidor, "consultar_orcamento"))["gasto"]["valor"] == 0.0


@pytest.mark.usefixtures("sem_precos_de_referencia")
async def test_compra_tira_o_item_da_lista_e_nao_desconta_duas_vezes(
    servidor: Any, sessao: Sessao
) -> None:
    confirmar_cozinha(sessao, "Frango com milho")
    antes = await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    assert antes["veredito"] == "BLOQUEADO", "sem preço do milho nem referência, fica de fora"
    assert not antes["perguntas"] or all(p["tipo"] != "ingrediente" for p in antes["perguntas"]), (
        "o preço nunca é pergunta"
    )

    d = await chamar(
        servidor,
        "registrar_compra",
        prato="Frango com milho",
        ingrediente="Milho Verde",
        quantidade=1,
        unidade="lata",
        valor=6.0,
    )
    assert d["veredito_agora"] == "APTO"
    assert d["ainda_falta"] == []
    orcamento = await chamar(servidor, "consultar_orcamento")
    assert orcamento["restante"]["valor"] == pytest.approx(74.0)

    cmv = await chamar(servidor, "calcular_cmv", receita=COM_MILHO)
    nomes = [linha["ingrediente"] for linha in cmv["linhas"]]
    assert "milho verde (comprado)" in nomes
    # 7,00 + 4,98 + 6,00 = 17,98 ÷ 4 = 4,495 → 4,50
    assert cmv["cmv_por_porcao"]["valor"] == pytest.approx(4.50)
    assert (await chamar(servidor, "consultar_orcamento"))["restante"]["valor"] == 74.0


async def test_compra_de_item_que_o_prato_nao_precisa_e_recusada(
    servidor: Any, sessao: Sessao
) -> None:
    confirmar_cozinha(sessao, "Frango com milho")
    await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    d = await chamar(
        servidor,
        "registrar_compra",
        prato="Frango com milho",
        ingrediente="trufa",
        quantidade=1,
        unidade="un",
        valor=6.0,
    )
    assert "não está entre o que" in d["erro"]


async def test_compra_acima_do_orcamento_e_recusada(servidor: Any, sessao: Sessao) -> None:
    confirmar_cozinha(sessao, "Frango com milho")
    await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    d = await chamar(
        servidor,
        "registrar_compra",
        prato="Frango com milho",
        ingrediente="milho verde",
        quantidade=1,
        unidade="lata",
        valor=200.0,
    )
    assert d["categoria"] == "regra"
    assert (await chamar(servidor, "consultar_orcamento"))["gasto"]["valor"] == 0.0


async def test_candidata_sobrevive_a_um_servidor_novo(sessao: Sessao, tmp_path: Path) -> None:
    """Cada turno do Hermes sobe um processo novo; o prato avaliado tem que continuar lá."""
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(construir_servidor(sessao), "avaliar_receita", receita=ARROZ_COM_FRANGO)
    sessao.dossie.fechar()

    outro = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    d = await chamar(construir_servidor(outro), "cenarios_preco", prato="Arroz com frango")
    assert d["cmv"]["valor"] == pytest.approx(3.00)


# --------------------------------------------------------------------------- #
# Resposta do portão: ida e volta, sem chute
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "caso",
    [
        ("equipamento", "forno", "não", lambda p: p.equipamentos["forno"] is Posse.NAO_TEM),
        ("equipamento", "air_fryer", "Sim", lambda p: p.equipamentos["air_fryer"] is Posse.TEM),
        ("tecnica", "fritar", "tem", lambda p: p.tecnicas["fritar"] is Posse.TEM),
        ("operacional", "bocas_fogao", "4", lambda p: p.restricoes.bocas_fogao == 4),
        (
            "operacional",
            "tempo_max_por_fornada_min",
            "1h30",
            lambda p: p.restricoes.tempo_max_por_fornada_min == 90,
        ),
        (
            "operacional",
            "tem_gas_sobrando",
            "não",
            lambda p: p.restricoes.tem_gas_sobrando is False,
        ),
        ("operacional", "tem_gas_sobrando", "sim", lambda p: p.restricoes.tem_gas_sobrando is True),
        (
            "operacional",
            "espaco_geladeira_litros",
            "20,5",
            lambda p: p.restricoes.espaco_geladeira_litros == 20,
        ),
    ],
)
async def test_cada_resposta_chega_ao_perfil(servidor: Any, sessao: Sessao, caso: Any) -> None:
    tipo, campo, resposta, confere = caso
    d = await chamar(servidor, "registrar_resposta", tipo=tipo, campo=campo, resposta=resposta)
    assert d["registrado"] is True, d
    assert confere(sessao.perfil)


@pytest.mark.parametrize(
    ("tipo", "campo", "resposta"),
    [
        # "não sei" agora é resposta (ver test_nao_sei_*); "talvez" continua sem sentido.
        ("equipamento", "forno", "talvez"),
        ("operacional", "bocas_fogao", "sim"),
        ("operacional", "tem_gas_sobrando", "mais ou menos"),
        ("gosto", "Feijoada", "talvez"),
        ("sabor", "x", "y"),
    ],
)
async def test_resposta_que_nao_da_para_entender_e_recusada(
    servidor: Any, sessao: Sessao, tipo: str, campo: str, resposta: str
) -> None:
    antes = sessao.perfil
    d = await chamar(servidor, "registrar_resposta", tipo=tipo, campo=campo, resposta=resposta)
    assert d["categoria"] == "uso"
    assert sessao.perfil == antes, "nada foi gravado"


async def test_gosto_entra_e_ingrediente_aponta_a_ferramenta_certa(
    servidor: Any, sessao: Sessao
) -> None:
    await chamar(
        servidor, "registrar_resposta", tipo="gosto", campo="Feijoada", resposta="nao_gosta"
    )
    opiniao = sessao.dossie.gosto_por("Feijoada")
    assert opiniao is not None
    assert opiniao.gosto is Gosto.NAO_GOSTA

    d = await chamar(
        servidor, "registrar_resposta", tipo="ingrediente", campo="milho verde", resposta="6"
    )
    assert "registrar_preco_mercado" in json.dumps(d, ensure_ascii=False)
    assert sessao.dossie.preco_de("milho verde") is None, "peso não vira cotação por engano"


async def test_preparo_e_rendimento_voltam_para_a_receita(servidor: Any) -> None:
    d = await chamar(
        servidor, "registrar_resposta", tipo="equipamento", campo="modo_preparo", resposta="panela"
    )
    assert "avaliar_receita" in d["erro"]


async def test_tempo_da_receita_volta_para_a_receita(servidor: Any, sessao: Sessao) -> None:
    """O tempo no fogo é da receita, como o rendimento: não vira restrição da cozinha."""
    d = await chamar(
        servidor,
        "registrar_resposta",
        tipo="operacional",
        campo="tempo_cozimento_min",
        resposta="40",
    )
    assert "avaliar_receita" in d["erro"]
    assert sessao.perfil.restricoes.tempo_max_por_fornada_min is None


async def test_avaliar_receita_com_o_tempo_respondido_libera(servidor: Any) -> None:
    """Ela diz quanto tempo fica no fogo, a receita volta com isso, e o prato sai da pergunta."""
    await chamar(servidor, "registrar_gosto", prato="Risoto", gosta=True)
    for campo, valor in (("tempo_max_por_fornada_min", "1 hora"), ("bocas_fogao", "4")):
        await chamar(
            servidor, "registrar_resposta", tipo="operacional", campo=campo, resposta=valor
        )
    risoto: dict[str, Any] = {
        "nome": "Risoto",
        "rendimento_porcoes": 2,
        "modo_preparo": ["Cozinhe o arroz na panela, mexendo sempre."],
        "ingredientes": [
            {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        ],
    }
    antes = await chamar(servidor, "avaliar_receita", receita=risoto)
    # O tempo da receita nunca é pergunta: sem ele, a receita não dá; ela corrige se quiser.
    assert "tempo_cozimento_min" not in {p["campo"] for p in antes["perguntas"]}
    assert antes["veredito"] == "BLOQUEADO"

    depois = await chamar(
        servidor, "avaliar_receita", receita={**risoto, "tempo_cozimento_min": 25}
    )
    assert depois["veredito"] == "APTO", depois["perguntas"]
    assert depois["avisos"] == []


async def test_avaliar_receita_traz_os_avisos(servidor: Any) -> None:
    await chamar(servidor, "registrar_gosto", prato="Arroz e feijão", gosta=True)
    for campo, valor in (("tempo_max_por_fornada_min", "1"), ("bocas_fogao", "1")):
        await chamar(
            servidor, "registrar_resposta", tipo="operacional", campo=campo, resposta=valor
        )
    receita_de_duas_panelas: dict[str, Any] = {
        "nome": "Arroz e feijão",
        "rendimento_porcoes": 2,
        "modo_preparo": [
            "Cozinhe o feijão na panela por 20 minutos.",
            "Em outra panela, refogue o arroz por 15 minutos.",
        ],
        "ingredientes": [
            {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        ],
    }
    d = await chamar(servidor, "avaliar_receita", receita=receita_de_duas_panelas)
    assert d["veredito"] == "APTO"
    assert d["avisos"] == [
        {
            "tipo": "bocas",
            "texto": "O passo 2 pede outra panela no fogo ao mesmo tempo. Com uma boca, a "
            "senhora faz uma parte depois da outra e leva mais tempo.",
        }
    ]


# --------------------------------------------------------------------------- #
# O que ela já tem (§2.1)
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("sem_precos_de_referencia")
async def test_comparar_candidatas_poe_na_frente_quem_aproveita_a_despensa(
    servidor: Any, sessao: Sessao
) -> None:
    confirmar_cozinha(sessao, "Arroz com frango", "Frango com milho")
    await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)

    d = await chamar(servidor, "comparar_candidatas")
    primeiro, segundo = d["candidatas"]
    assert primeiro["prato"] == "Arroz com frango"
    assert primeiro["falta_comprar"] == []
    assert primeiro["ingredientes_que_ela_tem"] == primeiro["ingredientes_da_receita"] == 2
    # 0,5 kg de frango a 14,00 + 1 kg de arroz a 4,98
    assert primeiro["usa_do_estoque_dela"]["texto"] == "R$ 11,98"
    assert segundo["falta_comprar"] == ["milho verde"]
    assert segundo["compra_para_completar"] is None, "sem cotação nem referência, não inventa"


async def test_capital_sem_prato_encolhe_com_cada_receita(servidor: Any, sessao: Sessao) -> None:
    antes = (await chamar(servidor, "diagnostico_despensa"))["capital_sem_prato"]
    assert antes["total"]["texto"] == "R$ 663,39"
    assert antes["receitas_avaliadas"] == 0
    # Alcaparras (R$ 82,00) e cobertura (R$ 79,90): a soma vem pronta do motor.
    assert antes["dois_maiores"]["somam"]["texto"] == "R$ 161,90"
    # 161,90 / 663,39 = 0,2440...: a proporção também vem pronta, com o texto.
    assert antes["dois_maiores"]["parte_de_tudo"] == {
        "fracao": 0.244,
        "texto": "24,4% de tudo o que a senhora pagou",
    }

    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    depois = (await chamar(servidor, "diagnostico_despensa"))["capital_sem_prato"]
    # Frango (R$ 28,00) e arroz (R$ 24,90) passam a ter prato.
    assert depois["total"]["texto"] == "R$ 610,49"
    assert all(m["ingrediente"] != "Peito de frango" for m in depois["maiores"])


# --------------------------------------------------------------------------- #
# Auditor independente
# --------------------------------------------------------------------------- #


def auditor_que_confere(pratos: list[dict[str, Any]]) -> Any:
    def auditar(prato: dict[str, Any]) -> dict[str, Any]:
        pratos.append(prato)
        return {"confere": True, "observacao": "ok", "por": "teste"}

    return auditar


async def test_todo_preco_passa_pelo_auditor(servidor: Any, sessao: Sessao) -> None:
    vistos: list[dict[str, Any]] = []
    sessao.auditor = auditor_que_confere(vistos)
    confirmar_cozinha(sessao, "Arroz com frango")

    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    cmv = await chamar(servidor, "calcular_cmv", receita=ARROZ_COM_FRANGO)
    assert cmv["auditoria_independente"]["confere"] is True
    assert vistos[-1]["cmv"] == "3.00"
    assert sum(float(linha["custo"]) for linha in vistos[-1]["linhas"]) == pytest.approx(3.00)

    cenarios = await chamar(servidor, "cenarios_preco", prato="Arroz com frango")
    assert cenarios["auditoria_independente"]["confere"] is True
    assert [p["preco"] for p in vistos if "preco" in p] == ["7.50", "8.57", "10.00"]

    aceite = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    assert aceite["auditoria_independente"]["confere"] is True
    assert Decimal(vistos[-1]["preco"]) == Decimal(12)
    assert vistos[-1]["lucro"] == "7.80"


async def test_auditor_que_discorda_segura_o_preco(servidor: Any, sessao: Sessao) -> None:
    sessao.auditor = lambda _p: {"confere": False, "divergencias": ["lucro"], "por": "teste"}
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)

    d = await chamar(servidor, "cenarios_preco", prato="Arroz com frango")
    assert d["categoria"] == "regra"
    assert "não confere com a auditoria independente" in d["erro"]


async def test_auditor_fora_do_ar_nao_para_a_conta(servidor: Any, sessao: Sessao) -> None:
    sessao.auditor = lambda _p: {"confere": None, "observacao": "indisponível", "por": "a2a"}
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)

    d = await chamar(servidor, "cenarios_preco", prato="Arroz com frango")
    assert d["auditoria_independente"]["confere"] is None
    assert len(d["cenarios"]) == 3


# --------------------------------------------------------------------------- #
# Por onde a decisão chegou
# --------------------------------------------------------------------------- #


async def test_sessao_grava_o_canal_de_quem_chamou(servidor: Any, sessao: Sessao) -> None:
    """O servidor do agente é `conversa`; a API da tela troca para `tela`."""
    from mise.dossie import Canal

    confirmar_cozinha(sessao, "Frango com milho")
    await chamar(servidor, "registrar_decisao", prato="Bolo", decisao="adiado")
    sessao.canal = Canal.TELA
    await chamar(servidor, "registrar_decisao", prato="Pudim", decisao="recusado")
    await chamar(servidor, "avaliar_receita", receita=COM_MILHO)
    await chamar(
        servidor,
        "registrar_compra",
        prato="Frango com milho",
        ingrediente="milho verde",
        quantidade=1,
        unidade="lata",
        valor=6.0,
    )

    assert [r.canal for r in sessao.dossie.historico()] == ["conversa", "tela"]
    with sessao.dossie.cursor() as cur:
        assert [linha["canal"] for linha in cur.execute("SELECT canal FROM gastos")] == ["tela"]


# --------------------------------------------------------------------------- #
# Mudar de ideia e voltar atrás
# --------------------------------------------------------------------------- #


async def test_aceitar_recusar_e_aceitar_de_novo_pela_agente(servidor: Any, sessao: Sessao) -> None:
    """O defeito como ela viveu: no terceiro passo o prato sumia do cardápio."""
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    for decisao, preco in (("aceito", 12.0), ("recusado", None), ("aceito", 12.0)):
        await chamar(
            servidor, "registrar_decisao", prato="Arroz com frango", decisao=decisao, preco=preco
        )

    cardapio = await chamar(servidor, "consultar_cardapio")
    assert cardapio["cardapio"] == ["Arroz com frango"]
    assert len(cardapio["historico"]) == 3
    assert cardapio["aceitos"][0]["preco"] == "R$ 12,00"


async def test_repetir_o_aceite_que_vale_nao_duplica_a_trilha(
    servidor: Any, sessao: Sessao
) -> None:
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    for _ in range(2):
        await chamar(
            servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
        )
    assert len(sessao.dossie.historico()) == 1


async def test_outra_grafia_do_nome_e_o_mesmo_prato(servidor: Any, sessao: Sessao) -> None:
    """Recusar "arroz com FRANGO" tira do cardápio o "Arroz com frango" aceito."""
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    d = await chamar(servidor, "registrar_decisao", prato="arroz com FRANGO", decisao="recusado")
    assert d["cardapio_atual"] == []
    assert {r.prato for r in sessao.dossie.historico()} == {"Arroz com frango"}


def test_decidir_com_a_chave_de_quem_chama_e_desfazer(sessao: Sessao) -> None:
    from mise.dossie import Canal

    confirmar_cozinha(sessao, "Arroz com frango")
    sessao.guardar(ReceitaEntrada(**ARROZ_COM_FRANGO).para_dominio())
    aceite, _ = sessao.decidir("Arroz com frango", "aceito", preco=12.0, chave="k-1")
    de_novo, _ = sessao.decidir("Arroz com frango", "aceito", preco=12.0, chave="k-1")
    assert de_novo == aceite
    recusa, _ = sessao.decidir("Arroz com frango", "recusado", chave="k-2")
    volta, detalhes = sessao.decidir(
        "Arroz com frango", "aceito", preco=12.0, desfaz=recusa.id, canal=Canal.TELA
    )
    assert (volta.desfaz, volta.canal) == (recusa.id, "tela")
    assert detalhes["lucro_por_porcao"] == "R$ 7,80", "desfazer passa de novo pelo portão"
    assert sessao.dossie.cardapio == ("Arroz com frango",)


def test_reenvio_da_compra_com_a_mesma_chave_devolve_o_estado_sem_recusar(
    sessao: Sessao,
) -> None:
    """A lata já entrou e deixou de faltar: conferir de novo recusaria a compra que ela fez."""
    from mise.erros import ErroDeUso

    confirmar_cozinha(sessao, "Frango com milho")
    sessao.guardar(ReceitaEntrada(**COM_MILHO).para_dominio())
    argumentos = ("Frango com milho", "milho verde", 1, "lata", 6.0)
    primeira = sessao.comprar(*argumentos, chave="clique-1")
    reenvio = sessao.comprar(*argumentos, chave="clique-1")
    assert reenvio == primeira
    assert primeira["ainda_falta"] == []
    assert sessao.dossie.orcamento().gasto.valor == 6

    # Chave nova é compra nova, e o que já não falta continua recusado pelo portão.
    with pytest.raises(ErroDeUso, match="não está entre"):
        sessao.comprar(*argumentos, chave="clique-2")


# --------------------------------------------------------------------------- #
# Abaixo do mínimo é escolha dela, também com o auditor ligado
# --------------------------------------------------------------------------- #


def auditor_que_avisa(prato: dict[str, Any]) -> dict[str, Any]:
    """Responde como o auditor independente: prejuízo com a conta certa avisa, não segura."""
    abaixo = "preco" in prato and Decimal(prato["preco"]) * Decimal("0.9") < Decimal(prato["cmv"])
    return {
        "confere": True,
        "da_prejuizo": abaixo,
        "aviso": "abaixo do mínimo sem prejuízo" if abaixo else "",
        "por": "teste",
    }


async def test_aceitar_abaixo_do_minimo_com_o_auditor_ligado_e_dela(
    servidor: Any, sessao: Sessao
) -> None:
    """Com o auditor injetado (sempre, no gateway), este aceite era recusado."""
    sessao.auditor = auditor_que_avisa
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=3.0
    )
    assert d["da_prejuizo"] is True
    assert d["aviso"] == (
        "A R$ 3,00, a senhora perde R$ 0,30 em cada porção vendida: depois da taxa de "
        "10%, chega menos do que o ingrediente custa. Para não ter prejuízo, o mínimo "
        "é R$ 3,34. A decisão é da senhora."
    )
    assert d["auditoria_independente"]["da_prejuizo"] is True
    assert d["cardapio_atual"] == ["Arroz com frango"]


async def test_aceite_com_folga_nao_traz_aviso(servidor: Any, sessao: Sessao) -> None:
    sessao.auditor = auditor_que_avisa
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=12.0
    )
    assert d["da_prejuizo"] is False
    assert "aviso" not in d


async def test_conta_que_nao_bate_continua_segurando_o_aceite(
    servidor: Any, sessao: Sessao
) -> None:
    sessao.auditor = lambda _p: {"confere": False, "divergencias": ["lucro"], "por": "teste"}
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=3.0
    )
    assert d["categoria"] == "regra"
    assert sessao.dossie.cardapio == ()


async def test_motor_e_auditor_discordando_do_prejuizo_seguram_o_aceite(
    servidor: Any, sessao: Sessao
) -> None:
    """Duas contas independentes que discordam sobre ela perder dinheiro: uma está errada."""
    sessao.auditor = lambda _p: {"confere": True, "da_prejuizo": False, "por": "teste"}
    confirmar_cozinha(sessao, "Arroz com frango")
    await chamar(servidor, "avaliar_receita", receita=ARROZ_COM_FRANGO)
    d = await chamar(
        servidor, "registrar_decisao", prato="Arroz com frango", decisao="aceito", preco=3.0
    )
    assert d["categoria"] == "regra"
    assert "discordam" in json.dumps(d, ensure_ascii=False)
    assert sessao.dossie.cardapio == ()


def test_prejuizo_de_menos_de_um_centavo_tambem_avisa(sessao: Sessao) -> None:
    """A R$ 3,33 ela recebe R$ 2,997 por um prato de R$ 3,00: perde, mesmo sem aparecer."""
    confirmar_cozinha(sessao, "Arroz com frango")
    sessao.guardar(ReceitaEntrada(**ARROZ_COM_FRANGO).para_dominio())
    _, detalhes = sessao.decidir("Arroz com frango", "aceito", preco=3.33)
    assert detalhes["da_prejuizo"] is True
    assert "perde menos de um centavo" in detalhes["aviso"]
    assert "o mínimo é R$ 3,34" in detalhes["aviso"]
