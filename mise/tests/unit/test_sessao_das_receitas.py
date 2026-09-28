"""A sessão resolve a receita pelo id, pelo endereço lido ou como a receita que ela dita.

É aqui que o modelo não consegue redigitar uma receita da internet nem trocar a
quantidade entre a conferência e o custo.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import receitas_de_teste as rt

from mise.catalogo import OrigemNoCatalogo
from mise.erros import Ausente, ErroDeUso
from mise.mcp_server import ReceitaEntrada, Sessao
from mise.perfil import Gosto
from mise.receita import Origem, Receita
from mise.receita import ingrediente as ing

PAGINA_SEM_RENDIMENTO = rt.pagina(
    "Feijão tropeiro",
    ["500 g de feijão carioquinha", "temperos de sua preferência", "sal a gosto"],
    ["Cozinhe o feijão na panela.", "Junte a farinha."],
    rende="",
    tempos=("PT10M", "", ""),
)
TROPEIRO_URL = "https://www.tudogostoso.com.br/receita/tropeiro"


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    return sessao


def _entrada(**campos: Any) -> ReceitaEntrada:
    return ReceitaEntrada.model_validate({**rt.ARROZ_COM_FRANGO, **campos})


# --------------------------------------------------------------------------- #
# Avaliar: pelo id, pelo endereço lido, ou a receita que ela dita               #
# --------------------------------------------------------------------------- #


def test_so_o_id_devolve_a_receita_guardada(sessao: Sessao) -> None:
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    receita, recado = sessao.receita_para_avaliar(carne.slug, None)
    assert (receita.nome, recado) == (carne.nome, None)
    with pytest.raises(ErroDeUso, match="receita_id"):
        sessao.receita_para_avaliar("  ", None)
    with pytest.raises(Ausente):
        sessao.receita_para_avaliar("nao-existe", None)


def test_o_endereco_lido_vale_o_id_e_so_completa(sessao: Sessao) -> None:
    tropeiro = rt.da_web(sessao, TROPEIRO_URL, PAGINA_SEM_RENDIMENTO)
    assert not tropeiro.receita.rendimento_informado
    entrada = ReceitaEntrada.model_validate(
        {
            "nome": "qualquer",
            "url": TROPEIRO_URL + "?utm=1",
            "rendimento_porcoes": 6,
            "ingredientes": [
                {
                    "texto": "temperos de sua preferência",
                    "nome": "temperos",
                    "quantidade": 1,
                    "medida": "colher de cha",
                }
            ],
        }
    )
    receita, recado = sessao.receita_para_avaliar(None, entrada)
    assert receita.rendimento_porcoes == 6 and receita.rendimento_informado
    assert recado is not None and "rendimento_porcoes: 6 porções" in recado
    assert receita.ingredientes[1].quantidade == Decimal(1)
    guardada = sessao.catalogo.obter(tropeiro.slug)
    assert guardada is not None and len(guardada.respostas) == 2
    sem_mudanca, recado = sessao.receita_para_avaliar(tropeiro.slug, entrada)
    assert recado is None and sem_mudanca.rendimento_porcoes == 6


def test_endereco_que_o_servidor_nao_leu_e_recusado(sessao: Sessao) -> None:
    with pytest.raises(ErroDeUso, match="buscar_receita_na_web"):
        sessao.receita_para_avaliar(None, _entrada(url="https://exemplo.com.br/x"))
    assert sessao.catalogo.contar() == 0


def test_a_receita_que_ela_dita_entra_no_catalogo_como_dita(sessao: Sessao) -> None:
    receita, recado = sessao.receita_para_avaliar(None, _entrada())
    assert (receita.origem, receita.url, recado) == (Origem.INFORMADA_POR_ELA, None, None)
    guardada = sessao.catalogo.obter("arroz-com-frango")
    assert guardada is not None and guardada.origem is OrigemNoCatalogo.DITA
    corrigida, _ = sessao.receita_para_avaliar("arroz-com-frango", _entrada(rendimento_porcoes=8))
    assert corrigida.rendimento_porcoes == 8
    with pytest.raises(ErroDeUso, match="sem o receita_id"):
        sessao.receita_para_avaliar("arroz-com-frango", _entrada(nome="Lasanha"))


def test_receita_em_avaliacao_de_antes_do_catalogo(sessao: Sessao) -> None:
    antiga = Receita(nome="Pudim", ingredientes=(ing("3 ovos", "ovos", 3, "ovo"),))
    sessao.guardar(antiga)
    receita, recado = sessao.receita_para_avaliar("pudim", _entrada(nome="Pudim"))
    assert receita == antiga
    assert recado is not None and "antes do catálogo" in recado


# --------------------------------------------------------------------------- #
# Uma resposta sobre a receita, como a grade pergunta                          #
# --------------------------------------------------------------------------- #


def test_resposta_sobre_a_receita_vai_para_o_catalogo(sessao: Sessao) -> None:
    tropeiro = rt.da_web(sessao, TROPEIRO_URL, PAGINA_SEM_RENDIMENTO)
    sessao.guardar(tropeiro.receita)
    rendimento = sessao.responder_sobre_a_receita(tropeiro.slug, "rendimento_porcoes", "6 porções")
    assert rendimento.receita.rendimento_porcoes == 6
    assert sessao.candidatas[tropeiro.nome].rendimento_porcoes == 6, "a em avaliação acompanha"
    tempo = sessao.responder_sobre_a_receita(
        tropeiro.slug, "tempo_cozimento_min", "1 hora e 10 minutos"
    )
    assert tempo.receita.tempo_cozimento_min == 70
    linha = sessao.responder_sobre_a_receita(
        tropeiro.slug, "temperos de sua preferência", "a gosto"
    )
    assert linha.receita.ingredientes[1].a_gosto
    assert [r.campo for r in linha.respostas] == [
        "rendimento_porcoes",
        "tempo_cozimento_min",
        "temperos de sua preferência",
    ]
    with pytest.raises(Ausente):
        sessao.responder_sobre_a_receita("nao-existe", "rendimento_porcoes", "4")


@pytest.mark.parametrize(
    ("campo", "resposta", "mensagem"),
    [
        ("rendimento_porcoes", "   ", "vazia"),
        ("rendimento_porcoes", "muitas", "Para o rendimento, preciso de um número de porções"),
        ("rendimento_porcoes", "0", "O rendimento vai de 1 a 500 porções"),
        ("rendimento_porcoes", "2,5", "em número inteiro"),
        ("tempo_cozimento_min", "3 dias", "minutos ou em horas"),
        ("tempo_cozimento_min", "muito tempo", "preciso de um número de minutos"),
        ("tempo_cozimento_min", "30 horas", "O tempo no fogo vai de 1 a 1440 minutos"),
        ("linha que não existe", "1 xícara", "não está na receita"),
        ("temperos de sua preferência", "não sei", "não muda a receita"),
    ],
)
def test_resposta_que_nao_da_para_gravar(
    sessao: Sessao, campo: str, resposta: str, mensagem: str
) -> None:
    tropeiro = rt.da_web(sessao, TROPEIRO_URL, PAGINA_SEM_RENDIMENTO)
    with pytest.raises(ErroDeUso, match=mensagem):
        sessao.responder_sobre_a_receita(tropeiro.slug, campo, resposta)


def test_preparo_que_faltava_e_tempo_em_minutos(sessao: Sessao) -> None:
    sem_preparo = rt.da_web(
        sessao,
        "https://blog.exemplo.com.br/pure",
        rt.pagina("Purê simples", ["1 kg de batata"], [], tempos=None),
    )
    feita = sessao.responder_sobre_a_receita(
        sem_preparo.slug, "modo_preparo", "Cozinhe a batata na panela por 20 minutos.\nAmasse."
    )
    assert feita.receita.modo_preparo == ("Cozinhe a batata na panela por 20 minutos.", "Amasse.")
    assert "fogao" in feita.receita.equipamentos
    so_minutos = sessao.responder_sobre_a_receita(sem_preparo.slug, "tempo_cozimento_min", "25")
    assert so_minutos.receita.tempo_cozimento_min == 25
    with pytest.raises(ErroDeUso, match="já diz que o cozimento leva 25 min"):
        sessao.responder_sobre_a_receita(sem_preparo.slug, "tempo_cozimento_min", "30 min")


# --------------------------------------------------------------------------- #
# O custo: só da receita conferida                                             #
# --------------------------------------------------------------------------- #


def test_custo_pelo_id_pelo_nome_e_pelo_endereco(sessao: Sessao) -> None:
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    assert sessao.receita_para_custear(carne.slug, None).nome == carne.nome
    pelo_endereco = ReceitaEntrada.model_validate(
        {"nome": carne.nome, "url": rt.CARNE_URL, "ingredientes": [{"texto": "x", "nome": "x"}]}
    )
    with pytest.raises(ErroDeUso, match="não é a mesma que passou pela conferência"):
        sessao.receita_para_custear(None, pelo_endereco)
    sem_leitura = ReceitaEntrada.model_validate(
        {
            "nome": "X",
            "url": "https://exemplo.com.br/y",
            "ingredientes": [{"texto": "x", "nome": "x"}],
        }
    )
    with pytest.raises(ErroDeUso, match="não li esse endereço"):
        sessao.receita_para_custear(None, sem_leitura)
    with pytest.raises(ErroDeUso, match="informe a receita"):
        sessao.receita_para_custear(None, None)
    sessao.receita_para_avaliar(None, _entrada())
    assert sessao.receita_para_custear(None, _entrada(nome="ARROZ COM FRANGO")).nome == (
        "Arroz com frango"
    )
    catalogada = ReceitaEntrada.model_validate(
        {"nome": carne.nome.upper(), "ingredientes": [{"texto": "x", "nome": "x"}]}
    )
    with pytest.raises(ErroDeUso, match="não é a mesma"):
        sessao.receita_para_custear(None, catalogada)


def test_id_so_do_catalogo_pede_a_conferencia_antes_do_preco(sessao: Sessao) -> None:
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    with pytest.raises(Ausente, match="ainda não passou pela conferência"):
        sessao.candidata_por_id(carne.slug)
    assert sessao.receita_por_id(carne.slug).nome == carne.nome
    with pytest.raises(Ausente):
        sessao.receita_por_id("nao-existe")


def test_receita_da_web_conhecida_nao_busca_de_novo(sessao: Sessao) -> None:
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    resposta = sessao.receita_da_web(
        "https://tudogostoso.com.br/receita/22090-carne-moida-com-arroz.html"
    )
    assert (resposta["receita_id"], resposta["ja_conhecida"]) == (carne.slug, True)
    assert resposta["procedencia"]["fonte"] == "TudoGostoso"


# --------------------------------------------------------------------------- #
# A avaliação dela pela sessão                                                 #
# --------------------------------------------------------------------------- #


def test_avaliacao_so_muda_o_gosto_quando_pedido(sessao: Sessao) -> None:
    sessao.receita_para_avaliar(None, _entrada())
    sessao.dossie.registrar_gosto("Arroz com frango", Gosto.NAO_GOSTA)
    sessao.registrar_avaliacao("arroz-com-frango", estrelas={"sabor": 3})
    opiniao = sessao.dossie.gosto_por("Arroz com frango")
    assert opiniao is not None and opiniao.gosto is Gosto.NAO_GOSTA
    sessao.registrar_avaliacao("arroz-com-frango", gosta=False, muda_o_gosto=True, notas="")
    assert sessao.avaliacoes.obter("arroz-com-frango").notas == ""


def test_resposta_que_muda_o_que_a_pagina_diz_e_dita_para_ela(sessao: Sessao) -> None:
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    with pytest.raises(ErroDeUso) as erro:
        sessao.responder_sobre_a_receita(carne.slug, "rendimento_porcoes", "8")
    assert erro.value.mensagem == "A receita guardada já diz que rende 4 porções."
    assert "receita_id" not in erro.value.mensagem
