"""As perguntas que liberam receitas: juntas pelo que perguntam, com quantas cada uma mexe.

Com a cozinha nova, depois da primeira descoberta, nenhuma receita dá para
fazer ainda: todas esperam uma resposta dela. A grade junta essas perguntas
(a mesma pergunta da cozinha, ou o preço do mesmo ingrediente, vale para
várias receitas) e diz, sem exagero, quantas cada resposta libera sozinha e
em quantas ela ajuda.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import receitas_de_teste as rt

from mise.compras import buscar
from mise.mcp_server import Sessao
from mise.receitas_json import Filtros, lista

CENOURA_REFOGADA = rt.pagina(
    "Cenoura refogada", ["2 cenouras", "1 colher de sopa de óleo"], ["Refogue na panela."]
)
ARROZ_COM_CENOURA = rt.pagina(
    "Arroz com cenoura",
    ["1 xícara de arroz", "1 cenoura média picada", "1 colher de sopa de canela"],
    ["Cozinhe o arroz na panela por 20 minutos."],
)
ARROZ_SEM_RENDIMENTO = rt.pagina(
    "Arroz soltinho", ["1 xícara de arroz"], ["Cozinhe o arroz na panela."], rende=""
)


@pytest.fixture
def sessao(tmp_path: Path, sem_precos_de_referencia: None) -> Sessao:
    """Sem os preços de referência: é o preço que ela dá que junta as cenouras das receitas."""
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/1-cenoura.html", CENOURA_REFOGADA)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/2-arroz.html", ARROZ_COM_CENOURA)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/3-arroz.html", ARROZ_SEM_RENDIMENTO)
    return sessao


def _painel(sessao: Sessao) -> list[dict[str, object]]:
    resposta = lista(sessao, Filtros(aba="pode_fazer"))
    # O arroz sem rendimento dá para fazer: o rendimento nunca é pergunta.
    assert [i["nome"] for i in resposta["itens"]] == ["Arroz soltinho"]
    # Sem preço na internet (aqui, sem as referências), nada é pergunta: ficam de fora.
    assert resposta["contagens"]["falta_resposta"] == 0
    assert sorted(resposta["sem_preco_na_internet"]["nomes"]) == [
        "Arroz com cenoura",
        "Cenoura refogada",
    ]
    painel: list[dict[str, object]] = resposta["perguntas_que_liberam"]
    return painel


def test_o_preco_da_mesma_cenoura_vale_para_as_duas_receitas(sessao: Sessao) -> None:
    # O preço não se pergunta: o painel não tem pergunta de preço nem de item parecido.
    assert _painel(sessao) == []


def test_o_preco_dado_pela_cenoura_serve_as_cenouras_das_outras_receitas(sessao: Sessao) -> None:
    sessao.cotar("cenouras", 5.0, 1, "kg")
    antes = {tuple(p["nomes"]) for p in _painel_depois(sessao)}
    assert ("Cenoura refogada", "Arroz com cenoura") not in antes
    pode_fazer = lista(sessao, Filtros(aba="pode_fazer"))
    assert [i["nome"] for i in pode_fazer["itens"]] == ["Arroz soltinho", "Cenoura refogada"]
    # O arroz com cenoura ainda fica de fora: a canela que não é a dela não tem preço.
    assert pode_fazer["sem_preco_na_internet"]["nomes"] == ["Arroz com cenoura"]


def _painel_depois(sessao: Sessao) -> list[dict[str, object]]:
    painel: list[dict[str, object]] = lista(sessao, Filtros(aba="falta_resposta"))[
        "perguntas_que_liberam"
    ]
    return painel


def test_so_o_que_ela_responde_ali_mesmo_entra_no_painel(sessao: Sessao) -> None:
    """Nenhuma medida vira pergunta: o peito e a colher de alcaparras têm peso com fonte.

    O peito de frango pela tabela do IBGE, e a colher de sopa de alcaparras pela
    tabela de porções do USDA: o painel só tem pergunta da cozinha dela.
    """
    rt.da_web(
        sessao,
        "https://www.tudogostoso.com.br/receita/4-frango.html",
        rt.pagina(
            "Frango simples",
            ["1 peito de frango", "1 colher de sopa de alcaparras", "sal a gosto"],
            ["Grelhe na frigideira."],
        ),
    )
    rt.da_web(
        sessao,
        "https://www.tudogostoso.com.br/receita/5-mingau.html",
        rt.pagina("Mingau simples", ["1 caixinha de leite integral", "sal a gosto"], ["Cozinhe."]),
    )
    painel = lista(sessao, Filtros(aba="falta_resposta"))["perguntas_que_liberam"]
    assert not [p for p in painel if p["pergunta"]["assunto"] == "medida"]
    assert all("Mingau simples" not in p["nomes"] for p in painel)
    assert "Frango simples" in [
        i["nome"] for i in lista(sessao, Filtros(aba="pode_fazer"))["itens"]
    ]


def test_a_mesma_pergunta_da_cozinha_junta_as_receitas(tmp_path: Path) -> None:
    """Sem a cozinha conferida, a pergunta do fogão vale para toda receita de panela."""
    sessao = rt.sessao_nova(tmp_path)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/1-cenoura.html", CENOURA_REFOGADA)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/3-arroz.html", ARROZ_SEM_RENDIMENTO)
    painel = lista(sessao, Filtros(aba="falta_resposta"))["perguntas_que_liberam"]
    (da_cozinha, *_) = painel
    assert da_cozinha["receitas"] == 2
    assert da_cozinha["pergunta"]["tipo"] in {"equipamento", "tecnica", "operacional"}
    assert da_cozinha["pergunta"]["motivo"] == "", "o porquê de uma receita não explica a outra"
    assert len(painel) <= 5


def test_buscar_acha_o_mesmo_produto_escrito_de_outro_jeito() -> None:
    precos = {"Cenoura": Decimal(5), "Cebola roxa": Decimal(9)}
    assert buscar(precos, "cenouras médias") == Decimal(5)
    assert buscar(precos, "cenoura descascada e em cubos") == Decimal(5)
    assert buscar(precos, "cebola") is None, "cebola roxa é outro produto"
    assert buscar({"cenoura": 1, "cenouras": 2}, "cenoura picada") is None, "dois preços: nenhum"
    assert buscar(precos, "   ") is None
