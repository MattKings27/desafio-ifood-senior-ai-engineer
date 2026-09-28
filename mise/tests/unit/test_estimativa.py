"""O preço preliminar: as linhas com a conta, o piso, os três preços e as recusas."""

from __future__ import annotations

import json
import re
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest

from mise import parametros
from mise.catalogo import Catalogo, OrigemNoCatalogo, ReceitaDoCatalogo
from mise.dinheiro import Dinheiro
from mise.dossie import Dossie, OrigemPreco
from mise.erros import Ausente, ErroDeUso
from mise.estimativa import (
    SEM_REFERENCIA,
    EstimativaRecusada,
    custo_da_porcao,
    estimar,
    receita_da_estimativa,
)
from mise.mcp_server import ReceitaEntrada, Sessao, abrir_sessao, construir_servidor
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import Receita

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"
CENTAVO = Decimal("0.01")

ARROZ: dict[str, Any] = {
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

BOLO: dict[str, Any] = {
    "nome": "Bolo de fubá",
    "rendimento_porcoes": 8,
    "modo_preparo": ["Bata tudo no liquidificador por 3 minutos.", "Leve ao forno por 40 minutos."],
    "url": "https://www.tudogostoso.com.br/receita/123-bolo-de-fuba",
    "fonte": "TudoGostoso",
    "ingredientes": [
        {"texto": "2 xícaras de fubá", "nome": "fubá", "quantidade": 2, "medida": "xicara"},
        {
            "texto": "1 xícara de coco ralado",
            "nome": "coco ralado",
            "quantidade": 1,
            "medida": "xicara",
        },
    ],
}

BATATA: dict[str, Any] = {
    "nome": "Batata rústica",
    "rendimento_porcoes": 4,
    "modo_preparo": ["Corte as batatas em gomos.", "Leve à air fryer por 25 minutos."],
    "ingredientes": [
        {"texto": "1 kg de batata", "nome": "batata", "quantidade": 1, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}

MERENGUE: dict[str, Any] = {
    "nome": "Suspiro",
    "rendimento_porcoes": 10,
    "modo_preparo": [
        "Bata as claras na batedeira por 10 minutos.",
        "Asse no forno por 60 minutos.",
    ],
    "ingredientes": [
        {"texto": "200 g de açúcar", "nome": "açúcar", "quantidade": 200, "medida": "g"},
        {"texto": "100 g de farinha", "nome": "farinha de trigo", "quantidade": 100, "medida": "g"},
    ],
}

SALADA: dict[str, Any] = {
    "nome": "Salada de tomate",
    "rendimento_porcoes": 2,
    "modo_preparo": ["Corte o tomate e a cebola e tempere com sal."],
    "ingredientes": [
        {"texto": "500 g de tomate", "nome": "tomate", "quantidade": 500, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}


def _para_cima(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_CEILING)


def _redondo(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _dec(dinheiro: dict[str, Any]) -> Decimal:
    return Decimal(str(dinheiro["valor"]))


def _cozinha_toda(banco: Path, **ajustes: Posse) -> None:
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        perfil = perfil.com_equipamentos(ajustes.items())
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 180)
        )


def _sessao(tmp_path: Path, *receitas: dict[str, Any], **ajustes: Posse) -> Sessao:
    banco = tmp_path / "dossie.db"
    _cozinha_toda(banco, **ajustes)
    sessao = abrir_sessao(PLANILHA, banco)
    for receita in receitas:
        sessao.guardar(ReceitaEntrada(**receita).para_dominio())
    return sessao


def _receita(sessao: Sessao, nome: str) -> Receita:
    receita = sessao.dossie.candidata(nome)
    assert receita is not None
    return receita


def _linhas(dados: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {linha["id"]: linha for linha in dados["linhas"]}


def _conferir_a_conta(dados: dict[str, Any]) -> None:
    """Os números fecham entre si, como o contrato pede."""
    linhas = _linhas(dados)
    ingrediente = _dec(linhas["ingredientes"]["valor"])
    producao = sum((_dec(ln["valor"]) for ln in linhas.values() if ln["valor"]), Decimal(0))
    assert _dec(dados["custo_producao"]) == producao
    piso = _para_cima(producao / Decimal("0.9"))
    assert _dec(dados["piso"]) == piso
    assert _dec(dados["minimo_so_ingrediente"]) == _para_cima(ingrediente / Decimal("0.9"))
    for ponto, fracao in zip(dados["pontos"], ("0.40", "0.35", "0.30"), strict=True):
        preco = max(piso, _redondo(ingrediente / Decimal(fracao)))
        assert _dec(ponto["preco"]) == preco
        recebe = _redondo(preco * Decimal("0.90"))
        assert _dec(ponto["recebe"]) == recebe
        assert _dec(ponto["taxa"]) == preco - recebe
        assert _dec(ponto["lucro"]) == _redondo(preco * Decimal("0.90") - ingrediente)
        assert _dec(ponto["sobra_real"]) == _redondo(preco * Decimal("0.90") - producao)
        assert _dec(ponto["sobra_real"]) >= 0


# --------------------------------------------------------------------------- #
# A conta
# --------------------------------------------------------------------------- #


def test_arroz_com_frango_linha_a_linha(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    dados = estimar(sessao, _receita(sessao, "Arroz com frango"))
    linhas = _linhas(dados)
    assert (dados["preliminar"], dados["rotulo"], dados["slug"]) == (
        True,
        "Preço preliminar",
        "arroz-com-frango",
    )
    assert list(linhas) == ["ingredientes", "mao_de_obra", "gas", "embalagem"]
    assert linhas["ingredientes"]["valor"] == {"valor": 3.0, "texto": "R$ 3,00"}
    assert linhas["mao_de_obra"]["rotulo"] == "Mão de obra sugerida"
    assert linhas["mao_de_obra"]["derivacao"].startswith(
        "40 min ÷ 60 × R$ 7,37 por hora ÷ 4 porções = R$ 1,23, arredondado para cima"
    )
    assert linhas["gas"]["derivacao"].startswith(
        "botijão de R$ 114,80 ÷ (40 h × 60 min) = 4,79 centavos por minuto de fogo; "
        "40 min × 4,79 centavos ÷ 4 porções = R$ 0,48"
    )
    assert linhas["embalagem"]["valor"] is None
    assert dados["custo_producao"]["derivacao"] == (
        "R$ 3,00 + R$ 1,23 + R$ 0,48 = R$ 4,71, sem a embalagem"
    )
    assert dados["piso"]["derivacao"] == "R$ 4,71 ÷ 0,90 = 5,233, arredondado para cima: R$ 5,24"
    assert [p["preco"]["texto"] for p in dados["pontos"]] == ["R$ 7,50", "R$ 8,57", "R$ 10,00"]
    assert dados["pontos"][0]["derivacao"] == (
        "R$ 3,00 ÷ 0,40 = R$ 7,50; a plataforma fica com R$ 0,75 e chegam R$ 6,75; tirando "
        "R$ 3,00 de ingrediente, sobram R$ 3,75; tirando também a mão de obra e o gás, "
        "sobram R$ 2,04"
    )
    assert dados["referencias_de_mercado"] == []
    assert dados["referencias_texto"] == SEM_REFERENCIA
    assert dados["sinais"]["faltam_parametros"] == ["embalagem_por_porcao"]
    assert dados["texto"].startswith("Preço preliminar, sem compromisso")
    assert "entre R$ 7,50 e R$ 10,00" in dados["texto"]
    assert "quanto paga na embalagem" in dados["texto"]
    _conferir_a_conta(dados)


def _textos(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    return []


def test_a_estimativa_fala_a_lingua_dela(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ, BOLO, MERENGUE)
    jargao = re.compile(
        r"\b(?:motor|port[aã]o|apto|falta info|bloqueado|veredito|cmv|food cost)\b",
        re.IGNORECASE,
    )
    for nome in ("Arroz com frango", "Bolo de fubá", "Suspiro"):
        for texto in _textos(estimar(sessao, _receita(sessao, nome))):
            assert not jargao.search(texto), texto
            assert " \u2014 " not in texto, texto


def test_a_estimativa_nao_grava_nada(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    antes = (sessao.dossie.historico(), sessao.dossie.extrato(), sessao.dossie.orcamento())
    estimar(sessao, _receita(sessao, "Arroz com frango"))
    assert (sessao.dossie.historico(), sessao.dossie.extrato(), sessao.dossie.orcamento()) == antes


def test_embalagem_informada_entra_na_conta(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    parametros.definir(sessao.dossie, "embalagem_por_porcao", 1.2)
    dados = estimar(sessao, _receita(sessao, "Arroz com frango"))
    assert _linhas(dados)["embalagem"]["valor"] == {"valor": 1.2, "texto": "R$ 1,20"}
    assert dados["sinais"]["faltam_parametros"] == []
    premissa = next(p for p in dados["premissas"] if p["nome"] == "embalagem_por_porcao")
    assert (premissa["origem"], premissa["fonte"]) == ("dela", "informado pela senhora")
    assert "tirando também a mão de obra, o gás e a embalagem" in dados["pontos"][0]["derivacao"]
    _conferir_a_conta(dados)


def test_o_piso_manda_quando_o_ingrediente_e_barato(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    parametros.definir(sessao.dossie, "valor_hora", 60)
    dados = estimar(sessao, _receita(sessao, "Arroz com frango"))
    piso = dados["piso"]["texto"]
    assert {p["preco"]["texto"] for p in dados["pontos"]} == {piso}
    assert "abaixo do piso" in dados["pontos"][0]["derivacao"]
    assert f"fica em {piso}" in dados["texto"]
    _conferir_a_conta(dados)


def test_premissas_com_fonte_e_data(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    dados = estimar(sessao, _receita(sessao, "Arroz com frango"))
    por_nome = {p["nome"]: p for p in dados["premissas"]}
    assert list(por_nome) == [
        "valor_hora",
        "botijao_preco",
        "botijao_horas",
        "embalagem_por_porcao",
    ]
    hora = por_nome["valor_hora"]
    assert hora["origem"] == "padrao"
    assert hora["fonte_url"].startswith("https://www.planalto.gov.br/")
    assert hora["atualizado_texto"] == "conferido em 26/09/2026"
    assert hora["valor"] == {"valor": 7.37, "texto": "R$ 7,37 por hora"}
    assert por_nome["embalagem_por_porcao"]["origem"] == "falta"
    assert all(p["editavel"] for p in dados["premissas"])


# --------------------------------------------------------------------------- #
# Gás, energia e tempo
# --------------------------------------------------------------------------- #


def test_air_fryer_vira_energia_e_nao_gas(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, BATATA)
    dados = estimar(sessao, _receita(sessao, "Batata rústica"))
    linhas = _linhas(dados)
    assert "gas" not in linhas
    energia = linhas["energia"]
    assert energia["derivacao"].startswith(
        "air fryer de 1.500 W por 25 min = 0,625 kWh; 0,625 kWh × 99,8 centavos ÷ 4 porções"
    )
    esperado = _para_cima(Decimal("0.625") * Decimal("0.998") / 4)
    assert _dec(energia["valor"]) == esperado
    assert energia["premissas"] == ["kwh_preco", "potencia_air_fryer"]
    _conferir_a_conta(dados)


def test_aparelho_sem_potencia_fica_de_fora_e_e_pedido(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, MERENGUE)
    dados = estimar(sessao, _receita(sessao, "Suspiro"))
    linhas = _linhas(dados)
    assert linhas["energia"]["valor"] is None
    assert "potência de batedeira" in linhas["energia"]["derivacao"]
    assert "potencia_batedeira" in dados["sinais"]["faltam_parametros"]
    assert "a potência da batedeira" in dados["texto"]
    assert linhas["gas"]["valor"] is not None, "o forno do fogão é gás"
    _conferir_a_conta(dados)


def test_potencia_informada_entra_e_a_linha_soma_os_aparelhos(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, MERENGUE)
    parametros.definir(sessao.dossie, "potencia_batedeira", 300)
    dados = estimar(sessao, _receita(sessao, "Suspiro"))
    energia = _linhas(dados)["energia"]
    assert energia["derivacao"].startswith("batedeira de 300 W por 10 min = 0,05 kWh")
    assert energia["valor"] == {"valor": 0.01, "texto": "R$ 0,01"}


def test_sem_forno_o_tempo_de_forno_vai_para_a_air_fryer(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, MERENGUE, forno=Posse.NAO_TEM, forno_eletrico=Posse.NAO_TEM)
    parametros.definir(sessao.dossie, "potencia_batedeira", 300)
    dados = estimar(sessao, _receita(sessao, "Suspiro"))
    linhas = _linhas(dados)
    assert "gas" not in linhas
    assert "air fryer de 1.500 W por 60 min = 1,5 kWh" in linhas["energia"]["derivacao"]
    assert "a senhora não tem forno" in linhas["energia"]["derivacao"]


def test_sem_tempo_nenhum_a_mao_de_obra_fica_de_fora(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, SALADA)
    dados = estimar(sessao, _receita(sessao, "Salada de tomate"))
    linhas = _linhas(dados)
    assert linhas["mao_de_obra"]["valor"] is None
    assert linhas["mao_de_obra"]["rotulo"] == "Mão de obra sugerida"
    assert "não diz quanto tempo leva" in linhas["mao_de_obra"]["derivacao"]
    assert "quanto tempo a receita leva, do começo ao fim" in dados["sinais"]["falta_confirmar"]
    assert "gas" not in linhas and "energia" not in linhas
    _conferir_a_conta(dados)


def test_tempo_declarado_vale_como_premissa_para_a_mao_de_obra(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, {**SALADA, "tempo_total_min": 15})
    dados = estimar(sessao, _receita(sessao, "Salada de tomate"))
    mao = _linhas(dados)["mao_de_obra"]
    assert mao["derivacao"].startswith("15 min ÷ 60 × R$ 7,37 por hora ÷ 2 porções")
    assert "a conta usa os 15 min que a receita declara" in mao["derivacao"]


def test_so_ingrediente_quando_nada_mais_tem_valor(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, SALADA)
    dados = estimar(sessao, _receita(sessao, "Salada de tomate"))
    assert dados["custo_producao"]["derivacao"].startswith("só o ingrediente")
    assert "sem outro custo na conta" in dados["pontos"][0]["derivacao"]


def test_tempo_declarado_sem_passos_com_tempo_vai_para_o_aparelho(tmp_path: Path) -> None:
    receita = {
        **BATATA,
        "nome": "Batata na air fryer",
        "modo_preparo": ["Tempere as batatas.", "Leve à air fryer até dourar."],
        "tempo_cozimento_min": 30,
    }
    sessao = _sessao(tmp_path, receita)
    dados = estimar(sessao, _receita(sessao, "Batata na air fryer"))
    energia = _linhas(dados)["energia"]
    assert "a conta põe os 30 min no aparelho elétrico" in energia["derivacao"]


def test_passo_em_aparelho_sem_custo_conhecido_e_dito(tmp_path: Path) -> None:
    receita = {
        **ARROZ,
        "nome": "Linguiça na brasa",
        "modo_preparo": ["Leve à churrasqueira por 20 minutos."],
        "tempo_cozimento_min": None,
    }
    sessao = _sessao(tmp_path, receita)
    dados = estimar(sessao, _receita(sessao, "Linguiça na brasa"))
    assert any("churrasqueira" in c for c in dados["sinais"]["falta_confirmar"])


# --------------------------------------------------------------------------- #
# O que ainda não dá para estimar
# --------------------------------------------------------------------------- #


def test_ingrediente_sem_preco_dela_usa_a_referencia_com_fonte(tmp_path: Path) -> None:
    """O coco ralado que ela não cotou sai pelo preço de referência: nada se pergunta."""
    sessao = _sessao(tmp_path, BOLO)
    dados = estimar(sessao, _receita(sessao, "Bolo de fubá"))
    # A xícara de coco ralado pesa 93 g (USDA), cotada pelo preço médio de São Paulo.
    assert _linhas(dados)["ingredientes"]["valor"] == {"valor": 1.38, "texto": "R$ 1,38"}
    assert dados["custo_producao"] is not None
    assert not any("coco ralado" in c for c in dados["sinais"]["falta_confirmar"])


def test_com_o_preco_do_que_falta_a_estimativa_sai(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, BOLO)
    sessao.dossie.registrar_preco(
        "coco ralado", Dinheiro.de("6.00"), OrigemPreco.INFORMADO_POR_ELA, Decimal(100), "g"
    )
    dados = estimar(sessao, _receita(sessao, "Bolo de fubá"))
    linhas = _linhas(dados)
    assert linhas["ingredientes"]["valor"] is not None
    assert {"gas", "energia"} <= set(linhas)
    assert "liquidificador de 400 W por 3 min = 0,02 kWh" in linhas["energia"]["derivacao"]
    _conferir_a_conta(dados)


def test_sem_rendimento_a_estimativa_pelo_peso_divide(tmp_path: Path) -> None:
    """O rendimento nunca é pergunta: sem ele, a porção de 350 g estima quantas saem."""
    receita = {**ARROZ, "nome": "Arroz sem rendimento", "rendimento_porcoes": None}
    sessao = _sessao(tmp_path, receita)
    dados = estimar(sessao, _receita(sessao, "Arroz sem rendimento"))
    ingredientes = next(linha for linha in dados["linhas"] if linha["id"] == "ingredientes")
    assert ingredientes["valor"] is not None
    assert dados["pontos"] != []
    assert "rende quantas porções" not in dados["texto"]


def test_medida_caseira_usa_o_topo_da_faixa(tmp_path: Path) -> None:
    receita = {
        **ARROZ,
        "nome": "Arroz de xícara",
        "ingredientes": [
            {"texto": "3 xícaras de arroz", "nome": "arroz", "quantidade": 3, "medida": "xicara"},
            {
                "texto": "2 xícaras de farinha",
                "nome": "farinha",
                "quantidade": 2,
                "medida": "xicara",
            },
        ],
    }
    sessao = _sessao(tmp_path, receita)
    alvo = _receita(sessao, "Arroz de xícara")
    cmv = custo_da_porcao(alvo, sessao.avaliar(alvo))
    dados = estimar(sessao, alvo)
    ingredientes = _linhas(dados)["ingredientes"]
    assert _dec(ingredientes["valor"]) == cmv.para_precificar.valor
    if cmv.e_faixa:
        assert "a conta usa o maior" in ingredientes["derivacao"]


def test_faixa_de_medida_caseira_aparece_na_derivacao(tmp_path: Path) -> None:
    receita = {
        **ARROZ,
        "nome": "Farofa",
        "ingredientes": [
            {
                "texto": "2 xícaras de farinha de mandioca",
                "nome": "farinha de mandioca",
                "quantidade": 2,
                "medida": "xicara",
            },
            {
                "texto": "3 colheres de manteiga",
                "nome": "manteiga",
                "quantidade": 3,
                "medida": "colher de sopa",
            },
        ],
    }
    sessao = _sessao(tmp_path, receita)
    alvo = _receita(sessao, "Farofa")
    cmv = custo_da_porcao(alvo, sessao.avaliar(alvo))
    derivacao = _linhas(estimar(sessao, alvo))["ingredientes"]["derivacao"]
    assert ("a conta usa o maior" in derivacao) is cmv.e_faixa


def test_o_que_falta_confirmar_nao_impede_a_estimativa(tmp_path: Path) -> None:
    banco = tmp_path / "dossie.db"
    sessao = abrir_sessao(PLANILHA, banco)
    sessao.guardar(ReceitaEntrada(**ARROZ).para_dominio())
    dados = estimar(sessao, _receita(sessao, "Arroz com frango"))
    assert dados["pontos"], "a cozinha sem resposta não impede o preço preliminar"
    assert dados["sinais"]["falta_confirmar"]
    assert "Ainda faltam confirmar" in dados["texto"]


# --------------------------------------------------------------------------- #
# Recusa e busca da receita
# --------------------------------------------------------------------------- #


def test_receita_que_ela_nao_consegue_fazer_e_recusada(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.NAO_GOSTA, "enjoei de fazer")
    with pytest.raises(EstimativaRecusada) as erro:
        estimar(sessao, _receita(sessao, "Arroz com frango"))
    assert "não consegue fazer essa receita hoje" in erro.value.mensagem
    assert "Por isso não faço estimativa de preço para ela." in erro.value.mensagem


def test_receita_pelo_id_pelo_nome_e_pelo_catalogo(tmp_path: Path, monkeypatch: Any) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    assert receita_da_estimativa(sessao, "arroz-com-frango", None).nome == "Arroz com frango"
    assert receita_da_estimativa(sessao, None, "arroz com FRANGO").nome == "Arroz com frango"
    with pytest.raises(Ausente):
        receita_da_estimativa(sessao, None, "Pudim")
    with pytest.raises(Ausente):
        receita_da_estimativa(sessao, "nao-existe", None)
    with pytest.raises(ErroDeUso):
        receita_da_estimativa(sessao, " ", None)

    guardada = ReceitaDoCatalogo(
        slug="3f2a9c0d1b7e4a55",
        receita=ReceitaEntrada(**{**BATATA, "nome": "Batata do catálogo"}).para_dominio(),
        origem=OrigemNoCatalogo.DESCOBERTA,
    )
    monkeypatch.setattr(
        Catalogo, "obter", lambda _self, slug: guardada if slug == guardada.slug else None
    )
    assert receita_da_estimativa(sessao, guardada.slug, None).nome == "Batata do catálogo"


# --------------------------------------------------------------------------- #
# A ferramenta
# --------------------------------------------------------------------------- #


async def _chamar(sessao: Sessao, **argumentos: Any) -> dict[str, Any]:
    resultado = await construir_servidor(sessao).call_tool("estimar_preco_preliminar", argumentos)
    return json.loads(resultado.content[0].text)


async def test_a_ferramenta_devolve_a_estimativa_com_a_orientacao(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    dados = await _chamar(sessao, receita_id="arroz-com-frango")
    assert (dados["preliminar"], dados["receita_id"], dados["prato"]) == (
        True,
        "arroz-com-frango",
        "Arroz com frango",
    )
    assert "preliminar" in dados["orientacao"]
    assert [p["preco"]["texto"] for p in dados["pontos"]] == ["R$ 7,50", "R$ 8,57", "R$ 10,00"]


async def test_a_ferramenta_recusa_com_o_motivo(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.NAO_GOSTA)
    dados = await _chamar(sessao, prato="Arroz com frango")
    assert dados["categoria"] == "regra"
    assert "não consegue fazer" in dados["erro"]
    assert "R$" not in json.dumps(dados, ensure_ascii=False)


async def test_a_ferramenta_sem_receita_pede_a_receita(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ARROZ)
    dados = await _chamar(sessao)
    assert dados["categoria"] == "uso"
